"""PDFs financeiros padronizados: capa e anexo no estilo FiscalPro RTC.

Nao altera contas, notas, anexos nem valores; formata dados ja apurados.
O mesmo asset de logo oficial utilizado nos PDFs CBS e RTC e reaproveitado.
"""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from pathlib import Path
import re
from xml.sax.saxutils import escape


def _limpo(x, limite=200):
    v = re.sub(r"[\x00-\x1f]", " ", str(x if x is not None else ""))
    return escape(" ".join(v.split())[:limite])


def _texto(x, limite=110):
    return re.sub(r"[\x00-\x1f]", " ", str(x if x is not None else ""))[:limite]


def capa_financeira(titulo, periodo, qtd, total, *, descricao="", empresa="Consolidado"):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.utils import simpleSplit
    from src.services.rtc_pdf_identidade_2027 import desenhar_logo

    memoria = BytesIO()
    w, h = A4
    c = canvas.Canvas(memoria, pagesize=A4)
    azul = colors.HexColor("#114B7A")
    marinho = colors.HexColor("#0B3155")
    claro = colors.HexColor("#E8F2FB")
    cinza = colors.HexColor("#25394D")

    def palavras(t, x, y, largura, tamanho=10, fonte="Helvetica",
                 entrelinha=15, max_linhas=5, cor=cinza):
        c.setFont(fonte, tamanho)
        c.setFillColor(cor)
        for linha in simpleSplit(_texto(t, 1000), fonte, tamanho, largura)[:max_linhas]:
            c.drawString(x, y, linha)
            y -= entrelinha

    c.setFillColor(azul)
    c.rect(0, h-116, w, 116, fill=1, stroke=0)
    desenhar_logo(c, 34, h-94, 110, 56)
    c.setStrokeColor(colors.HexColor("#8ECDE6"))
    c.line(159, h-100, 159, h-23)
    palavras(titulo, 175, h-49, w-195, 16, "Helvetica-Bold",
             21, 3, colors.white)
    palavras("FiscalPro | Relatorios financeiros", 176, h-94,
             w-195, 9, "Helvetica", 12, 1, colors.white)

    c.setFillColor(claro)
    c.roundRect(34, 571, w-68, 70, 8, fill=1, stroke=0)
    palavras("Periodo: " + _texto(periodo), 47, 609, w-94, 10,
             "Helvetica-Bold", 14, 1, marinho)
    palavras("Empresa(s): " + _texto(empresa), 47, 588, w-94, 9, "Helvetica",
             13, 2, cinza)

    for i, (nome, valor) in enumerate((("DOCUMENTOS", qtd), ("TOTAL (R$)", total))):
        x = 34 + i * (w-68 + 10)/2
        c.setFillColor(claro)
        c.roundRect(x, 459, (w-78)/2, 93, 7, fill=1, stroke=0)
        palavras(nome, x+14, 522, (w-107)/2, 9, "Helvetica-Bold", 12, 1, marinho)
        palavras(str(valor), x+14, 480, (w-107)/2, 18, "Helvetica-Bold", 22, 1, marinho)

    c.setFillColor(claro)
    c.roundRect(34, 377, w-68, 49, 6, fill=1, stroke=0)
    palavras("DOCUMENTACAO E CONFERENCIA", 47, 401, w-95,
             11, "Helvetica-Bold", 14, 1, marinho)
    palavras(descricao or "Valores de natureza financeira; consultar anexos por documento.",
             47, 382, w-95, 8.5, "Helvetica", 11, 2, cinza)
    c.setFillColor(colors.HexColor("#FFF4D9"))
    c.roundRect(34, 85, w-68, 82, 6, fill=1, stroke=0)
    palavras("Relatorio financeiro para conferencia", 49, 143,
             w-100, 11, "Helvetica-Bold", 15, 1, marinho)
    palavras(
        "Conferir CNPJ do fornecedor de cada documento, datas e anexos antes do "
        "envio a contabilidade. Este relatorio nao substitui comprovantes, "
        "documentos fiscais ou a escrituracao contabil.",
        49, 119, w-100, 9, "Helvetica", 13, 4, cinza
    )
    c.setStrokeColor(azul)
    c.line(34, 57, w-34, 57)
    palavras("FiscalPro | Stephane Rhis + ChatGPT", 34, 39, w-68,
             8, "Helvetica-Bold", 10, 1, marinho)
    c.setFont("Helvetica")
    c.drawRightString(w-34, 22, "Pagina 1")
    c.showPage()
    c.save()
    memoria.seek(0)
    return memoria


def cabecalho_financeiro(c, doc):
    """Logo e barra azul em cada pagina A4 paisagem do detalhamento."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from src.services.rtc_pdf_identidade_2027 import desenhar_logo
    w, h = landscape(A4)
    c.saveState()
    c.setFillColor(colors.HexColor("#114B7A"))
    c.rect(0, h-73, w, 73, fill=1, stroke=0)
    desenhar_logo(c, 30, h-67, 101, 45)
    c.setFont("Helvetica-Bold", 15)
    c.setFillColor(colors.white)
    c.drawString(146, h-38, "Anexo documental | Relatorios FiscalPro")
    c.setFont("Helvetica", 8.5)
    c.drawString(146, h-55, "Contas a Pagar / Pacote para Contabilidade")
    c.setFillColor(colors.HexColor("#0B3155"))
    c.setFont("Helvetica-Bold", 8)
    c.drawString(30, 14, "FiscalPro | Stephane Rhis + ChatGPT")
    c.drawRightString(w-30, 14, f"Pagina {doc.page + 1}")
    c.setLineWidth(0.5)
    c.line(30, 27, w-30, 27)
    c.restoreState()


def juntar_capa(destino, titulo, periodo, qtd, total, *,
                descricao="", empresa="Consolidado"):
    """Anexa capa ao PDF existente, substituindo-o apenas apos sucesso."""
    from pypdf import PdfReader, PdfWriter
    caminho = Path(destino)
    escritor = PdfWriter()
    escritor.append(PdfReader(capa_financeira(
        titulo, periodo, qtd, total, descricao=descricao, empresa=empresa
    )))
    escritor.append(PdfReader(str(caminho)))
    escritor.add_metadata({
        "/Title": _texto(titulo), "/Author": "FiscalPro | Stephane Rhis + ChatGPT"
    })
    tmp = caminho.with_suffix(".montando.pdf")
    try:
        with tmp.open("wb") as arq:
            escritor.write(arq)
        tmp.replace(caminho)
    finally:
        tmp.unlink(missing_ok=True)
    return caminho


def gerar_pdf_tabela(destino, *, titulo, periodo, registros, colunas,
                    resumo="", empresa="Consolidado", total=None):
    """Gera PDF financeiro (resumo + TODAS as linhas) usando capa aprovada."""
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph, LongTable, TableStyle, SimpleDocTemplate, Spacer
    )
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    dados = list(registros)
    if total is None:
        total = "Conferir valores"
    primeiro = destino.with_suffix(".conteudo.pdf")
    estilo = ParagraphStyle(
        "cel", fontName="Helvetica", fontSize=6.8,
        leading=9, textColor=colors.HexColor("#25394D"),
    )
    titulo_style = ParagraphStyle(
        "titulo", fontName="Helvetica-Bold", fontSize=16,
        leading=20, textColor=colors.HexColor("#114B7A"),
        spaceAfter=9,
    )
    subtitulo = ParagraphStyle(
        "subtitulo", fontName="Helvetica", fontSize=9,
        leading=13, spaceAfter=14,
    )
    cabecalho = ParagraphStyle(
        "cabecalho", fontName="Helvetica-Bold", fontSize=7,
        leading=9, textColor=colors.white,
    )
    pagina = landscape(A4)
    doc = SimpleDocTemplate(
        str(primeiro), pagesize=pagina,
        topMargin=33*mm, bottomMargin=18*mm,
        leftMargin=11*mm, rightMargin=11*mm,
        title=_texto(titulo),
        author="FiscalPro | Stephane Rhis + ChatGPT",
    )
    larg = doc.width
    proporcoes = [max(1, float(c[1])) for c in colunas]
    soma = sum(proporcoes)
    larguras = [larg*x/soma for x in proporcoes]
    grade = [[Paragraph(_limpo(c[0]), cabecalho) for c in colunas]]
    for dados_linha in dados:
        grade.append([
            Paragraph(_limpo(valor, 150), estilo)
            for valor in dados_linha
        ])
    if len(grade) == 1:
        grade.append([Paragraph("Nenhuma conta para o periodo.", estilo)] +
                     [Paragraph("", estilo)] * (len(colunas)-1))
    tabela = LongTable(grade, colWidths=larguras, repeatRows=1, hAlign="LEFT")
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#114B7A")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F4F8FC")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), .25, colors.HexColor("#D5E3EE")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    try:
        doc.build([
            Paragraph(_limpo(titulo), titulo_style),
            Paragraph(_limpo(resumo or periodo), subtitulo),
            Spacer(1, 4*mm), tabela
        ], onFirstPage=cabecalho_financeiro,
           onLaterPages=cabecalho_financeiro)
        juntar_capa(
            primeiro, titulo, periodo, len(dados), total,
            descricao=resumo, empresa=empresa,
        )
        primeiro.replace(destino)
    finally:
        primeiro.unlink(missing_ok=True)
    return destino
