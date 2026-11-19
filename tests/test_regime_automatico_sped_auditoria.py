"""Regime automaticamente identificado no SPED sem inventar cadastro."""
from src.services.empresas_regimes_service import EmpresasRegimesService


def test_nome_legal_trilha_carrega_lucro_real(monkeypatch):
    monkeypatch.setattr(EmpresasRegimesService, "listar_cadastros", classmethod(
        lambda cls, *args, **kwargs: ()
    ))
    regime = EmpresasRegimesService.resolver_regime_sped(
        "MEGA MOTOS TRILHA COMERCIO E SERVICOS LTDA", "11809691000195"
    )
    assert regime == "LUCRO REAL"


def test_cnpj_cadastrado_prevalece_sobre_nome(monkeypatch):
    monkeypatch.setattr(EmpresasRegimesService, "listar_cadastros", classmethod(
        lambda cls, *args, **kwargs: (
            {"nome": "EMPRESA ALFA", "cnpj": "11222333000144", "regime": "LUCRO PRESUMIDO"},
        )
    ))
    assert EmpresasRegimesService.resolver_regime_sped(
        "MEGA MOTOS TRILHA COMERCIO E SERVICOS LTDA", "11222333000144"
    ) == "LUCRO PRESUMIDO"


def test_cnpj_com_regimes_conflitantes_exige_revisao(monkeypatch):
    monkeypatch.setattr(EmpresasRegimesService, "listar_cadastros", classmethod(
        lambda cls, *args, **kwargs: (
            {"nome": "EMPRESA ALFA", "cnpj": "11222333000144", "regime": "LUCRO REAL"},
            {"nome": "EMPRESA BETA", "cnpj": "11222333000144", "regime": "LUCRO PRESUMIDO"},
        )
    ))
    assert EmpresasRegimesService.resolver_regime_sped("EMPRESA", "11222333000144") == ""


def test_empresa_desconhecida_nao_presume_regime(monkeypatch):
    monkeypatch.setattr(EmpresasRegimesService, "listar_cadastros", classmethod(
        lambda cls, *args, **kwargs: ()
    ))
    assert EmpresasRegimesService.resolver_regime_sped(
        "SOCIEDADE SEM CADASTRO LTDA", "99888777000166"
    ) == ""


def test_limpeza_do_campo_nao_deve_manter_regime_anterior():
    codigo = open(
        "src/ui/janela_sped_inteligente.py", encoding="utf-8"
    ).read()
    assert "self.aud_regime_var.set(regime_sped)" in codigo
    assert "self.resultado.estatisticas.cnpj" in codigo
