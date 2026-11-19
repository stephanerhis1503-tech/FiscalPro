"""Regressoes para cadeados NCM 8301.10.00 em MG."""
from decimal import Decimal

from src.services.icms_st_mg_service import ICMSSTMGService
from src.services.xml_icms_st_service import ItemNFe, XMLICMSSTService

DESCRICOES = (
    "CADEADO ESPIRAL 12MM*1500MM UNIVERS",
    "CADEADO ESPIRAL CHAVE K5 10X1500 VARIOS",
)


def _item(descricao, cest="1007500"):
    return ItemNFe(
        numero_item=1, codigo="TDO", descricao=descricao, ncm="83011000",
        cest_xml=cest, cfop="2102", quantidade=Decimal("1"), unidade="UN",
        valor_unitario=Decimal("136.53"), valor_produtos=Decimal("136.53"),
        desconto=Decimal("0"), frete=Decimal("0"), seguro=Decimal("0"),
        outros=Decimal("0"), ipi=Decimal("0"), icms_proprio=Decimal("5.46"),
        aliquota_icms_xml=Decimal("4"), origem_mercadoria="0", cst_icms="00",
        csosn="", base_st_xml=Decimal("0"), icms_st_xml=Decimal("0"),
        base_st_retida_xml=Decimal("0"), icms_st_retido_xml=Decimal("0"),
        fcp_st_xml=Decimal("0"), fcp_st_retido_xml=Decimal("0"),
        base_icms_proprio=Decimal("136.53"),
    )


def test_cadeados_nao_recebem_cest_1007500_ou_mva():
    for descricao in DESCRICOES:
        r = ICMSSTMGService.analisar(
            "83011000", {"uf_origem": "SP", "uf_destino": "MG"}, descricao,
        )
        assert r["decisao_st"] == "NAO"
        assert r["nao_aplicavel"] is True
        assert r["exige_revisao"] is False
        assert r["cest"] == ""
        assert r["cest_sugerido"] == ""
        assert r["mva_original"] is None
        assert r["mva_sugerida"] is None
        assert "CADEADO" in r["status"]


def test_cadeado_nao_calcula_st_com_cest_xml_e_mva_manual():
    r = XMLICMSSTService.calcular_item(
        _item(DESCRICOES[0]), uf_origem="SP", uf_destino="MG",
        aliquota_interna=18, aliquota_interestadual=4,
        aplicar_mva_ajustada=True, mva_manual=50,
    )
    assert r["calculado"] is False
    assert r["nao_aplicavel"] is True
    assert r["icms_st_xml"] == 0
    assert r["cest"] == ""
    assert r["mva_original"] is None
    assert r["conferencia_status"] == "NÃO APLICÁVEL — CADEADO FORA DO CEST 10.075.00"


def test_outros_produtos_8301_nao_sao_bloqueados_globalmente():
    # Nao cria dispensa geral para fechaduras sob subposicoes distintas.
    assert ICMSSTMGService.analisar(
        "83014000", {"uf_origem": "SP", "uf_destino": "MG"},
        "FECHADURA PARA PORTA",
    )["aplicabilidade_segmento"] != "CADEADO_FORA_CEST_1007500"


def test_ncm_830110_com_descricao_incompativel_exige_revisao():
    r = ICMSSTMGService.analisar(
        "83011000", {"uf_origem": "SP", "uf_destino": "MG"},
        "FECHADURA DE PORTA",
    )
    assert r["exige_revisao"]
    assert r["decisao_st"] == "CONDICIONAL"
    assert r["cest"] == ""
    assert r["mva_original"] is None
