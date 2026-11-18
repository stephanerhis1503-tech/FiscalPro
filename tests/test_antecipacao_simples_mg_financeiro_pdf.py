"""Teste do novo layout financeiro e da antecipacao SN sem misturar ICMS-ST."""
from decimal import Decimal
from pathlib import Path
import zipfile

from openpyxl import Workbook, load_workbook
import pytest
from pypdf import PdfReader

from src.financeiro.pdf_identidade_fiscalpro import gerar_pdf_tabela
from src.financeiro.documentos_contabilidade import GestorDocumentosFinanceiros
from src.financeiro.relatorio_pagas import GeradorRelatorioContasPagas
from src.services.antecipacao_simples_mg_service import calcular_item
from src.services.antecipacao_simples_mg_xlsx import adicionar_aba_antecipacao


def item(**kw):
    return {
        "numero_item": 1, "codigo": "A1", "descricao": "Peça para revenda",
        "ncm": "87141000", "cfop": "6102",
        "valor_produtos": 100, "desconto": 0, "frete": 0,
        "seguro": 0, "outros": 0, "ipi": 0,
        "icms_st_xml": 0, "icms_st_retido_xml": 0,
        "base_st_retida_xml": 0, "cst_icms": "00", "csosn": "", **kw
    }


def calcular(**kw):
    return calcular_item(
        item(), {"st_oficial": {"encontrado": False}},
        uf_origem="SP", uf_destino="MG", destinatario_simples=True,
        finalidade="REVENDA", aliquota_interna="18",
        aliquota_interestadual="12", **kw
    )


def test_formula_antecipacao_recompoe_base_sem_mva():
    x = calcular()
    assert x["status"] == "SIMULACAO CONDICIONAL"
    assert x["base_operacao"] == Decimal("100.00")
    assert x["icms_interestadual"] == Decimal("12.00")
    assert x["base_recomposta"] == Decimal("107.32")
    assert x["icms_interno"] == Decimal("19.32")
    assert x["antecipacao_estimada"] == Decimal("7.32")


def test_st_enquadrada_bloqueia_antecipacao():
    x = calcular_item(
        item(), {"st_oficial": {"encontrado": True, "confirmado": True}},
        uf_origem="SP", uf_destino="MG", destinatario_simples=True,
        finalidade="REVENDA", aliquota_interna=18,
        aliquota_interestadual=12,
    )
    assert x["status"] == "REVISAR ICMS-ST"
    assert x["antecipacao_estimada"] is None


def test_nao_simples_interna_ou_uso_consumo_sem_antecipacao():
    for opts in (
        dict(destinatario_simples=False, uf_origem="SP",
             uf_destino="MG", finalidade="REVENDA"),
        dict(destinatario_simples=True, uf_origem="MG",
             uf_destino="MG", finalidade="REVENDA"),
        dict(destinatario_simples=True, uf_origem="SP",
             uf_destino="MG", finalidade="USO_CONSUMO"),
    ):
        x = calcular_item(item(), {}, aliquota_interna=18,
                          aliquota_interestadual=12, **opts)
        assert x["antecipacao_estimada"] is None


def test_ipi_ambiguidade_e_aliquota_ausente_bloqueiam():
    opts = dict(
        uf_origem="SP", uf_destino="MG", destinatario_simples=True,
        finalidade="REVENDA",
    )
    x = calcular_item(item(ipi=10), {}, aliquota_interna=18,
                      aliquota_interestadual=12, **opts)
    assert x["status"] == "REVISAR IPI/BASE"
    y = calcular_item(item(), {}, aliquota_interna="",
                      aliquota_interestadual=12, **opts)
    assert y["status"] == "REVISAR ALIQUOTAS"


def test_exportacao_st_mantem_primeira_aba_e_acrescenta_simples(tmp_path):
    dest = tmp_path / "ST.xlsx"
    wb = Workbook()
    wb.active.title = "Conferência ICMS-ST"
    wb.active["A1"] = "ST ORIGINAL"
    wb.save(dest)
    original = {
        "uf_origem": "SP", "uf_destino": "MG",
        "itens": [{"item": item(), "st_oficial": {"encontrado": False}}],
    }
    dados = adicionar_aba_antecipacao(
        dest, original, destinatario_simples=True,
        finalidade="REVENDA", aliquota_interna="18",
        aliquota_interestadual="12",
    )
    novo = load_workbook(dest)
    assert novo.sheetnames == ["Conferência ICMS-ST", "Antecipacao SN MG"]
    assert novo.worksheets[0]["A1"].value == "ST ORIGINAL"
    assert novo.worksheets[1]["F9"].value == "SIMULACAO CONDICIONAL"
    assert novo.worksheets[1]["M9"].value == 7.32
    assert novo.worksheets[1]["M11"].value == "=SUM(M9:M9)"
    assert dados["status"]["SIMULACAO CONDICIONAL"] == 1


def test_finance_pdf_capa_logo_e_anexo(tmp_path):
    arq = tmp_path / "relatorio.pdf"
    gerar_pdf_tabela(
        arq, titulo="Contas pagas", periodo="10/2026",
        registros=[("Mega Trilha", "Fornecedor Teste", "12.345.678/0001-90", "R$ 123,45")],
        colunas=(("Empresa", 20), ("Fornecedor", 25), ("CNPJ", 25), ("Valor", 15)),
        empresa="Mega Trilha", total="R$ 123,45",
    )
    leitor = PdfReader(str(arq))
    assert len(leitor.pages) >= 2
    assert float(leitor.pages[0].mediabox.height) > float(leitor.pages[0].mediabox.width)
    assert float(leitor.pages[1].mediabox.width) > float(leitor.pages[1].mediabox.height)
    assert "FiscalPro" in (leitor.pages[0].extract_text() or "")
    assert "12.345.678/0001-90" in (leitor.pages[1].extract_text() or "")


def test_pacote_contabilidade_inclui_pdf_com_cnpj_do_documento(tmp_path):
    caminho_anexo = tmp_path / "nota.pdf"
    caminho_anexo.write_bytes(b"%PDF-1.4 teste")
    gestor = GestorDocumentosFinanceiros(tmp_path / "dados")
    conta = {
        "id": 10, "empresa": "Mega Trilha", "fornecedor": "Fornecedor A",
        "fornecedor_cnpj_relatorio": "12345678000190", "numero_documento": "0123",
        "descricao": "Compra", "vencimento": "2026-10-15", "valor": 123.45,
        "categoria": "Operacional", "status": "PAGA", "competencia": "2026-10",
        "caminho_documento": str(caminho_anexo),
    }
    res = gestor.gerar_pacote(
        [conta], tmp_path / "saida",
        competencia="2026-10", empresas=("Mega Trilha",),
    )
    with zipfile.ZipFile(res.caminho_zip) as z:
        nomes = z.namelist()
        assert any(x.endswith("RELATORIO_DOCUMENTOS_10-2026.pdf") for x in nomes)
        assert any(x.endswith("RELATORIO_DOCUMENTOS_10-2026.xlsx") for x in nomes)
        pdf = next(x for x in nomes if x.endswith(".pdf") and "RELATORIO_" in x)
        arq = tmp_path / "pacote_relatorio.pdf"
        arq.write_bytes(z.read(pdf))
        text = "\n".join(p.extract_text() for p in PdfReader(str(arq)).pages)
        assert "12.345.678/0001-90" in text


def test_relatorio_contas_pagas_preserva_cnpj_da_conta(tmp_path):
    pago = {
        "id": 2, "empresa": "Mega Trilha", "fornecedor": "Fornecedor B",
        "fornecedor_cnpj_relatorio": "12345678000190",
        "fornecedor_cnpj": "00000000000000", "numero_documento": "987",
        "data_pagamento": "2026-10-22", "vencimento": "2026-10-20",
        "valor": 150, "descricao": "Conta paga", "categoria": "Teste",
        "competencia": "2026-10", "origem": "Manual",
        "caminho_documento": "",
    }
    res = GeradorRelatorioContasPagas().gerar(
        [pago], tmp_path, competencia_iso="2026-10",
        empresas=("Mega Trilha",),
    )
    assert res.caminho.with_suffix(".pdf").exists()
    text = "\n".join(p.extract_text() for p in
                     PdfReader(str(res.caminho.with_suffix(".pdf"))).pages)
    assert "12.345.678/0001-90" in text
    assert "00.000.000/0000-00" not in text



@pytest.mark.parametrize("detalhado,separado,por_empresa", [
    (False, False, 1),
    (True, False, 1),
    (True, False, 60),
    (True, True, 60),
])
def test_pdf_semanal_pagina_em_paisagem_com_logo_e_preserva_contas(
    tmp_path, detalhado, separado, por_empresa,
):
    from src.financeiro.relatorios import (
        GeradorRelatoriosContasPagar, OpcoesRelatorioContas,
    )

    empresas = ("Empresa Alpha", "Empresa Beta")
    contas = [
        {
            "empresa": empresa,
            "vencimento": "2026-10-15",
            "fornecedor": f"Fornecedor {empresa}",
            "descricao": "Material de escritório",
            "categoria": "Operacional",
            "numero_documento": f"DOC-{indice}-{numero:03d}",
            "observacoes": "",
            "valor": 60.0,
        }
        for indice, empresa in enumerate(empresas)
        for numero in range(por_empresa)
    ]
    opcoes = OpcoesRelatorioContas(
        inicio_iso="2026-10-01", fim_iso="2026-10-31",
        detalhado=detalhado, separado=separado, gerar_excel=False, empresas=empresas,
    )
    resultado = GeradorRelatoriosContasPagar().gerar(contas, tmp_path, opcoes)

    assert len(resultado.arquivos) == (3 if separado else 1)
    for caminho in resultado.arquivos:
        leitor = PdfReader(caminho)
        tem_detalhes = detalhado and caminho.name != "00_RESUMO_GERAL.pdf"
        if tem_detalhes and (por_empresa == 60 or not separado):
            assert len(leitor.pages) > 1
        else:
            assert len(leitor.pages) == 1
        textos = []
        for indice, pagina in enumerate(leitor.pages, start=1):
            assert 841 < float(pagina.mediabox.width) < 843
            assert 595 < float(pagina.mediabox.height) < 596
            assert len(pagina.images) > 0
            texto_pagina = pagina.extract_text()
            assert f"Página {indice}" in texto_pagina
            assert "FiscalPro - Contas a Pagar" in texto_pagina
            assert "Anexo documental" not in texto_pagina
            if "DOC-" in texto_pagina:
                assert "Vencimento" in texto_pagina
            textos.append(texto_pagina)
        assert "01/10/2026 a 31/10/2026" in textos[0]
        assert "TOTAL GERAL DO GRUPO" in textos[0]
        texto = "\n".join(textos)
        contas_esperadas = contas
        if separado and caminho.name == "00_RESUMO_GERAL.pdf":
            contas_esperadas = []
        elif separado:
            contas_esperadas = [
                conta for conta in contas if conta["empresa"].replace(" ", "_") in caminho.name
            ]
            assert len(contas_esperadas) == por_empresa
        documentos_no_pdf = [trecho for trecho in texto.split() if trecho.startswith("DOC-")]
        documentos_esperados = [conta["numero_documento"] for conta in contas_esperadas]
        assert documentos_no_pdf == (documentos_esperados if detalhado else [])
        if tem_detalhes:
            assert "DOC-" in textos[0]
        if not separado:
            assert all(empresa in texto for empresa in empresas)
            total = "R$ 7.200,00" if por_empresa == 60 else "R$ 120,00"
            assert total in texto


@pytest.mark.parametrize("campos_xml,encontrado,opt_in,status", [
    ({}, False, False, "REVISAR ICMS-ST"),
    ({}, False, True, "SIMULACAO — ST PENDENTE"),
    ({"cest_xml": "28.059.00"}, False, True, "REVISAR ICMS-ST"),
    ({"icms_st_retido_xml": 10}, False, True, "REVISAR ICMS-ST"),
    ({}, True, True, "REVISAR ICMS-ST"),
])
def test_antecipacao_st_pendente_exige_opcao_e_sem_indicios_de_st(
    campos_xml, encontrado, opt_in, status,
):
    roupa = item(ncm="62121000", cst_icms="00", **campos_xml)
    regra = {
        "st_oficial": {
            "encontrado": encontrado, "exige_revisao": True,
            "decisao_st": "CONDICIONAL", "candidatos": int(encontrado),
        }
    }
    r = calcular_item(
        roupa, regra, uf_origem="RJ", uf_destino="MG", destinatario_simples=True,
        finalidade="REVENDA", aliquota_interna=18, aliquota_interestadual=12,
        simular_st_nao_localizada=opt_in,
    )
    assert r["status"] == status
    assert r["antecipacao_estimada"] == (
        Decimal("7.32") if status == "SIMULACAO — ST PENDENTE" else None
    )


@pytest.mark.parametrize("cst,csosn,calcula", [
    ("00", "", True),
    ("", "101", True),
    ("", "102", True),
    ("20", "", False),
    ("40", "", False),
    ("41", "", False),
    ("50", "", False),
    ("51", "", False),
    ("", "103", False),
    ("", "300", False),
    ("", "400", False),
    ("", "", False),
])
def test_antecipacao_padrao_somente_tributacao_normal(cst, csosn, calcula):
    r = calcular_item(
        item(cst_icms=cst, csosn=csosn), {"st_oficial": {"encontrado": False}},
        uf_origem="RJ", uf_destino="MG", destinatario_simples=True,
        finalidade="REVENDA", aliquota_interna=18, aliquota_interestadual=12,
    )
    assert r["status"] == ("SIMULACAO CONDICIONAL" if calcula else "REVISAR TRIBUTAÇÃO")
    assert r["antecipacao_estimada"] == (Decimal("7.32") if calcula else None)


def test_antecipacao_exporta_aliquota_do_xml_por_item_em_uma_planilha(tmp_path):
    dest = tmp_path / "mista.xlsx"
    Workbook().save(dest)
    itens = [
        {"item": item(numero_item=1, aliquota_icms_xml=4)},
        {"item": item(numero_item=2, aliquota_icms_xml=12)},
        {"item": item(numero_item=3, aliquota_icms_xml=7)},
        {"item": item(numero_item=4, aliquota_icms_xml=0, cst_icms="", csosn="102")},
        {"item": item(numero_item=5, aliquota_icms_xml=18)},
    ]
    resultado = {"uf_origem": "RJ", "uf_destino": "MG", "itens": itens}
    opcoes = {"destinatario_simples": True, "finalidade": "REVENDA", "aliquota_interna": 18}

    for taxa_manual in (None, 12):
        dados = adicionar_aba_antecipacao(dest, resultado, aliquota_interestadual=taxa_manual, **opcoes)
        wb = load_workbook(dest)
        try:
            ws = wb["Antecipacao SN MG"]
            assert [ws.cell(i, 9).value for i in range(9, 12)] == [4, 12, 7]
            assert [ws.cell(i, 13).value for i in range(9, 12)] == [17.07, 7.32, 13.41]
            assert "XML do item" in ws["N9"].value
            assert ws["M12"].value == (7.32 if taxa_manual is not None else None)
            assert ws["F13"].value == "REVISAR ALIQUOTAS"
            assert ws["M13"].value is None
            assert ws["M15"].value == "=SUM(M9:M13)"
            assert dados["calculados"] == (4 if taxa_manual is not None else 3)
        finally:
            wb.close()


def test_tela_xml_separa_antecipacao_mista_e_st(tmp_path, monkeypatch):
    import sys
    import tkinter as tk

    from src.ui.janela_xml_icms_st import JanelaXMLICMSST

    try:
        root = tk.Tk()
    except tk.TclError:
        if sys.platform == "win32":
            raise
        pytest.skip("A abertura da tela exige uma sessão gráfica.")
    root.withdraw()
    xml = tmp_path / "mista.xml"
    itens = [
        f"""<det nItem="{i}"><prod><cProd>{i}</cProd><xProd>Item {i}</xProd>
        <NCM>62121000</NCM><CFOP>6101</CFOP><vProd>100.00</vProd></prod>
        <imposto><ICMS><ICMS00><orig>{orig}</orig><CST>00</CST><vBC>100</vBC>
        <pICMS>{taxa}</pICMS><vICMS>{taxa}</vICMS></ICMS00></ICMS></imposto></det>"""
        for i, orig, taxa in [(1, 1, 4), (2, 0, 12)]
    ]
    xml.write_text(
        "<NFe><infNFe><ide><nNF>100</nNF></ide>"
        "<emit><CRT>3</CRT><enderEmit><UF>RJ</UF></enderEmit></emit>"
        "<dest><enderDest><UF>MG</UF></enderDest></dest>" + "".join(itens) + "</infNFe></NFe>",
        encoding="utf-8",
    )
    monkeypatch.setattr("src.ui.janela_xml_icms_st.filedialog.askopenfilename", lambda **_: str(xml))
    monkeypatch.setattr("src.ui.janela_xml_icms_st.messagebox.showinfo", lambda *_, **__: None)
    def alerta(titulo, texto, **_):
        pytest.fail(f"{titulo}: {texto}")

    for nome in ("showwarning", "showerror"):
        monkeypatch.setattr(f"src.ui.janela_xml_icms_st.messagebox.{nome}", alerta)
    monkeypatch.setattr(
        "src.services.xml_icms_st_service.ICMSSTMGService.analisar",
        lambda *_, **__: {"encontrado": False, "exige_revisao": False},
    )
    try:
        janela = JanelaXMLICMSST(root)
        janela.importar_xml()
        assert [janela.abas.tab(tab, "text") for tab in janela.abas.tabs()] == ["ICMS-ST", "Antecipação SN/MG"]
        janela.abas.select(janela.aba_antecipacao)
        root.update()
        assert janela.btn_exportar.cget("text") == "Gerar planilha de antecipação"
        janela.antecipacao_habilitada_var.set(True)
        janela.antecipacao_interna_var.set("18")
        janela.btn_calcular.invoke()
        assert "2 de 2 itens calculados" in janela.resumo_antecipacao.get()
        previa = janela.tree_antecipacao
        assert [previa.item(i, "values")[3] for i in previa.get_children()] == ["4,00%", "12,00%"]
        for abas, arquivo in [
            (["Antecipacao SN MG"], tmp_path / "antecipacao.xlsx"),
            (["Conferência ICMS-ST"], tmp_path / "st.xlsx"),
        ]:
            monkeypatch.setattr("src.ui.janela_xml_icms_st.filedialog.asksaveasfilename",
                                lambda **_: str(arquivo))
            janela.btn_exportar.invoke()
            wb = load_workbook(arquivo)
            try:
                assert wb.sheetnames == abas
                if abas == ["Antecipacao SN MG"]:
                    assert [wb.active[f"M{i}"].value for i in (9, 10)] == [17.07, 7.32]
            finally:
                wb.close()
            janela.abas.select(0)
            root.update()
    finally:
        root.destroy()
