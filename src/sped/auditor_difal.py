"""Auditoria automática de DIFAL/FCP no SPED Fiscal.

Sprint 17.4.0

O módulo cruza C100/C101/C190/C170 com os XMLs de NF-e já importados no
SPED Inteligente. A prioridade é a rastreabilidade:

* XML confirma operação interestadual, consumidor final e condição do IE;
* ICMSUFDest do XML fornece base, alíquotas e valores autorizados;
* C101 é conferido contra os totais da NF-e;
* se o XML confirma consumidor final não contribuinte, o cálculo devido não é bloqueado pelo CFOP;
* quando o XML não traz o cálculo do DIFAL, a memória é calculada pelo FiscalPro; se faltar base/rate no XML, usa C190/C100 como apoio;
* compara a alíquota interestadual do XML com a sugerida pela origem do CST no C190, sem substituir silenciosamente uma pela outra;
* quando houver origens/CST diferentes na mesma NF-e, calcula o cenário SPED por segmento e soma os valores;
* gera memória de cálculo rastreável por C190/CST, com base, origem, alíquotas, fórmula e DIFAL de cada segmento;
* sem XML, CFOP 6107/6108 ou destinatário CPF sem IE permitem uma memória estimada pelo SPED
  e pelas alíquotas vigentes na data da NF-e;
* o cálculo sem XML é sempre marcado como estimado/revisão e nunca altera o SPED.

Nenhuma linha do SPED é alterada nesta sprint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Optional

from .auditor_tributario import DocumentoXMLNFe, ResultadoImportacaoXMLNFe
from src.simulador.tabela_difal import (
    FONTE_TABELA_DIFAL,
    aliquota_interna_destino,
    aliquota_interestadual,
)

ProgressoCallback = Callable[[int, str], None]
CENTAVOS = Decimal("0.01")
TOLERANCIA = Decimal("0.03")
ZERO = Decimal("0")

_UF_POR_PREFIXO_IBGE = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}

CFOPS_NAO_CONTRIBUINTE_FORTES = {"6107", "6108"}


def _texto(valor: Any) -> str:
    return str(valor or "").strip()


def _digitos(valor: Any) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def _decimal(valor: Any) -> Decimal:
    if valor in (None, ""):
        return ZERO
    if isinstance(valor, Decimal):
        return valor
    texto = str(valor).strip().replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        return ZERO


def _dinheiro(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _moeda(valor: Decimal) -> str:
    numero = _dinheiro(valor)
    texto = f"{numero:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _percentual(valor: Any) -> str:
    numero = _decimal(valor)
    texto = format(numero.normalize(), "f") if numero else "0"
    return texto.replace(".", ",") + "%"


@dataclass(slots=True)
class ApontamentoDIFAL:
    nivel: str
    linha: int
    numero: str
    chave: str
    uf_destino: str
    cfops: str
    evidencia: str
    c101_presente: bool
    data_documento: str = ""
    memoria_calculo_sped: str = ""
    segmentos_memoria_sped: list[dict[str, Any]] = field(default_factory=list)
    base_xml: Decimal = ZERO
    aliquota_interna: Decimal = ZERO
    aliquota_interestadual: Decimal = ZERO
    aliquota_interestadual_xml_texto: str = ""
    aliquota_interestadual_sped_texto: str = ""
    difal_sped_origem: Decimal = ZERO
    divergencia_origem: bool = False
    detalhe_origem_sped: str = ""
    aliquota_fcp: Decimal = ZERO
    difal_sped: Decimal = ZERO
    difal_xml: Decimal = ZERO
    fcp_sped: Decimal = ZERO
    fcp_xml: Decimal = ZERO
    origem_calculo: str = ""
    base_calculo: Decimal = ZERO
    difal_devido: Decimal = ZERO
    fcp_devido: Decimal = ZERO
    fcp_calculado: bool = False
    diferenca_difal: Decimal = ZERO
    diferenca_fcp: Decimal = ZERO
    calculo_estimado: bool = False
    fonte_aliquota: str = ""
    mensagem: str = ""
    orientacao: str = ""


@dataclass(slots=True)
class ResultadoAuditoriaDIFAL:
    total_documentos_saida: int = 0
    total_interestaduais: int = 0
    total_xml_localizados: int = 0
    total_xml_ausentes: int = 0
    total_final_nao_contribuinte_confirmado: int = 0
    total_candidatos_sem_xml: int = 0
    total_com_c101: int = 0
    total_sem_c101_quando_confirmado: int = 0
    erros: int = 0
    avisos: int = 0
    ok: int = 0
    valor_difal_sped: Decimal = ZERO
    valor_difal_xml: Decimal = ZERO
    valor_fcp_sped: Decimal = ZERO
    valor_fcp_xml: Decimal = ZERO
    valor_difal_devido: Decimal = ZERO
    valor_fcp_devido: Decimal = ZERO
    total_calculados_sem_xml: int = 0
    total_fcp_nao_calculado_sem_xml: int = 0
    total_divergencias_origem: int = 0
    total_origem_mista_sped: int = 0
    apontamentos: list[ApontamentoDIFAL] = field(default_factory=list)
    uf_origem: str = ""
    empresa: str = ""
    periodo: str = ""
    usou_xml: bool = False

    @property
    def total_apontamentos(self) -> int:
        return len(self.apontamentos)


class AuditorDIFALSPED:
    """Confere DIFAL de saídas interestaduais e o registro C101."""

    def auditar(
        self,
        linhas: list[str],
        tipo_sped: str,
        empresa: str = "",
        periodo: str = "",
        importacao_xml: Optional[ResultadoImportacaoXMLNFe] = None,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAuditoriaDIFAL:
        if tipo_sped != "EFD ICMS/IPI (Fiscal)":
            raise RuntimeError("A auditoria automática de DIFAL funciona somente na EFD ICMS/IPI (SPED Fiscal).")

        uf_origem = self._uf_empresa(linhas)
        if not uf_origem:
            raise RuntimeError("Não foi possível identificar a UF da empresa no registro 0000.")

        participantes = self._participantes(linhas)
        notas = self._notas(linhas)
        xmls = importacao_xml.documentos if importacao_xml is not None else {}
        resultado = ResultadoAuditoriaDIFAL(
            uf_origem=uf_origem,
            empresa=empresa,
            periodo=periodo,
            usou_xml=bool(importacao_xml is not None),
        )

        saidas = [n for n in notas if n["ind_oper"] == "1" and n["modelo"] == "55" and n["situacao"] in {"00", "01"}]
        resultado.total_documentos_saida = len(saidas)
        total = max(1, len(saidas))

        for indice, nota in enumerate(saidas, start=1):
            participante = participantes.get(nota["cod_part"], {})
            uf_destino = _texto(participante.get("uf")).upper()
            chave = _digitos(nota["chave"])
            documento_xml = xmls.get(chave) if chave else None

            if documento_xml is not None:
                resultado.total_xml_localizados += 1
                uf_destino = _texto(documento_xml.uf_destinatario or uf_destino).upper()
            elif importacao_xml is not None:
                resultado.total_xml_ausentes += 1

            interestadual = bool(uf_destino and uf_destino != uf_origem)
            if not interestadual:
                continue
            resultado.total_interestaduais += 1

            cfops = sorted({cfop for cfop in nota["cfops"] if cfop})
            cfops_texto = ", ".join(cfops)
            c101_fcp, c101_difal, c101_rem = self._totais_c101(nota["c101"])
            tem_c101 = bool(nota["c101"])
            if tem_c101:
                resultado.total_com_c101 += 1
                resultado.valor_difal_sped += c101_difal
                resultado.valor_fcp_sped += c101_fcp

            if documento_xml is not None:
                self._auditar_com_xml(
                    resultado, nota, documento_xml, uf_destino, cfops_texto,
                    tem_c101, c101_fcp, c101_difal, c101_rem,
                )
            else:
                self._auditar_sem_xml(
                    resultado, nota, participante, uf_destino, cfops, cfops_texto,
                    tem_c101, c101_fcp, c101_difal,
                )

            percentual = 5 + int(indice / total * 94)
            self._progresso(progresso, percentual, f"Auditando DIFAL: {indice:,}/{len(saidas):,} NF-e(s)...")

        resultado.erros = sum(1 for a in resultado.apontamentos if a.nivel == "ERRO")
        resultado.avisos = sum(1 for a in resultado.apontamentos if a.nivel in {"AVISO", "REVISAR"})
        resultado.ok = sum(1 for a in resultado.apontamentos if a.nivel == "OK")
        resultado.valor_difal_sped = _dinheiro(resultado.valor_difal_sped)
        resultado.valor_difal_xml = _dinheiro(resultado.valor_difal_xml)
        resultado.valor_fcp_sped = _dinheiro(resultado.valor_fcp_sped)
        resultado.valor_fcp_xml = _dinheiro(resultado.valor_fcp_xml)
        resultado.valor_difal_devido = _dinheiro(resultado.valor_difal_devido)
        resultado.valor_fcp_devido = _dinheiro(resultado.valor_fcp_devido)
        self._progresso(progresso, 100, "Auditoria automática de DIFAL concluída.")
        return resultado

    def _auditar_com_xml(
        self,
        resultado: ResultadoAuditoriaDIFAL,
        nota: dict[str, Any],
        xml: DocumentoXMLNFe,
        uf_destino: str,
        cfops_texto: str,
        tem_c101: bool,
        c101_fcp: Decimal,
        c101_difal: Decimal,
        c101_rem: Decimal,
    ) -> None:
        final = bool(xml.consumidor_final)
        nao_contrib = xml.indicador_ie_dest == "9"
        contrib = xml.indicador_ie_dest == "1"
        id_inter = xml.id_destino == "2" or (xml.uf_emitente and xml.uf_destinatario and xml.uf_emitente != xml.uf_destinatario)

        memoria = self._memoria_xml(xml, uf_destino, nota.get("data_documento"))
        difal_xml = memoria["difal_xml"]
        difal_devido = memoria["difal_devido"]
        fcp_xml = memoria["fcp_xml"]
        base_xml = memoria["base_xml"]
        aliq_interna = memoria["aliquota_interna"]
        aliq_interna_xml = memoria["aliquota_interna_xml"]
        aliq_inter = memoria["aliquota_interestadual"]
        aliq_inter_xml_texto = memoria.get("aliquotas_interestadual_texto", "")
        taxas_xml = set(memoria.get("aliquotas_interestadual", tuple()))
        memoria_sped_origem = self._memoria_sped_por_origem(
            resultado.uf_origem, uf_destino, nota, somente_cfop_forte=False
        )
        taxas_sped = set(memoria_sped_origem.get("taxas", tuple())) if memoria_sped_origem.get("calculado") else set()
        aliq_inter_sped_texto = self._texto_taxas(taxas_sped)
        difal_sped_origem = memoria_sped_origem.get("difal", ZERO) if memoria_sped_origem.get("calculado") else ZERO
        detalhe_origem_sped = memoria_sped_origem.get("detalhes", "") if memoria_sped_origem.get("calculado") else ""
        memoria_calculo_sped = memoria_sped_origem.get("memoria_texto", detalhe_origem_sped) if memoria_sped_origem.get("calculado") else ""
        segmentos_memoria_sped = list(memoria_sped_origem.get("segmentos", [])) if memoria_sped_origem.get("calculado") else []
        divergencia_origem = bool(taxas_xml and taxas_sped and taxas_xml != taxas_sped)
        if divergencia_origem:
            resultado.total_divergencias_origem += 1
        if memoria_sped_origem.get("misto"):
            resultado.total_origem_mista_sped += 1
        aliq_fcp = memoria["aliquota_fcp"]
        tem_grupo = memoria["itens_com_grupo"] > 0
        formula_divergente = memoria["formula_divergente"]
        aliquota_divergente = memoria["aliquota_divergente"]
        cfops_xml = {c.strip() for c in str(cfops_texto or "").split(",") if c.strip()}
        cfop_6102 = "6102" in cfops_xml
        # Há XML, mas ele pode não trazer o cálculo do DIFAL.
        # Nessa situação o FiscalPro deve calcular o devido em vez de aceitar zero.
        xml_sem_valor_difal = bool(tem_grupo and difal_devido > TOLERANCIA and difal_xml <= TOLERANCIA)
        xml_sem_memoria_calculavel = bool(
            (not tem_grupo) or base_xml <= ZERO or aliq_interna <= ZERO or aliq_inter <= ZERO
        )

        base_calculo = base_xml
        fcp_devido = fcp_xml
        fcp_calculado = True
        origem_calculo = "XML autorizado"
        fonte_aliquota = "Campos ICMSUFDest da NF-e autorizada"
        calculo_estimado = False

        resultado.valor_difal_xml += difal_xml
        resultado.valor_fcp_xml += fcp_xml
        resultado.valor_difal_devido += difal_devido
        resultado.valor_fcp_devido += fcp_xml

        if final and nao_contrib and id_inter:
            resultado.total_final_nao_contribuinte_confirmado += 1
            evidencia = "XML: idDest=2, indFinal=1, indIEDest=9"
            if aliquota_divergente:
                evidencia += f" | pICMSUFDest XML={aliq_interna_xml}% | modal vigente={aliq_interna}%"
            if xml_sem_memoria_calculavel:
                # O enquadramento do DIFAL vem do destinatário/operação, não do CFOP isolado.
                # Se o XML confirma idDest=2 + indFinal=1 + indIEDest=9, mas não traz memória
                # suficiente do DIFAL, reconstruímos o cálculo pelo SPED, inclusive com CFOP 6102.
                fallback = self._memoria_sped_sem_xml(
                    resultado.uf_origem, uf_destino, nota, somente_cfop_forte=False
                )
                nivel = "REVISAR"
                if fallback["calculado"]:
                    difal_anterior = difal_devido
                    fcp_anterior = fcp_xml
                    base_calculo = fallback["base"]
                    aliq_interna = fallback["aliquota_interna"]
                    aliq_inter = fallback["aliquota_interestadual"]
                    if not aliq_inter_sped_texto:
                        aliq_inter_sped_texto = self._texto_taxas(set(fallback.get("taxas_sped", tuple()))) or (f"{aliq_inter.normalize()}%" if aliq_inter else "")
                    if not detalhe_origem_sped:
                        detalhe_origem_sped = fallback.get("detalhes_origem", "")
                    if not memoria_calculo_sped:
                        memoria_calculo_sped = fallback.get("memoria_texto", detalhe_origem_sped)
                    if not segmentos_memoria_sped:
                        segmentos_memoria_sped = list(fallback.get("segmentos_memoria", []))
                    aliq_fcp = fallback["aliquota_fcp"]
                    difal_devido = fallback["difal"]
                    fcp_devido = fallback["fcp"]
                    fcp_calculado = bool(fallback["fcp_calculado"])
                    origem_calculo = "XML confirma consumidor final + cálculo reconstruído pelo SPED"
                    fonte_aliquota = fallback["fonte"]
                    calculo_estimado = True
                    # Os totais já receberam os valores do XML (normalmente zero neste cenário).
                    resultado.valor_difal_devido += difal_devido - difal_anterior
                    if fcp_calculado:
                        resultado.valor_fcp_devido += fcp_devido - fcp_anterior
                    mensagem = (
                        "NF-e confirma consumidor final não contribuinte, mas não trouxe memória suficiente do DIFAL. "
                        f"O FiscalPro calculou o DIFAL devido pelo SPED em {_moeda(difal_devido)}."
                    )
                    orientacao = (
                        "Cálculo reconstruído pela base/ICMS do C190 (ou C100 como contingência) e pela "
                        "alíquota modal vigente da UF de destino. Confirme benefícios, redução de base e "
                        "alíquota específica do produto antes do recolhimento."
                    )
                    if not fcp_calculado:
                        orientacao += " FCP/FECOP não foi presumido sem regra específica do produto."
                else:
                    mensagem = (
                        "NF-e confirma consumidor final não contribuinte, mas o XML não trouxe memória suficiente do DIFAL "
                        "e o SPED não forneceu base/alíquota suficiente para reconstruir o cálculo."
                    )
                    orientacao = "Confira C190/C100, benefícios e a regra da UF antes de escriturar/recolher o DIFAL."
            elif aliquota_divergente:
                nivel = "REVISAR"
                mensagem = (
                    f"O XML autorizado informa alíquota interna de {aliq_interna_xml}%, mas a alíquota modal vigente "
                    f"para {uf_destino} na data da NF-e é {aliq_interna}%. O FiscalPro recalculou o DIFAL devido "
                    f"pela alíquota modal: {_moeda(difal_devido)} (XML: {_moeda(difal_xml)})."
                )
                orientacao = (
                    "Confirme se a mercadoria possui alíquota específica, redução de base ou benefício fiscal. "
                    "Se não houver exceção, use a alíquota modal vigente e revise a NF-e/C101 antes do recolhimento."
                )
            elif xml_sem_valor_difal:
                origem_calculo = "XML sem DIFAL informado + cálculo FiscalPro"
                fonte_aliquota = FONTE_TABELA_DIFAL
                if not tem_c101:
                    resultado.total_sem_c101_quando_confirmado += 1
                    nivel = "ERRO"
                    mensagem = (
                        "O XML confirma consumidor final não contribuinte, mas não informou valor de DIFAL. "
                        f"O FiscalPro calculou o DIFAL devido em {_moeda(difal_devido)} e não há C101 no SPED."
                    )
                    orientacao = (
                        "O cálculo usa a base/alíquota interestadual disponíveis no XML e a alíquota interna vigente "
                        "da UF de destino. Confirme benefício, redução de base ou alíquota específica antes de escriturar/recolher."
                    )
                elif abs(c101_difal - difal_devido) > TOLERANCIA:
                    nivel = "ERRO"
                    mensagem = (
                        "O XML não informou valor de DIFAL. O FiscalPro calculou o devido em "
                        f"{_moeda(difal_devido)}, mas o C101 informa {_moeda(c101_difal)}."
                    )
                    orientacao = (
                        "Revisar o C101 contra a memória calculada pelo FiscalPro e confirmar benefício, redução de base "
                        "ou alíquota específica da mercadoria antes da correção."
                    )
                else:
                    nivel = "REVISAR"
                    mensagem = (
                        "O XML não informou valor de DIFAL; o FiscalPro calculou o devido e o C101 coincide com a memória apurada."
                    )
                    orientacao = (
                        "O valor foi reconstruído pelo FiscalPro. Confirme a regra específica do produto/UF antes de concluir a auditoria."
                    )
            elif not tem_c101:
                resultado.total_sem_c101_quando_confirmado += 1
                nivel = "ERRO"
                mensagem = "DIFAL/FCP consta no XML da NF-e, porém o C100 não possui registro C101."
                orientacao = "Escriturar o C101 com os totais do XML autorizado, após confirmar a regra estadual aplicável."
            elif abs(c101_difal - difal_devido) > TOLERANCIA or abs(c101_fcp - fcp_xml) > TOLERANCIA:
                nivel = "ERRO"
                mensagem = "Os valores do C101 divergem do DIFAL devido apurado e/ou dos totais de FCP do XML autorizado."
                orientacao = "Conferir VL_FCP_UF_DEST e VL_ICMS_UF_DEST do C101 contra a NF-e e a alíquota interna vigente."
            elif c101_rem.copy_abs() > TOLERANCIA:
                nivel = "AVISO"
                mensagem = "C101 possui valor para a UF remetente; em operações atuais esse campo normalmente deve permanecer zerado."
                orientacao = "Confirme a situação específica e a regra do período antes de alterar."
            elif formula_divergente:
                nivel = "AVISO"
                mensagem = "C101 coincide com o XML, mas a memória simples dos campos ICMSUFDest divergiu do valor declarado."
                orientacao = "Pode existir redução/base especial. Revise a tributação da UF de destino antes do recolhimento."
            else:
                nivel = "OK"
                mensagem = "C101 confere com o grupo ICMSUFDest do XML autorizado."
                orientacao = "Nenhuma divergência documental encontrada para DIFAL/FCP."
        elif final and contrib and id_inter:
            evidencia = "XML: consumidor final contribuinte (indIEDest=1)"
            nivel = "REVISAR"
            mensagem = "Operação interestadual para consumidor final contribuinte: o responsável e a forma de escrituração exigem análise própria."
            orientacao = "O C101 desta rotina é voltado ao consumidor final não contribuinte. Confira a obrigação do destinatário e a legislação estadual."
        elif final and xml.indicador_ie_dest == "2" and id_inter:
            evidencia = "XML: consumidor final com IE isenta (indIEDest=2)"
            nivel = "REVISAR"
            mensagem = "A condição de contribuinte do destinatário não pode ser concluída apenas pelo indicador de IE isenta."
            orientacao = "Confirme a condição fiscal do destinatário e o responsável pelo DIFAL."
        else:
            evidencia = "XML não confirma consumidor final não contribuinte"
            if tem_c101 and (c101_difal.copy_abs() > TOLERANCIA or c101_fcp.copy_abs() > TOLERANCIA):
                nivel = "AVISO"
                mensagem = "Há C101 com valores, mas o XML não caracteriza a operação como consumidor final não contribuinte."
                orientacao = "Revise indFinal, indIEDest, idDest e a natureza da operação."
            else:
                return

        if final and nao_contrib and id_inter and memoria_sped_origem.get("misto"):
            evidencia += f" | SPED/CST com origens mistas: {aliq_inter_sped_texto or '-'}"
            orientacao += (
                " O cenário SPED foi calculado por segmento C190/CST e somado no final, sem aplicar uma única "
                "alíquota interestadual sobre toda a base."
            )
            if nivel == "OK":
                nivel = "REVISAR"

        if final and nao_contrib and id_inter and divergencia_origem:
            evidencia += (
                f" | ORIGEM DIVERGENTE: XML {aliq_inter_xml_texto or '-'} × SPED/CST {aliq_inter_sped_texto or '-'}"
            )
            mensagem += (
                f" Divergência de alíquota interestadual: o XML informa {aliq_inter_xml_texto or '-'}, "
                f"enquanto a origem/CST escriturada no C190 sugere {aliq_inter_sped_texto or '-'}. "
                f"Cenário calculado pela origem do SPED: {_moeda(difal_sped_origem)}."
            )
            orientacao += (
                " Revisar a origem real da mercadoria/FCI e a escrituração do CST antes de escolher 4%, 7% ou 12%. "
                "O FiscalPro mantém os dois cenários e não substitui automaticamente o XML ou o SPED."
            )
            if nivel in {"OK", "AVISO"}:
                nivel = "REVISAR"

        if final and nao_contrib and id_inter and cfop_6102:
            evidencia += " | CFOP 6102 — cálculo não bloqueado"
            aviso_cfop = (
                " CFOP 6.102 identificado em operação que o XML confirma como interestadual para "
                "consumidor final não contribuinte; revisar o enquadramento do CFOP separadamente."
            )
            if aviso_cfop.strip() not in mensagem:
                mensagem += aviso_cfop
            orientacao += " O CFOP não zera o DIFAL; revise a natureza da operação sem descartar o imposto devido."
            if nivel == "OK":
                nivel = "REVISAR"

        resultado.apontamentos.append(
            ApontamentoDIFAL(
                nivel=nivel,
                linha=nota["linha"], numero=nota["numero"], chave=nota["chave"],
                uf_destino=uf_destino, cfops=cfops_texto, evidencia=evidencia,
                c101_presente=tem_c101, data_documento=_texto(nota.get("data_documento")),
                memoria_calculo_sped=memoria_calculo_sped, segmentos_memoria_sped=segmentos_memoria_sped,
                base_xml=base_xml, base_calculo=base_calculo,
                aliquota_interna=aliq_interna, aliquota_interestadual=aliq_inter,
                aliquota_interestadual_xml_texto=aliq_inter_xml_texto,
                aliquota_interestadual_sped_texto=aliq_inter_sped_texto,
                difal_sped_origem=difal_sped_origem, divergencia_origem=divergencia_origem,
                detalhe_origem_sped=detalhe_origem_sped,
                aliquota_fcp=aliq_fcp, difal_sped=c101_difal, difal_xml=difal_xml,
                fcp_sped=c101_fcp, fcp_xml=fcp_xml,
                origem_calculo=(
                    origem_calculo if (calculo_estimado or xml_sem_valor_difal)
                    else ("XML + alíquota modal vigente" if aliquota_divergente else origem_calculo)
                ),
                difal_devido=difal_devido, fcp_devido=fcp_devido, fcp_calculado=fcp_calculado,
                diferenca_difal=_dinheiro(c101_difal - difal_devido),
                diferenca_fcp=(_dinheiro(c101_fcp - fcp_devido) if fcp_calculado else ZERO),
                calculo_estimado=calculo_estimado,
                fonte_aliquota=(FONTE_TABELA_DIFAL if aliquota_divergente else fonte_aliquota),
                mensagem=mensagem, orientacao=orientacao,
            )
        )

    def _auditar_sem_xml(
        self,
        resultado: ResultadoAuditoriaDIFAL,
        nota: dict[str, Any],
        participante: dict[str, str],
        uf_destino: str,
        cfops: list[str],
        cfops_texto: str,
        tem_c101: bool,
        c101_fcp: Decimal,
        c101_difal: Decimal,
    ) -> None:
        cfop_forte = any(cfop in CFOPS_NAO_CONTRIBUINTE_FORTES for cfop in cfops)
        cpf_destinatario = _digitos(participante.get("cpf"))
        ie_destinatario = _texto(participante.get("ie"))
        cpf_sem_ie = len(cpf_destinatario) == 11 and not ie_destinatario
        forte = cfop_forte or cpf_sem_ie
        if not forte and not tem_c101:
            return

        if cfop_forte:
            resultado.total_candidatos_sem_xml += 1
            evidencia = "CFOP 6107/6108 — operação destinada a não contribuinte"
        elif cpf_sem_ie:
            resultado.total_candidatos_sem_xml += 1
            evidencia = "SPED 0150: destinatário CPF sem IE — candidato a consumidor final não contribuinte"
            if "6102" in cfops:
                evidencia += " | CFOP 6102 — cálculo não bloqueado"
        else:
            evidencia = "C101 existente sem XML importado"

        # Com CPF sem IE, o destinatário é forte evidência mesmo que o CFOP seja 6102.
        # Nesse caso não filtramos o C190 apenas para 6107/6108.
        memoria = self._memoria_sped_sem_xml(
            resultado.uf_origem, uf_destino, nota, somente_cfop_forte=(cfop_forte and not cpf_sem_ie)
        )
        base = memoria["base"]
        interna = memoria["aliquota_interna"]
        inter = memoria["aliquota_interestadual"]
        difal_devido = memoria["difal"]
        fcp_devido = memoria["fcp"]
        fcp_calculado = bool(memoria["fcp_calculado"])
        origem_calculo = memoria["origem"]
        fonte = memoria["fonte"]
        taxas_sped = set(memoria.get("taxas_sped", tuple()))
        aliq_inter_sped_texto = self._texto_taxas(taxas_sped) or (f"{inter.normalize()}%" if inter else "")
        detalhe_origem_sped = memoria.get("detalhes_origem", "")
        memoria_calculo_sped = memoria.get("memoria_texto", detalhe_origem_sped)
        segmentos_memoria_sped = list(memoria.get("segmentos_memoria", []))
        if memoria.get("origem_mista"):
            resultado.total_origem_mista_sped += 1
        resultado.total_calculados_sem_xml += 1 if memoria["calculado"] else 0
        if not fcp_calculado:
            resultado.total_fcp_nao_calculado_sem_xml += 1
        resultado.valor_difal_devido += difal_devido
        if fcp_calculado:
            resultado.valor_fcp_devido += fcp_devido

        diff_difal = _dinheiro(c101_difal - difal_devido)
        diff_fcp = _dinheiro(c101_fcp - fcp_devido) if fcp_calculado else ZERO

        if memoria["calculado"]:
            nivel = "REVISAR"
            if tem_c101 and abs(diff_difal) <= TOLERANCIA:
                mensagem = (
                    "Sem XML, o C101 coincide com o cálculo reconstruído pelo SPED dentro da tolerância; "
                    "o enquadramento ainda precisa de confirmação documental."
                )
            elif tem_c101:
                mensagem = (
                    f"Sem XML, o C101 diverge do cálculo reconstruído pelo SPED em {_moeda(diff_difal.copy_abs())}."
                )
            else:
                mensagem = (
                    f"Sem XML e sem C101. DIFAL devido estimado pelo SPED: {_moeda(difal_devido)}."
                )
            orientacao = (
                "Cálculo estimado pela base/aliquota do C190 (ou C100 como contingência) e pela alíquota modal "
                "vigente da UF de destino. Confirme XML, benefícios, redução de base e alíquota específica do produto."
            )
            if cpf_sem_ie and "6102" in cfops:
                orientacao += (
                    " O destinatário consta como CPF sem IE; por isso o CFOP 6.102 não bloqueou o cálculo. "
                    "Revise o CFOP da operação separadamente."
                )
            if not fcp_calculado:
                orientacao += " FCP/FECOP não foi presumido sem regra específica do produto; revisar separadamente."
            if memoria.get("origem_mista"):
                mensagem += f" A NF-e possui origens/CST distintas no C190 ({aliq_inter_sped_texto}); o cálculo foi feito por segmento e somado."
                orientacao += " Não foi aplicada uma alíquota interestadual única à base total."
        else:
            nivel = "REVISAR"
            mensagem = "Não foi possível reconstruir uma base/rate confiável para calcular o DIFAL sem XML."
            orientacao = "Importe o XML ou revise os registros C170/C190/C100 e a regra da UF de destino."

        resultado.apontamentos.append(
            ApontamentoDIFAL(
                nivel=nivel,
                linha=nota["linha"],
                numero=nota["numero"],
                chave=nota["chave"],
                uf_destino=uf_destino,
                cfops=cfops_texto,
                evidencia=evidencia,
                c101_presente=tem_c101,
                data_documento=_texto(nota.get("data_documento")),
                memoria_calculo_sped=memoria_calculo_sped,
                segmentos_memoria_sped=segmentos_memoria_sped,
                base_calculo=base,
                aliquota_interna=interna,
                aliquota_interestadual=inter,
                aliquota_interestadual_xml_texto="",
                aliquota_interestadual_sped_texto=aliq_inter_sped_texto,
                difal_sped_origem=difal_devido,
                divergencia_origem=False,
                detalhe_origem_sped=detalhe_origem_sped,
                aliquota_fcp=memoria["aliquota_fcp"],
                difal_sped=c101_difal,
                fcp_sped=c101_fcp,
                origem_calculo=origem_calculo,
                difal_devido=difal_devido,
                fcp_devido=fcp_devido,
                fcp_calculado=fcp_calculado,
                diferenca_difal=diff_difal,
                diferenca_fcp=diff_fcp,
                calculo_estimado=True,
                fonte_aliquota=fonte,
                mensagem=mensagem,
                orientacao=orientacao,
            )
        )

    @staticmethod
    def _texto_taxas(taxas: set[Decimal] | tuple[Decimal, ...] | list[Decimal]) -> str:
        valores = sorted({_decimal(v) for v in taxas if _decimal(v) > ZERO})
        if not valores:
            return ""
        return " / ".join(f"{v.normalize()}%" for v in valores)

    @staticmethod
    def _origem_cst(cst: Any) -> str:
        codigo = _digitos(cst)
        return codigo[0] if len(codigo) >= 3 else ""

    @staticmethod
    def _memoria_sped_por_origem(
        uf_origem: str,
        uf_destino: str,
        nota: dict[str, Any],
        somente_cfop_forte: bool = False,
    ) -> dict[str, Any]:
        """Monta o cenário SPED/CST e a memória de cálculo por C190.

        A origem 1/2/3/8 sinaliza o cenário de 4% da Resolução do Senado
        13/2012; as demais origens usam a alíquota interestadual normal da
        rota. A memória é de auditoria e não substitui silenciosamente o XML.
        """
        data_doc = nota.get("data_documento") or ""
        try:
            interna = aliquota_interna_destino(uf_destino, data_doc)
        except Exception:
            interna = ZERO

        segmentos: list[dict[str, Any]] = []
        for grupo in nota.get("c190", []):
            cfop = _digitos(grupo.get("cfop"))
            if somente_cfop_forte and cfop not in CFOPS_NAO_CONTRIBUINTE_FORTES:
                continue
            if not somente_cfop_forte and not cfop.startswith("6"):
                continue
            base = _decimal(grupo.get("vl_opr"))
            if base <= ZERO:
                base = _decimal(grupo.get("vl_bc_icms"))
            cst = _digitos(grupo.get("cst"))
            origem = AuditorDIFALSPED._origem_cst(cst)
            if base <= ZERO or not origem:
                continue
            cenario_4 = origem in {"1", "2", "3", "8"}
            try:
                aliq = _decimal(aliquota_interestadual(uf_origem, uf_destino, cenario_4))
            except Exception:
                aliq = ZERO
            if aliq <= ZERO or interna <= ZERO:
                continue
            diferenca = max(ZERO, interna - aliq)
            difal_segmento = _dinheiro(base * diferenca / Decimal("100"))
            segmentos.append({
                "cst": cst,
                "origem": origem,
                "cfop": cfop,
                "linha_c190": int(grupo.get("linha") or 0),
                "base": _dinheiro(base),
                "aliquota_c190": _decimal(grupo.get("aliquota")),
                "aliquota_interna": interna,
                "aliquota_interestadual": aliq,
                "diferenca_aliquotas": diferenca,
                "difal": difal_segmento,
                "cenario_4": cenario_4,
                "formula": (
                    f"{_moeda(base)} × ({_percentual(interna)} - {_percentual(aliq)}) "
                    f"= {_moeda(difal_segmento)}"
                ),
                "fonte": "C190/CST — origem da mercadoria + alíquota interna vigente da UF/data",
            })

        if not segmentos or interna <= ZERO:
            return {
                "calculado": False, "base": ZERO, "aliquota_interna": interna,
                "aliquota_interestadual": ZERO, "taxas": tuple(), "difal": ZERO,
                "misto": False, "detalhes": "", "memoria_texto": "", "segmentos": [],
                "fonte": "CST/C190 — origem da mercadoria (memória de auditoria)",
            }

        base_total = sum((_decimal(seg["base"]) for seg in segmentos), ZERO)
        icms_origem = sum(
            (_decimal(seg["base"]) * _decimal(seg["aliquota_interestadual"]) / Decimal("100") for seg in segmentos),
            ZERO,
        )
        difal = sum((_decimal(seg["difal"]) for seg in segmentos), ZERO)
        taxas = tuple(sorted({_decimal(seg["aliquota_interestadual"]) for seg in segmentos}))
        inter_media = _dinheiro(icms_origem / base_total * Decimal("100")) if base_total else ZERO

        partes = []
        for seg in segmentos:
            partes.append(
                f"CST {seg['cst'] or '?'} origem {seg['origem'] or '?'} / CFOP {seg['cfop'] or '-'}: "
                f"{seg['formula']}"
            )
        memoria_texto = "; ".join(partes)

        return {
            "calculado": True,
            "base": _dinheiro(base_total),
            "aliquota_interna": interna,
            "aliquota_interestadual": inter_media,
            "taxas": taxas,
            "difal": _dinheiro(difal),
            "misto": len(taxas) > 1,
            "detalhes": memoria_texto,
            "memoria_texto": memoria_texto,
            "segmentos": segmentos,
            "fonte": "CST/C190 + regra interestadual por origem; cenário para conferência, não substituição automática",
        }

    @staticmethod
    def _memoria_sped_sem_xml(
        uf_origem: str,
        uf_destino: str,
        nota: dict[str, Any],
        somente_cfop_forte: bool,
    ) -> dict[str, Any]:
        data_doc = nota.get("data_documento") or ""
        try:
            interna = aliquota_interna_destino(uf_destino, data_doc)
        except Exception:
            interna = ZERO

        por_origem = AuditorDIFALSPED._memoria_sped_por_origem(
            uf_origem, uf_destino, nota, somente_cfop_forte=somente_cfop_forte
        )
        if por_origem["calculado"]:
            return {
                "calculado": True,
                "base": por_origem["base"],
                "aliquota_interna": por_origem["aliquota_interna"],
                "aliquota_interestadual": por_origem["aliquota_interestadual"],
                "aliquota_fcp": ZERO,
                "difal": por_origem["difal"],
                "fcp": ZERO,
                "fcp_calculado": False,
                "origem": "SPED C190 por origem/CST",
                "fonte": por_origem["fonte"],
                "taxas_sped": por_origem["taxas"],
                "detalhes_origem": por_origem["detalhes"],
                "memoria_texto": por_origem.get("memoria_texto", por_origem["detalhes"]),
                "segmentos_memoria": list(por_origem.get("segmentos", [])),
                "origem_mista": por_origem["misto"],
            }

        grupos: list[dict[str, Any]] = []
        for grupo in nota.get("c190", []):
            cfop = _digitos(grupo.get("cfop"))
            if somente_cfop_forte and cfop not in CFOPS_NAO_CONTRIBUINTE_FORTES:
                continue
            if not somente_cfop_forte and not cfop.startswith("6"):
                continue
            base = _decimal(grupo.get("vl_opr"))
            if base <= ZERO:
                base = _decimal(grupo.get("vl_bc_icms"))
            aliq = _decimal(grupo.get("aliquota"))
            if base > ZERO and aliq > ZERO:
                grupos.append({
                    "base": base, "aliquota": aliq, "cst": _digitos(grupo.get("cst")),
                    "origem": AuditorDIFALSPED._origem_cst(grupo.get("cst")), "cfop": cfop,
                    "linha_c190": int(grupo.get("linha") or 0),
                    "aliquota_c190": aliq, "fonte": "C190 — alíquota escriturada (contingência)",
                })

        origem = "SPED C190"
        if not grupos:
            base = _decimal(nota.get("valor_documento"))
            if base > ZERO and interna > ZERO:
                try:
                    aliq = aliquota_interestadual(uf_origem, uf_destino, False)
                except Exception:
                    aliq = ZERO
                if aliq > ZERO:
                    grupos = [{
                        "base": base, "aliquota": aliq, "cst": "", "origem": "",
                        "cfop": ",".join(sorted({_digitos(c) for c in nota.get("cfops", []) if _digitos(c)})),
                        "linha_c190": 0, "aliquota_c190": ZERO, "fonte": "C100 — base contingencial",
                    }]
                    origem = "SPED C100 — base contingencial"

        if not grupos or interna <= ZERO:
            return {
                "calculado": False,
                "base": ZERO,
                "aliquota_interna": interna,
                "aliquota_interestadual": ZERO,
                "aliquota_fcp": ZERO,
                "difal": ZERO,
                "fcp": ZERO,
                "fcp_calculado": False,
                "origem": origem,
                "fonte": FONTE_TABELA_DIFAL,
                "taxas_sped": tuple(),
                "detalhes_origem": "",
                "memoria_texto": "",
                "segmentos_memoria": [],
                "origem_mista": False,
            }

        segmentos_memoria: list[dict[str, Any]] = []
        for grupo in grupos:
            base = _decimal(grupo["base"])
            aliq = _decimal(grupo["aliquota"])
            diferenca = max(ZERO, interna - aliq)
            difal_segmento = _dinheiro(base * diferenca / Decimal("100"))
            segmentos_memoria.append({
                "cst": grupo.get("cst", ""), "origem": grupo.get("origem", ""),
                "cfop": grupo.get("cfop", ""), "linha_c190": int(grupo.get("linha_c190") or 0),
                "base": _dinheiro(base),
                "aliquota_c190": _decimal(grupo.get("aliquota_c190")),
                "aliquota_interna": interna, "aliquota_interestadual": aliq,
                "diferenca_aliquotas": diferenca, "difal": difal_segmento,
                "cenario_4": False,
                "formula": f"{_moeda(base)} × ({_percentual(interna)} - {_percentual(aliq)}) = {_moeda(difal_segmento)}",
                "fonte": grupo.get("fonte", origem),
            })

        base_total = sum((_decimal(seg["base"]) for seg in segmentos_memoria), ZERO)
        icms_origem = sum(
            (_decimal(seg["base"]) * _decimal(seg["aliquota_interestadual"]) / Decimal("100") for seg in segmentos_memoria),
            ZERO,
        )
        difal = _dinheiro(sum((_decimal(seg["difal"]) for seg in segmentos_memoria), ZERO))
        inter_media = _dinheiro(icms_origem / base_total * Decimal("100")) if base_total else ZERO
        memoria_texto = "; ".join(
            f"CST {seg.get('cst') or '?'} origem {seg.get('origem') or '?'} / CFOP {seg.get('cfop') or '-'}: {seg['formula']}"
            for seg in segmentos_memoria
        )

        # Sem XML/NCM, não se presume FCP/FECOP: o adicional varia por UF/produto.
        # Exceção operacional segura para AL após 01/04/2026: FECOEP geral de 1%
        # nas operações de DIFAL abrangidas pela regra modal; ainda marcado como estimado.
        fcp_calculado = False
        aliquota_fcp = ZERO
        fcp = ZERO
        if uf_destino == "AL" and interna == Decimal("20.5"):
            aliquota_fcp = Decimal("1")
            fcp = _dinheiro(base_total * aliquota_fcp / Decimal("100"))
            fcp_calculado = True

        return {
            "calculado": True,
            "base": _dinheiro(base_total),
            "aliquota_interna": interna,
            "aliquota_interestadual": inter_media,
            "aliquota_fcp": aliquota_fcp,
            "difal": difal,
            "fcp": fcp,
            "fcp_calculado": fcp_calculado,
            "origem": origem,
            "fonte": FONTE_TABELA_DIFAL,
            "taxas_sped": tuple(sorted({_decimal(seg["aliquota_interestadual"]) for seg in segmentos_memoria})),
            "detalhes_origem": memoria_texto,
            "memoria_texto": memoria_texto,
            "segmentos_memoria": segmentos_memoria,
            "origem_mista": len({_decimal(seg["aliquota_interestadual"]) for seg in segmentos_memoria}) > 1,
        }


    @staticmethod
    def _memoria_xml(
        xml: DocumentoXMLNFe,
        uf_destino: str = "",
        data_referencia: Any = None,
    ) -> dict[str, Any]:
        base_total = ZERO
        difal_xml = ZERO
        difal_devido = ZERO
        fcp_xml = ZERO
        aliq_interna_xml: set[Decimal] = set()
        aliq_inter: set[Decimal] = set()
        base_por_inter: dict[Decimal, Decimal] = {}
        aliq_fcp: set[Decimal] = set()
        itens_com_grupo = 0
        formula_divergente = False

        try:
            aliquota_modal = aliquota_interna_destino(uf_destino, data_referencia) if uf_destino else ZERO
        except Exception:
            aliquota_modal = ZERO

        for item in xml.itens:
            if not item.tem_icms_uf_dest:
                continue
            itens_com_grupo += 1
            base = _decimal(item.base_difal)
            base_fcp = _decimal(item.base_fcp_difal) or base
            p_interna_xml = _decimal(item.aliquota_icms_destino)
            p_inter = _decimal(item.aliquota_icms_interestadual)
            partilha = _decimal(item.percentual_partilha_destino) or Decimal("100")
            p_fcp = _decimal(item.aliquota_fcp_destino)
            v_difal = _decimal(item.valor_icms_destino)
            v_fcp = _decimal(item.valor_fcp_destino)

            base_total += base
            difal_xml += v_difal
            fcp_xml += v_fcp
            if p_interna_xml:
                aliq_interna_xml.add(p_interna_xml)
            if p_inter:
                aliq_inter.add(p_inter)
                base_por_inter[p_inter] = base_por_inter.get(p_inter, ZERO) + base
            if p_fcp:
                aliq_fcp.add(p_fcp)

            # O DIFAL devido usa a alíquota modal vigente da UF/data.
            # Se houver alíquota específica/benefício, a divergência fica em REVISAR.
            p_interna_devida = aliquota_modal or p_interna_xml
            if base > ZERO and p_interna_devida > ZERO and p_inter >= ZERO:
                devido_item = _dinheiro(
                    max(ZERO, base * (p_interna_devida - p_inter) / Decimal("100") * partilha / Decimal("100"))
                )
                difal_devido += devido_item
            else:
                difal_devido += v_difal

            if base > ZERO and p_interna_xml > ZERO and p_inter >= ZERO:
                calculado_xml = _dinheiro(
                    max(ZERO, base * (p_interna_xml - p_inter) / Decimal("100") * partilha / Decimal("100"))
                )
                if abs(calculado_xml - _dinheiro(v_difal)) > Decimal("0.05"):
                    formula_divergente = True
            if base_fcp > ZERO and p_fcp > ZERO:
                fcp_calc = _dinheiro(base_fcp * p_fcp / Decimal("100"))
                if abs(fcp_calc - _dinheiro(v_fcp)) > Decimal("0.05"):
                    formula_divergente = True

        aliq_xml_unica = next(iter(aliq_interna_xml)) if len(aliq_interna_xml) == 1 else ZERO
        aliquota_divergente = bool(
            aliquota_modal > ZERO
            and aliq_interna_xml
            and any(abs(a - aliquota_modal) > Decimal("0.001") for a in aliq_interna_xml)
        )

        inter_ponderada = ZERO
        if base_total > ZERO and base_por_inter:
            inter_ponderada = _dinheiro(
                sum((base * aliq / Decimal("100") for aliq, base in base_por_inter.items()), ZERO)
                / base_total * Decimal("100")
            )

        return {
            "base_xml": _dinheiro(base_total),
            "difal_xml": _dinheiro(difal_xml),
            "difal_devido": _dinheiro(difal_devido),
            "fcp_xml": _dinheiro(fcp_xml),
            "aliquota_interna": aliquota_modal or aliq_xml_unica,
            "aliquota_interna_xml": aliq_xml_unica,
            "aliquota_interestadual": next(iter(aliq_inter)) if len(aliq_inter) == 1 else inter_ponderada,
            "aliquotas_interestadual": tuple(sorted(aliq_inter)),
            "aliquotas_interestadual_texto": AuditorDIFALSPED._texto_taxas(aliq_inter),
            "aliquota_fcp": next(iter(aliq_fcp)) if len(aliq_fcp) == 1 else ZERO,
            "itens_com_grupo": itens_com_grupo,
            "formula_divergente": formula_divergente,
            "aliquota_divergente": aliquota_divergente,
        }

    @staticmethod
    def _uf_empresa(linhas: list[str]) -> str:
        for linha in linhas:
            if linha.startswith("|0000|"):
                campos = linha.rstrip("\r\n").split("|")
                return _texto(campos[9] if len(campos) > 9 else "").upper()
        return ""

    @staticmethod
    def _participantes(linhas: list[str]) -> dict[str, dict[str, str]]:
        participantes: dict[str, dict[str, str]] = {}
        for linha in linhas:
            if not linha.startswith("|0150|"):
                continue
            campos = linha.rstrip("\r\n").split("|")
            codigo = _texto(campos[2] if len(campos) > 2 else "")
            cod_mun = _digitos(campos[8] if len(campos) > 8 else "")
            participantes[codigo] = {
                "cnpj": _digitos(campos[5] if len(campos) > 5 else ""),
                "cpf": _digitos(campos[6] if len(campos) > 6 else ""),
                "ie": _texto(campos[7] if len(campos) > 7 else ""),
                "uf": _UF_POR_PREFIXO_IBGE.get(cod_mun[:2], ""),
            }
        return participantes

    @staticmethod
    def _notas(linhas: list[str]) -> list[dict[str, Any]]:
        notas: list[dict[str, Any]] = []
        atual: Optional[dict[str, Any]] = None
        for numero_linha, linha in enumerate(linhas, start=1):
            if linha.startswith("|C100|"):
                campos = linha.rstrip("\r\n").split("|")
                atual = {
                    "linha": numero_linha,
                    "ind_oper": _texto(campos[2] if len(campos) > 2 else ""),
                    "ind_emit": _texto(campos[3] if len(campos) > 3 else ""),
                    "cod_part": _texto(campos[4] if len(campos) > 4 else ""),
                    "modelo": _texto(campos[5] if len(campos) > 5 else ""),
                    "situacao": _texto(campos[6] if len(campos) > 6 else ""),
                    "serie": _texto(campos[7] if len(campos) > 7 else ""),
                    "numero": _texto(campos[8] if len(campos) > 8 else ""),
                    "chave": _digitos(campos[9] if len(campos) > 9 else ""),
                    "data_documento": _texto(campos[10] if len(campos) > 10 else ""),
                    "valor_documento": _decimal(campos[12] if len(campos) > 12 else ""),
                    "cfops": [],
                    "c190": [],
                    "c101": [],
                }
                notas.append(atual)
            elif atual is not None and linha.startswith("|C170|"):
                campos = linha.rstrip("\r\n").split("|")
                cfop = _digitos(campos[11] if len(campos) > 11 else "")
                if cfop:
                    atual["cfops"].append(cfop)
            elif atual is not None and linha.startswith("|C190|"):
                campos = linha.rstrip("\r\n").split("|")
                cfop = _digitos(campos[3] if len(campos) > 3 else "")
                if cfop:
                    atual["cfops"].append(cfop)
                atual["c190"].append(
                    {
                        "linha": numero_linha,
                        "cst": _texto(campos[2] if len(campos) > 2 else ""),
                        "cfop": cfop,
                        "aliquota": _decimal(campos[4] if len(campos) > 4 else ""),
                        "vl_opr": _decimal(campos[5] if len(campos) > 5 else ""),
                        "vl_bc_icms": _decimal(campos[6] if len(campos) > 6 else ""),
                    }
                )
            elif atual is not None and linha.startswith("|C101|"):
                campos = linha.rstrip("\r\n").split("|")
                atual["c101"].append(
                    {
                        "linha": numero_linha,
                        "fcp": _decimal(campos[2] if len(campos) > 2 else ""),
                        "difal": _decimal(campos[3] if len(campos) > 3 else ""),
                        "rem": _decimal(campos[4] if len(campos) > 4 else ""),
                    }
                )
        return notas

    @staticmethod
    def _totais_c101(registros: list[dict[str, Any]]) -> tuple[Decimal, Decimal, Decimal]:
        fcp = sum((_decimal(r.get("fcp")) for r in registros), ZERO)
        difal = sum((_decimal(r.get("difal")) for r in registros), ZERO)
        rem = sum((_decimal(r.get("rem")) for r in registros), ZERO)
        return _dinheiro(fcp), _dinheiro(difal), _dinheiro(rem)

    def salvar_relatorio(
        self,
        resultado: ResultadoAuditoriaDIFAL,
        caminho_saida: str | Path,
        caminho_sped: str | Path | None = None,
    ) -> Path:
        destino = Path(caminho_saida)
        linhas = [
            "FISCALPRO — AUDITORIA AUTOMÁTICA DE DIFAL/FCP — SPRINT 17.4.0",
            "=" * 84,
            f"Empresa: {resultado.empresa or '-'}",
            f"Período: {resultado.periodo or '-'}",
            f"UF de origem: {resultado.uf_origem or '-'}",
            f"SPED: {Path(caminho_sped).name if caminho_sped else '-'}",
            f"XMLs usados: {'SIM' if resultado.usou_xml else 'NÃO'}",
            "",
            "RESUMO",
            "-" * 84,
            f"NF-e de saída analisáveis: {resultado.total_documentos_saida}",
            f"NF-e interestaduais: {resultado.total_interestaduais}",
            f"XMLs localizados por chave: {resultado.total_xml_localizados}",
            f"XMLs ausentes no lote importado: {resultado.total_xml_ausentes}",
            f"Consumidor final não contribuinte confirmado pelo XML: {resultado.total_final_nao_contribuinte_confirmado}",
            f"Candidatos por CFOP 6107/6108 sem XML: {resultado.total_candidatos_sem_xml}",
            f"Documentos com C101: {resultado.total_com_c101}",
            f"Confirmados pelo XML sem C101: {resultado.total_sem_c101_quando_confirmado}",
            f"Erros: {resultado.erros} | Avisos/Revisões: {resultado.avisos} | OK: {resultado.ok}",
            f"DIFAL no SPED (C101): {_moeda(resultado.valor_difal_sped)}",
            f"DIFAL nos XMLs localizados: {_moeda(resultado.valor_difal_xml)}",
            f"FCP no SPED (C101): {_moeda(resultado.valor_fcp_sped)}",
            f"FCP nos XMLs localizados: {_moeda(resultado.valor_fcp_xml)}",
            f"DIFAL devido (XML + cálculo SPED sem XML): {_moeda(resultado.valor_difal_devido)}",
            f"Divergências origem/CST SPED x XML: {resultado.total_divergencias_origem}",
            f"NF-e com origens/CST mistas no SPED: {resultado.total_origem_mista_sped}",
            f"FCP devido calculado: {_moeda(resultado.valor_fcp_devido)}",
            f"NF-e sem XML com cálculo reconstruído: {resultado.total_calculados_sem_xml}",
            f"NF-e sem XML com FCP não calculado: {resultado.total_fcp_nao_calculado_sem_xml}",
            "",
            "APONTAMENTOS",
            "-" * 84,
        ]
        for a in resultado.apontamentos:
            linhas.extend(
                [
                    f"[{a.nivel}] Linha {a.linha} | NF {a.numero} | UF {a.uf_destino} | CFOP {a.cfops or '-'}",
                    f"Chave: {a.chave or '-'}",
                    f"Evidência: {a.evidencia}",
                    f"C101: {'SIM' if a.c101_presente else 'NÃO'} | DIFAL SPED {_moeda(a.difal_sped)} | XML {_moeda(a.difal_xml)} | DEVIDO {_moeda(a.difal_devido)} | FCP SPED {_moeda(a.fcp_sped)} | XML {_moeda(a.fcp_xml)} | DEVIDO {(_moeda(a.fcp_devido) if a.fcp_calculado else 'REVISAR')}",
                    f"Origem cálculo: {a.origem_calculo or '-'} | Base: {_moeda(a.base_calculo or a.base_xml)} | Interna: {a.aliquota_interna}% | Inter. XML: {a.aliquota_interestadual_xml_texto or '-'} | Inter. SPED/CST: {a.aliquota_interestadual_sped_texto or '-'} | FCP: {a.aliquota_fcp}%",
                    f"Cenário SPED/CST: {_moeda(a.difal_sped_origem)} | {a.detalhe_origem_sped or '-'}",
                    f"Memória de cálculo SPED/CST: {a.memoria_calculo_sped or '-'}",
                    f"Diferença SPED-devido: DIFAL {_moeda(a.diferenca_difal)} | FCP {(_moeda(a.diferenca_fcp) if a.fcp_calculado else 'REVISAR')}",
                    f"Problema: {a.mensagem}",
                    f"Orientação: {a.orientacao}",
                    "",
                ]
            )
        if not resultado.apontamentos:
            linhas.append("Nenhuma pendência de DIFAL foi identificada nas regras executadas.")
        linhas.extend(
            [
                "",
                "SEGURANÇA",
                "-" * 84,
                "O módulo não altera o SPED. Sem XML, CFOP 6107/6108 permite cálculo estimado pelo SPED, sempre marcado para revisão.",
                "Benefícios, reduções de base, FCP e regras específicas da UF podem alterar o cálculo.",
                "Valide a escrituração no PVA e confirme a legislação da UF de destino antes do recolhimento/transmissão.",
            ]
        )
        destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        return destino

    def salvar_excel(
        self,
        resultado: ResultadoAuditoriaDIFAL,
        caminho_saida: str | Path,
        caminho_sped: str | Path | None = None,
    ) -> Path:
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
            from openpyxl.utils import get_column_letter
        except ImportError as erro:
            raise RuntimeError("Instale o pacote openpyxl para exportar a auditoria DIFAL em Excel.") from erro

        destino = Path(caminho_saida)
        wb = Workbook()
        ws = wb.active
        ws.title = "Resumo"
        resumo = [
            ("FiscalPro — Auditoria DIFAL/FCP", "18.2.19"),
            ("Empresa", resultado.empresa or "-"),
            ("Período", resultado.periodo or "-"),
            ("UF origem", resultado.uf_origem or "-"),
            ("SPED", Path(caminho_sped).name if caminho_sped else "-"),
            ("NF-e saídas", resultado.total_documentos_saida),
            ("NF-e interestaduais", resultado.total_interestaduais),
            ("XMLs localizados", resultado.total_xml_localizados),
            ("XMLs ausentes", resultado.total_xml_ausentes),
            ("Sem XML calculados pelo SPED", resultado.total_calculados_sem_xml),
            ("Com C101", resultado.total_com_c101),
            ("Erros", resultado.erros),
            ("Avisos/Revisões", resultado.avisos),
            ("OK", resultado.ok),
            ("DIFAL SPED", float(resultado.valor_difal_sped)),
            ("DIFAL XML", float(resultado.valor_difal_xml)),
            ("DIFAL devido", float(resultado.valor_difal_devido)),
            ("FCP SPED", float(resultado.valor_fcp_sped)),
            ("FCP XML", float(resultado.valor_fcp_xml)),
            ("FCP devido calculado", float(resultado.valor_fcp_devido)),
            ("Sem XML com FCP para revisar", resultado.total_fcp_nao_calculado_sem_xml),
            ("Divergências origem/CST SPED x XML", resultado.total_divergencias_origem),
            ("NF-e com origens/CST mistas", resultado.total_origem_mista_sped),
            ("Tabela de alíquotas", FONTE_TABELA_DIFAL),
        ]
        for linha in resumo:
            ws.append(linha)
        ws["A1"].font = Font(bold=True, size=14)
        for row in range(15, 21):
            ws.cell(row=row, column=2).number_format = 'R$ #,##0.00'
        ws.column_dimensions["A"].width = 34
        ws.column_dimensions["B"].width = 88

        headers = [
            "Nível", "Linha SPED", "NF", "Chave", "UF destino", "CFOP", "Evidência", "C101",
            "Origem cálculo", "Base cálculo", "Alíq. interna %", "Alíq. inter. usada %",
            "Alíq. inter. XML", "Alíq. inter. SPED/CST", "DIFAL cenário SPED/CST", "Origem/CST SPED", "Memória cálculo SPED/CST", "Alíq. FCP %",
            "DIFAL SPED", "DIFAL XML", "DIFAL devido", "Dif. SPED - devido",
            "FCP SPED", "FCP XML", "FCP devido", "Dif. FCP SPED - devido", "FCP calculado?",
            "Diagnóstico", "Orientação", "Fonte alíquota",
        ]

        def preencher(aba, apontamentos):
            aba.append(headers)
            for cell in aba[1]:
                cell.font = Font(bold=True)
                cell.fill = PatternFill("solid", fgColor="D9EAF7")
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            for a in apontamentos:
                aba.append([
                    a.nivel, a.linha, a.numero, a.chave, a.uf_destino, a.cfops, a.evidencia,
                    "SIM" if a.c101_presente else "NÃO", a.origem_calculo,
                    float(a.base_calculo or a.base_xml), float(a.aliquota_interna),
                    float(a.aliquota_interestadual), a.aliquota_interestadual_xml_texto,
                    a.aliquota_interestadual_sped_texto, float(a.difal_sped_origem), a.detalhe_origem_sped,
                    a.memoria_calculo_sped, float(a.aliquota_fcp),
                    float(a.difal_sped), float(a.difal_xml), float(a.difal_devido), float(a.diferenca_difal),
                    float(a.fcp_sped), float(a.fcp_xml), (float(a.fcp_devido) if a.fcp_calculado else None),
                    (float(a.diferenca_fcp) if a.fcp_calculado else None), "SIM" if a.fcp_calculado else "REVISAR",
                    a.mensagem, a.orientacao, a.fonte_aliquota,
                ])
            aba.freeze_panes = "A2"
            aba.auto_filter.ref = aba.dimensions
            moeda_cols = {10, 15, 19, 20, 21, 22, 23, 24, 25, 26}
            for row in aba.iter_rows(min_row=2):
                for idx in moeda_cols:
                    row[idx-1].number_format = 'R$ #,##0.00'
                for cell in row:
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
            larguras = [12, 12, 12, 48, 12, 18, 42, 10, 28, 16, 16, 18, 18, 20, 20, 36, 72, 14, 16, 16, 16, 18, 16, 16, 16, 20, 15, 60, 72, 70]
            for idx, largura in enumerate(larguras, start=1):
                aba.column_dimensions[get_column_letter(idx)].width = largura

        detalhes = wb.create_sheet("Detalhes DIFAL")
        preencher(detalhes, resultado.apontamentos)
        sem_xml = wb.create_sheet("Sem XML")
        preencher(sem_xml, [a for a in resultado.apontamentos if a.calculo_estimado])

        memoria_ws = wb.create_sheet("Memória de Cálculo")
        memoria_headers = [
            "Tipo linha", "Competência", "Data", "NF-e", "Chave NF-e", "CST", "Origem CST", "CFOP",
            "Base VL_OPR (R$)", "Alíq. ICMS C190 %", "Alíq. interestadual cenário %",
            "Alíq. interna destino %", "Diferença alíquotas %", "Fórmula", "DIFAL segmento (R$)",
            "Linha C190", "DIFAL cenário SPED/CST NF (R$)", "DIFAL C101 NF (R$)",
            "Dif. C101 - cenário SPED/CST (R$)", "DIFAL devido principal NF (R$)", "Alíq. inter. XML",
            "Status origem XML x SPED", "Nível", "UF origem", "UF destino", "Arquivo fonte", "Fonte / observação",
        ]
        memoria_ws.append(memoria_headers)
        for cell in memoria_ws[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="D9EAF7")
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        arquivo_fonte = Path(caminho_sped).name if caminho_sped else "-"
        for a in resultado.apontamentos:
            segmentos = list(a.segmentos_memoria_sped or [])
            dif_c101_cenario = _dinheiro(a.difal_sped - a.difal_sped_origem)
            base_memoria_total = _dinheiro(sum((_decimal(seg.get("base")) for seg in segmentos), ZERO))
            if segmentos:
                for seg in segmentos:
                    memoria_ws.append([
                        "SEGMENTO", resultado.periodo or "-", a.data_documento, a.numero, a.chave,
                        seg.get("cst", ""), seg.get("origem", ""), seg.get("cfop", ""),
                        float(_decimal(seg.get("base"))), float(_decimal(seg.get("aliquota_c190"))),
                        float(_decimal(seg.get("aliquota_interestadual"))), float(_decimal(seg.get("aliquota_interna"))),
                        float(_decimal(seg.get("diferenca_aliquotas"))), seg.get("formula", ""),
                        float(_decimal(seg.get("difal"))), int(seg.get("linha_c190") or 0) or None,
                        None, None, None, None, a.aliquota_interestadual_xml_texto,
                        "DIVERGENTE" if a.divergencia_origem else "COINCIDENTE/SEM CONFRONTO",
                        a.nivel, resultado.uf_origem, a.uf_destino, arquivo_fonte, seg.get("fonte", ""),
                    ])
            total_row = memoria_ws.max_row + 1
            memoria_ws.append([
                "TOTAL NF", resultado.periodo or "-", a.data_documento, a.numero, a.chave,
                "", "", a.cfops, float(base_memoria_total or (a.base_calculo or a.base_xml)), None,
                None, float(a.aliquota_interna), None,
                a.memoria_calculo_sped or "Memória C190/CST indisponível para esta NF-e", None, None,
                float(a.difal_sped_origem), float(a.difal_sped), float(dif_c101_cenario), float(a.difal_devido),
                a.aliquota_interestadual_xml_texto,
                "DIVERGENTE" if a.divergencia_origem else "COINCIDENTE/SEM CONFRONTO", a.nivel,
                resultado.uf_origem, a.uf_destino, arquivo_fonte, a.detalhe_origem_sped or a.fonte_aliquota,
            ])
            for cell in memoria_ws[total_row]:
                cell.font = Font(bold=True)
                cell.fill = PatternFill("solid", fgColor="E2F0D9")

        memoria_ws.freeze_panes = "A2"
        memoria_ws.auto_filter.ref = memoria_ws.dimensions
        moeda_memoria = {9, 15, 17, 18, 19, 20}
        percent_memoria = {10, 11, 12, 13}
        for row in memoria_ws.iter_rows(min_row=2):
            for idx in moeda_memoria:
                row[idx-1].number_format = 'R$ #,##0.00'
            for idx in percent_memoria:
                row[idx-1].number_format = '0.00'
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
        memoria_larguras = [12, 14, 12, 11, 48, 11, 11, 12, 17, 17, 22, 20, 20, 54, 18, 12, 24, 18, 25, 24, 20, 24, 11, 10, 10, 48, 56]
        for idx, largura in enumerate(memoria_larguras, start=1):
            memoria_ws.column_dimensions[get_column_letter(idx)].width = largura

        wb.save(destino)
        return destino


    @staticmethod
    def _progresso(callback: ProgressoCallback | None, percentual: int, mensagem: str) -> None:
        if callback:
            callback(max(0, min(100, percentual)), mensagem)


__all__ = ["AuditorDIFALSPED", "ApontamentoDIFAL", "ResultadoAuditoriaDIFAL"]
