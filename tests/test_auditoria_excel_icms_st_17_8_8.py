from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

from src.core.app_info import VERSAO_APP
from src.services.auditoria_cadastros_excel_service import AuditoriaCadastrosExcelService
from src.services.xml_icms_st_service import ItemNFe, XMLICMSSTService


def _item(*, cst="00", icms="0", base="1000") -> ItemNFe:
    return ItemNFe(
        numero_item=1,
        codigo="X",
        descricao="PEÇA DE MOTOCICLETA",
        ncm="87141000",
        cest_xml="0107600",
        cfop="2102",
        quantidade=Decimal("1"),
        unidade="UN",
        valor_unitario=Decimal("1000"),
        valor_produtos=Decimal("1000"),
        desconto=Decimal("0"),
        frete=Decimal("0"),
        seguro=Decimal("0"),
        outros=Decimal("0"),
        ipi=Decimal("0"),
        icms_proprio=Decimal(icms),
        aliquota_icms_xml=Decimal("0"),
        origem_mercadoria="0",
        cst_icms=cst,
        csosn="",
        base_st_xml=Decimal("0"),
        icms_st_xml=Decimal("0"),
        base_st_retida_xml=Decimal("0"),
        icms_st_retido_xml=Decimal("0"),
        fcp_st_xml=Decimal("0"),
        fcp_st_retido_xml=Decimal("0"),
        base_icms_proprio=Decimal(base),
    )


def test_1788_deduz_icms_interestadual_sem_vicms_fornecedor_normal():
    r = XMLICMSSTService.calcular_item(
        _item(cst="00", icms="0", base="1000"),
        uf_origem="SP",
        uf_destino="MG",
        aliquota_interna=18,
        aliquota_interestadual=12,
        remetente_simples=False,
        aplicar_mva_ajustada=False,
        deduzir_icms_inter_sem_destaque=True,
    )
    assert r["icms_proprio_deduzir"] == 120.0
    assert r["deducao_icms_origem"] == "ALÍQUOTA INTERESTADUAL"
    assert r["mva_utilizada"] == 71.78
    assert r["tipo_mva"] == "MVA ORIGINAL"
    assert "não representa crédito fiscal escritural" in r["deducao_icms_observacao"]


def test_1788_simples_usa_deducao_legal_e_cst_60_normal_nao_estima():
    simples = XMLICMSSTService.calcular_item(
        _item(cst="00"), uf_origem="SP", uf_destino="MG", aliquota_interna=18,
        aliquota_interestadual=12, remetente_simples=True, aplicar_mva_ajustada=False,
    )
    retido = XMLICMSSTService.calcular_item(
        _item(cst="60"), uf_origem="SP", uf_destino="MG", aliquota_interna=18,
        aliquota_interestadual=12, remetente_simples=False, aplicar_mva_ajustada=False,
    )
    assert simples["icms_proprio_deduzir"] == 120.0
    assert simples["deducao_icms_origem"] == "ALÍQUOTA INTERESTADUAL — SIMPLES NACIONAL"
    assert "art. 22, § 1º" in simples["deducao_icms_observacao"]
    assert retido["icms_proprio_deduzir"] == 0.0


def test_1788_valor_manual_tem_prioridade():
    r = XMLICMSSTService.calcular_item(
        _item(cst="00"), uf_origem="SP", uf_destino="MG", aliquota_interna=18,
        aliquota_interestadual=12, remetente_simples=False, aplicar_mva_ajustada=False,
        icms_proprio_manual=99.99,
    )
    assert r["icms_proprio_deduzir"] == 99.99
    assert r["deducao_icms_origem"] == "AJUSTE MANUAL"


def test_1788_auditoria_excel_sinaliza_retentor_fora_do_ncm_40169300(tmp_path):
    caminho = tmp_path / "cadastro.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Produtos"
    ws.append(["Código", "Descrição", "NCM", "CEST", "CST PIS", "CST COFINS", "CST IPI"])
    ws.append(["91002808", "RETENTOR GARFO DIANT", "84879000", "01.075.00", "49", "49", "53"])
    ws.append(["M730001047000", "RETENTOR PINHÃO TITAN", "40169300", "01.007.00", "49", "49", "53"])
    wb.save(caminho)

    r = AuditoriaCadastrosExcelService.analisar(
        caminho,
        {"regime": "Lucro Real", "operacao": "Venda", "finalidade": "Revenda", "uf_origem": "MG", "uf_destino": "MG"},
    )
    primeiro, segundo = r.itens
    assert primeiro.ncm_sugerido == "40169300"
    assert primeiro.cest_sugerido == "01.007.00"
    assert primeiro.status == "REVISAR"
    assert "RETENTOR" in primeiro.problema
    assert segundo.ncm_sugerido == "40169300"


def test_1788_interface_xml_mais_enxuta_e_modulo_excel_integrado():
    raiz = Path(__file__).resolve().parents[1]
    ui_xml = (raiz / "src/ui/janela_xml_icms_st.py").read_text(encoding="utf-8")
    principal = (raiz / "src/ui/janela_principal.py").read_text(encoding="utf-8")
    assert '"mva_usada", "deducao_icms", "st_calc", "st_xml"' in ui_xml
    assert '"valor", "ipi", "com_ipi"' not in ui_xml
    assert "não cria crédito escritural" in ui_xml
    assert "Auditoria de cadastro por Excel" in principal
    assert "JanelaAuditoriaCadastrosExcel" in principal
    assert tuple(int(parte) for parte in VERSAO_APP.split(".")) >= (17, 8, 8)
