from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

import src.nfe.servico as servico_mod
from src.nfe.cliente import ErroNFe, RespostaDistribuicao
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


def _servico(tmp_path: Path):
    cert = tmp_path / "certificado.pfx"
    cert.write_bytes(b"teste")
    repo = RepositorioManifestacaoNFe(tmp_path / "manifestacao.db")
    return ServicoManifestacaoNFe(repo, RepoEmpresasFake(str(cert))), repo


def test_consulta_chave_respeita_bloqueio_656_existente(tmp_path, monkeypatch):
    servico, repo = _servico(tmp_path)
    ate = (datetime.now() + timedelta(minutes=40)).isoformat(timespec="seconds")
    repo.salvar_config(
        CNPJ, "PRODUCAO", uf_autor="MG", ultimo_nsu=62471, max_nsu=62433,
        bloqueado_ate=ate, ultimo_cstat="656", ultimo_motivo="Consumo Indevido",
    )

    class ClienteNaoPodeSerChamado:
        def __init__(self, *_a, **_k):
            raise AssertionError("cliente não deveria ser criado durante bloqueio 656")

    monkeypatch.setattr(servico_mod, "ClienteNFeAmbienteNacional", ClienteNaoPodeSerChamado)

    with pytest.raises(ErroNFe, match="inclusive consulta por chave"):
        servico.consultar_por_chave(1, "senha", "MG", CHAVE)


def test_limite_local_de_20_consultas_por_chave(tmp_path, monkeypatch):
    servico, repo = _servico(tmp_path)
    for i in range(20):
        chave = CHAVE[:-2] + f"{i:02d}"
        repo.registrar_consulta_chave(CNPJ, "PRODUCAO", chave, "137", "Nenhum documento localizado")

    class ClienteNaoPodeSerChamado:
        def __init__(self, *_a, **_k):
            raise AssertionError("cliente não deveria ser criado após 20 consultas na janela")

    monkeypatch.setattr(servico_mod, "ClienteNFeAmbienteNacional", ClienteNaoPodeSerChamado)

    with pytest.raises(ErroNFe, match="20 consultas por chave"):
        servico.consultar_por_chave(1, "senha", "MG", CHAVE)


def test_656_por_chave_bloqueia_sem_alterar_nsu(tmp_path, monkeypatch):
    servico, repo = _servico(tmp_path)
    repo.salvar_config(CNPJ, "PRODUCAO", uf_autor="MG", ultimo_nsu=62471, max_nsu=62433)

    resposta = RespostaDistribuicao(
        cstat="656",
        motivo="Consumo indevido",
        ultimo_nsu=0,
        max_nsu=0,
        documentos=[],
        xml_retorno="<retDistDFeInt/>",
    )

    class ClienteFake:
        def __init__(self, *_a, **_k):
            pass

        def consultar_por_chave(self, *_a, **_k):
            return resposta

    monkeypatch.setattr(servico_mod, "ClienteNFeAmbienteNacional", ClienteFake)

    with pytest.raises(ErroNFe, match="cStat 656"):
        servico.consultar_por_chave(1, "senha", "MG", CHAVE)

    config = repo.obter_config(CNPJ, "PRODUCAO")
    assert config["ultimo_nsu"] == 62471
    assert config["max_nsu"] == 62433
    assert config["ultimo_cstat"] == "656_CHAVE"
    assert config["bloqueado_ate"]
    assert repo.contar_consultas_chave_ultima_hora(CNPJ, "PRODUCAO") == 1
