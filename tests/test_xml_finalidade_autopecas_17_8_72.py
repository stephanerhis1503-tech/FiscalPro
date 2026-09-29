"""Regressões da finalidade automotiva no XML → ICMS-ST 17.8.72."""

from __future__ import annotations

from decimal import Decimal

from src.services.icms_st_mg_service import ICMSSTMGService
from src.services.xml_icms_st_service import ItemNFe, XMLICMSSTService


def _item(numero: int, ncm: str, descricao: str, cest: str) -> ItemNFe:
    return ItemNFe(
        numero_item=numero,
        codigo=str(numero),
        descricao=descricao,
        ncm=ncm,
        cest_xml=cest,
        cfop="2102",
        quantidade=Decimal("1"),
        unidade="UN",
        valor_unitario=Decimal("100"),
        valor_produtos=Decimal("100"),
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
        base_icms_proprio=Decimal("100"),
    )


def _calcular(item: ItemNFe) -> dict:
    return XMLICMSSTService.calcular_item(
        item,
        uf_origem="SP",
        uf_destino="MG",
        aliquota_interna=18,
        aliquota_interestadual=4,
        aplicar_mva_ajustada=True,
    )


def test_travas_de_moto_nao_usam_cest_de_construcao() -> None:
    for descricao in (
        "TRAVA.BANCO BIZ 125 ES 06-15",
        "TRAVA.T.LAT. CG 150 TITAN KS 04-",
    ):
        resultado = _calcular(_item(9, "83014000", descricao, "1007500"))
        assert resultado["cest"] == "01.999.00"
        assert resultado["mva_original"] == 71.78
        assert round(resultado["mva_utilizada"], 2) == 101.11
        assert resultado["conferencia_status"] == "ST NÃO DESTACADO"


def test_cabos_abreviados_recebem_residual_e_mva() -> None:
    for descricao in (
        "CAB.MOT.PART. YS 150 FAZER SED",
        "CAB.MOT.PART. CG 150 TITAN ESC",
        "CAB.BAT.POS. CG 150 TITAN ESD",
    ):
        resultado = _calcular(_item(11, "85444200", descricao, "0199900"))
        assert resultado["cest"] == "01.999.00"
        assert resultado["mva_original"] == 71.78
        assert resultado["finalidade_automotiva_origem"] == "DESCRIÇÃO/CEST DO XML"


def test_descricao_generica_continua_condicional() -> None:
    assert ICMSSTMGService.inferir_finalidade_automotiva("PRODUTO GENERICO") == "NAO_INFORMADA"


def test_cests_especificos_permanecem_prioritarios() -> None:
    casos = (
        (_item(12, "85443000", "FIACAO.PRIN. FACTOR 125 YBR ED", "0107300"), "01.073.00"),
        (_item(15, "85365090", "INTER.TRAS.FACTOR 125 YBR ED", "0106500"), "01.065.00"),
    )
    for item, cest in casos:
        resultado = _calcular(item)
        assert resultado["cest"] == cest
        assert resultado["mva_original"] == 71.78
