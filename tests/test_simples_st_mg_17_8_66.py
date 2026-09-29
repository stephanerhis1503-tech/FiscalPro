from decimal import Decimal
from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.xml_icms_st_service import ItemNFe, XMLICMSSTService


def _item(*, origem="0", base="1000", valor="1000", icms="0", cst="", csosn="102") -> ItemNFe:
    return ItemNFe(
        numero_item=1,
        codigo="SN-1",
        descricao="PEÇA DE MOTOCICLETA ST",
        ncm="87141000",
        cest_xml="0107600",
        cfop="2102",
        quantidade=Decimal("1"),
        unidade="UN",
        valor_unitario=Decimal(valor),
        valor_produtos=Decimal(valor),
        desconto=Decimal("0"),
        frete=Decimal("0"),
        seguro=Decimal("0"),
        outros=Decimal("0"),
        ipi=Decimal("0"),
        icms_proprio=Decimal(icms),
        aliquota_icms_xml=Decimal("0"),
        origem_mercadoria=origem,
        cst_icms=cst,
        csosn=csosn,
        base_st_xml=Decimal("0"),
        icms_st_xml=Decimal("0"),
        base_st_retida_xml=Decimal("0"),
        icms_st_retido_xml=Decimal("0"),
        fcp_st_xml=Decimal("0"),
        fcp_st_retido_xml=Decimal("0"),
        base_icms_proprio=Decimal(base),
    )


def test_1766_simples_interestadual_deduz_12_e_forca_mva_original():
    r = XMLICMSSTService.calcular_item(
        _item(),
        uf_origem="SP",
        uf_destino="MG",
        aliquota_interna=18,
        aliquota_interestadual=12,
        remetente_simples=True,
        aplicar_mva_ajustada=True,
        deduzir_icms_inter_sem_destaque=False,  # no Simples a dedução legal é automática
    )
    assert r["icms_proprio_deduzir"] == 120.0
    assert r["deducao_icms_origem"] == "ALÍQUOTA INTERESTADUAL — SIMPLES NACIONAL"
    assert r["mva_utilizada"] == 71.78
    assert r["tipo_mva"] == "MVA ORIGINAL"
    assert r["mva_ajustada"] is None
    assert "não representa crédito fiscal escritural" in r["deducao_icms_observacao"]


def test_1766_simples_importado_sugere_4_porcento_quando_aliquota_vazia():
    r = XMLICMSSTService.calcular_item(
        _item(origem="1"),
        uf_origem="SP",
        uf_destino="MG",
        aliquota_interna=18,
        aliquota_interestadual=None,
        remetente_simples=True,
    )
    assert r["aliquota_interestadual"] == 4.0
    assert r["icms_proprio_deduzir"] == 40.0
    assert r["tipo_mva"] == "MVA ORIGINAL"


def test_1766_simples_operacao_interna_usa_aliquota_interna_na_deducao():
    r = XMLICMSSTService.calcular_item(
        _item(),
        uf_origem="MG",
        uf_destino="MG",
        aliquota_interna=18,
        aliquota_interestadual=None,
        remetente_simples=True,
    )
    assert r["aliquota_interestadual"] == 18.0
    assert r["icms_proprio_deduzir"] == 180.0
    assert r["deducao_icms_origem"] == "ALÍQUOTA INTERNA — SIMPLES NACIONAL"


def test_1766_ajuste_manual_continua_tendo_prioridade_no_simples():
    r = XMLICMSSTService.calcular_item(
        _item(),
        uf_origem="SP",
        uf_destino="MG",
        aliquota_interna=18,
        aliquota_interestadual=12,
        remetente_simples=True,
        icms_proprio_manual=99.99,
    )
    assert r["icms_proprio_deduzir"] == 99.99
    assert r["deducao_icms_origem"] == "AJUSTE MANUAL"


def test_1766_interface_explica_mva_original_e_deducao_automatica_simples():
    raiz = Path(__file__).resolve().parents[1]
    ui = (raiz / "src/ui/janela_xml_icms_st.py").read_text(encoding="utf-8")
    assert "automático no Simples" in ui
    assert "Simples Nacional: usa MVA original" in ui
    assert "não cria crédito escritural" in ui
    assert tuple(int(p) for p in VERSAO_APP.split(".")) >= (17, 8, 66)
