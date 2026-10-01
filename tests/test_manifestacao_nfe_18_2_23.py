from __future__ import annotations

from pathlib import Path

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
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def consultar_distribuicao(self, cnpj, uf, nsu):
        self.chamadas.append((cnpj, uf, nsu))
        return self.respostas.pop(0)


def _servico(tmp_path: Path, monkeypatch, respostas):
    cert = tmp_path / "certificado.pfx"
    cert.write_bytes(b"teste")
    repo = RepositorioManifestacaoNFe(tmp_path / "manifestacao.db")
    cliente = ClienteFake(respostas)
    monkeypatch.setattr(servico_mod, "ClienteNFeAmbienteNacional", lambda *_a, **_k: cliente)
    return ServicoManifestacaoNFe(repo, RepoEmpresasFake(str(cert))), repo, cliente


def test_138_no_fim_para_sem_segunda_chamada(tmp_path, monkeypatch):
    resposta = RespostaDistribuicao(
        cstat="138",
        motivo="Documentos localizados",
        ultimo_nsu=105,
        max_nsu=105,
        documentos=[],
        xml_retorno="<retDistDFeInt/>",
        ultimo_nsu_informado=True,
        max_nsu_informado=True,
    )
    servico, repo, cliente = _servico(tmp_path, monkeypatch, [resposta])
    repo.salvar_config(CNPJ, "PRODUCAO", uf_autor="MG", ultimo_nsu=100, max_nsu=100)

    resultado = servico.sincronizar(1, "senha", "MG", pausa=0)

    assert resultado["ultimo_nsu"] == 105
    assert resultado["max_nsu"] == 105
    assert len(cliente.chamadas) == 1
    assert repo.obter_config(CNPJ, "PRODUCAO")["bloqueado_ate"]

    log = repo.obter_ultima_consulta_dfe(CNPJ, "PRODUCAO")
    assert log["nsu_enviado"] == 100
    assert log["cstat"] == "138"
    assert log["ultimo_nsu_retornado"] == 105
    assert log["max_nsu_retornado"] == 105


def test_656_preserva_max_valido_e_mostra_nsu_enviado_x_retornado(tmp_path, monkeypatch):
    resposta = RespostaDistribuicao(
        cstat="656",
        motivo="Rejeicao: Consumo Indevido",
        ultimo_nsu=62429,
        max_nsu=0,
        documentos=[],
        xml_retorno="<retDistDFeInt/>",
        ultimo_nsu_informado=True,
        max_nsu_informado=True,
    )
    servico, repo, cliente = _servico(tmp_path, monkeypatch, [resposta])
    repo.salvar_config(CNPJ, "PRODUCAO", uf_autor="MG", ultimo_nsu=62424, max_nsu=62424)

    with pytest.raises(ErroNFe, match="Consumo indevido"):
        servico.sincronizar(1, "senha", "MG", pausa=0)

    config = repo.obter_config(CNPJ, "PRODUCAO")
    assert config["ultimo_nsu"] == 62429
    assert config["max_nsu"] == 62424
    assert len(cliente.chamadas) == 1

    log = repo.obter_ultima_consulta_dfe(CNPJ, "PRODUCAO")
    assert log["nsu_enviado"] == 62424
    assert log["ultimo_nsu_retornado"] == 62429
    assert log["max_nsu_retornado"] == 0

    diagnostico = servico.diagnostico(1)
    assert diagnostico["divergencia_nsu"] is True
    assert "enviou o NSU 000000000062424" in diagnostico["orientacao"]
    assert "000000000062429" in diagnostico["orientacao"]
    assert "Rastro das últimas chamadas" in diagnostico["texto"]
