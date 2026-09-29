"""Correção tributária assistida baseada na Ficha Inteligente — Sprint 13.6.

Transforma divergências da Auditoria Tributária em propostas confirmáveis. O
arquivo original nunca é alterado. Correções fiscais permanecem desmarcadas até
a confirmação da usuária, mesmo quando Ficha Tributária e XML concordam.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Callable, Iterable

from .auditor_tributario import (
    AuditorTributarioSPED,
    ResultadoAuditoriaTributaria,
    ResultadoImportacaoXMLNFe,
)
from .corretor_assistido import CorretorAssistidoPVA
from .pre_validador import PreValidadorPVA, ResultadoPreValidacaoPVA
from .recalculador_piscofins import RecalculadorPISCOFINS

ProgressoCallback = Callable[[int, str], None]


@dataclass(slots=True)
class PropostaCorrecaoTributaria:
    identificador: int
    selecionada: bool
    modo: str
    origem: str
    nivel: str
    registro: str
    numero_linha: int | None
    documento: str
    item: str
    codigo: str
    ncm: str
    campo: str
    campo_sped: str
    valor_atual: str
    valor_sugerido: str
    regra_id: str
    aderencia: float
    justificativa: str
    indice_campo: int | None
    editavel: bool = True
    alta_confianca: bool = False
    alternativas: tuple[str, ...] = ()

    @property
    def aplicavel(self) -> bool:
        return (
            self.numero_linha is not None
            and self.indice_campo is not None
            and bool(str(self.valor_sugerido).strip())
            and self.modo != "Conflito — escolher valor"
        )


@dataclass(slots=True)
class ResultadoPreparacaoCorrecaoTributaria:
    propostas: list[PropostaCorrecaoTributaria] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.propostas)

    @property
    def selecionadas(self) -> list[PropostaCorrecaoTributaria]:
        return [p for p in self.propostas if p.selecionada and p.aplicavel]

    @property
    def conflitos(self) -> list[PropostaCorrecaoTributaria]:
        return [p for p in self.propostas if p.modo == "Conflito — escolher valor"]

    @property
    def alta_confianca(self) -> list[PropostaCorrecaoTributaria]:
        return [p for p in self.propostas if p.alta_confianca and p.aplicavel]

    def obter(self, identificador: int) -> PropostaCorrecaoTributaria:
        for proposta in self.propostas:
            if proposta.identificador == identificador:
                return proposta
        raise KeyError(f"Proposta tributária {identificador} não encontrada.")


@dataclass(frozen=True, slots=True)
class AlteracaoTributariaAplicada:
    numero_linha: int
    registro: str
    documento: str
    item: str
    codigo: str
    campo: str
    valor_anterior: str
    valor_novo: str
    origem: str
    regra_id: str
    justificativa: str


@dataclass(frozen=True, slots=True)
class ResultadoAplicacaoCorrecaoTributaria:
    caminho_sped: Path
    caminho_relatorio: Path
    total_aplicadas: int
    total_confirmadas: int
    total_recalculadas: int
    documentos_retotalizados: int
    total_ignoradas: int
    total_conflitos: int
    erros_auditoria_antes: int
    avisos_auditoria_antes: int
    erros_auditoria_depois: int
    avisos_auditoria_depois: int
    erros_pre_pva_depois: int
    avisos_pre_pva_depois: int
    avisos_recalculo: tuple[str, ...]
    requer_reapuracao_bloco_m: bool
    aplicadas: tuple[AlteracaoTributariaAplicada, ...]
    auditoria_depois: ResultadoAuditoriaTributaria
    pre_validacao_depois: ResultadoPreValidacaoPVA


@dataclass(slots=True)
class _Candidata:
    linha: int
    registro: str
    indice: int
    documento: str
    item: str
    codigo: str
    ncm: str
    campo: str
    campo_sped: str
    atual: str
    sugerido: str
    origem: str
    regra_id: str
    aderencia: float
    nivel: str
    justificativa: str


class CorretorTributarioAssistido:
    """Prepara e aplica correções tributárias somente após confirmação."""

    # Índices sem os separadores externos: 0 = código do registro.
    CAMPOS = {
        "NCM": ("0200", 7, "COD_NCM", "codigo"),
        "CEST": ("0200", 12, "CEST", "codigo"),
        "CFOP": ("C170", 10, "CFOP", "codigo"),
        "CST ICMS": ("C170", 9, "CST_ICMS", "codigo"),
        "Alíquota ICMS": ("C170", 13, "ALIQ_ICMS", "numero"),
        "CST PIS": ("C170", 24, "CST_PIS", "codigo"),
        "Alíquota PIS": ("C170", 26, "ALIQ_PIS", "numero"),
        "CST COFINS": ("C170", 30, "CST_COFINS", "codigo"),
        "Alíquota COFINS": ("C170", 32, "ALIQ_COFINS", "numero"),
        "CST IPI": ("C170", 19, "CST_IPI", "codigo"),
        "Alíquota IPI": ("C170", 22, "ALIQ_IPI", "numero"),
    }

    TAMANHOS = {
        "NCM": {8},
        "CEST": {7},
        "CFOP": {4},
        "CST ICMS": {2, 3},
        "CST PIS": {2},
        "CST COFINS": {2},
        "CST IPI": {2},
    }

    ORIGENS_CORRIGIVEIS = {"FICHA TRIBUTÁRIA", "XML NF-e"}

    def preparar(
        self,
        linhas: list[str],
        auditoria: ResultadoAuditoriaTributaria,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoPreparacaoCorrecaoTributaria:
        self._progresso(progresso, 5, "Transformando divergências em propostas tributárias...")
        mapa_0200 = self._mapear_0200(linhas)
        agrupadas: dict[tuple[int | None, int | None, str, str], list[_Candidata]] = {}

        apontamentos = [
            item
            for item in auditoria.apontamentos
            if item.origem in self.ORIGENS_CORRIGIVEIS and item.campo in self.CAMPOS
        ]
        total = max(1, len(apontamentos))

        for posicao, apontamento in enumerate(apontamentos, start=1):
            registro, indice, campo_sped, tipo = self.CAMPOS[apontamento.campo]
            linha_alvo: int | None
            atual = ""
            justificativa_extra = ""

            if registro == "0200":
                ocorrencias = mapa_0200.get(apontamento.codigo, [])
                if len(ocorrencias) == 1:
                    linha_alvo = ocorrencias[0]
                    atual = self._obter_campo(linhas[linha_alvo - 1], indice)
                elif len(ocorrencias) > 1:
                    linha_alvo = None
                    justificativa_extra = (
                        f"O produto {apontamento.codigo} possui {len(ocorrencias)} registros 0200; "
                        "é necessário resolver a duplicidade antes de alterar o cadastro."
                    )
                else:
                    linha_alvo = None
                    justificativa_extra = (
                        f"O produto {apontamento.codigo} não possui um registro 0200 localizável."
                    )
            else:
                linha_alvo = apontamento.linha if apontamento.linha > 0 else None
                if linha_alvo and linha_alvo <= len(linhas) and self._codigo(linhas[linha_alvo - 1]) == registro:
                    atual = self._obter_campo(linhas[linha_alvo - 1], indice)
                else:
                    linha_alvo = None
                    justificativa_extra = "A linha original do C170 não pôde ser localizada com segurança."

            sugerido = self._normalizar_valor(apontamento.campo, apontamento.esperado, tipo)
            atual_normalizado = self._normalizar_valor(apontamento.campo, atual, tipo)
            if linha_alvo is not None and sugerido and atual_normalizado == sugerido:
                continue

            chave = (linha_alvo, indice if linha_alvo is not None else None, apontamento.campo, apontamento.codigo)
            candidata = _Candidata(
                linha=linha_alvo or 0,
                registro=registro,
                indice=indice,
                documento=apontamento.documento,
                item=apontamento.item,
                codigo=apontamento.codigo,
                ncm=apontamento.ncm,
                campo=apontamento.campo,
                campo_sped=campo_sped,
                atual=atual,
                sugerido=sugerido,
                origem=apontamento.origem,
                regra_id=apontamento.regra_id,
                aderencia=apontamento.aderencia,
                nivel=apontamento.nivel,
                justificativa=" ".join(
                    parte for parte in (apontamento.mensagem, apontamento.orientacao, justificativa_extra) if parte
                ),
            )
            agrupadas.setdefault(chave, []).append(candidata)

            if posicao % 250 == 0:
                self._progresso(
                    progresso,
                    10 + int(posicao / total * 65),
                    f"Preparando propostas: {posicao:,}/{len(apontamentos):,}",
                )

        propostas: list[PropostaCorrecaoTributaria] = []
        for candidatas in agrupadas.values():
            propostas.append(self._consolidar(len(propostas) + 1, candidatas))

        propostas.sort(
            key=lambda p: (
                p.modo == "Conflito — escolher valor",
                p.numero_linha or 10**12,
                p.registro,
                p.campo,
            )
        )
        for identificador, proposta in enumerate(propostas, start=1):
            proposta.identificador = identificador

        self._progresso(
            progresso,
            100,
            f"Correção tributária preparada: {len(propostas):,} proposta(s).",
        )
        return ResultadoPreparacaoCorrecaoTributaria(propostas=propostas)

    def atualizar_proposta(
        self,
        resultado: ResultadoPreparacaoCorrecaoTributaria,
        identificador: int,
        valor_novo: str | None = None,
        selecionada: bool | None = None,
    ) -> PropostaCorrecaoTributaria:
        proposta = resultado.obter(identificador)
        if valor_novo is not None:
            if not proposta.editavel:
                raise RuntimeError("Esta proposta não aceita edição direta.")
            if any(caractere in valor_novo for caractere in ("|", "\r", "\n")):
                raise RuntimeError("O valor não pode conter '|', quebra de linha ou retorno de carro.")
            tipo = self.CAMPOS[proposta.campo][3]
            normalizado = self._normalizar_valor(proposta.campo, valor_novo, tipo, validar=True)
            proposta.valor_sugerido = normalizado
            proposta.selecionada = bool(normalizado)
            proposta.modo = "Valor escolhido pela usuária"
            proposta.origem = "DECISÃO DA USUÁRIA"
            proposta.alta_confianca = False
        if selecionada is not None:
            if selecionada and not proposta.aplicavel:
                raise RuntimeError("Escolha um valor válido antes de marcar esta proposta.")
            proposta.selecionada = selecionada
        return proposta

    def aplicar(
        self,
        linhas: list[str],
        encoding: str,
        tipo_sped: str,
        empresa_sped: str,
        auditoria_antes: ResultadoAuditoriaTributaria,
        preparacao: ResultadoPreparacaoCorrecaoTributaria,
        caminho_saida: str | Path,
        importacao_xml: ResultadoImportacaoXMLNFe | None = None,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAplicacaoCorrecaoTributaria:
        selecionadas = preparacao.selecionadas
        if not selecionadas:
            raise RuntimeError("Nenhuma correção tributária foi marcada para aplicar.")

        destino = Path(caminho_saida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            raise FileExistsError(f"O arquivo de destino já existe: {destino}")

        self._progresso(progresso, 5, "Criando nova cópia para correção tributária...")
        novas_linhas = list(linhas)
        aplicadas: list[AlteracaoTributariaAplicada] = []
        total_confirmadas = len(selecionadas)
        total = max(1, total_confirmadas)
        aliquotas_piscofins_afetadas: set[tuple[int, str]] = set()

        for posicao, proposta in enumerate(sorted(selecionadas, key=lambda p: (p.numero_linha or 0, p.indice_campo or 0)), start=1):
            assert proposta.numero_linha is not None and proposta.indice_campo is not None
            indice_linha = proposta.numero_linha - 1
            if indice_linha < 0 or indice_linha >= len(novas_linhas):
                raise RuntimeError(f"Linha {proposta.numero_linha} não existe mais no SPED.")
            if self._codigo(novas_linhas[indice_linha]) != proposta.registro:
                raise RuntimeError(
                    f"A linha {proposta.numero_linha} não corresponde mais ao registro {proposta.registro}."
                )
            anterior = self._obter_campo(novas_linhas[indice_linha], proposta.indice_campo)
            novas_linhas[indice_linha] = CorretorAssistidoPVA._substituir_campo(
                novas_linhas[indice_linha], proposta.indice_campo, proposta.valor_sugerido
            )
            aplicadas.append(
                AlteracaoTributariaAplicada(
                    numero_linha=proposta.numero_linha,
                    registro=proposta.registro,
                    documento=proposta.documento,
                    item=proposta.item,
                    codigo=proposta.codigo,
                    campo=proposta.campo,
                    valor_anterior=anterior,
                    valor_novo=proposta.valor_sugerido,
                    origem=proposta.origem,
                    regra_id=proposta.regra_id,
                    justificativa=proposta.justificativa,
                )
            )
            if proposta.campo == "Alíquota PIS":
                aliquotas_piscofins_afetadas.add((proposta.numero_linha, "PIS"))
            elif proposta.campo == "Alíquota COFINS":
                aliquotas_piscofins_afetadas.add((proposta.numero_linha, "COFINS"))
            if posicao % 100 == 0 or posicao == total:
                self._progresso(
                    progresso,
                    8 + int(posicao / total * 44),
                    f"Aplicando correções: {posicao:,}/{total:,}",
                )

        self._progresso(progresso, 54, "Recalculando valores e totais de PIS/COFINS...")
        recalculo = RecalculadorPISCOFINS().recalcular(
            novas_linhas,
            aliquotas_piscofins_afetadas,
            tipo_sped,
        )
        novas_linhas = recalculo.linhas
        for item in recalculo.alteracoes:
            aplicadas.append(
                AlteracaoTributariaAplicada(
                    numero_linha=item.numero_linha,
                    registro=item.registro,
                    documento="",
                    item="",
                    codigo="",
                    campo=item.campo,
                    valor_anterior=item.valor_anterior,
                    valor_novo=item.valor_novo,
                    origem="RECÁLCULO AUTOMÁTICO",
                    regra_id="DEPENDÊNCIA PIS/COFINS",
                    justificativa=item.justificativa,
                )
            )

        self._progresso(progresso, 62, "Reauditando a cópia com a Ficha Tributária...")
        auditoria_depois = AuditorTributarioSPED().auditar(
            novas_linhas,
            tipo_sped,
            empresa_sped,
            auditoria_antes.contexto,
            importacao_xml,
        )
        self._progresso(progresso, 78, "Executando Pré-Validador PVA na cópia...")
        pre_validacao_depois = PreValidadorPVA().validar(novas_linhas, tipo_sped)

        encoding_saida = CorretorAssistidoPVA._encoding_saida_sem_bom(encoding)
        with destino.open("w", encoding=encoding_saida, newline="") as arquivo:
            arquivo.writelines(novas_linhas)

        relatorio = destino.with_name(f"{destino.stem}_RELATORIO_CORRECAO_TRIBUTARIA.txt")
        self._salvar_relatorio(
            relatorio,
            destino,
            auditoria_antes,
            auditoria_depois,
            pre_validacao_depois,
            aplicadas,
            preparacao,
            recalculo.avisos,
            recalculo.documentos_retotalizados,
            recalculo.requer_reapuracao_bloco_m,
        )
        self._progresso(progresso, 100, "Correção tributária aplicada, reauditada e relatada.")
        return ResultadoAplicacaoCorrecaoTributaria(
            caminho_sped=destino,
            caminho_relatorio=relatorio,
            total_aplicadas=len(aplicadas),
            total_confirmadas=total_confirmadas,
            total_recalculadas=len(recalculo.alteracoes),
            documentos_retotalizados=recalculo.documentos_retotalizados,
            total_ignoradas=len([p for p in preparacao.propostas if not p.selecionada]),
            total_conflitos=len(preparacao.conflitos),
            erros_auditoria_antes=auditoria_antes.erros,
            avisos_auditoria_antes=auditoria_antes.avisos,
            erros_auditoria_depois=auditoria_depois.erros,
            avisos_auditoria_depois=auditoria_depois.avisos,
            erros_pre_pva_depois=len(pre_validacao_depois.erros),
            avisos_pre_pva_depois=len(pre_validacao_depois.avisos),
            avisos_recalculo=tuple(recalculo.avisos),
            requer_reapuracao_bloco_m=recalculo.requer_reapuracao_bloco_m,
            aplicadas=tuple(aplicadas),
            auditoria_depois=auditoria_depois,
            pre_validacao_depois=pre_validacao_depois,
        )

    def _consolidar(self, identificador: int, candidatas: list[_Candidata]) -> PropostaCorrecaoTributaria:
        base = candidatas[0]
        validas = [item for item in candidatas if item.sugerido]
        valores = sorted({item.sugerido for item in validas})
        origens = sorted({item.origem for item in candidatas})
        regra_ids = sorted({item.regra_id for item in candidatas if item.regra_id})
        justificativas = list(dict.fromkeys(item.justificativa for item in candidatas if item.justificativa))
        linha = base.linha or None

        if linha is None:
            return PropostaCorrecaoTributaria(
                identificador=identificador,
                selecionada=False,
                modo="Somente revisão",
                origem=" + ".join(origens),
                nivel="AVISO",
                registro=base.registro,
                numero_linha=None,
                documento=base.documento,
                item=base.item,
                codigo=base.codigo,
                ncm=base.ncm,
                campo=base.campo,
                campo_sped=base.campo_sped,
                valor_atual=base.atual,
                valor_sugerido="",
                regra_id=", ".join(regra_ids),
                aderencia=max((item.aderencia for item in candidatas), default=0),
                justificativa=" ".join(justificativas),
                indice_campo=None,
                editavel=False,
                alta_confianca=False,
                alternativas=tuple(valores),
            )

        if len(valores) != 1:
            alternativas = tuple(valores)
            detalhe = "; ".join(
                f"{item.origem}: {item.sugerido or '(sem valor válido)'}"
                for item in candidatas
            )
            return PropostaCorrecaoTributaria(
                identificador=identificador,
                selecionada=False,
                modo="Conflito — escolher valor",
                origem=" + ".join(origens),
                nivel="ERRO",
                registro=base.registro,
                numero_linha=linha,
                documento=base.documento,
                item=base.item,
                codigo=base.codigo,
                ncm=base.ncm,
                campo=base.campo,
                campo_sped=base.campo_sped,
                valor_atual=base.atual,
                valor_sugerido="",
                regra_id=", ".join(regra_ids),
                aderencia=max((item.aderencia for item in candidatas), default=0),
                justificativa=(
                    "A Ficha Tributária e/ou o XML apresentaram valores diferentes. "
                    f"Escolha manualmente após conferir a base legal. Alternativas: {detalhe}."
                ),
                indice_campo=base.indice,
                editavel=True,
                alta_confianca=False,
                alternativas=alternativas,
            )

        valor = valores[0]
        tem_ficha = "FICHA TRIBUTÁRIA" in origens
        tem_xml = "XML NF-e" in origens
        aderencia = max((item.aderencia for item in candidatas), default=0)
        alta = (tem_ficha and tem_xml) or (tem_xml and len(origens) == 1) or (tem_ficha and aderencia >= 80)
        if tem_ficha and tem_xml:
            modo = "Ficha + XML concordam"
        elif tem_xml:
            modo = "XML autorizado — confirmar"
        elif aderencia >= 80:
            modo = "Regra aderente — confirmar"
        else:
            modo = "Regra genérica — revisar"

        return PropostaCorrecaoTributaria(
            identificador=identificador,
            selecionada=False,
            modo=modo,
            origem=" + ".join(origens),
            nivel=max((item.nivel for item in candidatas), key=lambda n: n == "ERRO", default="AVISO"),
            registro=base.registro,
            numero_linha=linha,
            documento=base.documento,
            item=base.item,
            codigo=base.codigo,
            ncm=base.ncm,
            campo=base.campo,
            campo_sped=base.campo_sped,
            valor_atual=base.atual,
            valor_sugerido=valor,
            regra_id=", ".join(regra_ids),
            aderencia=aderencia,
            justificativa=" ".join(justificativas),
            indice_campo=base.indice,
            editavel=True,
            alta_confianca=alta,
            alternativas=(valor,),
        )

    @classmethod
    def _normalizar_valor(
        cls,
        campo: str,
        valor: object,
        tipo: str,
        validar: bool = False,
    ) -> str:
        texto = str(valor or "").strip().replace("%", "")
        if not texto:
            if validar:
                raise RuntimeError("Informe um valor para a correção.")
            return ""
        if tipo == "codigo":
            digitos = re.sub(r"\D", "", texto)
            tamanhos = cls.TAMANHOS.get(campo)
            if tamanhos and len(digitos) not in tamanhos:
                if validar:
                    esperado = " ou ".join(str(t) for t in sorted(tamanhos))
                    raise RuntimeError(f"{campo} deve possuir {esperado} dígitos.")
                return ""
            return digitos

        bruto = texto.replace(" ", "")
        if "," in bruto:
            bruto = bruto.replace(".", "").replace(",", ".")
        try:
            numero = Decimal(bruto)
        except (InvalidOperation, ValueError):
            if validar:
                raise RuntimeError(f"Informe uma alíquota numérica válida para {campo}.")
            return ""
        if numero < 0 or numero > Decimal("1000"):
            if validar:
                raise RuntimeError(f"A alíquota informada para {campo} está fora do intervalo esperado.")
            return ""
        numero = numero.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        resultado = format(numero, "f").rstrip("0").rstrip(".")
        return (resultado or "0").replace(".", ",")

    @staticmethod
    def _mapear_0200(linhas: Iterable[str]) -> dict[str, list[int]]:
        mapa: dict[str, list[int]] = {}
        for numero, linha in enumerate(linhas, start=1):
            if not linha.startswith("|0200|"):
                continue
            partes = linha.rstrip("\r\n").split("|")
            codigo = partes[2].strip() if len(partes) > 2 else ""
            if codigo:
                mapa.setdefault(codigo, []).append(numero)
        return mapa

    @staticmethod
    def _codigo(linha: str) -> str:
        texto = linha.rstrip("\r\n")
        partes = texto.split("|")
        return partes[1].strip().upper() if texto.startswith("|") and len(partes) > 2 else ""

    @staticmethod
    def _obter_campo(linha: str, indice_campo: int) -> str:
        return CorretorAssistidoPVA._obter_campo(linha, indice_campo)

    @staticmethod
    def _salvar_relatorio(
        caminho: Path,
        sped: Path,
        antes: ResultadoAuditoriaTributaria,
        depois: ResultadoAuditoriaTributaria,
        pre_pva: ResultadoPreValidacaoPVA,
        aplicadas: list[AlteracaoTributariaAplicada],
        preparacao: ResultadoPreparacaoCorrecaoTributaria,
        avisos_recalculo: list[str],
        documentos_retotalizados: int,
        requer_reapuracao_bloco_m: bool,
    ) -> None:
        linhas = [
            "FISCALPRO — CORREÇÃO TRIBUTÁRIA ASSISTIDA",
            "=" * 96,
            f"Gerado em: {datetime.now():%d/%m/%Y %H:%M:%S}",
            f"Nova cópia: {sped}",
            f"Empresa/contexto: {antes.contexto.get('empresa', '')}",
            f"Regime: {antes.contexto.get('regime', '')}",
            f"Finalidade: {antes.contexto.get('finalidade', '')}",
            "",
            "RESUMO",
            "-" * 96,
            f"Ações gravadas no arquivo: {len(aplicadas)}",
            f"Correções confirmadas pela usuária: {len(preparacao.selecionadas)}",
            f"Recálculos dependentes automáticos: {len([a for a in aplicadas if a.origem == 'RECÁLCULO AUTOMÁTICO'])}",
            f"Documentos C100 retotalizados: {documentos_retotalizados}",
            f"Propostas não marcadas: {len([p for p in preparacao.propostas if not p.selecionada])}",
            f"Conflitos aguardando decisão: {len(preparacao.conflitos)}",
            f"Erros da auditoria antes: {antes.erros}",
            f"Avisos da auditoria antes: {antes.avisos}",
            f"Erros da auditoria depois: {depois.erros}",
            f"Avisos da auditoria depois: {depois.avisos}",
            f"Erros do Pré-PVA na cópia: {len(pre_pva.erros)}",
            f"Avisos do Pré-PVA na cópia: {len(pre_pva.avisos)}",
            "",
            "ALTERAÇÕES APLICADAS",
            "-" * 96,
        ]
        if not aplicadas:
            linhas.append("Nenhuma alteração aplicada.")
        for indice, item in enumerate(aplicadas, start=1):
            linhas.extend(
                [
                    f"{indice}. {item.registro} linha {item.numero_linha} | NF {item.documento or '-'} | "
                    f"item {item.item or '-'} | produto {item.codigo or '-'} | {item.campo}",
                    f"   Anterior: {item.valor_anterior}",
                    f"   Novo: {item.valor_novo}",
                    f"   Origem: {item.origem} | Regra: {item.regra_id or '-'}",
                    f"   Motivo: {item.justificativa}",
                    "",
                ]
            )
        linhas.extend(["AVISOS DO RECÁLCULO PIS/COFINS", "-" * 96])
        if not avisos_recalculo:
            linhas.append("Nenhum aviso de recálculo.")
        else:
            for aviso in avisos_recalculo:
                linhas.append(f"- {aviso}")
        if requer_reapuracao_bloco_m:
            linhas.append("- STATUS: REAPURAÇÃO DO BLOCO M OBRIGATÓRIA NO PVA ANTES DA TRANSMISSÃO.")
        linhas.extend(["", "PENDÊNCIAS NÃO APLICADAS", "-" * 96])
        pendentes = [p for p in preparacao.propostas if not p.selecionada]
        if not pendentes:
            linhas.append("Nenhuma proposta pendente.")
        for item in pendentes:
            linhas.append(
                f"[{item.modo}] {item.registro} linha {item.numero_linha or '-'} | produto {item.codigo or '-'} | "
                f"{item.campo}: {item.valor_atual!r} -> {item.valor_sugerido or item.alternativas or '-'}"
            )
        linhas.extend(
            [
                "",
                "IMPORTANTE",
                "- O arquivo original não foi alterado.",
                "- Nenhuma correção fiscal é marcada automaticamente; a seleção depende da usuária.",
                "- Conflitos entre Ficha e XML precisam de decisão após conferência da base legal.",
                "- Alíquotas confirmadas de PIS/COFINS recalculam VL_PIS/VL_COFINS no C170 e os totais do C100.",
                "- O Bloco M não é alterado por aproximação; quando indicado, regenere a apuração no PVA oficial.",
                "- A nova cópia deve ser validada no PVA oficial antes da transmissão.",
            ]
        )
        caminho.write_text("\n".join(linhas), encoding="utf-8")

    @staticmethod
    def _progresso(callback: ProgressoCallback | None, percentual: int, mensagem: str) -> None:
        if callback:
            callback(max(0, min(100, percentual)), mensagem)
