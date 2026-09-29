"""Regressões do motor contextual de ICMS-ST/MG 17.8.127."""

from decimal import Decimal

from src.services.icms_mg_lote_integracao_service import ICMSMGLoteIntegracaoService
from src.services.icms_st_mg_service import ICMSSTMGService
from src.services.xml_icms_st_service import ItemNFe, XMLICMSSTService


def _item(descricao: str, cest: str = "") -> ItemNFe:
    return ItemNFe(
        numero_item=1,
        codigo="74024",
        descricao=descricao,
        ncm="76169900",
        cest_xml=cest,
        cfop="2102",
        quantidade=Decimal("1"),
        unidade="UN",
        valor_unitario=Decimal("72.87"),
        valor_produtos=Decimal("72.87"),
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
        base_icms_proprio=Decimal("72.87"),
    )


def test_tampa_valvula_aluminio_nao_cai_em_material_de_construcao() -> None:
    r = ICMSSTMGService.analisar(
        "76169900",
        {"uf_origem": "SP", "uf_destino": "MG"},
        "TAMPA VALVULA BUTYL ALUM AZ 20PC",
    )

    assert r["confirmado"] is True
    assert r["decisao_st"] == "SIM"
    assert r["segmento"] == "AUTOPEÇAS"
    assert r["cest"] == "01.999.00"
    assert r["mva_original"] == 71.78
    assert "10.073.00" in r["observacao"]


def test_xml_tampa_valvula_usa_mva_ajustada_de_4_para_18() -> None:
    r = XMLICMSSTService.calcular_item(
        _item("TAMPA VALVULA BUTYL ALUM AZ 20PC"),
        uf_origem="SP",
        uf_destino="MG",
        aliquota_interna=18,
        aliquota_interestadual=4,
        aplicar_mva_ajustada=True,
    )

    assert r["calculado"] is True
    assert r["cest"] == "01.999.00"
    assert r["mva_original"] == 71.78
    assert round(r["mva_utilizada"], 2) == 101.11


def test_candidato_condicional_nao_e_mais_calculado_automaticamente() -> None:
    r = XMLICMSSTService.calcular_item(
        _item("TAMPA GENERICA"),
        uf_origem="SP",
        uf_destino="MG",
        aliquota_interna=18,
        aliquota_interestadual=4,
        finalidade_automotiva="NAO_AUTOMOTIVA",
        aplicar_mva_ajustada=True,
    )

    assert r["calculado"] is False
    assert r["cest"] == ""
    assert r["cest_sugerido"] == "10.073.00"
    assert r["mva_original"] is None
    assert r["mva_sugerida"] == 45.0
    assert r["status"] == "REVISAR ENQUADRAMENTO — CÁLCULO BLOQUEADO"
    assert r["conferencia_status"] == "REVISAR NCM / CEST / MVA"


def test_lote_nao_promove_cest_mva_candidatos_para_st_confirmada() -> None:
    r = ICMSMGLoteIntegracaoService.analisar(
        "76169900",
        contexto={
            "uf_origem": "SP",
            "uf_destino": "MG",
            "finalidade_automotiva": "NAO_AUTOMOTIVA",
            "data_operacao": "2026-09-16",
        },
        descricao="TAMPA GENERICA",
    )

    assert r["st_confirmado"] is False
    assert r["st_decisao_confirmada"] is False
    assert r["cest_sugerido"] == "10.073.00"
    assert r["mva_sugerida"] == 45.0
    assert r["mva_aplicada"] is None
    assert r["mva_ajustada"] is None
    assert r["exige_revisao"] is True
