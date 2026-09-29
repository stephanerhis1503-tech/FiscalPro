from pathlib import Path

from openpyxl import load_workbook

from src.services.analise_tributaria_lote_service import ItemBrutoLote, ResultadoItemLote
from src.services.auditoria_cadastros_excel_service import (
    AuditoriaCadastrosExcelService,
    ExportadorFichaTributariaCompletaXLSX,
    ResultadoAuditoriaExcel,
    STATUS_OK,
    STATUS_REVISAR,
)


def _analise(**kwargs):
    base = dict(
        fonte_tipo="CADASTRO EXCEL",
        arquivo="teste.xlsx",
        documento="Produtos",
        chave="",
        numero_item="1",
        codigo="1",
        descricao="Produto teste",
        ncm="85129000",
        ncm_oficial="Descrição oficial",
        cfop="",
        uf_origem="MG",
        uf_destino="MG",
        data_operacao="2026-09-21",
        status="REVISAR",
        confiabilidade=95.0,
        confirmado=False,
        exige_revisao=True,
        cst_pis_atual="",
        aliquota_pis_atual=0.0,
        cst_pis_esperado="01",
        aliquota_pis_esperada=0.65,
        cst_cofins_atual="",
        aliquota_cofins_atual=0.0,
        cst_cofins_esperado="01",
        aliquota_cofins_esperada=3.0,
        piscofins_status="SUGESTÃO CONDICIONAL — REGIME CUMULATIVO",
        piscofins_confirmado=False,
        aliquota_icms_esperada=18.0,
        icms_status="PADRÃO RESIDUAL — REVISAR EXCEÇÕES DO ANEXO I",
        icms_confirmado=True,
        aliquota_icms_confirmada=True,
        st_status="ICMS-ST NÃO APLICÁVEL",
        st_confirmado=False,
        fcp_esperado=0.0,
        fcp_confirmado=True,
        aliquota_ipi_referencia=0.0,
        tipi_status="TIPI OK",
        pendencias=[
            "SUGESTÃO CONDICIONAL — REGIME CUMULATIVO",
            "PADRÃO RESIDUAL — REVISAR EXCEÇÕES DO ANEXO I",
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
        descricao="Produto teste",
        ncm="85129000",
        uf_origem="MG",
        uf_destino="MG",
        data_operacao="2026-09-21",
        operacao_sugerida="Venda",
    )


def test_alertas_genericos_nao_rebaixam_status_e_preenchem_operacional():
    item = AuditoriaCadastrosExcelService._converter(
        _bruto(),
        _analise(),
        2,
        {
            "red_bc_icms": 0.0,
            "aliq_icms": 0.0,
            "icms_st_indicador": "",
            "mva_st": 0.0,
            "red_bc_st": 0.0,
            "aliq_icms_st": 0.0,
            "aliq_fem": 0.0,
        },
        {
            "regime": "Lucro Presumido",
            "operacao": "Venda",
            "finalidade": "Revenda",
            "uf_origem": "MG",
            "uf_destino": "MG",
        },
    )
    assert item.status == STATUS_OK
    assert item.problema == "Nenhuma divergência objetiva encontrada."
    assert len(item.avisos_informativos) == 3
    assert "Alertas informativos" in item.observacao
    assert item.cst_icms_sugerido == "00"
    assert item.cfop_sugerido == "5102"
    assert item.icms_desonerado_sugerido == "NÃO"
    assert item.cst_ipi_sugerido == ""
    assert item.nat_receita_sugerida == ""


def test_pendencia_especifica_continua_revisar():
    analise = _analise(
        pendencias=[
            "SUGESTÃO CONDICIONAL — REGIME CUMULATIVO",
            "CONDICIONAL — CONFIRMAR FINALIDADE AUTOMOTIVA",
        ],
        st_status="CONDICIONAL — CONFIRMAR FINALIDADE AUTOMOTIVA",
    )
    item = AuditoriaCadastrosExcelService._converter(
        _bruto(), analise, 2, {},
        {"regime": "Lucro Presumido", "operacao": "Venda", "finalidade": "Revenda", "uf_origem": "MG", "uf_destino": "MG"},
    )
    assert item.status == STATUS_REVISAR
    assert "CONFIRMAR FINALIDADE AUTOMOTIVA" in item.problema


def test_responsabilidade_st_confirmada_como_aviso_nao_rebaixa_status():
    analise = _analise(
        st_confirmado=True,
        st_status="ICMS-ST/MG APLICÁVEL",
        cest_esperado="0100700",
        pendencias=[
            "SUGESTÃO CONDICIONAL — REGIME CUMULATIVO",
            "ICMS-ST/MG APLICÁVEL; RESPONSABILIDADE PELO RECOLHIMENTO A REVISAR CONFORME ÂMBITO, INSCRIÇÃO DO REMETENTE E REGIME ESPECIAL",
        ],
    )
    bruto = _bruto()
    bruto.cest_atual = "0100700"
    item = AuditoriaCadastrosExcelService._converter(
        bruto, analise, 2, {},
        {"regime": "Lucro Presumido", "operacao": "Venda", "finalidade": "Revenda", "uf_origem": "MG", "uf_destino": "MG"},
    )
    assert item.status == STATUS_REVISAR
    # Como a responsabilidade ainda depende da operação, CST/CFOP não são inventados
    # e o status também não pode permanecer OK.
    assert item.cst_icms_sugerido == "REVISAR"
    assert item.cfop_sugerido == "REVISAR"
    assert "CST ICMS" in item.problema
    assert "CFOP" in item.problema


def test_exportador_usa_campos_sugeridos_quando_origem_vazia(tmp_path: Path):
    item = AuditoriaCadastrosExcelService._converter(
        _bruto(),
        _analise(),
        2,
        {},
        {"regime": "Lucro Presumido", "operacao": "Venda", "finalidade": "Revenda", "uf_origem": "MG", "uf_destino": "MG"},
    )
    resultado = ResultadoAuditoriaExcel(
        arquivo="teste.xlsx", planilha="Produtos", itens=[item],
        contexto={"regime": "Lucro Presumido", "finalidade": "Revenda", "uf_origem": "MG", "uf_destino": "MG"},
    )
    destino = tmp_path / "ficha.xlsx"
    ExportadorFichaTributariaCompletaXLSX.exportar(resultado, destino)
    wb = load_workbook(destino, read_only=True, data_only=True)
    try:
        ws = wb["Ficha Tributária"]
        assert ws.cell(2, 7).value == "00"
        assert ws.cell(2, 8).value == "5102"
        assert ws.cell(2, 9).value == "NÃO"
        assert ws.cell(2, 17).value in (None, "")
        assert ws.cell(2, 23).value == "OK"
    finally:
        wb.close()
