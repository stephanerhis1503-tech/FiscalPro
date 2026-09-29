"""Decodificação e leitura tolerante dos DF-e distribuídos pelo ADN."""

from __future__ import annotations

import base64
import gzip
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET


def somente_digitos(valor: str) -> str:
    return "".join(ch for ch in str(valor or "") if ch.isdigit())


def local_nome(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _texto(elem) -> str:
    return (elem.text or "").strip() if elem is not None else ""


def _descendente(grupo, nomes: tuple[str, ...]):
    if grupo is None:
        return None
    alvos = {n.casefold() for n in nomes}
    for elem in grupo.iter():
        if local_nome(elem.tag).casefold() in alvos and _texto(elem):
            return elem
    return None


def _primeiro(root, nomes: tuple[str, ...]):
    alvos = {n.casefold() for n in nomes}
    for elem in root.iter():
        if local_nome(elem.tag).casefold() in alvos and _texto(elem):
            return elem
    return None


def _grupo(root, nomes: tuple[str, ...]):
    alvos = {n.casefold() for n in nomes}
    for elem in root.iter():
        if local_nome(elem.tag).casefold() in alvos:
            return elem
    return None


def _decimal(texto: str) -> float:
    try:
        return float(Decimal(str(texto or "0").replace(",", ".")))
    except (InvalidOperation, ValueError):
        return 0.0


def _normalizar_data(valor: str) -> str:
    valor = (valor or "").strip()
    if not valor:
        return ""
    candidato = valor.replace("Z", "+00:00")
    try:
        data = datetime.fromisoformat(candidato)
        return data.strftime("%Y-%m-%d")
    except ValueError:
        return valor[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", valor) else valor


def decodificar_xml(valor) -> str:
    """Aceita XML cru, Base64 simples ou GZip+Base64."""
    if valor is None:
        return ""
    if isinstance(valor, bytes):
        dados = valor
    else:
        texto = str(valor).strip()
        if not texto:
            return ""
        if texto.startswith("<"):
            return texto
        try:
            dados = base64.b64decode(texto, validate=False)
        except Exception:
            return texto if "<" in texto else ""

    try:
        if dados[:2] == b"\x1f\x8b":
            dados = gzip.decompress(dados)
        texto = dados.decode("utf-8-sig", errors="replace").strip()
        return texto if texto.startswith("<") else ""
    except Exception:
        return ""


def extrair_xml_item(item: dict) -> str:
    for chave in (
        "ArquivoXml", "arquivoXml", "Xml", "xml", "XML",
        "nfseXmlGZipB64", "NfseXmlGZipB64", "xmlGZipB64",
    ):
        if chave in item:
            xml = decodificar_xml(item.get(chave))
            if xml:
                return xml
    return ""


def _doc_e_nome(grupo) -> tuple[str, str]:
    documento = _descendente(grupo, ("CNPJ", "CPF", "NIF"))
    nome = _descendente(grupo, ("xNome", "xFant"))
    return somente_digitos(_texto(documento)) or _texto(documento), _texto(nome)


def _valor_em_grupo(root, grupo_nomes: tuple[str, ...], tag_nomes: tuple[str, ...]) -> float:
    grupo = _grupo(root, grupo_nomes)
    return _decimal(_texto(_descendente(grupo, tag_nomes)))


def analisar_nfse(xml: str, cnpj_empresa: str = "") -> dict:
    if not xml.strip():
        return {}
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return {}

    inf_nfse_encontrado = _grupo(root, ("infNFSe",))
    inf_nfse = inf_nfse_encontrado if inf_nfse_encontrado is not None else root
    dps = _grupo(inf_nfse, ("infDPS",))

    emit = _grupo(inf_nfse, ("emit",))
    prest = _grupo(dps, ("prest", "prestador")) if dps is not None else None
    toma = _grupo(dps, ("toma", "tomador")) if dps is not None else None
    interm = _grupo(dps, ("interm", "intermediario")) if dps is not None else None

    prest_doc, prest_nome = _doc_e_nome(prest)
    emit_doc, emit_nome = _doc_e_nome(emit)
    if not prest_doc:
        prest_doc = emit_doc
    if not prest_nome:
        prest_nome = emit_nome
    toma_doc, toma_nome = _doc_e_nome(toma)
    interm_doc, interm_nome = _doc_e_nome(interm)

    numero = _texto(_primeiro(inf_nfse, ("nNFSe", "numeroNFSe")))
    competencia = _normalizar_data(_texto(_descendente(dps, ("dCompet", "competencia")))) if dps is not None else ""
    data_emissao = _normalizar_data(_texto(_primeiro(inf_nfse, ("dhEmi", "dhProc", "dataEmissao"))))

    base_valores = dps if dps is not None else inf_nfse
    v_serv = _valor_em_grupo(base_valores, ("vServPrest",), ("vServ", "vReceb"))
    if not v_serv:
        v_serv = _decimal(_texto(_primeiro(inf_nfse, ("vServ", "vServico"))))
    v_liq = _decimal(_texto(_primeiro(inf_nfse, ("vLiq", "vLiquido", "vReceb")))) or v_serv

    iss = _decimal(_texto(_primeiro(inf_nfse, ("vISSQN", "vISS", "vISSRet"))))
    pis = _decimal(_texto(_primeiro(inf_nfse, ("vPis", "vPIS"))))
    cofins = _decimal(_texto(_primeiro(inf_nfse, ("vCofins", "vCOFINS"))))
    csll = _decimal(_texto(_primeiro(inf_nfse, ("vCSLL", "vCsll"))))
    ir = _decimal(_texto(_primeiro(inf_nfse, ("vRetIRRF", "vIR", "vIRRF"))))
    inss = _decimal(_texto(_primeiro(inf_nfse, ("vRetCP", "vINSS", "vInss"))))

    empresa = somente_digitos(cnpj_empresa)
    if empresa and somente_digitos(prest_doc) == empresa:
        direcao = "EMITIDA"
    elif empresa and somente_digitos(toma_doc) == empresa:
        direcao = "RECEBIDA"
    elif empresa and somente_digitos(interm_doc) == empresa:
        direcao = "INTERMEDIADA"
    else:
        direcao = "OUTRA"

    return {
        "numero_nfse": numero,
        "competencia": competencia,
        "data_emissao": data_emissao,
        "prestador_doc": prest_doc,
        "prestador_nome": prest_nome,
        "tomador_doc": toma_doc,
        "tomador_nome": toma_nome,
        "intermediario_doc": interm_doc,
        "intermediario_nome": interm_nome,
        "valor_servico": v_serv,
        "valor_liquido": v_liq,
        "iss": iss,
        "pis": pis,
        "cofins": cofins,
        "csll": csll,
        "ir": ir,
        "inss": inss,
        "direcao": direcao,
    }
