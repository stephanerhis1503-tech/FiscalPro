from __future__ import annotations

import base64
import gzip
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from lxml import etree

from src.nfe.assinatura import montar_evento_assinado
from src.nfe.cliente import ClienteNFeAmbienteNacional
from src.nfe.parser import analisar_documento_distribuido
from src.nfe.repositorio import RepositorioManifestacaoNFe


NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"


def _pfx_teste(tmp_path: Path, senha: str = "1234") -> Path:
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "FiscalPro Teste")])
    agora = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - timedelta(days=1))
        .not_valid_after(agora + timedelta(days=30))
        .sign(chave, hashes.SHA256())
    )
    bruto = pkcs12.serialize_key_and_certificates(
        b"fiscalpro", chave, cert, None,
        serialization.BestAvailableEncryption(senha.encode()),
    )
    caminho = tmp_path / "teste.pfx"
    caminho.write_bytes(bruto)
    return caminho


def test_parser_resnfe_calcula_prazo_de_90_dias():
    xml = """<resNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
      <chNFe>31260912345678000123550010000000011000000010</chNFe>
      <CNPJ>12345678000123</CNPJ><xNome>FORNECEDOR TESTE</xNome><IE>123</IE>
      <dhEmi>2026-09-01T08:00:00-03:00</dhEmi><tpNF>1</tpNF><vNF>123.45</vNF>
      <dhRecbto>2026-09-01T08:10:00-03:00</dhRecbto><cSitNFe>1</cSitNFe>
    </resNFe>"""
    dados = analisar_documento_distribuido(xml, "resNFe_v1.01.xsd")
    assert dados["tipo"] == "NFE"
    assert dados["emitente_nome"] == "FORNECEDOR TESTE"
    assert dados["valor_nf"] == pytest.approx(123.45)
    assert dados["prazo_final"] == "2026-11-30"
    assert dados["tem_xml_completo"] is False


def test_repositorio_consolida_nfe_e_manifestacao(tmp_path):
    repo = RepositorioManifestacaoNFe(tmp_path / "manifestacao.db")
    cnpj = "11111111000191"
    chave = "31260912345678000123550010000000011000000010"
    dados = {
        "tipo": "NFE", "chave": chave, "emitente_doc": "12345678000123",
        "emitente_nome": "FORNECEDOR", "data_emissao": "2026-09-01T08:00:00-03:00",
        "data_autorizacao": "2026-09-01T08:10:00-03:00", "valor_nf": 500,
        "situacao_nfe": "1", "tp_nf": "1", "prazo_final": "2026-11-30",
        "tem_xml_completo": False,
    }
    assert repo.salvar_documento(cnpj, "PRODUCAO", 10, "resNFe_v1.01.xsd", "<resNFe/>", dados)
    repo.salvar_manifestacao(
        cnpj, "PRODUCAO", chave, "210210", "Ciencia da Operacao", "",
        {"cstat": "135", "motivo": "Evento registrado", "protocolo": "123", "data_evento": "2026-09-02T10:00:00-03:00"},
        "<envEvento/>", "<retEnvEvento/>",
    )
    notas = repo.listar_notas(cnpj, "PRODUCAO")
    assert len(notas) == 1
    assert notas[0]["manifestacao"] == "Ciencia da Operacao"
    assert notas[0]["protocolo_manifestacao"] == "123"


def test_evento_assinado_tem_id_digest_e_assinatura_validos(tmp_path):
    senha = "1234"
    pfx = _pfx_teste(tmp_path, senha)
    cnpj = "11111111000191"
    chave = "31260912345678000123550010000000011000000010"
    bruto = montar_evento_assinado(str(pfx), senha, cnpj, chave, "210200", ambiente="2")
    raiz = etree.fromstring(bruto)
    ns = {"n": NS_NFE, "d": NS_DS}
    inf = raiz.find(".//n:infEvento", ns)
    assert inf is not None
    assert inf.get("Id") == f"ID210200{chave}01"
    assert inf.findtext("n:cOrgao", namespaces=ns) == "91"
    assert inf.findtext("n:tpAmb", namespaces=ns) == "2"
    assert inf.findtext(".//n:descEvento", namespaces=ns) == "Confirmacao da Operacao"

    canon_inf = etree.tostring(inf, method="c14n", exclusive=False, with_comments=False)
    h = hashes.Hash(hashes.SHA1())
    h.update(canon_inf)
    digest_esperado = base64.b64encode(h.finalize()).decode("ascii")
    assert raiz.findtext(".//d:DigestValue", namespaces=ns) == digest_esperado

    signed_info = raiz.find(".//d:SignedInfo", ns)
    assinatura = raiz.findtext(".//d:SignatureValue", namespaces=ns)
    cert_b64 = raiz.findtext(".//d:X509Certificate", namespaces=ns)
    cert = x509.load_der_x509_certificate(base64.b64decode(cert_b64))
    cert.public_key().verify(
        base64.b64decode(assinatura),
        etree.tostring(signed_info, method="c14n", exclusive=False, with_comments=False),
        padding.PKCS1v15(), hashes.SHA1(),
    )


def test_operacao_nao_realizada_exige_justificativa(tmp_path):
    pfx = _pfx_teste(tmp_path)
    chave = "31260912345678000123550010000000011000000010"
    with pytest.raises(ValueError, match="15 a 255"):
        montar_evento_assinado(str(pfx), "1234", "11111111000191", chave, "210240", justificativa="curta")


def test_distribuicao_descompacta_doczip(monkeypatch):
    res = b'''<resNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01"><chNFe>31260912345678000123550010000000011000000010</chNFe></resNFe>'''
    zip64 = base64.b64encode(gzip.compress(res)).decode("ascii")
    retorno = f'''<?xml version="1.0" encoding="utf-8"?>
    <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Body><nfeDistDFeInteresseResponse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
        <nfeDistDFeInteresseResult><retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
          <tpAmb>1</tpAmb><verAplic>1</verAplic><cStat>138</cStat><xMotivo>Documento localizado</xMotivo>
          <dhResp>2026-09-22T10:00:00-03:00</dhResp><ultNSU>000000000000123</ultNSU><maxNSU>000000000000123</maxNSU>
          <loteDistDFeInt><docZip NSU="000000000000123" schema="resNFe_v1.01.xsd">{zip64}</docZip></loteDistDFeInt>
        </retDistDFeInt></nfeDistDFeInteresseResult>
      </nfeDistDFeInteresseResponse></soap:Body>
    </soap:Envelope>'''
    cliente = ClienteNFeAmbienteNacional("nao-usado.pfx", "x")
    monkeypatch.setattr(cliente, "_post_soap", lambda *_args, **_kwargs: retorno)
    resp = cliente.consultar_distribuicao("11111111000191", "MG", 0)
    assert resp.cstat == "138"
    assert resp.ultimo_nsu == 123
    assert resp.max_nsu == 123
    assert len(resp.documentos) == 1
    assert "<resNFe" in resp.documentos[0].xml


def test_manifestacao_usa_metodo_e_soapaction_nacional(monkeypatch, tmp_path):
    pfx = _pfx_teste(tmp_path)
    chave = "31260912345678000123550010000000011000000010"
    capturado = {}
    retorno = '''<?xml version="1.0" encoding="utf-8"?>
    <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Body><nfeRecepcaoEventoNFResponse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4">
        <nfeResultMsg><retEnvEvento xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00">
          <idLote>1</idLote><tpAmb>2</tpAmb><verAplic>AN_TESTE</verAplic><cOrgao>91</cOrgao><cStat>128</cStat><xMotivo>Lote processado</xMotivo>
          <retEvento versao="1.00"><infEvento><tpAmb>2</tpAmb><verAplic>AN_TESTE</verAplic><cOrgao>91</cOrgao>
            <cStat>135</cStat><xMotivo>Evento registrado e vinculado a NF-e</xMotivo>
            <chNFe>31260912345678000123550010000000011000000010</chNFe><tpEvento>210210</tpEvento>
            <nSeqEvento>1</nSeqEvento><dhRegEvento>2026-09-22T10:30:00-03:00</dhRegEvento><nProt>912600000000001</nProt>
          </infEvento></retEvento>
        </retEnvEvento></nfeResultMsg>
      </nfeRecepcaoEventoNFResponse></soap:Body>
    </soap:Envelope>'''

    def falso_post(url, acao, corpo):
        capturado["url"] = url
        capturado["acao"] = acao
        capturado["corpo"] = corpo.decode("utf-8")
        return retorno

    cliente = ClienteNFeAmbienteNacional(str(pfx), "1234", "HOMOLOGACAO")
    monkeypatch.setattr(cliente, "_post_soap", falso_post)
    resp = cliente.enviar_manifestacao("11111111000191", chave, "210210")
    assert capturado["acao"].endswith("/nfeRecepcaoEventoNF")
    assert "<nfeRecepcaoEventoNF" in capturado["corpo"]
    assert resp["cstat"] == "135"
    assert resp["protocolo"] == "912600000000001"
