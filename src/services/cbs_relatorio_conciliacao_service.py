"""Relatorios de conciliacao CBS: dados LOCAIS e retornos OFICIAIS incrementais.

O cruzamento por chave nao homologa creditos, nao atesta a integralidade da
competencia e nao permite somar a apuracao da matriz e filiais pela raiz.
Os relatorios nunca acessam a API nem modificam dados fiscais.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal
from html import escape
from pathlib import Path

from src.core.caminhos import pasta_recursos
from src.services.apuracao_assistida_local_service import ServicoApuracaoLocalRTC
from src.services.cbs_apuracao_oficial_service import ServicoCBSOficial
from src.services.rtc_relatorio_local_excel_service import _texto_seguro

AZUL = "164B78"
AZUL_CLARO = "EAF2F8"
AMARELO = "FFF1D4"
TEXTO = "263647"
AVISO = (
    "CONFERENCIA DOCUMENTAL - NAO E APURACAO DEFINITIVA. "
    "Retornos oficiais incrementais por RAIZ do CNPJ podem incluir filiais e "
    "nao comprovam a totalidade da competencia. Ausencia neste retorno NAO "
    "significa ausencia na Receita. A apropriar NAO significa credito "
    "automaticamente autorizado. Nao ha compensacao ou recolhimento."
)
CAMPOS = (
    "Operacao", "Numero NF", "Chave NF-e", "CBS XML (R$)",
    "CBS oficial (R$)", "Saldo devedor oficial (R$)",
    "Credito apropriado oficial (R$)", "A apropriar informado (R$)",
    "Resultado",
)
STATUS_ALERTA = {"SEM_DADO_NESTE_RETORNO", "DIFERENCA_REVISAR",
                "MULTIPLOS_OFICIAIS_REVISAR"}


def _logo() -> Path:
    return pasta_recursos() / "assets" / "fiscalpro_logo_horizontal.png"


def _monetario(valor):
    """None para informacao ausente; nunca confundir com R$ 0,00."""
    return None if valor in (None, "") else float(Decimal(str(valor)))


def _formatar_valor_pdf(valor) -> str:
    """Formata valores no padrao brasileiro, sem transformar ausentes em zero."""
    if valor is None:
        return "-"
    numero = f"{Decimal(str(valor)):,.2f}"
    return numero.translate(str.maketrans({",": ".", ".": ","}))


def _triagem_pendencia(doc: dict) -> str:
    """Classificacao documental informativa, sem concluir ausencia na Receita."""
    status = doc["status"]
    if status == "CONFERE":
        return "CONFERE"
    if status == "DIFERENCA_REVISAR":
        return "REVISAR_DIVERGENCIA"
    if status == "MULTIPLOS_OFICIAIS_REVISAR":
        return "REVISAR_MULTIPLOS"
    if status == "SEM_DADO_NESTE_RETORNO":
        valor = doc.get("cbs_xml")
        if valor in (None, ""):
            return "SEM_RETORNO_VALOR_INDISPONIVEL"
        try:
            quantia = Decimal(str(valor))
        except (ValueError, ArithmeticError):
            return "SEM_RETORNO_VALOR_INDISPONIVEL"
        if quantia == 0:
            return "SEM_RETORNO_CBS_ZERO"
        if quantia > 0:
            return "SEM_RETORNO_CBS_POSITIVA"
        return "SEM_RETORNO_VALOR_NEGATIVO_REVISAR"
    return "OUTRO_STATUS_REVISAR"


def _contagem_triagem(dados: dict) -> Counter:
    return Counter(
        _triagem_pendencia(doc)
        for grupo in dados["grupos"].values()
        for doc in grupo["linhas"]
        if doc["status"] != "CONFERE"
    )


def _linha(doc: dict) -> tuple:
    return (
        doc["tipo"], doc["nf"], doc["chave"],
        _monetario(doc["cbs_xml"]), _monetario(doc["cbs_oficial"]),
        _monetario(doc["saldo_oficial"]),
        _monetario(doc["apropriado_oficial"]),
        _monetario(doc["a_apropriar_oficial"]),
        doc["status"],
    )


def _somar_xml(linhas: list[dict]) -> float:
    return float(sum((Decimal(x["cbs_xml"]) for x in linhas), Decimal("0.00")))


class ServicoRelatorioConciliacaoCBS:
    def __init__(self, servico: ServicoCBSOficial | None = None):
        self.servico = servico or ServicoCBSOficial()

    def dados(self, cnpj: str, competencia: str) -> dict:
        cnpj = ServicoApuracaoLocalRTC.validar_cnpj(cnpj)
        competencia = ServicoApuracaoLocalRTC.validar_competencia(competencia)
        grupos = {}
        for tipo in ("debitos", "creditos"):
            linhas = self.servico.conciliar(cnpj, competencia, tipo)
            periodos = self.servico.resumo_competencias(cnpj, tipo)
            oficial = next(
                (p for p in periodos if p["competencia"] == competencia),
                {"registros": 0, "candidatos_xml": 0},
            )
            grupos[tipo] = {
                "linhas": linhas,
                "contagens": Counter(l["status"] for l in linhas),
                "registros_raiz": oficial["registros"],
                "candidatos_raiz": oficial["candidatos_xml"],
                "total_xml": _somar_xml(linhas),
            }
        if not any(g["linhas"] or g["registros_raiz"] for g in grupos.values()):
            raise ValueError(
                "Nao ha XMLs locais ou retornos oficiais da CBS para esta "
                "empresa e competencia."
            )
        return {"cnpj": cnpj, "competencia": competencia, "grupos": grupos}

    def gerar(self, cnpj: str, competencia: str, destino: str | Path,
              nome_empresa: str = "") -> Path:
        destino = Path(destino)
        if destino.suffix.lower() not in (".xlsx", ".pdf"):
            raise ValueError("Escolha um arquivo .xlsx ou .pdf.")
        dados = self.dados(cnpj, competencia)
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.suffix.lower() == ".xlsx":
            self._excel(destino, nome_empresa, dados)
        else:
            self._pdf(destino, nome_empresa, dados)
        return destino

    @staticmethod
    def _resumos(dados: dict) -> list[tuple]:
        retorno = []
        for tipo, nome in (("debitos", "Debitos"), ("creditos", "Creditos")):
            g = dados["grupos"][tipo]
            contagens = g["contagens"]
            retorno.append((
                nome, len(g["linhas"]), contagens["CONFERE"],
                contagens["SEM_DADO_NESTE_RETORNO"],
                contagens["DIFERENCA_REVISAR"],
                contagens["MULTIPLOS_OFICIAIS_REVISAR"],
                g["registros_raiz"], g["candidatos_raiz"], g["total_xml"],
            ))
        return retorno

    @staticmethod
    def _cabecalho_excel(ws, titulo: str, nome: str, dados: dict):
        from openpyxl.styles import Alignment, Font, PatternFill

        ws.sheet_view.showGridLines = False
        ws.row_dimensions[1].height = 33
        ws.row_dimensions[2].height = 25
        ws.merge_cells("C1:I2")
        c = ws["C1"]
        c.value = "FiscalPro | " + titulo
        c.font = Font(bold=True, size=15, color=AZUL)
        c.alignment = Alignment(vertical="center", wrap_text=True)
        logo = _logo()
        if logo.is_file():
            try:
                from openpyxl.drawing.image import Image
                imagem = Image(str(logo))
                fator = min(155 / imagem.width, 51 / imagem.height)
                imagem.width = int(imagem.width * fator)
                imagem.height = int(imagem.height * fator)
                ws.add_image(imagem, "A1")
            except (OSError, ValueError, ImportError):
                ws["A1"] = "FP"
        else:
            ws["A1"] = "FP"
        ws.merge_cells("A3:I3")
        ws["A3"] = (
            f"Empresa: {_texto_seguro(nome)} | CNPJ: {dados['cnpj']} | "
            f"Competencia: {dados['competencia']} | "
            f"Gerado em: {datetime.now():%d/%m/%Y %H:%M}"
        )
        ws["A3"].font = Font(bold=True, color=TEXTO, size=10)
        ws.row_dimensions[3].height = 23
        ws.merge_cells("A5:I7")
        ws["A5"] = AVISO
        ws["A5"].font = Font(bold=True, color="8A4D12", size=10)
        ws["A5"].fill = PatternFill("solid", fgColor=AMARELO)
        ws["A5"].alignment = Alignment(wrap_text=True, vertical="center")
        for r in (5, 6, 7):
            ws.row_dimensions[r].height = 24

    @staticmethod
    def _titulos_tabela(ws, titulos: tuple):
        from openpyxl.styles import Alignment, Font, PatternFill

        for n, titulo in enumerate(titulos, 1):
            cell = ws.cell(9, n, titulo)
            cell.fill = PatternFill("solid", fgColor=AZUL)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[9].height = 35
        ws.freeze_panes = "D10"

    @classmethod
    def _aba_detalhe(cls, ws, nome: str, dados: dict, linhas: list[dict]):
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter

        cls._cabecalho_excel(ws, nome, dados["nome"], dados)
        cls._titulos_tabela(ws, CAMPOS)
        for idx, doc in enumerate(linhas, 10):
            valores = _linha(doc)
            for coluna, valor in enumerate(valores, 1):
                celula = ws.cell(
                    idx, coluna,
                    valor if 4 <= coluna <= 8 else _texto_seguro(valor),
                )
                if 4 <= coluna <= 8:
                    celula.number_format = '#,##0.00;[Red](#,##0.00);-'
                if idx % 2 == 0:
                    celula.fill = PatternFill("solid", fgColor="F5F9FC")
                if coluna == 9 and doc["status"] != "CONFERE":
                    celula.fill = PatternFill("solid", fgColor=AMARELO)
                    celula.font = Font(bold=True, color="8A4D12")
        for i, largura in enumerate((14, 15, 51, 19, 19, 24, 28, 28, 34), 1):
            ws.column_dimensions[get_column_letter(i)].width = largura
        ws.auto_filter.ref = f"A9:I{max(9, len(linhas) + 9)}"
        ws.column_dimensions["C"].number_format = "@"
        if nome == "Pendencias":
            ws["J9"] = "Triagem documental"
            ws["J9"].fill = PatternFill("solid", fgColor=AZUL)
            ws["J9"].font = Font(bold=True, color="FFFFFF")
            ws.column_dimensions["J"].width = 37
            for idx, documento in enumerate(linhas, 10):
                celula = ws.cell(idx, 10, _triagem_pendencia(documento))
                celula.fill = PatternFill("solid", fgColor=AMARELO)
                celula.font = Font(color="8A4D12", bold=True)
            ws.auto_filter.ref = f"A9:J{max(9, len(linhas) + 9)}"
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.orientation = "landscape"
        ws.print_title_rows = "1:9"

    @classmethod
    def _excel(cls, destino: Path, nome: str, dados: dict):
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill

        wb = Workbook()
        ws = wb.active
        ws.title = "Resumo"
        dados = {**dados, "nome": nome}
        cls._cabecalho_excel(ws, "Conciliacao CBS", nome, dados)
        headers = (
            "Operacao", "XMLs locais", "Conferem", "Sem dado oficial",
            "Diferenca revisar", "Multiplos revisar",
            "Registros oficiais (raiz)", "Candidatos por chave (raiz)",
            "CBS nos XMLs (R$)",
        )
        cls._titulos_tabela(ws, headers)
        for row, valores in enumerate(cls._resumos(dados), 10):
            for coluna, valor in enumerate(valores, 1):
                cell = ws.cell(row, coluna, valor)
                if row % 2 == 0:
                    cell.fill = PatternFill("solid", fgColor=AZUL_CLARO)
                if coluna == 1:
                    cell.font = Font(bold=True, color=AZUL)
                if coluna == 9:
                    cell.number_format = '#,##0.00;[Red](#,##0.00);-'
        for col, largura in zip("ABCDEFGHI", (18, 18, 18, 22, 24, 25, 27, 28, 24)):
            ws.column_dimensions[col].width = largura
        ws["A14"] = "Os valores nos XMLs sao informativos, nao um imposto a pagar."
        ws["A15"] = "Registros oficiais por raiz podem incluir outros estabelecimentos."
        ws["A16"] = "Nao realizar liquido de debitos menos creditos com estes dados."
        for linha in (14, 15, 16):
            ws.merge_cells(start_row=linha, start_column=1, end_row=linha, end_column=9)
            ws.cell(linha, 1).font = Font(color="8A4D12", italic=True)
        ws.freeze_panes = "B10"
        ws["A18"] = "Triagem informativa de documentos sem correspondencia no retorno incremental"
        ws["A18"].font = Font(bold=True, color=AZUL)
        categorias = (
            ("SEM_RETORNO_CBS_POSITIVA", "Sem retorno, CBS positiva (verificar)"),
            ("SEM_RETORNO_CBS_ZERO", "Sem retorno, CBS zero (acompanhamento)"),
            ("SEM_RETORNO_VALOR_INDISPONIVEL", "Sem retorno, valor indisponivel"),
            ("SEM_RETORNO_VALOR_NEGATIVO_REVISAR", "Sem retorno, valor negativo (revisar)"),
            ("REVISAR_DIVERGENCIA", "Valores divergentes (revisar)"),
            ("REVISAR_MULTIPLOS", "Multiplos oficiais (revisar)"),
            ("OUTRO_STATUS_REVISAR", "Outro status (revisar)"),
        )
        contagem = _contagem_triagem(dados)
        for indice, (chave, rotulo) in enumerate(categorias, 19):
            ws.cell(indice, 1, rotulo)
            ws.cell(indice, 2, contagem[chave])
        ws["A27"] = (
            "A classificacao nao comprova ausencia na Receita nem autoriza "
            "credito automatico; consultar origem e natureza dos documentos."
        )
        ws.merge_cells("A27:I27")
        ws["A27"].font = Font(color="8A4D12", italic=True)

        todos = []
        for tipo, aba in (("debitos", "Debitos"), ("creditos", "Creditos")):
            linhas = dados["grupos"][tipo]["linhas"]
            todos.extend(linhas)
            cls._aba_detalhe(wb.create_sheet(aba), aba, dados, linhas)
        cls._aba_detalhe(
            wb.create_sheet("Pendencias"), "Pendencias", dados,
            [doc for doc in todos if doc["status"] != "CONFERE"],
        )
        wb.properties.title = f"FiscalPro | Conciliacao CBS {dados['competencia']}"
        wb.properties.subject = "Retornos incrementais CBS versus XMLs locais"
        wb.properties.creator = "FiscalPro"
        wb.save(destino)

    @classmethod
    def _pdf(cls, destino: Path, nome: str, dados: dict):
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.platypus import CondPageBreak, LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        pagina = landscape(A4)
        documento_pdf = SimpleDocTemplate(
            str(destino), pagesize=pagina,
            leftMargin=26, rightMargin=26, topMargin=62, bottomMargin=36,
            title=f"FiscalPro - Conciliacao CBS {dados['competencia']}",
        )
        styles = getSampleStyleSheet()
        aviso = ParagraphStyle(
            "AvisoFiscalPro", parent=styles["BodyText"], fontSize=8.5,
            leading=12, textColor=colors.HexColor("#8A4D12"),
            spaceAfter=12,
        )
        secoes = ParagraphStyle(
            "SecaoFiscalPro", parent=styles["Heading2"], fontSize=12,
            leading=16, spaceBefore=12, spaceAfter=7,
            textColor=colors.HexColor("#164B78"),
        )
        corpo = ParagraphStyle(
            "CorpoFiscalPro", parent=styles["BodyText"],
            fontSize=8, leading=11, alignment=TA_LEFT,
        )
        story = [
            Paragraph(
                f"<b>Empresa:</b> {escape(str(nome))} | "
                f"<b>CNPJ:</b> {dados['cnpj']} | "
                f"<b>Competencia:</b> {dados['competencia']}",
                corpo,
            ),
            Spacer(1, 9),
            Paragraph(escape(AVISO), aviso),
            Paragraph("Resumo documental", secoes),
        ]
        resum = [["Operacao", "XMLs", "Conferem", "Sem retorno", "Diferenca",
                  "Multiplos", "Oficiais raiz", "Candidatos raiz", "CBS XML (R$)"]]
        for lin in cls._resumos(dados):
            resum.append([str(v) if i != 8 else _formatar_valor_pdf(v) for i, v in enumerate(lin)])
        tabela = Table(resum, colWidths=[80, 62, 67, 81, 70, 70, 90, 100, 92])
        tabela.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#164B78")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#EFF5FA")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.extend([tabela, Spacer(1, 8)])
        triagem = _contagem_triagem(dados)
        story.append(Paragraph("Triagem das pendencias (informativa)", secoes))
        linhas_triagem = [
            ["Sem retorno, CBS positiva", str(triagem["SEM_RETORNO_CBS_POSITIVA"])],
            ["Sem retorno, CBS zero", str(triagem["SEM_RETORNO_CBS_ZERO"])],
            ["Sem retorno, valor indisponivel", str(triagem["SEM_RETORNO_VALOR_INDISPONIVEL"])],
            ["Sem retorno, valor negativo", str(triagem["SEM_RETORNO_VALOR_NEGATIVO_REVISAR"])],
            ["Valores divergentes", str(triagem["REVISAR_DIVERGENCIA"])],
            ["Multiplos oficiais", str(triagem["REVISAR_MULTIPLOS"])],
            ["Outros status", str(triagem["OUTRO_STATUS_REVISAR"])],
        ]
        quadro = Table(linhas_triagem, colWidths=[245, 65], hAlign="LEFT")
        quadro.setStyle(TableStyle([
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#EFF5FA")]),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(quadro)
        story.append(Paragraph(
            "Sem retorno nao significa erro ou ausencia na Receita. "
            "CBS zero nao implica direito a credito. Valores sao documentais.",
            corpo,
        ))
        story.append(Paragraph(
            "Oficiais por raiz: a contagem pode incluir filiais. "
            "Nao corresponde necessariamente aos XMLs deste estabelecimento.",
            corpo,
        ))
        for tipo, rotulo in (("debitos", "Debitos - saidas"),
                            ("creditos", "Creditos - entradas")):
            linhas = dados["grupos"][tipo]["linhas"]
            # Reserva espaco para o titulo, cabecalho e primeira linha.
            # Evita titulo de Creditos sozinho no final da folha.
            story.append(CondPageBreak(85))
            story.append(Paragraph(
                f"{rotulo} | {len(linhas)} XML(s) locais", secoes,
            ))
            if not linhas:
                story.append(Paragraph("Nenhum XML local para confrontar.", corpo))
                continue
            cab = ["NF", "Chave NF-e", "CBS XML", "CBS oficial", "Saldo dev.",
                   "Apropriado", "A apropriar", "Resultado"]
            conteudo = [cab]
            for doc in linhas:
                valores = _linha(doc)
                def v(item):
                    return _formatar_valor_pdf(item)
                conteudo.append([
                    str(valores[1]), str(valores[2]), v(valores[3]),
                    v(valores[4]), v(valores[5]), v(valores[6]),
                    v(valores[7]), str(valores[8]),
                ])
            t = LongTable(
                conteudo, repeatRows=1,
                colWidths=[48, 210, 70, 70, 68, 70, 72, 132],
                hAlign="LEFT",
            )
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#164B78")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#F3F7FA")]),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(t)

        def moldura(canvas, documento):
            canvas.saveState()
            largura, altura = pagina
            logo = _logo()
            if logo.is_file():
                try:
                    canvas.drawImage(str(logo), 26, altura - 49, width=116, height=36,
                                     preserveAspectRatio=True, mask="auto")
                except (OSError, ValueError):
                    canvas.setFont("Helvetica-Bold", 13)
                    canvas.drawString(26, altura - 31, "FiscalPro")
            else:
                canvas.setFont("Helvetica-Bold", 13)
                canvas.drawString(26, altura - 31, "FiscalPro")
            canvas.setFillColor(colors.HexColor("#164B78"))
            canvas.setFont("Helvetica-Bold", 13)
            canvas.drawString(161, altura - 29, "Conferencia CBS | XML x Receita")
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#556678"))
            canvas.drawString(26, 18, "Retorno incremental - nao constitui apuracao definitiva")
            canvas.drawRightString(largura - 26, 18,
                                   f"FiscalPro | pagina {documento.page}")
            canvas.restoreState()

        documento_pdf.build(story, onFirstPage=moldura, onLaterPages=moldura)
