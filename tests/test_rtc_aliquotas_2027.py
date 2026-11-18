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
    from pathlib import Path
    from src.services import rtc_aliquotas_service
    # Ler o codigo da central sem importar a cadeia de certificados A1.
    fonte = (Path(__file__).parents[1] / "src/ui/painel_documentos_fiscais.py").read_text(encoding="utf-8")
    assert "PainelAliquotasRTC" in fonte
    assert "importar" not in inspect.getsource(rtc_aliquotas_service.ServicoAliquotasRTC)
    assert "conexao" not in inspect.getsource(rtc_aliquotas_service.ServicoAliquotasRTC)



ITEM_VENDA = {
    "numero_nf": "12345",
    "numero_item": "1",
    "descricao": "Produto de venda comum",
    "direcao": "SAIDA",
    "cfop": "5102",
    "cst_ibscbs": "000",
    "cclass_trib": "000001",
    "base_ibs_cbs": "1000.00",
    "status_auditoria": "OK",
}


def test_simulacao_item_venda_2027_sem_cbs_definitiva_e_sem_mutacao():
    item = ITEM_VENDA.copy()
    retorno = ServicoAliquotasRTC.simular_item_2027(
        item, regime="Lucro Real"
    )
    assert retorno["status"] == "CBS_PENDENTE_DEFINICAO"
    assert retorno["ibs_uf"] == Decimal("0.50")
    assert retorno["ibs_municipal"] == Decimal("0.50")
    assert retorno["cbs"] is None
    assert retorno["efeito_fiscal"] is False
    assert item == ITEM_VENDA


def test_simulacao_item_2027_tcu_somente_explicitamente():
    retorno = ServicoAliquotasRTC.simular_item_2027(
        ITEM_VENDA, regime="Lucro Real", usar_cenario_tcu=True
    )
    assert retorno["status"] == "CENARIO_TCU_NAO_OFICIAL"
    assert retorno["cbs"] == Decimal("112.00")
    assert retorno["total"] == Decimal("113.00")


@pytest.mark.parametrize(
    "alteracoes,status",
    [
        ({"direcao": "ENTRADA"}, "REVISAR_TIPO_OPERACAO"),
        ({"direcao": "GARANTIA"}, "REVISAR_TIPO_OPERACAO"),
        ({"status_auditoria": "REVISAR"}, "REVISAR_AUDITORIA_XML"),
        ({"status_auditoria": "REGRA ESPECIAL"}, "REVISAR_AUDITORIA_XML"),
        ({"cfop": "5405"}, "REVISAR_CFOP_ST"),
        ({"cfop": "6108"}, "REVISAR_CFOP_OPERACAO"),
        ({"cfop": "5152"}, "REVISAR_CFOP_OPERACAO"),
        ({"base_ibs_cbs": ""}, "REVISAR_DADOS_ITEM"),
    ],
)
def test_item_fora_do_escopo_nao_recebe_aliquota(alteracoes, status):
    item = {**ITEM_VENDA, **alteracoes}
    retorno = ServicoAliquotasRTC.simular_item_2027(
        item, regime="Lucro Real", usar_cenario_tcu=True
    )
    assert retorno["status"] == status
    assert retorno["cbs"] is None
    assert retorno["ibs_uf"] is None
    assert retorno["total"] is None
    assert retorno["efeito_fiscal"] is False


def test_item_cst_especial_nao_calcula():
    item = {**ITEM_VENDA, "cst_ibscbs": "200", "cclass_trib": "200001"}
    resultado = ServicoAliquotasRTC.simular_item_2027(
        item, regime="Lucro Real", usar_cenario_tcu=True
    )
    assert resultado["status"] == "REGRA_ESPECIAL_REVISAR"
    assert resultado["cbs"] is None


def test_item_simples_nao_calcula():
    resultado = ServicoAliquotasRTC.simular_item_2027(
        ITEM_VENDA, regime="Simples Nacional", usar_cenario_tcu=True
    )
    assert resultado["status"] == "REVISAR_REGIME"
    assert resultado["total"] is None



def test_5405_requer_flag_explicita_e_nao_conclui_incidencia():
    item = {**ITEM_VENDA, "cfop": "5405"}
    revisao = ServicoAliquotasRTC.simular_item_2027(
        item, regime="Lucro Real"
    )
    assert revisao["status"] == "REVISAR_CFOP_ST"
    assert revisao["cbs"] is None
    assert "NAO define" in revisao["observacao"]

    hipotese = ServicoAliquotasRTC.simular_item_2027(
        item, regime="Lucro Real", permitir_venda_icms_st=True
    )
    assert hipotese["status"] == "CENARIO_CONDICIONAL_CFOP_5405"
    assert hipotese["ibs_uf"] == Decimal("0.50")
    assert hipotese["ibs_municipal"] == Decimal("0.50")
    assert hipotese["cbs"] is None
    assert hipotese["total"] is None
    assert hipotese["efeito_fiscal"] is False
    assert item["cfop"] == "5405"


def test_5405_hipotese_tcu_nao_oficial_e_sem_efeito_fiscal():
    item = {**ITEM_VENDA, "cfop": "5405"}
    hipotese = ServicoAliquotasRTC.simular_item_2027(
        item, regime="Lucro Real", usar_cenario_tcu=True,
        permitir_venda_icms_st=True
    )
    assert hipotese["status"] == "CENARIO_CONDICIONAL_CFOP_5405"
    assert hipotese["cbs"] == Decimal("112.00")
    assert hipotese["total"] == Decimal("113.00")
    assert "HIPOTESE CONDICIONAL" in hipotese["observacao"]
    assert hipotese["efeito_fiscal"] is False


@pytest.mark.parametrize("cfop", ["6108", "5152", "5949", "6411", "6404"])
def test_hipotese_5405_nao_liberar_outras_operacoes(cfop):
    resultado = ServicoAliquotasRTC.simular_item_2027(
        {**ITEM_VENDA, "cfop": cfop}, regime="Lucro Real",
        permitir_venda_icms_st=True, usar_cenario_tcu=True
    )
    assert resultado["status"] == "REVISAR_CFOP_OPERACAO"
    assert resultado["total"] is None


def test_5405_com_regra_especial_permanece_revisar():
    resultado = ServicoAliquotasRTC.simular_item_2027(
        {**ITEM_VENDA, "cfop": "5405", "cst_ibscbs": "200",
         "cclass_trib": "200001"}, regime="Lucro Real",
        permitir_venda_icms_st=True, usar_cenario_tcu=True
    )
    assert resultado["status"] == "REGRA_ESPECIAL_REVISAR"
    assert resultado["total"] is None
