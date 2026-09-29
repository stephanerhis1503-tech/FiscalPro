from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

import src.nfe.servico as servico_mod
from src.nfe.cliente import ErroNFe, RespostaDistribuicao
from src.nfe.repositorio import RepositorioManifestacaoNFe
from src.nfe.servico import ServicoManifestacaoNFe


CNPJ = "11111111000191"


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


class ClienteFake:
    def __init__(self, resposta):
        self.resposta = resposta
        self.chamadas = 0

    def consultar_distribuicao(self, *_args, **_kwargs):
        self.chamadas += 1
        return self.resposta


def _servico(tmp_path, monkeypatch, resposta):
    cert = tmp_path / "certificado.pfx"
    cert.write_bytes(b"teste")
    repo = RepositorioManifestacaoNFe(tmp_path / "manifestacao.db")
    cliente = ClienteFake(resposta)
    monkeypatch.setattr(
        servico_mod,
        "ClienteNFeAmbienteNacional",
        lambda *_args, **_kwargs: cliente,
    )
    servico = ServicoManifestacaoNFe(repo, RepoEmpresasFake(str(cert)))
    return servico, repo, cliente


def test_656_grava_ultnsu_da_sefaz_e_bloqueia_por_uma_hora(tmp_path, monkeypatch):
    resposta = RespostaDistribuicao(
        cstat="656",
        motivo="Rejeicao: Consumo Indevido. Deve ser utilizado o ultNSU nas solicitacoes subsequentes.",
        ultimo_nsu=987654,
        max_nsu=999999,
        documentos=[],
        xml_retorno="<retDistDFeInt><ultNSU>000000000987654</ultNSU></retDistDFeInt>",
        ultimo_nsu_informado=True,
        max_nsu_informado=True,
    )
    servico, repo, cliente = _servico(tmp_path, monkeypatch, resposta)

    with pytest.raises(ErroNFe, match="guardou o ultNSU"):
        servico.sincronizar(1, "senha", "MG", pausa=0)

    config = repo.obter_config(CNPJ, "PRODUCAO")
    assert config["ultimo_nsu"] == 987654
    assert config["max_nsu"] == 999999
    assert config["ultimo_cstat"] == "656"
    assert config["bloqueado_ate"]
    assert datetime.fromisoformat(config["bloqueado_ate"]) > datetime.now()
    assert cliente.chamadas == 1

    # Uma segunda tentativa local não chega à SEFAZ e, portanto, não reinicia a hora.
    with pytest.raises(ErroNFe, match="protegida"):
        servico.sincronizar(1, "senha", "MG", pausa=0)
    assert cliente.chamadas == 1


def test_cstat_137_grava_intervalo_antes_de_nova_consulta(tmp_path, monkeypatch):
    resposta = RespostaDistribuicao(
        cstat="137",
        motivo="Nenhum documento localizado",
        ultimo_nsu=123,
        max_nsu=123,
        documentos=[],
        xml_retorno="<retDistDFeInt/>",
        ultimo_nsu_informado=True,
        max_nsu_informado=True,
    )
    servico, repo, _cliente = _servico(tmp_path, monkeypatch, resposta)
    resultado = servico.sincronizar(1, "senha", "MG", pausa=0)

    assert resultado["cstat"] == "137"
    assert resultado["ultimo_nsu"] == 123
    assert resultado["bloqueado_ate"]
    status = servico.status_sincronizacao(1)
    assert status["bloqueado"] is True
    assert status["segundos_restantes"] > 0
    assert repo.obter_config(CNPJ, "PRODUCAO")["ultimo_cstat"] == "137"


def test_migracao_adiciona_campos_de_protecao_em_banco_antigo(tmp_path):
    banco = tmp_path / "antigo.db"
    with sqlite3.connect(banco) as conn:
        conn.execute(
            """
            CREATE TABLE configuracao_nfe (
                cnpj TEXT NOT NULL,
                ambiente TEXT NOT NULL,
                uf_autor TEXT NOT NULL DEFAULT '',
                ultimo_nsu INTEGER NOT NULL DEFAULT 0,
                max_nsu INTEGER NOT NULL DEFAULT 0,
                atualizado_em TEXT NOT NULL,
                PRIMARY KEY(cnpj, ambiente)
            )
            """
        )
        conn.execute(
            "INSERT INTO configuracao_nfe(cnpj,ambiente,uf_autor,ultimo_nsu,max_nsu,atualizado_em) VALUES(?,?,?,?,?,?)",
            (CNPJ, "PRODUCAO", "MG", 55, 77, "2026-09-22T10:00:00"),
        )

    repo = RepositorioManifestacaoNFe(banco)
    config = repo.obter_config(CNPJ, "PRODUCAO")
    assert config["ultimo_nsu"] == 55
    assert config["max_nsu"] == 77
    assert config["bloqueado_ate"] == ""
    assert config["ultima_consulta_em"] == ""
    assert config["ultimo_cstat"] == ""
    assert config["ultimo_motivo"] == ""


def test_cliente_le_ultnsu_de_rejeicao_656(monkeypatch):
    from src.nfe.cliente import ClienteNFeAmbienteNacional

    retorno = '''<?xml version="1.0" encoding="utf-8"?>
    <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Body><nfeDistDFeInteresseResponse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
        <nfeDistDFeInteresseResult><retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
          <tpAmb>1</tpAmb><verAplic>AN_TESTE</verAplic><cStat>656</cStat>
          <xMotivo>Rejeicao: Consumo Indevido. Deve ser utilizado o ultNSU nas solicitacoes subsequentes.</xMotivo>
          <ultNSU>000000000654321</ultNSU>
        </retDistDFeInt></nfeDistDFeInteresseResult>
      </nfeDistDFeInteresseResponse></soap:Body>
    </soap:Envelope>'''
    cliente = ClienteNFeAmbienteNacional("nao-usado.pfx", "x")
    monkeypatch.setattr(cliente, "_post_soap", lambda *_args, **_kwargs: retorno)
    resp = cliente.consultar_distribuicao(CNPJ, "MG", 0)
    assert resp.cstat == "656"
    assert resp.ultimo_nsu == 654321
    assert resp.ultimo_nsu_informado is True
    assert resp.max_nsu_informado is False
