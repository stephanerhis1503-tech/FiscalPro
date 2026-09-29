"""Sincronização segura do Bloco M após correções de PIS/COFINS no C170.

Hotfix 17.8.23
---------------
A rotina não tenta reconstruir créditos, ajustes ou saldos por aproximação.
Ela atua somente na parte do Bloco M que pode ser derivada de forma
rastreável das alterações feitas pelo próprio FiscalPro:

* atualiza M210/M200 pelo delta de base e contribuição de PIS das saídas;
* sincroniza M205 com o novo valor a recolher do M200 quando o vínculo é único;
* atualiza M610/M600 pelo delta equivalente de COFINS quando esses registros
  já existem e sincroniza M605 nas mesmas condições;
* se M600/M610 estiverem ausentes, só os cria quando o arquivo possui uma
  única apuração básica em M210, as bases PIS/COFINS dos documentos são
  pareadas e não há deduções especiais no M200 que não possam ser espelhadas.

M100/M105/M500/M505 (créditos) são preservados. Correções 08 -> 74 em entradas
não geram crédito e, portanto, não alteram esses registros.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


@dataclass(frozen=True, slots=True)
class AlteracaoBlocoM:
    numero_linha: int | None
    registro: str
    campo: str
    valor_anterior: str
    valor_novo: str
    justificativa: str


@dataclass(slots=True)
class ResultadoReapuracaoBlocoM:
    linhas: list[str]
    alteracoes: list[AlteracaoBlocoM] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    estrutura_alterada: bool = False


class ReapuradorBlocoM:
    """Sincroniza débitos do Bloco M com alterações determinísticas no C170."""

    CST_DEBITO = {"01", "02", "03", "05"}

    # Índices sem os separadores externos (0 = código do registro).
    C170 = {
        "PIS": {"cst": 24, "base": 25, "aliquota": 26, "valor": 29},
        "COFINS": {"cst": 30, "base": 31, "aliquota": 32, "valor": 35},
    }

    # M210/M610 possuem estrutura paralela.
    M_DET = {
        "receita_bruta": 2,
        "base": 3,
        "aj_acres_base": 4,
        "aj_red_base": 5,
        "base_ajustada": 6,
        "aliquota": 7,
        "quantidade": 8,
        "aliquota_qtd": 9,
        "valor_apurado": 10,
        "aj_acres_cont": 11,
        "aj_red_cont": 12,
        "diferida": 13,
        "diferida_ant": 14,
        "valor_periodo": 15,
    }

    # M200/M600 possuem estrutura paralela de consolidação.
    M_CONS = {
        "tot_nc_periodo": 1,
        "cred_desc": 2,
        "cred_desc_ant": 3,
        "tot_nc_devido": 4,
        "ret_nc": 5,
        "outras_ded_nc": 6,
        "nc_recolher": 7,
        "tot_cum_periodo": 8,
        "ret_cum": 9,
        "outras_ded_cum": 10,
        "cum_recolher": 11,
        "total_recolher": 12,
    }

    def sincronizar(
        self,
        linhas_antes: list[str],
        linhas_depois: list[str],
        tipo_sped: str,
    ) -> ResultadoReapuracaoBlocoM:
        novas = list(linhas_depois)
        resultado = ResultadoReapuracaoBlocoM(linhas=novas)
        if str(tipo_sped or "").strip().upper() != "EFD CONTRIBUIÇÕES":
            return resultado
        if len(linhas_antes) != len(linhas_depois):
            resultado.avisos.append(
                "Bloco M não foi sincronizado porque a estrutura do arquivo mudou antes da reapuração."
            )
            return resultado

        deltas = {
            "PIS": self._deltas_por_aliquota(linhas_antes, linhas_depois, "PIS"),
            "COFINS": self._deltas_por_aliquota(linhas_antes, linhas_depois, "COFINS"),
        }

        if not any(deltas[tributo] for tributo in deltas):
            return resultado

        # PIS: sincroniza registros existentes. O arquivo de origem já possui
        # M200/M210 quando há débito de PIS.
        self._aplicar_delta_detalhe_e_consolidacao(
            novas, resultado, "PIS", "M210", "M200", deltas["PIS"]
        )
        self._sincronizar_debitos_a_recolher(
            linhas_antes, novas, resultado, "PIS", "M200", "M205"
        )

        # COFINS: atualiza M610/M600 se existirem. Se estiverem ausentes, só
        # cria quando for seguro espelhar a apuração básica de PIS.
        indices_m610 = self._indices(novas, "M610")
        indices_m600 = self._indices(novas, "M600")
        if indices_m610 or indices_m600:
            self._aplicar_delta_detalhe_e_consolidacao(
                novas, resultado, "COFINS", "M610", "M600", deltas["COFINS"]
            )
            self._sincronizar_debitos_a_recolher(
                linhas_antes, novas, resultado, "COFINS", "M600", "M605"
            )
        elif deltas["COFINS"]:
            self._criar_cofins_quando_seguro(novas, resultado)

        resultado.linhas = novas
        return resultado

    def _deltas_por_aliquota(
        self, antes: list[str], depois: list[str], tributo: str
    ) -> dict[Decimal, tuple[Decimal, Decimal]]:
        mapa = self.C170[tributo]
        deltas: dict[Decimal, tuple[Decimal, Decimal]] = {}
        for antiga, nova in zip(antes, depois):
            if self._codigo(antiga) != "C170" or self._codigo(nova) != "C170":
                continue
            fa = self._campos(antiga)
            fn = self._campos(nova)
            if not fa or not fn:
                continue

            base_a, valor_a, aliq_a = self._valor_debito(fa, mapa)
            base_n, valor_n, aliq_n = self._valor_debito(fn, mapa)
            delta_base = base_n - base_a
            delta_valor = valor_n - valor_a
            if delta_base == 0 and delta_valor == 0:
                continue

            # Usa a alíquota nova quando a operação passou a integrar a
            # apuração. Em redução/retirada, usa a alíquota anterior.
            aliquota = aliq_n if (base_n != 0 or valor_n != 0) else aliq_a
            if aliquota is None:
                continue
            b0, v0 = deltas.get(aliquota, (Decimal("0"), Decimal("0")))
            deltas[aliquota] = (b0 + delta_base, v0 + delta_valor)
        return deltas

    def _valor_debito(
        self, campos: list[str], mapa: dict[str, int]
    ) -> tuple[Decimal, Decimal, Decimal | None]:
        cst = self._campo(campos, mapa["cst"]).strip()
        base = self._decimal(self._campo(campos, mapa["base"])) or Decimal("0")
        aliquota = self._decimal(self._campo(campos, mapa["aliquota"]))
        valor = self._decimal(self._campo(campos, mapa["valor"])) or Decimal("0")
        if cst not in self.CST_DEBITO or aliquota is None or aliquota == 0:
            return Decimal("0"), Decimal("0"), aliquota
        return base, valor, aliquota

    def _aplicar_delta_detalhe_e_consolidacao(
        self,
        linhas: list[str],
        resultado: ResultadoReapuracaoBlocoM,
        tributo: str,
        codigo_detalhe: str,
        codigo_consolidacao: str,
        deltas: dict[Decimal, tuple[Decimal, Decimal]],
    ) -> None:
        if not deltas:
            return

        total_delta_valor = Decimal("0")
        for aliquota, (delta_base, delta_valor) in sorted(deltas.items()):
            if delta_base == 0 and delta_valor == 0:
                continue
            candidatos = []
            for indice in self._indices(linhas, codigo_detalhe):
                campos = self._campos(linhas[indice])
                aliq = self._decimal(self._campo(campos, self.M_DET["aliquota"]))
                if aliq is not None and self._igual(aliq, aliquota, 4):
                    candidatos.append(indice)
            if len(candidatos) != 1:
                resultado.avisos.append(
                    f"{codigo_detalhe}: não foi possível localizar de forma única a alíquota "
                    f"{self._fmt(aliquota, 4)} para sincronizar o {tributo}."
                )
                continue
            indice = candidatos[0]
            self._somar_campo(
                linhas, resultado, indice, codigo_detalhe, "VL_REC_BRT",
                self.M_DET["receita_bruta"], delta_base,
                f"Base bruta sincronizada pelo delta dos C170 corrigidos ({tributo}).",
            )
            self._somar_campo(
                linhas, resultado, indice, codigo_detalhe, "VL_BC_CONT",
                self.M_DET["base"], delta_base,
                f"Base da contribuição sincronizada pelo delta dos C170 corrigidos ({tributo}).",
            )
            self._somar_campo(
                linhas, resultado, indice, codigo_detalhe, "VL_BC_CONT_AJUS",
                self.M_DET["base_ajustada"], delta_base,
                f"Base ajustada sincronizada pelo delta dos C170 corrigidos ({tributo}).",
            )
            self._somar_campo(
                linhas, resultado, indice, codigo_detalhe, "VL_CONT_APUR",
                self.M_DET["valor_apurado"], delta_valor,
                f"Contribuição apurada sincronizada pelo delta dos C170 corrigidos ({tributo}).",
            )
            self._somar_campo(
                linhas, resultado, indice, codigo_detalhe, "VL_CONT_PER",
                self.M_DET["valor_periodo"], delta_valor,
                f"Contribuição do período sincronizada pelo delta dos C170 corrigidos ({tributo}).",
            )
            total_delta_valor += delta_valor

        if total_delta_valor == 0:
            return
        consolidacoes = self._indices(linhas, codigo_consolidacao)
        if len(consolidacoes) != 1:
            resultado.avisos.append(
                f"{codigo_consolidacao}: não foi possível localizar uma consolidação única para o {tributo}."
            )
            return
        i = consolidacoes[0]
        # Mantém créditos, retenções e outras deduções já existentes; apenas
        # propaga o delta do débito até os campos de contribuição a recolher.
        for nome, campo in (
            ("VL_TOT_CONT_NC_PER", "tot_nc_periodo"),
            ("VL_TOT_CONT_NC_DEV", "tot_nc_devido"),
            ("VL_CONT_NC_REC", "nc_recolher"),
            ("VL_TOT_CONT_REC", "total_recolher"),
        ):
            self._somar_campo(
                linhas, resultado, i, codigo_consolidacao, nome,
                self.M_CONS[campo], total_delta_valor,
                f"Consolidação do {tributo} atualizada pelo delta do detalhamento do período.",
            )

    def _sincronizar_debitos_a_recolher(
        self,
        linhas_antes: list[str],
        linhas: list[str],
        resultado: ResultadoReapuracaoBlocoM,
        tributo: str,
        codigo_pai: str,
        codigo_filho: str,
    ) -> None:
        """Sincroniza M205/M605 com M200/M600 sem inventar rateios.

        O PGE exige que o somatório do VL_DEBITO dos registros filhos, por
        NUM_CAMPO (08 = não cumulativo; 12 = cumulativo), seja igual ao valor
        a recolher correspondente do registro pai. Quando há exatamente um
        filho para o campo, o ajuste é determinístico. Havendo mais de um, o
        FiscalPro não distribui o delta entre códigos de receita por
        aproximação: registra aviso e a correção é bloqueada pela camada
        chamadora.
        """
        pais_novos = self._indices(linhas, codigo_pai)
        pais_antigos = self._indices(linhas_antes, codigo_pai)
        if len(pais_novos) != 1 or len(pais_antigos) != 1:
            return

        todos_filhos = self._indices(linhas, codigo_filho)
        # Mantém compatibilidade com arquivos que não escrituram M205/M605.
        # A regra abaixo só atua quando esse detalhamento já existe no arquivo.
        if not todos_filhos:
            return

        mapa = {
            "08": self.M_CONS["nc_recolher"],
            "12": self.M_CONS["cum_recolher"],
        }
        pai_novo = self._campos(linhas[pais_novos[0]])
        pai_antigo = self._campos(linhas_antes[pais_antigos[0]])

        for num_campo, indice_pai in mapa.items():
            valor_novo = self._decimal(self._campo(pai_novo, indice_pai)) or Decimal("0")
            valor_antigo = self._decimal(self._campo(pai_antigo, indice_pai)) or Decimal("0")
            if valor_novo == valor_antigo:
                continue

            filhos = []
            for indice in todos_filhos:
                campos = self._campos(linhas[indice])
                if self._campo(campos, 1).strip().zfill(2) == num_campo:
                    filhos.append(indice)

            # Se não havia débito no campo nem filho correspondente, não há o
            # que sincronizar. Se havia débito e o filho sumiu, é inseguro.
            if not filhos:
                if valor_antigo != 0 or valor_novo != 0:
                    resultado.avisos.append(
                        f"{codigo_filho}: não foi localizado registro do NUM_CAMPO {num_campo} "
                        f"para sincronizar o {tributo}."
                    )
                continue

            soma_atual = sum(
                (self._decimal(self._campo(self._campos(linhas[i]), 3)) or Decimal("0"))
                for i in filhos
            )
            # Antes de mexer, prova que o conjunto de filhos representava o
            # valor do pai antes da alteração. Isso evita corrigir sobre uma
            # apuração que já estava inconsistente.
            filhos_antigos = []
            for indice in self._indices(linhas_antes, codigo_filho):
                campos = self._campos(linhas_antes[indice])
                if self._campo(campos, 1).strip().zfill(2) == num_campo:
                    filhos_antigos.append(indice)
            soma_antiga = sum(
                (self._decimal(self._campo(self._campos(linhas_antes[i]), 3)) or Decimal("0"))
                for i in filhos_antigos
            )
            if not self._igual(soma_antiga, valor_antigo, 2):
                resultado.avisos.append(
                    f"{codigo_filho}: o somatório anterior do NUM_CAMPO {num_campo} "
                    f"({self._fmt(soma_antiga, 2)}) já divergia do {codigo_pai} "
                    f"({self._fmt(valor_antigo, 2)}); ajuste automático bloqueado."
                )
                continue

            if len(filhos) != 1:
                resultado.avisos.append(
                    f"{codigo_filho}: existem {len(filhos)} registros para o NUM_CAMPO {num_campo}. "
                    "O FiscalPro não rateia automaticamente o novo débito entre códigos de receita."
                )
                continue

            indice = filhos[0]
            anterior = self._obter_campo_linha(linhas[indice], 3)
            novo = self._fmt(valor_novo, 2)
            if self._decimal(anterior) == valor_novo:
                continue
            linhas[indice] = self._substituir(linhas[indice], 3, novo)
            resultado.alteracoes.append(
                AlteracaoBlocoM(
                    numero_linha=indice + 1,
                    registro=codigo_filho,
                    campo="VL_DEBITO",
                    valor_anterior=anterior,
                    valor_novo=novo,
                    justificativa=(
                        f"Débito a recolher sincronizado com o NUM_CAMPO {num_campo} do "
                        f"{codigo_pai} após o delta confirmado do {tributo}."
                    ),
                )
            )

    def _criar_cofins_quando_seguro(
        self, linhas: list[str], resultado: ResultadoReapuracaoBlocoM
    ) -> None:
        m210 = self._indices(linhas, "M210")
        m200 = self._indices(linhas, "M200")
        if len(m210) != 1 or len(m200) != 1:
            resultado.avisos.append(
                "M600/M610 ausentes: criação automática não realizada porque a apuração de PIS "
                "não possui um único M200/M210 básico para espelhamento seguro."
            )
            return

        f210 = self._campos(linhas[m210[0]])
        f200 = self._campos(linhas[m200[0]])
        if not self._m200_sem_deducoes_especiais(f200):
            resultado.avisos.append(
                "M600/M610 ausentes: criação automática não realizada porque o M200 contém "
                "créditos/deduções/retenções que não podem ser espelhados para COFINS."
            )
            return
        if not self._bases_pis_cofins_pareadas(linhas):
            resultado.avisos.append(
                "M600/M610 ausentes: as bases PIS/COFINS dos documentos não estão pareadas; "
                "a COFINS deve ser reapurada no PGE."
            )
            return

        base = self._decimal(self._campo(f210, self.M_DET["base_ajustada"]))
        receita = self._decimal(self._campo(f210, self.M_DET["receita_bruta"]))
        if base is None or receita is None:
            resultado.avisos.append("M600/M610 ausentes: base do M210 insuficiente para espelhamento.")
            return

        aliquota_cofins = self._aliquota_cofins_pareada(linhas)
        if aliquota_cofins is None:
            resultado.avisos.append(
                "M600/M610 ausentes: não foi identificada uma única alíquota básica de COFINS "
                "nos C170 tributados."
            )
            return

        valor = (base * aliquota_cofins / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        cod_cont = self._campo(f210, 1) or "01"
        m610 = [
            "M610", cod_cont, self._fmt(receita, 2), self._fmt(base, 2),
            "0", "0", self._fmt(base, 2), self._fmt(aliquota_cofins, 4),
            "", "", self._fmt(valor, 2), "0", "0", "0", "0", self._fmt(valor, 2),
        ]
        m600 = [
            "M600", self._fmt(valor, 2), "0,00", "0,00", self._fmt(valor, 2),
            "0,00", "0,00", self._fmt(valor, 2), "0,00", "0,00", "0,00",
            "0,00", self._fmt(valor, 2),
        ]

        # Na hierarquia oficial do Bloco M, M600/M610 pertencem à apuração
        # da COFINS e devem aparecer antes dos registros de receitas sem
        # incidência M800/M810. O 17.6.5 inseria os registros apenas antes do
        # M990; em arquivos que já possuíam M800/M810 isso deixava M600/M610
        # fora de ordem e o PGE esperava M990 após M810.
        indice_m990 = self._indices(linhas, "M990")
        if len(indice_m990) != 1:
            resultado.avisos.append("M600/M610 ausentes: M990 não localizado de forma única.")
            return

        candidatos = [
            i for i, linha in enumerate(linhas)
            if self._codigo(linha) in {"M800", "M810", "M990"}
        ]
        pos = min(candidatos) if candidatos else indice_m990[0]
        quebra = self._quebra(linhas[pos])
        linhas[pos:pos] = [self._linha(m600, quebra), self._linha(m610, quebra)]
        resultado.estrutura_alterada = True
        resultado.alteracoes.extend(
            [
                AlteracaoBlocoM(
                    numero_linha=None,
                    registro="M600",
                    campo="REGISTRO",
                    valor_anterior="(ausente)",
                    valor_novo="M600 criado",
                    justificativa=(
                        "Consolidação de COFINS criada por espelhamento seguro da base do M210, "
                        "com bases PIS/COFINS pareadas e sem deduções especiais no M200."
                    ),
                ),
                AlteracaoBlocoM(
                    numero_linha=None,
                    registro="M610",
                    campo="REGISTRO",
                    valor_anterior="(ausente)",
                    valor_novo=f"Base {self._fmt(base, 2)} / alíquota {self._fmt(aliquota_cofins, 4)}",
                    justificativa=(
                        "Detalhamento da COFINS criado a partir da mesma base tributável do PIS, "
                        "validada como pareada nos registros de origem."
                    ),
                ),
            ]
        )

    def _bases_pis_cofins_pareadas(self, linhas: list[str]) -> bool:
        houve = False
        for linha in linhas:
            if self._codigo(linha) != "C170":
                continue
            c = self._campos(linha)
            cst_p = self._campo(c, 24).strip()
            cst_c = self._campo(c, 30).strip()
            if cst_p not in self.CST_DEBITO and cst_c not in self.CST_DEBITO:
                continue
            houve = True
            if cst_p != cst_c:
                return False
            bp = self._decimal(self._campo(c, 25)) or Decimal("0")
            bc = self._decimal(self._campo(c, 31)) or Decimal("0")
            if bp != bc:
                return False
        return houve

    def _aliquota_cofins_pareada(self, linhas: list[str]) -> Decimal | None:
        aliquotas: set[Decimal] = set()
        for linha in linhas:
            if self._codigo(linha) != "C170":
                continue
            c = self._campos(linha)
            if self._campo(c, 30).strip() not in self.CST_DEBITO:
                continue
            aliq = self._decimal(self._campo(c, 32))
            base = self._decimal(self._campo(c, 31)) or Decimal("0")
            if aliq is not None and aliq > 0 and base > 0:
                aliquotas.add(aliq)
        return next(iter(aliquotas)) if len(aliquotas) == 1 else None

    def _m200_sem_deducoes_especiais(self, campos: list[str]) -> bool:
        # Para gerar COFINS do zero, só aceitamos M200 sem créditos descontados,
        # retenções, outras deduções ou contribuição cumulativa.
        for indice in (2, 3, 5, 6, 8, 9, 10, 11):
            valor = self._decimal(self._campo(campos, indice)) or Decimal("0")
            if valor != 0:
                return False
        return True

    def _somar_campo(
        self,
        linhas: list[str],
        resultado: ResultadoReapuracaoBlocoM,
        indice_linha: int,
        registro: str,
        nome_campo: str,
        indice_campo: int,
        delta: Decimal,
        justificativa: str,
    ) -> None:
        if delta == 0:
            return
        anterior = self._obter_campo_linha(linhas[indice_linha], indice_campo)
        atual = self._decimal(anterior) or Decimal("0")
        novo_decimal = (atual + delta).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        novo = self._fmt(novo_decimal, 2)
        if self._decimal(anterior) == novo_decimal:
            return
        linhas[indice_linha] = self._substituir(linhas[indice_linha], indice_campo, novo)
        resultado.alteracoes.append(
            AlteracaoBlocoM(
                numero_linha=indice_linha + 1,
                registro=registro,
                campo=nome_campo,
                valor_anterior=anterior,
                valor_novo=novo,
                justificativa=justificativa,
            )
        )

    @classmethod
    def _indices(cls, linhas: list[str], codigo: str) -> list[int]:
        return [i for i, linha in enumerate(linhas) if cls._codigo(linha) == codigo]

    @staticmethod
    def _codigo(linha: str) -> str:
        texto = linha.rstrip("\r\n")
        if not (texto.startswith("|") and texto.endswith("|")):
            return ""
        partes = texto.split("|")
        return partes[1].strip().upper() if len(partes) > 2 else ""

    @staticmethod
    def _campos(linha: str) -> list[str]:
        texto = linha.rstrip("\r\n")
        if not (texto.startswith("|") and texto.endswith("|")):
            return []
        return texto.split("|")[1:-1]

    @staticmethod
    def _campo(campos: list[str], indice: int) -> str:
        return campos[indice] if indice < len(campos) else ""

    @staticmethod
    def _obter_campo_linha(linha: str, indice: int) -> str:
        campos = ReapuradorBlocoM._campos(linha)
        return ReapuradorBlocoM._campo(campos, indice)

    @staticmethod
    def _decimal(texto: str) -> Decimal | None:
        bruto = str(texto or "").strip()
        if not bruto:
            return None
        try:
            if "," in bruto:
                bruto = bruto.replace(".", "").replace(",", ".")
            return Decimal(bruto)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _fmt(valor: Decimal, casas: int) -> str:
        q = Decimal("1").scaleb(-casas)
        valor = valor.quantize(q, rounding=ROUND_HALF_UP)
        return f"{valor:.{casas}f}".replace(".", ",")

    @staticmethod
    def _igual(a: Decimal, b: Decimal, casas: int) -> bool:
        q = Decimal("1").scaleb(-casas)
        return a.quantize(q) == b.quantize(q)

    @staticmethod
    def _substituir(linha: str, indice_campo: int, valor: str) -> str:
        texto = linha.rstrip("\r\n")
        quebra = linha[len(texto):]
        partes = texto.split("|")
        indice = indice_campo + 1
        while len(partes) <= indice:
            partes.append("")
        partes[indice] = valor
        return "|".join(partes) + quebra

    @staticmethod
    def _quebra(linha: str) -> str:
        if linha.endswith("\r\n"):
            return "\r\n"
        if linha.endswith("\n"):
            return "\n"
        return "\n"

    @staticmethod
    def _linha(campos: list[str], quebra: str) -> str:
        return "|" + "|".join(campos) + "|" + quebra
