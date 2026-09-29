from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.entregas.repositorio import EntregasRepositorio
from src.financeiro.repositorio import ContasPagarRepositorio
from src.nfse.repositorio import RepositorioNFSe
from src.services.empresas_regimes_service import EmpresasRegimesService


def _central(tmp_path: Path) -> EntregasRepositorio:
    repo = EntregasRepositorio(tmp_path / "central.db")
    repo.salvar_empresa("Mega Motos Comércio", regime="LUCRO PRESUMIDO")
    repo.salvar_empresa(
        "Empresa Integrada Ltda",
        cnpj="12345678000190",
        regime="LUCRO REAL",
        manual=True,
    )
    return repo


def test_versao_18_2_18_e_aba_empresas():
    assert tuple(int(x) for x in VERSAO_APP.split(".")) >= (18, 2, 18)
    texto = Path("src/ui/janela_principal.py").read_text(encoding="utf-8")
    assert "aba_empresas" in texto
    assert 'text="  Empresas  "' in texto
    assert "PainelEmpresas" in texto


def test_banco_central_prevalece_sobre_default_do_regime(tmp_path, monkeypatch):
    repo = _central(tmp_path)
    empresa = repo.obter_empresa_por_nome("Mega Motos Comércio")
    repo.atualizar_empresa(
        int(empresa["id"]),
        nome="Mega Motos Comércio",
        cnpj="11222333000144",
        regime="LUCRO REAL",
    )
    monkeypatch.setattr("src.services.empresas_regimes_service.BANCO_ENTREGAS", repo.banco)

    perfil = EmpresasRegimesService.obter_perfil("Mega Motos Comércio")
    assert perfil is not None
    assert perfil.regime == "LUCRO REAL"
    assert perfil.pis_padrao == 1.65


def test_contas_pagar_recebe_empresa_do_cadastro_central(tmp_path, monkeypatch):
    repo_central = _central(tmp_path)
    monkeypatch.setattr("src.services.empresas_regimes_service.BANCO_ENTREGAS", repo_central.banco)

    financeiro = ContasPagarRepositorio(tmp_path / "financeiro.db")
    empresas = financeiro.listar_empresas()
    assert "Empresa Integrada Ltda" in empresas


def test_nfse_recebe_identidade_central_sem_certificado(tmp_path, monkeypatch):
    repo_central = _central(tmp_path)
    monkeypatch.setattr("src.services.empresas_regimes_service.BANCO_ENTREGAS", repo_central.banco)

    nfse = RepositorioNFSe(tmp_path / "nfse.db")
    empresas = nfse.listar_empresas()
    integrada = next(e for e in empresas if e["nome"] == "Empresa Integrada Ltda")
    assert integrada["cnpj"] == "12345678000190"
    assert integrada["certificado_path"] == ""
    assert integrada["ambiente"] == "PRODUCAO"


def test_nfse_preserva_certificado_ao_ressincronizar_nome(tmp_path, monkeypatch):
    repo_central = _central(tmp_path)
    monkeypatch.setattr("src.services.empresas_regimes_service.BANCO_ENTREGAS", repo_central.banco)
    nfse = RepositorioNFSe(tmp_path / "nfse.db")
    empresa = next(e for e in nfse.listar_empresas() if e["nome"] == "Empresa Integrada Ltda")
    nfse.salvar_empresa(
        nome=empresa["nome"],
        cnpj=empresa["cnpj"],
        certificado_path=r"C:\\certificados\\empresa.pfx",
        ambiente="PRODUCAO",
        empresa_id=empresa["id"],
    )

    central = repo_central.obter_empresa_por_nome("Empresa Integrada Ltda")
    repo_central.atualizar_empresa(
        int(central["id"]),
        nome="Empresa Integrada Nova Ltda",
        cnpj="12345678000190",
        regime="LUCRO REAL",
    )
    empresas = nfse.listar_empresas()
    atual = next(e for e in empresas if e["cnpj"] == "12345678000190")
    assert atual["nome"] == "Empresa Integrada Nova Ltda"
    assert atual["certificado_path"].endswith("empresa.pfx")
