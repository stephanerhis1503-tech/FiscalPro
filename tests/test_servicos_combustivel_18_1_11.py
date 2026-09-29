from src.services.auditoria_cadastros_excel_service import (
    AuditoriaCadastrosExcelService,
    ResultadoAuditoriaExcel,
    STATUS_SERVICO,
)


def test_servico_explicito_nao_recebe_ncm():
    det = AuditoriaCadastrosExcelService._detectar_servico(
        "SERVIÇO TROCA BOMBA GASOLINA", "4598712"
    )
    assert det is not None
    motivo, confianca = det
    assert "serviço" in motivo.lower()
    assert confianca >= 98


def test_acoes_de_oficina_sao_servico():
    exemplos = [
        "REVISÃO GERAL",
        "TROCA ÓLEO SUSPENSÃO",
        "PINTURA CURVA ESCAPAMENTO",
        "ENRAIAÇÃO RODA",
        "MONTAGEM BIELA",
        "ROSCA BUJAO OLEO",
        "FRETE",
    ]
    for descricao in exemplos:
        assert AuditoriaCadastrosExcelService._detectar_servico(descricao) is not None, descricao


def test_produto_nao_e_confundido_com_servico():
    exemplos = [
        "BOMBA GASOLINA TITAN 160",
        "ESCOVA ARRANQUE CG 150",
        "ACABAMENTO GUIDÃO VERMELHO",
        "MANGUEIRA GASOLINA UNIVERSAL",
    ]
    for descricao in exemplos:
        assert AuditoriaCadastrosExcelService._detectar_servico(descricao) is None, descricao


def test_gasolina_recebe_ncm_sem_forcar_cest():
    inferencia = AuditoriaCadastrosExcelService._inferir_ncm_regra_semantica("GASOLINA")
    assert inferencia is not None
    assert inferencia.ncm == "27101259"
    assert inferencia.confianca >= 95
    assert "CEST" in inferencia.referencia


def test_item_servico_tem_status_proprio_e_sem_ncm_sugerido():
    item = AuditoriaCadastrosExcelService._item_servico(
        linha_excel=10,
        codigo="REVI TITAN",
        descricao="REVISÃO GERAL",
        ncm_atual="00000000",
        cest_atual="",
        motivo="revisão/manutenção",
        confianca=98.0,
        originais={"codigo_barras": "", "ex_tipi": "", "nat_receita": ""},
    )
    assert item.status == STATUS_SERVICO
    assert item.ncm_sugerido == ""
    assert item.ncm_candidatos == ""
    assert "não se aplicam" in item.problema.lower()


def test_resumo_separa_servicos_de_sem_ncm():
    item = AuditoriaCadastrosExcelService._item_servico(
        linha_excel=2,
        codigo="FRETE",
        descricao="FRETE",
        ncm_atual="",
        cest_atual="",
        motivo="frete/encargo de transporte",
        confianca=99.0,
        originais={},
    )
    resultado = ResultadoAuditoriaExcel(arquivo="x.xlsx", planilha="Produtos", itens=[item])
    resumo = resultado.resumo()
    assert resumo["servicos"] == 1
    assert resumo["sem_ncm"] == 0


def test_analise_planilha_separa_servico_e_classifica_gasolina(tmp_path):
    from openpyxl import Workbook

    caminho = tmp_path / "servicos_gasolina.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Cadastro"
    ws.append(["Código", "Descrição", "NCM", "CEST"])
    ws.append(["REVI TITAN", "REVISÃO GERAL", "00000000", ""])
    ws.append(["GASOLINA 10", "GASOLINA", "00000000", ""])
    wb.save(caminho)

    r = AuditoriaCadastrosExcelService.analisar(
        caminho,
        {
            "regime": "Lucro Real",
            "operacao": "Venda",
            "finalidade": "Revenda",
            "uf_origem": "MG",
            "uf_destino": "MG",
        },
    )
    servico, gasolina = r.itens
    assert servico.status == STATUS_SERVICO
    assert servico.ncm_sugerido == ""
    assert gasolina.ncm_sugerido == "27101259"
    assert gasolina.status != STATUS_SERVICO


def test_ficha_servico_nao_forca_campos_de_mercadoria():
    from src.services.auditoria_cadastros_excel_service import ExportadorFichaTributariaCompletaXLSX

    item = AuditoriaCadastrosExcelService._item_servico(
        linha_excel=5,
        codigo="PINTURA",
        descricao="PINTURA CURVA ESCAPAMENTO",
        ncm_atual="00000000",
        cest_atual="",
        motivo="serviço de pintura",
        confianca=98.0,
        originais={},
    )
    linha = ExportadorFichaTributariaCompletaXLSX._linha(item)
    assert linha[3] == ""  # Cód. NCM na ficha de mercadoria
    assert linha[6] == "N/A"  # CST ICMS
    assert linha[7] == "N/A"  # CFOP
    assert linha[11] == "N/A"  # ICMS ST
    assert linha[22] == STATUS_SERVICO
