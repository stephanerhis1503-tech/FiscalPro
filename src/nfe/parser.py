"""Leitura dos documentos compactados retornados pela Distribuição DF-e da NF-e."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET


EVENTOS_MANIFESTACAO = {
    "210200": "CONFIRMADA",
    "210210": "CIÊNCIA",
    "210220": "DESCONHECIDA",
    "210240": "NÃO REALIZADA",
}


def _local(tag: str) -> str:
    return str(tag or "").rsplit("}", 1)[-1]


def _descendente(raiz: ET.Element | None, nome: str) -> ET.Element | None:
    if raiz is None:
        return None
    for elem in raiz.iter():
        if _local(elem.tag) == nome:
            return elem
    return None


def _texto(raiz: ET.Element | None, nome: str, padrao: str = "") -> str:
    elem = _descendente(raiz, nome)
    return (elem.text or "").strip() if elem is not None and elem.text else padrao


def _numero(texto: str) -> float:
    try:
        return float(Decimal(str(texto or "0").replace(",", ".")))
    except (InvalidOperation, ValueError):
        return 0.0


def _somente_digitos(texto: str) -> str:
    return "".join(ch for ch in str(texto or "") if ch.isdigit())


def _prazo_final(data_autorizacao: str) -> str:
    """Prazo conclusivo vigente desde 01/06/2026: 90 dias da autorização."""
    texto = str(data_autorizacao or "").strip()
    if not texto:
        return ""
    try:
        dt = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return (dt + timedelta(days=90)).date().isoformat()


def analisar_documento_distribuido(xml: str, schema: str = "") -> dict:
    """Extrai um resumo uniforme de resNFe, procNFe/nfeProc e eventos."""
    if not str(xml or "").strip():
        return {}
    try:
        raiz = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    except ET.ParseError:
        return {}

    tipo_raiz = _local(raiz.tag)
    schema_l = str(schema or "").lower()

    # Resumo de NF-e retornado pelo Ambiente Nacional.
    if tipo_raiz == "resNFe" or "resnfe" in schema_l:
        data_aut = _texto(raiz, "dhRecbto")
        return {
            "tipo": "NFE",
            "chave": _somente_digitos(_texto(raiz, "chNFe")),
            "emitente_doc": _somente_digitos(_texto(raiz, "CNPJ") or _texto(raiz, "CPF")),
            "emitente_nome": _texto(raiz, "xNome"),
            "emitente_ie": _texto(raiz, "IE"),
            "data_emissao": _texto(raiz, "dhEmi"),
            "data_autorizacao": data_aut,
            "valor_nf": _numero(_texto(raiz, "vNF")),
            "situacao_nfe": _texto(raiz, "cSitNFe"),
            "tp_nf": _texto(raiz, "tpNF"),
            "manifestacao_codigo": "",
            "manifestacao": "SEM MANIFESTAÇÃO",
            "prazo_final": _prazo_final(data_aut),
            "tem_xml_completo": False,
        }

    # NF-e completa/protocolada.
    inf_nfe = _descendente(raiz, "infNFe")
    if inf_nfe is not None:
        emit = _descendente(inf_nfe, "emit")
        ide = _descendente(inf_nfe, "ide")
        total = _descendente(inf_nfe, "ICMSTot")
        inf_prot = _descendente(raiz, "infProt")
        chave = _somente_digitos(inf_nfe.attrib.get("Id", ""))
        if len(chave) != 44:
            chave = _somente_digitos(_texto(inf_prot, "chNFe"))
        data_aut = _texto(inf_prot, "dhRecbto")
        return {
            "tipo": "NFE",
            "chave": chave,
            "emitente_doc": _somente_digitos(_texto(emit, "CNPJ") or _texto(emit, "CPF")),
            "emitente_nome": _texto(emit, "xNome"),
            "emitente_ie": _texto(emit, "IE"),
            "data_emissao": _texto(ide, "dhEmi") or _texto(ide, "dEmi"),
            "data_autorizacao": data_aut,
            "valor_nf": _numero(_texto(total, "vNF")),
            "situacao_nfe": _texto(inf_prot, "cStat"),
            "tp_nf": _texto(ide, "tpNF"),
            "manifestacao_codigo": "",
            "manifestacao": "SEM MANIFESTAÇÃO",
            "prazo_final": _prazo_final(data_aut),
            "tem_xml_completo": True,
        }

    # Evento distribuído (inclusive manifestação própria).
    if tipo_raiz in {"procEventoNFe", "resEvento", "evento"} or "evento" in schema_l:
        chave = _somente_digitos(_texto(raiz, "chNFe"))
        tp_evento = _texto(raiz, "tpEvento")
        if chave and tp_evento:
            return {
                "tipo": "EVENTO",
                "chave": chave,
                "manifestacao_codigo": tp_evento if tp_evento in EVENTOS_MANIFESTACAO else "",
                "manifestacao": EVENTOS_MANIFESTACAO.get(tp_evento, ""),
                "protocolo": _texto(raiz, "nProt"),
                "data_manifestacao": _texto(raiz, "dhRegEvento") or _texto(raiz, "dhEvento"),
                "cstat_manifestacao": _texto(raiz, "cStat"),
                "motivo_manifestacao": _texto(raiz, "xMotivo"),
            }

    return {"tipo": "OUTRO", "chave": _somente_digitos(_texto(raiz, "chNFe"))}
