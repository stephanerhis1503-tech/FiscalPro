"""Protecoes do painel de aliquotas RTC 2026/2027: nao ha efeito fiscal."""
from decimal import Decimal

import pytest

from src.services.rtc_aliquotas_service import ServicoAliquotasRTC


def test_regras_2026_preservadas_e_cbs_2027_nao_definitiva():
    svc = ServicoAliquotasRTC()
    r26, r27 = svc.consultar(2026), svc.consultar(2027)
    assert r26.cbs_vigente == Decimal("0.90")
    assert r26.ibs_uf == Decimal("0.10")
    assert r26.ibs_municipal == Decimal("0")
    assert r27.cbs_vigente is None
    assert r27.ibs_uf == Decimal("0.05")
    assert r27.ibs_municipal == Decimal("0.05")
    assert r27.referencia_tcu_cbs == Decimal("11.30")
    assert r27.cbs_cenario_tcu == Decimal("11.20")
    assert r27.status == "CBS_AGUARDANDO_RESOLUCAO_SENADO"


def test_simulacao_2026_ano_teste_sem_efeito_fiscal():
    dado = ServicoAliquotasRTC.simular(
        "2026", "1.000,00", regime="Lucro Real"
    )
    assert dado["status"] == "SIMULACAO_TESTE_2026"
    assert dado["cbs"] == Decimal("9.00")
    assert dado["ibs_uf"] == Decimal("1.00")
    assert dado["ibs_municipal"] == Decimal("0.00")
    assert dado["total"] == Decimal("10.00")
    assert dado["efeito_fiscal"] is False


def test_2027_cbs_bloqueada_por_padrao():
    dado = ServicoAliquotasRTC.simular(2027, "1000", regime="Lucro Presumido")
    assert dado["status"] == "CBS_PENDENTE_DEFINICAO"
    assert dado["cbs"] is None
    assert dado["total"] is None
    assert dado["p_cbs_usado"] is None
    assert dado["ibs_uf"] == Decimal("0.50")
    assert dado["ibs_municipal"] == Decimal("0.50")


def test_simulacao_tcu_somente_com_ativacao_explicita():
    dado = ServicoAliquotasRTC.simular(
        2027, "1.234,56", regime="Lucro Real", usar_cenario_tcu=True
    )
    assert dado["status"] == "CENARIO_TCU_NAO_OFICIAL"
    assert dado["p_cbs_usado"] == Decimal("11.20")
    assert dado["cbs"] == Decimal("138.27")
    assert dado["ibs_uf"] == Decimal("0.62")
    assert dado["ibs_municipal"] == Decimal("0.62")
    assert dado["total"] == Decimal("139.51")
    assert dado["efeito_fiscal"] is False


@pytest.mark.parametrize(
    "cst,cclass",
    [("200", "200001"), ("620", "620001"), ("000", "000002"), ("090", "000001")],
)
def test_regras_especiais_revisar_sem_calcular_cbs(cst, cclass):
    dado = ServicoAliquotasRTC.simular(
        2027, "1000", cst=cst, cclass_trib=cclass,
        regime="Lucro Real", usar_cenario_tcu=True,
    )
    assert dado["status"] == "REGRA_ESPECIAL_REVISAR"
    assert dado["total"] is None
    assert dado["cbs"] is None
    assert dado["ibs_uf"] is None


@pytest.mark.parametrize("regime", ["Simples Nacional", "Nao informado"])
def test_regime_nao_simulavel(regime):
    dado = ServicoAliquotasRTC.simular(
        2026, "1000", regime=regime
    )
    assert dado["status"] == "REVISAR_REGIME"
    assert dado["cbs"] is None


@pytest.mark.parametrize("ano", [2025, 2028, "", "2026.0", "2027abc"])
def test_anos_fora_do_escopo_bloqueados(ano):
    with pytest.raises(ValueError):
        ServicoAliquotasRTC.consultar(ano)


@pytest.mark.parametrize("base", ["", "-1", "0", "1.234.56", "1,234.56", "2,999", "NaN", "Infinity", 2.4])
def test_bases_invalidas(base):
    with pytest.raises(ValueError):
        ServicoAliquotasRTC.simular(2027, base, regime="Lucro Real")


def test_taxa_nao_entra_na_apuracao_xml():
    import inspect
    from src.ui.painel_documentos_fiscais import PainelDocumentosFiscais
    from src.services import rtc_aliquotas_service
    fonte = inspect.getsource(PainelDocumentosFiscais)
    assert "PainelAliquotasRTC" in fonte
    assert "importar" not in inspect.getsource(rtc_aliquotas_service.ServicoAliquotasRTC)
    assert "conexao" not in inspect.getsource(rtc_aliquotas_service.ServicoAliquotasRTC)
