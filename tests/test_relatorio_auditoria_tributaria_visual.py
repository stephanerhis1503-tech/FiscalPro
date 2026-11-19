"""Testes do novo relatorio visual da Auditoria Tributaria no SPED."""
from pathlib import Path
from tempfile import TemporaryDirectory

from openpyxl import load_workbook

from src.sped.auditor_tributario import (
    ApontamentoAuditoriaTributaria,
    ResultadoAuditoriaTributaria,
)
from src.services.relatorio_auditoria_tributaria_service import (
    ServicoRelatorioAuditoriaTributaria,
)


def _resultado():
    aponta = [
        ApontamentoAuditoriaTributaria(
            nivel="ERRO", origem="XML NF-e", linha=18, registro="C170",
            documento="123", chave="3" * 44, item="1",
            codigo="=2+2", descricao="Cadeado", ncm="83011000",
            campo="NCM", atual="83011000", esperado="83014000",
            regra_id="", aderencia=0, mensagem="NCM divergente",
            orientacao="Conferir nota e classificacao.",
        ),
        ApontamentoAuditoriaTributaria(
            nivel="AVISO", origem="FICHA TRIBUTÁRIA", linha=20, registro="C170",
            documento="124", chave="", item="2",
            codigo="AB34", descricao="Produto de uso e consumo",
            ncm="85044029", campo="Regra tributária", atual="Nao encontrada",
            esperado="Regra vigente", regra_id="", aderencia=0,
            mensagem="Regra nao localizada.", orientacao="Verificar natureza.",
        ),
    ]
    return ResultadoAuditoriaTributaria(
        total_itens=5, itens_com_0200=5, itens_sem_0200=0,
        itens_com_regra=4, itens_sem_regra=1, itens_com_xml=2, itens_sem_xml=3,
        erros=1, avisos=1, apontamentos=aponta,
        contexto={"empresa": "Mega Motos Trilha", "regime": "LUCRO REAL"},
    )


def test_excel_profissional_completo_e_sem_formulas(tmp_path):
    destino = ServicoRelatorioAuditoriaTributaria().gerar(
        _resultado(), "SPED 11-2026.txt", tmp_path / "auditoria.xlsx",
    )
    wb = load_workbook(destino)
    assert wb.sheetnames == ["Resumo", "Todos", "Erros", "Avisos", "NF-e com C170", "XMLs importados", "Referencias fiscais"]
    assert wb["Resumo"]["A9"].value == 5
    assert wb["Resumo"]["E9"].value == 1
    assert wb["Resumo"]["I9"].value == 1
    assert wb["Todos"]["G9"].value == "'=2+2"
    assert wb["Todos"]["E9"].value == "3" * 44
    assert wb["Todos"]["E9"].number_format == "@"
    assert wb["Erros"].max_row == 9
    assert wb["Avisos"].max_row == 9
    assert wb["Todos"].auto_filter.ref == "A8:P10"
    assert wb["Todos"]["P9"].value == "Conferir nota e classificacao."
    assert wb["NF-e com C170"]["A1"].value == "Operacao"
    assert wb["XMLs importados"]["I1"].value == "Pasta ou arquivo de origem"
    assert wb["Referencias fiscais"]["H1"].value == "NCM na base oficial"
    assert wb["Referencias fiscais"]["AC1"].value == "Restricoes de uso"


def test_pdf_profissional_gera_cabecalho_e_paginas(tmp_path):
    destino = ServicoRelatorioAuditoriaTributaria().gerar(
        _resultado(), "SPED 11-2026.txt", tmp_path / "auditoria.pdf",
    )
    assert destino.read_bytes().startswith(b"%PDF")
    assert destino.stat().st_size > 2000
    from pypdf import PdfReader
    texto = "\n".join(p.extract_text() for p in PdfReader(str(destino)).pages)
    assert "Auditoria Tributaria" in texto
    assert "Cadeado" not in texto or "83011000" in texto
    assert "conferencia" in texto.lower()


def test_pdf_e_excel_sem_apontamentos(tmp_path):
    vazio = ResultadoAuditoriaTributaria(total_itens=0, contexto={"empresa": "Teste"})
    servico = ServicoRelatorioAuditoriaTributaria()
    arquivo_xlsx = servico.gerar(vazio, "sped.txt", tmp_path / "vazio.xlsx")
    arquivo_pdf = servico.gerar(vazio, "sped.txt", tmp_path / "vazio.pdf")
    wb = load_workbook(arquivo_xlsx)
    assert wb.sheetnames == ["Resumo", "Todos", "Erros", "Avisos", "NF-e com C170", "XMLs importados", "Referencias fiscais"]
    assert arquivo_pdf.read_bytes().startswith(b"%PDF")
