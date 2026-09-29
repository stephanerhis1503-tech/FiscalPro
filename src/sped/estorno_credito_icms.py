from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Callable

ProgressoCallback = Callable[[int, str], None]
CENTAVO = Decimal("0.01")
MEIO_CENTAVO = Decimal("0.005")


@dataclass(slots=True)
class ItemEstornoICMS:
    numero_documento: str
    chave_nfe: str
    data_entrada: str
    codigo_participante: str
    participante: str
    codigo_item: str
    descricao_item: str
    cfop: str
    base_icms: Decimal
    aliquota_icms: Decimal
    valor_icms: Decimal
    linhas_c170: tuple[int, ...]
    status: str
    codigo_existente: str = ""
    observacao: str = ""
    valor_icms_geracao: Decimal | None = None
    ajuste_arredondamento: Decimal = Decimal("0")
    residuos_arredondamento: tuple[Decimal, ...] = ()
    valor_c197_existente: Decimal = Decimal("0")

    @property
    def valor_estorno(self) -> Decimal:
        return self.valor_icms if self.valor_icms_geracao is None else self.valor_icms_geracao


@dataclass(slots=True)
class NotaEstornoICMS:
    indice_c100: int
    indice_fim_bloco: int
    numero_documento: str
    chave_nfe: str
    data_entrada: str
    codigo_participante: str
    participante: str
    valor_icms_c100: Decimal
    itens: list[ItemEstornoICMS] = field(default_factory=list)
    status: str = "PENDENTE"
    observacao: str = ""
    valor_c197_existente: Decimal = Decimal("0")
    arredondamento_validado: bool = False
    valor_icms_teorico: Decimal = Decimal("0")
    limite_arredondamento: Decimal = Decimal("0")
    linhas_icms_consideradas: int = 0

    @property
    def diferenca_c170_c100(self) -> Decimal:
        return (self.valor_itens - self.valor_icms_c100).quantize(CENTAVO, rounding=ROUND_HALF_UP)

    @property
    def diferenca_c197_c100(self) -> Decimal:
        if self.valor_c197_existente == 0:
            return Decimal("0")
        return (self.valor_c197_existente - self.valor_icms_c100).quantize(CENTAVO, rounding=ROUND_HALF_UP)

    @property
    def valor_previsto_estorno(self) -> Decimal:
        return sum((item.valor_estorno for item in self.itens if item.status == "PENDENTE"), Decimal("0")).quantize(CENTAVO, rounding=ROUND_HALF_UP)

    @property
    def ajuste_arredondamento(self) -> Decimal:
        return sum((item.ajuste_arredondamento for item in self.itens), Decimal("0")).quantize(CENTAVO, rounding=ROUND_HALF_UP)

    @property
    def valor_itens(self) -> Decimal:
        return sum((item.valor_icms for item in self.itens), Decimal("0"))

    @property
    def itens_pendentes(self) -> list[ItemEstornoICMS]:
        return [item for item in self.itens if item.status == "PENDENTE"]


@dataclass(slots=True)
class ResultadoAnaliseEstornoICMS:
    notas: list[NotaEstornoICMS]
    regime_especial: str
    mencao_tts_ecommerce: bool
    codigos_existentes: dict[str, int]
    total_creditos_entradas: Decimal
    total_pendente: Decimal
    total_existente: Decimal
    total_revisao: Decimal
    notas_pendentes: int
    notas_existentes: int
    notas_revisao: int
    itens_pendentes: int
    itens_existentes: int
    itens_revisao: int
    codigo_modelo_detectado: str
    alerta_codigo_modelo: str

    @property
    def pode_gerar(self) -> bool:
        return self.total_pendente > 0 and self.itens_pendentes > 0


@dataclass(slots=True)
class ResultadoGeracaoEstornoICMS:
    caminho_sped: Path
    caminho_memoria: Path
    caminho_relatorio: Path
    codigo_ajuste: str
    codigo_observacao: str
    total_estornado: Decimal
    notas_alteradas: int
    itens_ajustados: int
    linhas_inseridas: int


class EstornadorCreditosICMSMG:
    """Prepara e aplica estorno integral dos créditos de ICMS das NF-e de entrada.

    O motor não escolhe silenciosamente o código de ajuste. A interface deve apresentar
    as opções e exigir confirmação, pois o arquivo-modelo fornecido usa MG50000018,
    enquanto a tabela vigente da SEF/MG destina esse código ao FEM em devolução. Para
    TTS, a tabela vigente identifica MG50000100.
    """

    CODIGOS_ESTORNO_CONHECIDOS = {
        "MG50000100",  # TTS / regime especial
        "MG50000999",  # outros ajustes
        "MG50000018",  # FEM em entrada devolvida; mantido para leitura de legado
    }
    TEXTO_OBSERVACAO = "ESTORNO DE CREDITO DE ICMS"
    CFOPS_USO_CONSUMO_BLOQUEADOS = {"1407", "1556", "2407", "2556"}

    def analisar(
        self,
        linhas: list[str],
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAnaliseEstornoICMS:
        self._progresso(progresso, 5, "Mapeando cadastros e documentos de entrada...")
        participantes = self._mapear_participantes(linhas)
        produtos = self._mapear_produtos(linhas)
        regime_especial, mencao_tts = self._detectar_regime(linhas)

        limites_c100 = self._limites_blocos_c100(linhas)
        notas: list[NotaEstornoICMS] = []
        codigos_existentes: Counter[str] = Counter()

        for ordem, (inicio, fim) in enumerate(limites_c100, start=1):
            campos_c100 = self._campos(linhas[inicio])
            if len(campos_c100) < 22 or campos_c100[1].strip() != "0":
                continue

            valor_icms_c100 = self._decimal(campos_c100[21])

            numero_documento = campos_c100[7].strip()
            chave_nfe = campos_c100[8].strip()
            data_entrada = campos_c100[10].strip()
            codigo_part = campos_c100[3].strip()
            participante = participantes.get(codigo_part, codigo_part or "Não identificado")

            grupos_c170: dict[tuple[str, Decimal], dict] = {}
            grupos_c170_bloqueados: dict[tuple[str, Decimal], dict] = {}
            c170_por_item: dict[str, list[dict]] = defaultdict(list)
            grupos_c197: dict[tuple[str, Decimal], dict] = {}
            codigos_bloco: Counter[str] = Counter()

            for indice in range(inicio + 1, fim):
                campos = self._campos(linhas[indice])
                if not campos:
                    continue
                registro = campos[0]
                if registro == "C170" and len(campos) > 14:
                    codigo_item = campos[2].strip()
                    cfop = campos[10].strip()
                    base = self._decimal(campos[12])
                    aliquota = self._decimal(campos[13])
                    valor = self._decimal(campos[14])
                    chave = (codigo_item, aliquota)
                    c170_por_item[codigo_item].append(
                        {
                            "linha": indice + 1,
                            "cfop": cfop,
                            "base": base,
                            "aliquota": aliquota,
                            "icms": valor,
                        }
                    )

                    motivo_bloqueio = self._motivo_bloqueio_credito_c170(
                        cfop=cfop, base=base, aliquota=aliquota, valor_icms=valor
                    )
                    if motivo_bloqueio:
                        if valor > 0:
                            grupo = grupos_c170_bloqueados.setdefault(
                                chave,
                                {"base": Decimal("0"), "icms": Decimal("0"), "linhas": [], "cfops": [], "motivos": []},
                            )
                            grupo["base"] += base
                            grupo["icms"] += valor
                            grupo["linhas"].append(indice + 1)
                            grupo["cfops"].append(cfop)
                            grupo["motivos"].append(motivo_bloqueio)
                        continue

                    grupo = grupos_c170.setdefault(
                        chave,
                        {
                            "base": Decimal("0"),
                            "icms": Decimal("0"),
                            "linhas": [],
                            "cfops": [],
                            "residuos": [],
                            "componentes": [],
                        },
                    )
                    valor_teorico_exato = base * aliquota / Decimal("100")
                    valor_teorico_item = self._moeda(valor_teorico_exato)
                    grupo["base"] += base
                    grupo["icms"] += valor
                    grupo["linhas"].append(indice + 1)
                    grupo["cfops"].append(cfop)
                    grupo["residuos"].append(valor_teorico_exato - valor)
                    grupo["componentes"].append(
                        {
                            "linha": indice + 1,
                            "base": base,
                            "aliquota": aliquota,
                            "icms": valor,
                            "teorico_exato": valor_teorico_exato,
                            "teorico_item": valor_teorico_item,
                        }
                    )
                elif registro == "C197" and len(campos) > 6:
                    codigo_ajuste = campos[1].strip().upper()
                    descricao = campos[2].strip().upper()
                    if (
                        codigo_ajuste not in self.CODIGOS_ESTORNO_CONHECIDOS
                        and "ESTORNO" not in descricao
                        and "CREDITO" not in descricao
                    ):
                        continue
                    codigo_item = campos[3].strip()
                    aliquota = self._decimal(campos[5])
                    chave = (codigo_item, aliquota)
                    grupo = grupos_c197.setdefault(
                        chave,
                        {"base": Decimal("0"), "icms": Decimal("0"), "codigos": Counter()},
                    )
                    grupo["base"] += self._decimal(campos[4])
                    grupo["icms"] += self._decimal(campos[6])
                    grupo["codigos"][codigo_ajuste] += 1
                    codigos_bloco[codigo_ajuste] += 1
                    codigos_existentes[codigo_ajuste] += 1

            nota = NotaEstornoICMS(
                indice_c100=inicio,
                indice_fim_bloco=fim,
                numero_documento=numero_documento,
                chave_nfe=chave_nfe,
                data_entrada=data_entrada,
                codigo_participante=codigo_part,
                participante=participante,
                valor_icms_c100=valor_icms_c100,
            )
            nota.valor_c197_existente = self._moeda(
                sum((grupo["icms"] for grupo in grupos_c197.values()), Decimal("0"))
            )

            # 17.8.95 — um C197 existente em nota sem crédito no C100 não pode ser
            # ignorado. Ele é exibido como REVISAR/INDEVIDO para que a diferença
            # apareça na conferência por NF (caso real: NF 49092, R$ 1,88).
            if valor_icms_c100 <= 0:
                if grupos_c197:
                    nota.status = "REVISAR"
                    nota.observacao = (
                        "C197 de estorno localizado em documento sem crédito de ICMS no C100. "
                        "O ajuste é indevido e não será reproduzido automaticamente."
                    )
                    for (codigo_item, aliquota_c197), existente in grupos_c197.items():
                        referencias = c170_por_item.get(codigo_item, [])
                        referencia = referencias[0] if referencias else {}
                        cfop_ref = referencia.get("cfop", "")
                        valor_c170 = referencia.get("icms", Decimal("0"))
                        base_c170 = referencia.get("base", Decimal("0"))
                        aliq_c170 = referencia.get("aliquota", Decimal("0"))
                        cod = existente["codigos"].most_common(1)[0][0] if existente["codigos"] else ""
                        detalhe = (
                            f"BLOQUEADO: C100 sem ICMS; C197 existente {cod} no valor de "
                            f"R$ {self._formatar_decimal(existente['icms'])}."
                        )
                        if referencias:
                            detalhe += (
                                f" C170 do item: CFOP {cfop_ref or '-'}, BC {self._formatar_decimal(base_c170)}, "
                                f"alíquota {self._formatar_decimal(aliq_c170)}%, ICMS {self._formatar_decimal(valor_c170)}."
                            )
                        nota.itens.append(
                            ItemEstornoICMS(
                                numero_documento=numero_documento,
                                chave_nfe=chave_nfe,
                                data_entrada=data_entrada,
                                codigo_participante=codigo_part,
                                participante=participante,
                                codigo_item=codigo_item,
                                descricao_item=produtos.get(codigo_item, ""),
                                cfop=cfop_ref,
                                base_icms=base_c170,
                                aliquota_icms=self._aliquota(aliq_c170),
                                valor_icms=valor_c170,
                                linhas_c170=tuple(r.get("linha") for r in referencias if r.get("linha")),
                                status="REVISAR",
                                codigo_existente=cod,
                                observacao=detalhe,
                                valor_c197_existente=self._moeda(existente["icms"]),
                            )
                        )
                    notas.append(nota)
                continue

            if not grupos_c170 and not grupos_c170_bloqueados:
                nota.status = "REVISAR"
                nota.observacao = (
                    "A nota possui crédito de ICMS no C100, mas não possui C170 com crédito "
                    "suficiente para gerar C197 por item."
                )
                nota.itens.append(
                    ItemEstornoICMS(
                        numero_documento=numero_documento,
                        chave_nfe=chave_nfe,
                        data_entrada=data_entrada,
                        codigo_participante=codigo_part,
                        participante=participante,
                        codigo_item="",
                        descricao_item="Sem detalhamento C170",
                        cfop="",
                        base_icms=Decimal("0"),
                        aliquota_icms=Decimal("0"),
                        valor_icms=valor_icms_c100,
                        linhas_c170=(),
                        status="REVISAR",
                        observacao=nota.observacao,
                    )
                )
                notas.append(nota)
                continue

            # Itens com ICMS informado mas não elegíveis ao estorno automático
            # (ex.: CFOP de uso/consumo ou base/alíquota inválida) ficam em REVISAR.
            for (codigo_item, aliquota), grupo in grupos_c170_bloqueados.items():
                cfops = sorted({cfop for cfop in grupo["cfops"] if cfop})
                motivos = "; ".join(dict.fromkeys(grupo.get("motivos", [])))
                nota.itens.append(
                    ItemEstornoICMS(
                        numero_documento=numero_documento,
                        chave_nfe=chave_nfe,
                        data_entrada=data_entrada,
                        codigo_participante=codigo_part,
                        participante=participante,
                        codigo_item=codigo_item,
                        descricao_item=produtos.get(codigo_item, ""),
                        cfop=", ".join(cfops),
                        base_icms=self._moeda(grupo["base"]),
                        aliquota_icms=self._aliquota(aliquota),
                        valor_icms=self._moeda(grupo["icms"]),
                        linhas_c170=tuple(grupo["linhas"]),
                        status="REVISAR",
                        observacao=f"BLOQUEADO para C197 automático: {motivos}",
                    )
                )

            soma_c170 = sum((g["icms"] for g in grupos_c170.values()), Decimal("0"))
            diferenca_assinada = self._moeda(valor_icms_c100 - soma_c170)
            diferenca_nota = diferenca_assinada.copy_abs()
            diagnostico_arredondamento = self._diagnosticar_arredondamento_cumulativo(
                valor_icms_c100, grupos_c170
            )
            nota.arredondamento_validado = diagnostico_arredondamento["seguro"]
            nota.valor_icms_teorico = diagnostico_arredondamento["total_teorico"]
            nota.limite_arredondamento = diagnostico_arredondamento["limite"]
            nota.linhas_icms_consideradas = diagnostico_arredondamento["linhas"]

            for (codigo_item, aliquota), grupo in grupos_c170.items():
                existente = grupos_c197.get((codigo_item, aliquota))
                status = "PENDENTE"
                codigo_existente = ""
                observacao = "Crédito de entrada ainda sem ajuste C197 correspondente."
                if existente:
                    codigo_existente = existente["codigos"].most_common(1)[0][0]
                    diferenca_existente = (existente["icms"] - grupo["icms"]).copy_abs()
                    diferenca_base = (existente["base"] - grupo["base"]).copy_abs()
                    if diferenca_existente <= CENTAVO and diferenca_base <= CENTAVO:
                        status = "EXISTENTE"
                        observacao = f"Estorno já localizado no C197 ({codigo_existente})."
                    else:
                        status = "REVISAR"
                        observacao = (
                            "Existe C197 para o item, mas base ou ICMS não coincide com o C170; "
                            "o FiscalPro não complementará automaticamente."
                        )

                cfops = sorted({cfop for cfop in grupo["cfops"] if cfop})
                nota.itens.append(
                    ItemEstornoICMS(
                        numero_documento=numero_documento,
                        chave_nfe=chave_nfe,
                        data_entrada=data_entrada,
                        codigo_participante=codigo_part,
                        participante=participante,
                        codigo_item=codigo_item,
                        descricao_item=produtos.get(codigo_item, ""),
                        cfop=", ".join(cfops),
                        base_icms=self._moeda(grupo["base"]),
                        aliquota_icms=self._aliquota(aliquota),
                        valor_icms=self._moeda(grupo["icms"]),
                        linhas_c170=tuple(grupo["linhas"]),
                        status=status,
                        codigo_existente=codigo_existente,
                        observacao=observacao,
                        residuos_arredondamento=tuple(grupo.get("residuos", ())),
                        valor_c197_existente=self._moeda(existente["icms"]) if existente else Decimal("0"),
                    )
                )

            # C197 sem C170 elegível correspondente é sempre revisão. Isso também
            # captura ajustes antigos calculados sobre item com ICMS zero, ainda que
            # a nota tenha outros créditos válidos.
            for (codigo_item, aliquota_c197), existente in grupos_c197.items():
                if (codigo_item, aliquota_c197) in grupos_c170:
                    continue
                referencias = c170_por_item.get(codigo_item, [])
                referencia = referencias[0] if referencias else {}
                cod = existente["codigos"].most_common(1)[0][0] if existente["codigos"] else ""
                detalhe = (
                    f"C197 {cod} no valor de R$ {self._formatar_decimal(existente['icms'])} não possui "
                    "C170 elegível com crédito correspondente. Ajuste bloqueado para revisão."
                )
                if referencias:
                    detalhe += (
                        f" C170: CFOP {referencia.get('cfop') or '-'}, BC "
                        f"{self._formatar_decimal(referencia.get('base', Decimal('0')))}, alíquota "
                        f"{self._formatar_decimal(referencia.get('aliquota', Decimal('0')))}%, ICMS "
                        f"{self._formatar_decimal(referencia.get('icms', Decimal('0')))}."
                    )
                nota.itens.append(
                    ItemEstornoICMS(
                        numero_documento=numero_documento,
                        chave_nfe=chave_nfe,
                        data_entrada=data_entrada,
                        codigo_participante=codigo_part,
                        participante=participante,
                        codigo_item=codigo_item,
                        descricao_item=produtos.get(codigo_item, ""),
                        cfop=referencia.get("cfop", ""),
                        base_icms=referencia.get("base", Decimal("0")),
                        aliquota_icms=self._aliquota(referencia.get("aliquota", Decimal("0"))),
                        valor_icms=referencia.get("icms", Decimal("0")),
                        linhas_c170=tuple(r.get("linha") for r in referencias if r.get("linha")),
                        status="REVISAR",
                        codigo_existente=cod,
                        observacao=detalhe,
                        valor_c197_existente=self._moeda(existente["icms"]),
                    )
                )

            if diferenca_nota > CENTAVO and not nota.arredondamento_validado:
                nota.status = "REVISAR"
                nota.observacao = (
                    f"O ICMS do C100 ({self._formatar_decimal(valor_icms_c100)}) não coincide "
                    f"com a soma dos C170 ({self._formatar_decimal(soma_c170)}). A diferença "
                    "não foi comprovada como simples arredondamento item a item."
                )
                for item in nota.itens:
                    if item.status == "PENDENTE":
                        item.status = "REVISAR"
                        item.observacao = nota.observacao
            elif any(item.status == "REVISAR" for item in nota.itens):
                nota.status = "REVISAR"
                nota.observacao = "A nota possui item bloqueado, ajuste parcial ou divergente e exige conferência."
                for item in nota.itens:
                    if item.status == "PENDENTE":
                        item.status = "REVISAR"
                        item.observacao = (item.observacao + " Geração da nota inteira bloqueada até a revisão.").strip()
            elif nota.itens and all(item.status == "EXISTENTE" for item in nota.itens):
                nota.status = "EXISTENTE"
                nota.observacao = "Todos os créditos da nota já possuem estorno correspondente."
            else:
                nota.status = "PENDENTE"
                nota.observacao = "Nota apta para estorno integral dos créditos de ICMS."
                if nota.arredondamento_validado and diferenca_nota > CENTAVO:
                    sinal = "+" if diferenca_assinada > 0 else ""
                    nota.observacao += (
                        f" Diferença cumulativa de arredondamento comprovada: "
                        f"{sinal}{self._formatar_decimal(diferenca_assinada)} em "
                        f"{nota.linhas_icms_consideradas} linha(s) C170; total teórico pela base × alíquota: "
                        f"{self._formatar_decimal(nota.valor_icms_teorico)}."
                    )

            # 17.8.94 — reconciliação segura de arredondamento item a item.
            # A diferença deixa de ficar limitada a R$ 0,01 por NF quando o motor
            # consegue provar matematicamente que o C100 corresponde ao total
            # teórico (soma de BC × alíquota sem arredondar cada item) e cada C170
            # individual coincide com o arredondamento normal para centavos.
            # O ajuste é então distribuído em passos de R$ 0,01 entre os itens
            # cujos resíduos justificam o sinal, preservando a memória de cálculo.
            if nota.status == "PENDENTE":
                pendentes = nota.itens_pendentes
                total_itens = sum((item.valor_icms for item in pendentes), Decimal("0"))
                total_existente_seguro = nota.valor_c197_existente if any(
                    item.status == "EXISTENTE" for item in nota.itens
                ) else Decimal("0")
                ajuste = self._moeda(valor_icms_c100 - total_existente_seguro - total_itens)
                if ajuste != 0 and pendentes:
                    ajuste_simples = ajuste.copy_abs() <= CENTAVO
                    ajuste_cumulativo = nota.arredondamento_validado
                    if ajuste_simples or ajuste_cumulativo:
                        aplicado = self._distribuir_ajuste_arredondamento(pendentes, ajuste)
                        if aplicado:
                            sinal = "+" if ajuste > 0 else ""
                            nota.observacao += (
                                f" Reconciliação de arredondamento: {sinal}{self._formatar_decimal(ajuste)}; "
                                "o C197 gerado fechará com o ICMS do C100."
                            )
                        elif ajuste.copy_abs() > CENTAVO:
                            nota.status = "REVISAR"
                            nota.observacao += (
                                " A diferença parecia arredondamento, mas não foi possível distribuí-la "
                                "com segurança entre os itens pendentes; geração automática bloqueada."
                            )
                            for item in pendentes:
                                item.status = "REVISAR"
                                item.valor_icms_geracao = None
                                item.ajuste_arredondamento = Decimal("0")

            notas.append(nota)
            if ordem % 100 == 0:
                percentual = min(80, 10 + int(ordem / max(1, len(limites_c100)) * 70))
                self._progresso(progresso, percentual, f"{ordem} documentos analisados...")

        itens = [item for nota in notas for item in nota.itens]
        total_creditos = sum((nota.valor_icms_c100 for nota in notas), Decimal("0"))
        total_pendente = sum((item.valor_estorno for item in itens if item.status == "PENDENTE"), Decimal("0"))
        total_existente = sum((item.valor_icms for item in itens if item.status == "EXISTENTE"), Decimal("0"))
        total_revisao = sum(
            (max(item.valor_icms, item.valor_c197_existente) for item in itens if item.status == "REVISAR"),
            Decimal("0"),
        )

        codigo_modelo = codigos_existentes.most_common(1)[0][0] if codigos_existentes else ""
        alerta_codigo = ""
        if codigo_modelo == "MG50000018":
            alerta_codigo = (
                "O arquivo-modelo usa MG50000018. Na tabela vigente da SEF/MG esse código está "
                "associado ao FEM em entrada devolvida; para estorno de crédito de TTS, a tabela "
                "vigente identifica MG50000100. Confirme o código previsto no regime especial."
            )

        self._progresso(progresso, 100, "Análise dos créditos de ICMS concluída.")
        return ResultadoAnaliseEstornoICMS(
            notas=notas,
            regime_especial=regime_especial,
            mencao_tts_ecommerce=mencao_tts,
            codigos_existentes=dict(codigos_existentes),
            total_creditos_entradas=self._moeda(total_creditos),
            total_pendente=self._moeda(total_pendente),
            total_existente=self._moeda(total_existente),
            total_revisao=self._moeda(total_revisao),
            notas_pendentes=sum(1 for nota in notas if nota.status == "PENDENTE"),
            notas_existentes=sum(1 for nota in notas if nota.status == "EXISTENTE"),
            notas_revisao=sum(1 for nota in notas if nota.status == "REVISAR"),
            itens_pendentes=sum(1 for item in itens if item.status == "PENDENTE"),
            itens_existentes=sum(1 for item in itens if item.status == "EXISTENTE"),
            itens_revisao=sum(1 for item in itens if item.status == "REVISAR"),
            codigo_modelo_detectado=codigo_modelo,
            alerta_codigo_modelo=alerta_codigo,
        )

    @classmethod
    def _motivo_bloqueio_credito_c170(
        cls, *, cfop: str, base: Decimal, aliquota: Decimal, valor_icms: Decimal
    ) -> str:
        """Retorna o motivo que impede a geração automática de C197 para o C170.

        A 17.8.95 torna explícito o princípio que já deveria reger o estorno: só
        existe crédito automático a estornar quando o próprio C170 traz base,
        alíquota e VL_ICMS positivos e a natureza da entrada não é de uso/consumo.
        """
        if valor_icms <= 0:
            return "C170 sem crédito de ICMS (VL_ICMS <= 0)"
        if base <= 0:
            return "C170 com crédito informado, mas sem base de ICMS positiva"
        if aliquota <= 0:
            return "C170 com crédito informado, mas sem alíquota de ICMS positiva"
        if (cfop or "").strip() in cls.CFOPS_USO_CONSUMO_BLOQUEADOS:
            return f"CFOP {cfop} é aquisição para uso/consumo e não entra no estorno automático de crédito"
        return ""

    def _diagnosticar_arredondamento_cumulativo(
        self,
        valor_icms_c100: Decimal,
        grupos_c170: dict[tuple[str, Decimal], dict],
    ) -> dict[str, Decimal | int | bool]:
        componentes = [
            componente
            for grupo in grupos_c170.values()
            for componente in grupo.get("componentes", ())
        ]
        quantidade = len(componentes)
        if not componentes:
            return {
                "seguro": False,
                "total_teorico": Decimal("0"),
                "limite": Decimal("0"),
                "linhas": 0,
            }

        total_c170 = sum((c["icms"] for c in componentes), Decimal("0"))
        total_teorico_exato = sum((c["teorico_exato"] for c in componentes), Decimal("0"))
        total_teorico = self._moeda(total_teorico_exato)
        diferenca = self._moeda(valor_icms_c100 - total_c170)
        limite = self._moeda(MEIO_CENTAVO * Decimal(quantidade) + MEIO_CENTAVO)

        # Para classificar uma diferença acima de R$ 0,01 como arredondamento:
        # 1) cada C170 precisa bater exatamente com BC × alíquota arredondado a centavos;
        # 2) o total C100 precisa bater com a soma teórica sem arredondar item a item;
        # 3) a diferença precisa caber no teto matemático de 0,5 centavo por linha.
        itens_coerentes = all(c["icms"] == c["teorico_item"] for c in componentes)
        total_coerente = valor_icms_c100 == total_teorico
        dentro_teto = diferenca.copy_abs() <= (limite + CENTAVO)
        residuos = [c["teorico_exato"] - c["icms"] for c in componentes]
        centavos_necessarios = int((diferenca.copy_abs() / CENTAVO).to_integral_value(rounding=ROUND_HALF_UP))
        if diferenca > 0:
            capacidade_sinal = sum(1 for r in residuos if r > 0)
        elif diferenca < 0:
            capacidade_sinal = sum(1 for r in residuos if r < 0)
        else:
            capacidade_sinal = quantidade
        distribuivel = centavos_necessarios <= capacidade_sinal

        seguro = bool(
            diferenca.copy_abs() > CENTAVO
            and itens_coerentes
            and total_coerente
            and dentro_teto
            and distribuivel
        )
        return {
            "seguro": seguro,
            "total_teorico": total_teorico,
            "limite": limite,
            "linhas": quantidade,
        }

    def _distribuir_ajuste_arredondamento(
        self,
        itens: list[ItemEstornoICMS],
        ajuste: Decimal,
    ) -> bool:
        ajuste = self._moeda(ajuste)
        if ajuste == 0:
            return True

        centavos = int((ajuste.copy_abs() / CENTAVO).to_integral_value(rounding=ROUND_HALF_UP))
        if centavos <= 0:
            return True

        candidatos: list[tuple[Decimal, int]] = []
        for indice_item, item in enumerate(itens):
            residuos = item.residuos_arredondamento or (Decimal("0"),)
            for residuo in residuos:
                if ajuste > 0 and residuo > 0:
                    candidatos.append((residuo, indice_item))
                elif ajuste < 0 and residuo < 0:
                    candidatos.append((residuo, indice_item))

        # O caso simples de 1 centavo da 17.8.90 continua aceito mesmo quando
        # não há resíduo disponível (ex.: bases já vieram arredondadas do ERP).
        if len(candidatos) < centavos:
            if centavos == 1 and itens:
                indice_item = max(range(len(itens)), key=lambda i: itens[i].valor_icms)
                candidatos = [(Decimal("0"), indice_item)]
            else:
                return False

        candidatos.sort(key=lambda x: x[0], reverse=ajuste > 0)
        por_item: Counter[int] = Counter(indice for _residuo, indice in candidatos[:centavos])
        sinal_centavo = CENTAVO if ajuste > 0 else -CENTAVO

        aplicados: list[tuple[ItemEstornoICMS, Decimal, Decimal | None, str]] = []
        for indice_item, quantidade in por_item.items():
            item = itens[indice_item]
            parcela = sinal_centavo * Decimal(quantidade)
            novo_valor = self._moeda(item.valor_icms + parcela)
            if novo_valor < 0:
                for alvo, ajuste_antigo, geracao_antiga, obs_antiga in aplicados:
                    alvo.ajuste_arredondamento = ajuste_antigo
                    alvo.valor_icms_geracao = geracao_antiga
                    alvo.observacao = obs_antiga
                return False
            aplicados.append((item, item.ajuste_arredondamento, item.valor_icms_geracao, item.observacao))
            item.ajuste_arredondamento = parcela
            item.valor_icms_geracao = novo_valor
            sinal = "+" if parcela > 0 else ""
            item.observacao = (
                item.observacao
                + f" Ajuste de arredondamento distribuído: {sinal}{self._formatar_decimal(parcela)}."
            ).strip()

        total_aplicado = self._moeda(sum((item.ajuste_arredondamento for item in itens), Decimal("0")))
        if total_aplicado != ajuste:
            for alvo, ajuste_antigo, geracao_antiga, obs_antiga in aplicados:
                alvo.ajuste_arredondamento = ajuste_antigo
                alvo.valor_icms_geracao = geracao_antiga
                alvo.observacao = obs_antiga
            return False
        return True

    def gerar(
        self,
        linhas: list[str],
        encoding: str,
        caminho_saida: str | Path,
        analise: ResultadoAnaliseEstornoICMS,
        codigo_ajuste: str,
        descricao_ajuste: str = TEXTO_OBSERVACAO,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoGeracaoEstornoICMS:
        codigo_ajuste = codigo_ajuste.strip().upper()
        if not re.fullmatch(r"MG\d{8}", codigo_ajuste):
            raise ValueError("Informe um código de ajuste mineiro válido, no formato MG00000000.")
        if not analise.pode_gerar:
            raise RuntimeError("A análise não encontrou créditos pendentes seguros para estornar.")

        notas_aptas = [nota for nota in analise.notas if nota.status == "PENDENTE"]
        if not notas_aptas:
            raise RuntimeError("Nenhuma nota está apta para geração automática do estorno.")

        self._progresso(progresso, 5, "Preparando registros 0460, C195 e C197...")
        novas = list(linhas)
        quebra = self._quebra_padrao(novas)
        codigo_observacao, novas, linhas_0460 = self._garantir_0460(novas, quebra)

        insercoes: dict[int, list[str]] = defaultdict(list)
        memoria: list[ItemEstornoICMS] = []
        total_estornado = Decimal("0")
        itens_ajustados = 0

        # Se um 0460 foi inserido, os índices posteriores deslocam uma posição. As inserções
        # de C195/C197 são calculadas com base no arquivo original e compensadas abaixo.
        deslocamento_0460 = linhas_0460
        for nota in notas_aptas:
            pendentes = nota.itens_pendentes
            if not pendentes:
                continue
            indice_insercao = nota.indice_fim_bloco + deslocamento_0460
            registros = [f"|C195|{codigo_observacao}|{self.TEXTO_OBSERVACAO}|{quebra}"]
            for item in pendentes:
                registros.append(
                    "|C197|{codigo}|{descricao}|{item}|{base}|{aliq}|{icms}||{quebra}".format(
                        codigo=codigo_ajuste,
                        descricao=descricao_ajuste.strip() or self.TEXTO_OBSERVACAO,
                        item=item.codigo_item,
                        base=self._formatar_decimal(item.base_icms),
                        aliq=self._formatar_decimal(item.aliquota_icms),
                        icms=self._formatar_decimal(item.valor_estorno),
                        quebra=quebra,
                    )
                )
                memoria.append(item)
                total_estornado += item.valor_estorno
                itens_ajustados += 1
            insercoes[indice_insercao].extend(registros)

        if not insercoes:
            raise RuntimeError("Nenhum registro C197 novo foi preparado.")

        reconstruidas: list[str] = []
        for indice, linha in enumerate(novas):
            if indice in insercoes:
                reconstruidas.extend(insercoes[indice])
            reconstruidas.append(linha)
        if len(novas) in insercoes:
            reconstruidas.extend(insercoes[len(novas)])
        novas = reconstruidas

        self._progresso(progresso, 55, "Atualizando a apuração do ICMS no registro E110...")
        novas = self._atualizar_e110(novas, total_estornado)
        self._progresso(progresso, 70, "Recalculando fechamentos e inventário do bloco 9...")
        novas = self._recalcular_totalizadores(novas)

        destino = Path(caminho_saida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        encoding_saida = self._encoding_sped_sem_bom(encoding)
        with destino.open("w", encoding=encoding_saida, newline="") as arquivo:
            arquivo.writelines(novas)

        caminho_memoria = destino.with_name(f"{destino.stem}_MEMORIA_ESTORNO_ICMS.csv")
        self._salvar_memoria_csv(
            caminho_memoria,
            memoria,
            codigo_ajuste,
            analise.regime_especial,
        )
        caminho_relatorio = destino.with_name(f"{destino.stem}_RELATORIO_ESTORNO_ICMS.txt")
        self._salvar_relatorio(
            caminho_relatorio,
            destino,
            analise,
            codigo_ajuste,
            codigo_observacao,
            total_estornado,
            len(notas_aptas),
            itens_ajustados,
        )

        linhas_inseridas = linhas_0460 + sum(len(registros) for registros in insercoes.values())
        self._progresso(progresso, 100, "SPED estornado e memória de cálculo gerados.")
        return ResultadoGeracaoEstornoICMS(
            caminho_sped=destino,
            caminho_memoria=caminho_memoria,
            caminho_relatorio=caminho_relatorio,
            codigo_ajuste=codigo_ajuste,
            codigo_observacao=codigo_observacao,
            total_estornado=self._moeda(total_estornado),
            notas_alteradas=len(notas_aptas),
            itens_ajustados=itens_ajustados,
            linhas_inseridas=linhas_inseridas,
        )

    @staticmethod
    def _encoding_sped_sem_bom(encoding: str) -> str:
        normalizado = (encoding or "utf-8").lower().replace("_", "-")
        if normalizado in {"utf-8-sig", "utf8-sig", "utf-8", "utf8"}:
            return "utf-8"
        return encoding

    def _garantir_0460(self, linhas: list[str], quebra: str) -> tuple[str, list[str], int]:
        usados: dict[str, str] = {}
        for linha in linhas:
            campos = self._campos(linha)
            if campos and campos[0] == "0460" and len(campos) > 2:
                usados[campos[1].strip()] = campos[2].strip()
                if self._normalizar(campos[2]) == self._normalizar(self.TEXTO_OBSERVACAO):
                    return campos[1].strip(), linhas, 0

        codigo = ""
        for numero in range(1, 1000):
            candidato = f"{numero:03d}"
            if candidato not in usados:
                codigo = candidato
                break
        if not codigo:
            raise RuntimeError("Não foi possível criar um código livre para o registro 0460.")

        indice_0990 = next((i for i, linha in enumerate(linhas) if self._codigo(linha) == "0990"), None)
        if indice_0990 is None:
            raise RuntimeError("Registro 0990 não encontrado; não é seguro incluir o 0460.")
        novas = list(linhas)
        novas.insert(indice_0990, f"|0460|{codigo}|{self.TEXTO_OBSERVACAO}|{quebra}")
        return codigo, novas, 1

    def _atualizar_e110(self, linhas: list[str], valor_adicional: Decimal) -> list[str]:
        novas = list(linhas)
        indices = [i for i, linha in enumerate(novas) if self._codigo(linha) == "E110"]
        if len(indices) != 1:
            raise RuntimeError(
                f"Era esperado um único E110, mas foram encontrados {len(indices)}. Revise a apuração manualmente."
            )
        indice = indices[0]
        campos = self._campos(novas[indice])
        if len(campos) < 15:
            raise RuntimeError("O registro E110 está incompleto e não pode ser recalculado com segurança.")

        campos[2] = self._formatar_decimal(self._decimal(campos[2]) + valor_adicional)
        debitos = self._decimal(campos[1])
        ajustes_debito_doc = self._decimal(campos[2])
        ajustes_debito_apur = self._decimal(campos[3])
        estornos_credito = self._decimal(campos[4])
        creditos = self._decimal(campos[5])
        ajustes_credito_doc = self._decimal(campos[6])
        ajustes_credito_apur = self._decimal(campos[7])
        estornos_debito = self._decimal(campos[8])
        saldo_credor_anterior = self._decimal(campos[9])
        total_deducoes = self._decimal(campos[11])

        saldo = (
            debitos
            + ajustes_debito_doc
            + ajustes_debito_apur
            + estornos_credito
            - creditos
            - ajustes_credito_doc
            - ajustes_credito_apur
            - estornos_debito
            - saldo_credor_anterior
        )
        saldo_apurado = max(saldo, Decimal("0"))
        saldo_credor = max(-saldo, Decimal("0"))
        icms_recolher = max(saldo_apurado - total_deducoes, Decimal("0"))
        campos[10] = self._formatar_decimal(saldo_apurado)
        campos[12] = self._formatar_decimal(icms_recolher)
        campos[13] = self._formatar_decimal(saldo_credor)
        novas[indice] = self._montar(campos, self._fim_linha(novas[indice]))
        return novas

    def _recalcular_totalizadores(self, linhas: list[str]) -> list[str]:
        novas = list(linhas)
        quebra = self._quebra_padrao(novas)

        indices_9900 = [i for i, linha in enumerate(novas) if self._codigo(linha) == "9900"]
        indice_9990 = next((i for i, linha in enumerate(novas) if self._codigo(linha) == "9990"), None)
        if indice_9990 is not None:
            remover = set(indices_9900)
            sem_9900 = [linha for i, linha in enumerate(novas) if i not in remover]
            indice_9990 = next(i for i, linha in enumerate(sem_9900) if self._codigo(linha) == "9990")
            contagens = Counter(self._codigo(linha) for linha in sem_9900 if self._codigo(linha))
            codigos = sorted(set(contagens) - {"9900"}) + ["9900"]
            qtd_9900 = len(codigos)
            registros = [
                f"|9900|{codigo}|{qtd_9900 if codigo == '9900' else contagens[codigo]}|{quebra}"
                for codigo in codigos
            ]
            novas = sem_9900[:indice_9990] + registros + sem_9900[indice_9990:]

        pares_blocos = {
            "0990": "0000",
            "A990": "A001",
            "B990": "B001",
            "C990": "C001",
            "D990": "D001",
            "E990": "E001",
            "G990": "G001",
            "H990": "H001",
            "K990": "K001",
            "1990": "1001",
            "9990": "9001",
        }
        posicoes: dict[str, list[int]] = defaultdict(list)
        for indice, linha in enumerate(novas):
            codigo = self._codigo(linha)
            if codigo:
                posicoes[codigo].append(indice)

        for fechamento, abertura in pares_blocos.items():
            if len(posicoes.get(fechamento, [])) != 1 or not posicoes.get(abertura):
                continue
            i_fechamento = posicoes[fechamento][0]
            i_abertura = posicoes[abertura][0]
            if fechamento == "9990" and posicoes.get("9999"):
                quantidade = posicoes["9999"][0] - i_abertura + 1
            else:
                quantidade = i_fechamento - i_abertura + 1
            campos = self._campos(novas[i_fechamento])
            if len(campos) > 1:
                campos[1] = str(quantidade)
                novas[i_fechamento] = self._montar(campos, self._fim_linha(novas[i_fechamento]))

        indice_9999 = next((i for i, linha in enumerate(novas) if self._codigo(linha) == "9999"), None)
        if indice_9999 is not None:
            campos = self._campos(novas[indice_9999])
            if len(campos) > 1:
                campos[1] = str(len(novas))
                novas[indice_9999] = self._montar(campos, self._fim_linha(novas[indice_9999]))
        return novas

    def _salvar_memoria_csv(
        self,
        caminho: Path,
        itens: list[ItemEstornoICMS],
        codigo_ajuste: str,
        regime_especial: str,
    ) -> None:
        with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
            escritor = csv.writer(arquivo, delimiter=";")
            escritor.writerow(["FISCALPRO — MEMÓRIA DO ESTORNO DE CRÉDITOS DE ICMS"])
            escritor.writerow(["Gerado em", datetime.now().strftime("%d/%m/%Y %H:%M:%S")])
            escritor.writerow(["Regime especial detectado", regime_especial or "Não identificado"])
            escritor.writerow(["Código do ajuste", codigo_ajuste])
            escritor.writerow([])
            escritor.writerow(
                [
                    "NF",
                    "Chave NF-e",
                    "Data de entrada",
                    "Fornecedor",
                    "Código do item",
                    "Descrição",
                    "CFOP",
                    "Base ICMS",
                    "Alíquota ICMS",
                    "Crédito C170",
                    "Ajuste arredondamento",
                    "Crédito estornado",
                    "Código do ajuste",
                ]
            )
            for item in itens:
                escritor.writerow(
                    [
                        item.numero_documento,
                        item.chave_nfe,
                        item.data_entrada,
                        item.participante,
                        item.codigo_item,
                        item.descricao_item,
                        item.cfop,
                        self._formatar_decimal(item.base_icms),
                        self._formatar_decimal(item.aliquota_icms),
                        self._formatar_decimal(item.valor_icms),
                        self._formatar_decimal(item.ajuste_arredondamento),
                        self._formatar_decimal(item.valor_estorno),
                        codigo_ajuste,
                    ]
                )

    def _salvar_relatorio(
        self,
        caminho: Path,
        sped: Path,
        analise: ResultadoAnaliseEstornoICMS,
        codigo_ajuste: str,
        codigo_observacao: str,
        total: Decimal,
        notas: int,
        itens: int,
    ) -> None:
        conteudo = [
            "FISCALPRO — ESTORNO DE CRÉDITOS DE ICMS",
            "=" * 78,
            f"Gerado em: {datetime.now():%d/%m/%Y %H:%M:%S}",
            f"SPED gerado: {sped}",
            f"Regime especial detectado: {analise.regime_especial or 'Não identificado'}",
            f"Código do ajuste C197: {codigo_ajuste}",
            f"Código da observação 0460/C195: {codigo_observacao}",
            f"Notas alteradas: {notas}",
            f"Itens ajustados: {itens}",
            f"Total estornado: R$ {self._formatar_decimal(total)}",
            "",
            "REGRAS APLICADAS",
            "-" * 78,
            "- Foram consideradas NF-e de entrada (C100 IND_OPER=0) com crédito de ICMS.",
            "- O estorno foi gerado por item em C195/C197, agrupando código do item e alíquota.",
            "- Diferenças de arredondamento são reconciliadas por NF; acima de R$ 0,01, somente quando BC × alíquota comprova matematicamente o acúmulo item a item.",
            "- Créditos já estornados ou divergentes não foram duplicados.",
            "- O campo VL_AJ_DEBITOS do E110 e os totalizadores foram recalculados.",
            "- O arquivo original não foi alterado.",
            "",
            "ATENÇÃO",
            "- A validação final deve ser feita no PVA.",
            "- O código do ajuste precisa corresponder ao regime especial vigente da empresa.",
        ]
        if analise.alerta_codigo_modelo:
            conteudo.extend(["", "ALERTA SOBRE O ARQUIVO-MODELO", analise.alerta_codigo_modelo])
        caminho.write_text("\n".join(conteudo) + "\n", encoding="utf-8")

    @classmethod
    def _limites_blocos_c100(cls, linhas: list[str]) -> list[tuple[int, int]]:
        indices = [i for i, linha in enumerate(linhas) if cls._codigo(linha) == "C100"]
        limite_bloco_c = next((i for i, linha in enumerate(linhas) if cls._codigo(linha) == "C990"), len(linhas))
        resultado: list[tuple[int, int]] = []
        for posicao, inicio in enumerate(indices):
            proximo = indices[posicao + 1] if posicao + 1 < len(indices) else limite_bloco_c
            resultado.append((inicio, proximo))
        return resultado

    @classmethod
    def _mapear_participantes(cls, linhas: list[str]) -> dict[str, str]:
        resultado: dict[str, str] = {}
        for linha in linhas:
            campos = cls._campos(linha)
            if campos and campos[0] == "0150" and len(campos) > 2:
                resultado[campos[1].strip()] = campos[2].strip()
        return resultado

    @classmethod
    def _mapear_produtos(cls, linhas: list[str]) -> dict[str, str]:
        resultado: dict[str, str] = {}
        for linha in linhas:
            campos = cls._campos(linha)
            if campos and campos[0] == "0200" and len(campos) > 2:
                resultado[campos[1].strip()] = campos[2].strip()
        return resultado

    @classmethod
    def _detectar_regime(cls, linhas: list[str]) -> tuple[str, bool]:
        padrao = re.compile(r"\b\d{2}\.\d{9}-\d{2}\b")
        regime = ""
        mencao_tts = False
        for linha in linhas:
            campos = cls._campos(linha)
            if not campos or campos[0] != "C110":
                continue
            texto = " ".join(campos[1:]).upper()
            if not regime:
                encontrado = padrao.search(texto)
                if encontrado:
                    regime = encontrado.group(0)
            if "TTS" in texto or "E-COMMERCE" in texto or "ECOMMERCE" in texto:
                mencao_tts = True
        return regime, mencao_tts

    @staticmethod
    def _decimal(valor: str | Decimal | None) -> Decimal:
        if isinstance(valor, Decimal):
            return valor
        texto = (valor or "").strip()
        if not texto:
            return Decimal("0")
        try:
            return Decimal(texto.replace(".", "").replace(",", "."))
        except InvalidOperation:
            return Decimal("0")

    @staticmethod
    def _moeda(valor: Decimal) -> Decimal:
        return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)

    @staticmethod
    def _aliquota(valor: Decimal) -> Decimal:
        return valor.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP).normalize()

    @classmethod
    def _formatar_decimal(cls, valor: Decimal) -> str:
        numero = cls._moeda(valor)
        texto = format(numero, "f")
        if "." in texto:
            texto = texto.rstrip("0").rstrip(".")
        return texto.replace(".", ",") or "0"

    @staticmethod
    def _normalizar(texto: str) -> str:
        return re.sub(r"\s+", " ", (texto or "").strip().upper())

    @staticmethod
    def _campos(linha: str) -> list[str]:
        texto = linha.rstrip("\r\n")
        partes = texto.split("|")
        if len(partes) < 3:
            return []
        if partes[0] == "":
            partes = partes[1:]
        if partes and partes[-1] == "":
            partes = partes[:-1]
        return partes

    @classmethod
    def _codigo(cls, linha: str) -> str:
        campos = cls._campos(linha)
        return campos[0] if campos else ""

    @staticmethod
    def _fim_linha(linha: str) -> str:
        if linha.endswith("\r\n"):
            return "\r\n"
        if linha.endswith("\n"):
            return "\n"
        return ""

    @classmethod
    def _quebra_padrao(cls, linhas: list[str]) -> str:
        for linha in linhas:
            fim = cls._fim_linha(linha)
            if fim:
                return fim
        return "\n"

    @staticmethod
    def _montar(campos: list[str], quebra: str) -> str:
        return "|" + "|".join(campos) + "|" + quebra

    @staticmethod
    def _progresso(callback: ProgressoCallback | None, percentual: int, mensagem: str) -> None:
        if callback:
            callback(percentual, mensagem)
