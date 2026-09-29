"""Regressões do motor ICMS-ST/MG 17.8.128."""

from decimal import Decimal

from src.services.icms_st_mg_service import ICMSSTMGService
from src.services.xml_icms_st_service import ItemNFe, XMLICMSSTService


def _item(ncm: str, descricao: str, valor: str = "100.00") -> ItemNFe:
    v = Decimal(valor)
    return ItemNFe(
        numero_item=1,
        codigo="TESTE",
        descricao=descricao,
        ncm=ncm,
        cest_xml="",
        cfop="2102",
        quantidade=Decimal("1"),
        unidade="UN",
        valor_unitario=v,
        valor_produtos=v,
        desconto=Decimal("0"),
        frete=Decimal("0"),
        seguro=Decimal("0"),
        outros=Decimal("0"),
        ipi=Decimal("0"),
        icms_proprio=Decimal("0"),
        aliquota_icms_xml=Decimal("0"),
        origem_mercadoria="2",
        cst_icms="00",
        csosn="",
        base_st_xml=Decimal("0"),
        icms_st_xml=Decimal("0"),
        base_st_retida_xml=Decimal("0"),
        icms_st_retido_xml=Decimal("0"),
        fcp_st_xml=Decimal("0"),
        fcp_st_retido_xml=Decimal("0"),
        base_icms_proprio=v,
    )


def _calcular(ncm: str, descricao: str, finalidade: str = "") -> dict:
    return XMLICMSSTService.calcular_item(
        _item(ncm, descricao),
        uf_origem="SP",
        uf_destino="MG",
        aliquota_interna=18,
        aliquota_interestadual=4,
        aplicar_mva_ajustada=True,
        finalidade_automotiva=finalidade,
    )


def test_tampa_valvula_aluminio_continua_no_segmento_autopecas() -> None:
    r = _calcular("76169900", "TAMPA VALVULA BUTYL ALUM AZ 20PC")
    assert r["calculado"] is True
    assert r["cest"] == "01.999.00"
    assert r["mva_original"] == 71.78
    assert round(r["mva_utilizada"], 2) == 101.11


def test_regulador_retificador_volta_a_calcular_mesmo_com_descricao_abreviada() -> None:
    r = _calcular("85118020", "REGUL.RETIF. CBX 200 STRADA 94-02")
    assert r["calculado"] is True
    assert r["cest"] == "01.054.00"
    assert round(r["mva_utilizada"], 2) == 101.11


def test_sensor_inclinacao_volta_a_calcular() -> None:
    r = _calcular("85364100", "SENS.INCL. CG 150 TITAN ESD 11-15")
    assert r["calculado"] is True
    assert r["cest"] == "01.068.00"
    assert round(r["mva_utilizada"], 2) == 101.11


def test_pastilha_freio_volta_a_calcular() -> None:
    r = _calcular("87141000", "PASTILHA DIANT BROS160 18 1886")
    assert r["calculado"] is True
    assert r["cest"] == "01.076.00"
    assert round(r["mva_utilizada"], 2) == 101.11


def test_confirmacao_manual_autopecas_confirma_descricao_comercial_abreviada() -> None:
    r = ICMSSTMGService.analisar(
        "85118020",
        {
            "uf_origem": "SP",
            "uf_destino": "MG",
            "finalidade_automotiva": "AUTOPECA_CONFIRMADA",
        },
        "REGUL.RETIF. CBX 200 STRADA 94-02",
    )
    assert r["segmento"] == "AUTOPEÇAS"
    assert r["cest"] == "01.054.00"
    assert r["confirmado"] is True
    assert r["exige_revisao"] is False
    assert r["decisao_st"] == "SIM"


def test_consumivel_nao_vira_residual_so_por_confirmar_autopecas() -> None:
    r = ICMSSTMGService.analisar(
        "35061090",
        {
            "uf_origem": "SP",
            "uf_destino": "MG",
            "finalidade_automotiva": "AUTOPECA_CONFIRMADA",
        },
        "COLA INST 401 20G BICO PRECISAO",
    )
    assert r["decisao_st"] == "NAO"
    assert r["cest"] == ""
