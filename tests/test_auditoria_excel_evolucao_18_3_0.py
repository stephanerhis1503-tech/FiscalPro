from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.analise_tributaria_lote_service import ItemBrutoLote, ResultadoItemLote
from src.services.auditoria_cadastros_excel_service import (
    AuditoriaCadastrosExcelService,
    STATUS_OK,
    STATUS_REVISAR,
)


def _resultado_st(**kwargs):
    base = dict(
        fonte_tipo="CADASTRO EXCEL",
        arquivo="teste.xlsx",
        documento="Produtos",
        chave="",
        numero_item="1",
        codigo="1",
        descricao="PECA MOTO TESTE",
        ncm="87141000",
        ncm_oficial="Partes e acessorios de motocicletas",
        cfop="",
        uf_origem="MG",
        uf_destino="MG",
        data_operacao="2026-10-22",
        status="REVISAR",
        confiabilidade=95.0,
        confirmado=False,
        exige_revisao=True,
        cst_pis_atual="01",
        aliquota_pis_atual=1.65,
        cst_pis_esperado="01",
        aliquota_pis_esperada=1.65,
        cst_cofins_atual="01",
        aliquota_cofins_atual=7.60,
        cst_cofins_esperado="01",
        aliquota_cofins_esperada=7.60,
        piscofins_status="OK",
        piscofins_confirmado=True,
        aliquota_icms_esperada=18.0,
        icms_status="ICMS/MG",
        icms_confirmado=True,
        aliquota_icms_confirmada=True,
        cest_esperado="0107600",
        st_status="ICMS-ST/MG APLICAVEL",
        st_confirmado=True,
        st_decisao_confirmada=True,
        st_responsabilidade_confirmada=False,
        st_responsabilidade_status="Responsabilidade pelo recolhimento do ICMS-ST exige revisao.",
        mva_aplicada=71.78,
        fcp_esperado=0.0,
        fcp_confirmado=True,
        aliquota_ipi_referencia=0.0,
        tipi_status="TIPI OK",
        pendencias=[
            "ICMS-ST/MG APLICAVEL; RESPONSABILIDADE PELO RECOLHIMENTO A REVISAR"
        ],
    )
    base.update(kwargs)
    return ResultadoItemLote(**base)


def _bruto():
    return ItemBrutoLote(
        fonte_tipo="CADASTRO EXCEL",
        arquivo="teste.xlsx",
        documento="Produtos",
        numero_item="1",
        codigo="1",
        descricao="PECA MOTO TESTE",
        ncm="87141000",
        cest_atual="0107600",
        uf_origem="MG",
        uf_destino="MG",
        data_operacao="2026-10-22",
        operacao_sugerida="Venda",
        cst_pis_atual="01",
        aliquota_pis_atual=1.65,
        cst_cofins_atual="01",
        aliquota_cofins_atual=7.60,
    )


def test_st_referencia_usa_decisao_estruturada_e_nao_texto():
    nao = _resultado_st(
        st_confirmado=False,
        st_decisao_confirmada=True,
        st_status="texto livre sem marcador padronizado",
    )
    revisar = _resultado_st(
        st_confirmado=False,
        st_decisao_confirmada=False,
        st_status="ICMS-ST NAO APLICAVEL",
    )
    assert AuditoriaCadastrosExcelService._st_referencia(nao) == "NÃO"
    assert AuditoriaCadastrosExcelService._st_referencia(revisar) == "REVISAR"


def test_auditoria_separa_cadastro_ok_de_pendencia_operacional():
    item = AuditoriaCadastrosExcelService._converter(
        _bruto(),
        _resultado_st(),
        2,
        {
            "cst_icms": "",
            "cfop": "",
            "icms_desonerado": "",
            "red_bc_icms": 0.0,
            "aliq_icms": 18.0,
            "icms_st_indicador": "SIM",
            "mva_st": 71.78,
            "red_bc_st": 0.0,
            "aliq_icms_st": 18.0,
            "aliq_fem": 0.0,
        },
        {
            "regime": "Lucro Real",
            "operacao": "Venda",
            "finalidade": "Revenda",
            "uf_origem": "MG",
            "uf_destino": "MG",
            "data_operacao": "2026-10-22",
        },
    )
    assert item.status_cadastro == STATUS_OK
    assert item.status_operacao == STATUS_REVISAR
    assert item.status == STATUS_REVISAR
    assert item.pendencias_operacionais
    assert item.st_decisao_confirmada is True
    assert item.st_responsabilidade_confirmada is False


def test_interface_expoe_data_fiscal_e_filtros_por_tipo():
    fonte = Path("src/ui/janela_auditoria_cadastros_excel.py").read_text(encoding="utf-8")
    assert "Data fiscal" in fonte
    assert "var_data_referencia" in fonte
    assert "CEST / ST / MVA" in fonte
    assert "PIS / COFINS" in fonte
    assert "Operação" in fonte
    assert "Processamento" in fonte


def test_falha_do_validador_ncm_nao_e_mais_silenciosa():
    fonte = Path("src/services/auditoria_cadastros_excel_service.py").read_text(encoding="utf-8")
    assert "Falha ao validar o NCM na base oficial instalada" in fonte
    assert "erro_validacao_ncm" in fonte
    assert "não tratar esta linha como validada" in fonte


def test_versao_18_3_0_ou_superior():
    assert tuple(int(p) for p in VERSAO_APP.split(".")) >= (18, 3, 0)
