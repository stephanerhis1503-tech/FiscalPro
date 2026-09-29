"""Montagem e assinatura XML dos eventos de Manifestação do Destinatário da NF-e."""

from __future__ import annotations

import base64
from datetime import datetime

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from lxml import etree

from src.nfse.certificado import _carregar_pfx


NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"
C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
RSA_SHA1 = "http://www.w3.org/2000/09/xmldsig#rsa-sha1"
SHA1 = "http://www.w3.org/2000/09/xmldsig#sha1"
ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"

DESCRICOES_EVENTO = {
    "210200": "Confirmacao da Operacao",
    "210210": "Ciencia da Operacao",
    "210220": "Desconhecimento da Operacao",
    "210240": "Operacao nao Realizada",
}


def _digitos(valor: str) -> str:
    return "".join(ch for ch in str(valor or "") if ch.isdigit())


def _adicionar(pai: etree._Element, nome: str, valor: str) -> etree._Element:
    elem = etree.SubElement(pai, etree.QName(NS_NFE, nome))
    elem.text = str(valor)
    return elem


def montar_evento_assinado(certificado_path: str, senha: str, cnpj: str, chave: str,
                            tp_evento: str, *, ambiente: str = "1", justificativa: str = "") -> bytes:
    cnpj = _digitos(cnpj)
    chave = _digitos(chave)
    tp_evento = str(tp_evento or "")
    if len(cnpj) != 14:
        raise ValueError("CNPJ deve conter 14 dígitos.")
    if len(chave) != 44:
        raise ValueError("Chave da NF-e deve conter 44 dígitos.")
    if tp_evento not in DESCRICOES_EVENTO:
        raise ValueError("Tipo de manifestação inválido.")
    justificativa = " ".join(str(justificativa or "").split())
    if tp_evento == "210240" and not (15 <= len(justificativa) <= 255):
        raise ValueError("Na Operação não Realizada, informe uma justificativa de 15 a 255 caracteres.")
    if tp_evento != "210240":
        justificativa = ""

    chave_privada, certificado, _cadeia = _carregar_pfx(certificado_path, senha)
    if not hasattr(chave_privada, "sign"):
        raise ValueError("A chave privada do certificado A1 não suporta assinatura RSA.")

    env = etree.Element(etree.QName(NS_NFE, "envEvento"), nsmap={None: NS_NFE}, versao="1.00")
    _adicionar(env, "idLote", str(int(datetime.now().timestamp() * 1000))[-15:])
    evento = etree.SubElement(env, etree.QName(NS_NFE, "evento"), versao="1.00")
    seq = "1"
    identificador = f"ID{tp_evento}{chave}{int(seq):02d}"
    inf = etree.SubElement(evento, etree.QName(NS_NFE, "infEvento"), Id=identificador)
    _adicionar(inf, "cOrgao", "91")  # Manifestação é recepcionada pelo Ambiente Nacional.
    _adicionar(inf, "tpAmb", "2" if str(ambiente) == "2" else "1")
    _adicionar(inf, "CNPJ", cnpj)
    _adicionar(inf, "chNFe", chave)
    _adicionar(inf, "dhEvento", datetime.now().astimezone().isoformat(timespec="seconds"))
    _adicionar(inf, "tpEvento", tp_evento)
    _adicionar(inf, "nSeqEvento", seq)
    _adicionar(inf, "verEvento", "1.00")
    det = etree.SubElement(inf, etree.QName(NS_NFE, "detEvento"), versao="1.00")
    _adicionar(det, "descEvento", DESCRICOES_EVENTO[tp_evento])
    if justificativa:
        _adicionar(det, "xJust", justificativa)

    # Digest do elemento infEvento já no contexto do namespace padrão da NF-e.
    canon_inf = etree.tostring(inf, method="c14n", exclusive=False, with_comments=False)
    digest = hashes.Hash(hashes.SHA1())
    digest.update(canon_inf)
    digest_b64 = base64.b64encode(digest.finalize()).decode("ascii")

    assinatura = etree.SubElement(evento, etree.QName(NS_DS, "Signature"), nsmap={None: NS_DS})
    signed_info = etree.SubElement(assinatura, etree.QName(NS_DS, "SignedInfo"))
    etree.SubElement(signed_info, etree.QName(NS_DS, "CanonicalizationMethod"), Algorithm=C14N)
    etree.SubElement(signed_info, etree.QName(NS_DS, "SignatureMethod"), Algorithm=RSA_SHA1)
    ref = etree.SubElement(signed_info, etree.QName(NS_DS, "Reference"), URI=f"#{identificador}")
    transforms = etree.SubElement(ref, etree.QName(NS_DS, "Transforms"))
    etree.SubElement(transforms, etree.QName(NS_DS, "Transform"), Algorithm=ENVELOPED)
    etree.SubElement(transforms, etree.QName(NS_DS, "Transform"), Algorithm=C14N)
    etree.SubElement(ref, etree.QName(NS_DS, "DigestMethod"), Algorithm=SHA1)
    etree.SubElement(ref, etree.QName(NS_DS, "DigestValue")).text = digest_b64

    canon_signed = etree.tostring(signed_info, method="c14n", exclusive=False, with_comments=False)
    valor_assinatura = chave_privada.sign(canon_signed, padding.PKCS1v15(), hashes.SHA1())
    etree.SubElement(assinatura, etree.QName(NS_DS, "SignatureValue")).text = base64.b64encode(valor_assinatura).decode("ascii")
    key_info = etree.SubElement(assinatura, etree.QName(NS_DS, "KeyInfo"))
    x509_data = etree.SubElement(key_info, etree.QName(NS_DS, "X509Data"))
    der = certificado.public_bytes(serialization.Encoding.DER)
    etree.SubElement(x509_data, etree.QName(NS_DS, "X509Certificate")).text = base64.b64encode(der).decode("ascii")

    return etree.tostring(env, xml_declaration=True, encoding="UTF-8", pretty_print=False)
