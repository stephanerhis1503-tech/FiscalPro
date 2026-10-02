from __future__ import annotations

import base64
import gzip
from pathlib import Path

import src.nfe.servico as servico_mod
from src.nfe.cliente import ClienteNFeAmbienteNacional, DocumentoDistribuido, RespostaDistribuicao
from src.nfe.repositorio import RepositorioManifestacaoNFe
from src.nfe.servico import ServicoManifestacaoNFe


CNPJ = "11111111000191"
CHAVE = "31261011111111000191550010000000011000000011"


class RepoEmpresasFake:
    def __init__(self, certificado_path: str):
        self.empresa = {
            "id": 1,
            "cnpj": CNPJ,
            "nome": "EMPRESA TESTE",
            "ambiente": "PRODUCAO",
            "certificado_path": certificado_path,
        }

    def obter_empresa(self, empresa_id: int):
        return dict(self.empresa) if int(empresa_id) == 1 else None

    def listar_empresas(self):
        return [dict(self.empresa)]


def _resumo_xml() -> str:
    return f"""<resNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
      <chNFe>{CHAVE}</chNFe>
      <CNPJ>22222222000191</CNPJ>
      <xNome>FORNECEDOR TESTE</xNome>
      <IE>123</IE>
      <dhEmi>2026-10-02T10:00:00-03:00</dhEmi>
      <tpNF>1</tpNF>
      <vNF>150.00</vNF>
      <dhRecbto>2026-10-02T10:05:00-03:00</dhRecbto>
      <cSitNFe>1</cSitNFe>
    </resNFe>"""


def test_cliente_consulta_por_chave_monta_consch_nfe(monkeypatch):
    capturado = {}

    def fake_post(self, url, acao, corpo):
        capturado["corpo"] = corpo.decode("utf-8")
        doc = base64.b64encode(gzip.compress(_resumo_xml().encode("utf-8"))).decode("ascii")
        return f"""<retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
          <tpAmb>1</tpAmb><verAplic>1</verAplic><cStat>138</cStat><xMotivo>Documento localizado</xMotivo>
          <dhResp>2026-10-02T14:00:00-03:00</dhResp>
          <loteDistDFeInt><docZip NSU="000000000062500" schema="resNFe_v1.01.xsd">{doc}</docZip></loteDistDFeInt>
        </retDistDFeInt>"""

    monkeypatch.setattr(ClienteNFeAmbienteNacional, "_post_soap", fake_post)
    cliente = ClienteNFeAmbienteNacional("cert.pfx", "senha", "PRODUCAO")
    resposta = cliente.consultar_por_chave(CNPJ, "MG", CHAVE)

    assert "<consChNFe>" in capturado["corpo"]
    assert f"<chNFe>{CHAVE}</chNFe>" in capturado["corpo"]
    assert "<distNSU>" not in capturado["corpo"]
    assert resposta.cstat == "138"
    assert len(resposta.documentos) == 1
    assert resposta.documentos[0].nsu == 62500


def test_servico_consulta_chave_nao_altera_ult_nsu(tmp_path: Path, monkeypatch):
    cert = tmp_path / "certificado.pfx"
    cert.write_bytes(b"teste")
    repo = RepositorioManifestacaoNFe(tmp_path / "manifestacao.db")
    repo.salvar_config(CNPJ, "PRODUCAO", uf_autor="MG", ultimo_nsu=62433, max_nsu=62433)

    resposta = RespostaDistribuicao(
        cstat="138",
        motivo="Documento localizado",
        ultimo_nsu=0,
        max_nsu=0,
        documentos=[
            DocumentoDistribuido(
                nsu=62500,
                schema="resNFe_v1.01.xsd",
                xml=_resumo_xml(),
            )
        ],
        xml_retorno="<retDistDFeInt/>",
    )

    class ClienteFake:
        def __init__(self, *_a, **_k):
            self.chamadas = []

        def consultar_por_chave(self, cnpj, uf, chave):
            self.chamadas.append((cnpj, uf, chave))
            return resposta

    monkeypatch.setattr(servico_mod, "ClienteNFeAmbienteNacional", ClienteFake)
    servico = ServicoManifestacaoNFe(repo, RepoEmpresasFake(str(cert)))

    resultado = servico.consultar_por_chave(1, "senha", "MG", CHAVE)
    config = repo.obter_config(CNPJ, "PRODUCAO")

    assert resultado["cstat"] == "138"
    assert resultado["processados"] == 1
    assert resultado["chave_localizada"] is True
    assert config["ultimo_nsu"] == 62433
    assert config["max_nsu"] == 62433

    notas = repo.listar_notas(CNPJ, "PRODUCAO")
    assert len(notas) == 1
    assert notas[0]["chave"] == CHAVE
    assert notas[0]["tem_xml_completo"] == 0
