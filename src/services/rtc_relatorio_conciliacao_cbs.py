"""Relatorios locais de conciliacao CBS Oficial x XMLs, em Excel e PDF.

Usa SOMENTE os snapshots existentes no banco FiscalPro. Nao faz consultas
online, nao solicita tiquetes, nao altera apuracoes ou reconhece creditos.
O retorno da Receita e incremental e por raiz do CNPJ.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal
from html import escape
from pathlib import Path

from src.core.caminhos import pasta_recursos
from src.services.apuracao_assistida_local_service import ServicoApuracaoLocalRTC
from src.services.cbs_apuracao_oficial_service import ServicoCBSOficial, TIPOS


STATUS_DESCRICOES = {
    "CONFERE": "CBS dos XMLs corresponde ao retorno oficial (tolerancia R$ 0,02).",
    "DIFERENCA_REVISAR": "Diferenca de CBS entre XML e retorno oficial. Revisar.",
    "MULTIPLOS_OFICIAIS_REVISAR": "Ha mais de um registro oficial para a chave; conferir manualmente.",
    "SEM_DADO_NESTE_RETORNO": (
        "Nota sem registro correspondente no retorno incremental importado. "
        "Isso nao comprova ausencia na Receita Federal."
    ),
}
STATUS_REVISAR = {"DIFERENCA_REVISAR", "MULTIPLOS_OFICIAIS_REVISAR"}


def _numero(valor) -> Decimal | None:
    return Decimal(str(valor)) if valor is not None and str(valor).strip() else None


def _texto_seguro(valor) -> str:
    texto = str(valor or "").replace("\r", " ").replace("\n", " ")
    if texto.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + texto
    return texto


def _br_num(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def _br_cnpj(cnpj: str) -> str:
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


class ServicoRelatorioConciliacaoCBS:
    def __init__(self, oficial: ServicoCBSOficial | None = None):
        self.oficial = oficial or ServicoCBSOficial()

    def preparar(
        self, cnpj: str, competencia: str, tipo: str, empresa: str = ""
    ) -> dict:
        """Reconstroi a conciliação sem limite visual de 5000 linhas."""
        cnpj = ServicoApuracaoLocalRTC.validar_cnpj(cnpj)
        competencia = ServicoApuracaoLocalRTC.validar_competencia(competencia)
        if tipo not in TIPOS:
            raise ValueError("Tipo de retorno invalido: utilize debitos ou creditos.")

        # Mesmo algoritmo usado na grade da CBS oficial.
        conciliados = self.oficial.conciliar(cnpj, competencia, tipo)
        if not conciliados:
            raise ValueError(
                "Nao ha XMLs locais da operacao selecionada para esta empresa "
                "e competencia. Importe os XMLs antes de exportar."
            )
        locais = ServicoApuracaoLocalRTC(self.oficial.banco).listar(cnpj, competencia)
        emissoes = {doc["chave_nfe"]: doc["emissao"] for doc in locais}

        periodos = self.oficial.resumo_competencias(cnpj, tipo)
        situacao_periodo = next(
            (p for p in periodos if p["competencia"] == competencia), None
        )
        linhas = []
        for doc in conciliados:
            xml = _numero(doc["cbs_xml"])
            oficial = _numero(doc["cbs_oficial"])
            if xml is None:
                raise ValueError("CBS XML ausente no registro local.")
            diferenca = (xml - oficial).quantize(Decimal("0.01")) if oficial is not None else None
            estado = str(doc["status"])
            if estado not in STATUS_DESCRICOES:
                raise ValueError(f"Status de conciliacao nao reconhecido: {estado}.")
            observacao = STATUS_DESCRICOES[estado]
            if estado == "CONFERE" and diferenca:
                observacao = "Diferenca dentro da tolerancia de R$ 0,02."
            linhas.append({
                "tipo": doc["tipo"], "nf": str(doc["nf"]),
                "emissao": emissoes.get(doc["chave"], ""),
                "chave": str(doc["chave"]), "cbs_xml": xml,
                "cbs_oficial": oficial, "diferenca": diferenca,
                "saldo_oficial": _numero(doc["saldo_oficial"]),
                "apropriado_oficial": _numero(doc["apropriado_oficial"]),
                "a_apropriar_oficial": _numero(doc["a_apropriar_oficial"]),
                "status": estado, "observacao": observacao,
            })
        contagens = Counter(doc["status"] for doc in linhas)
        resumo = {
            "cnpj": cnpj,
            "cnpj_base": cnpj[:8],
            "competencia": competencia,
            "tipo": tipo,
            "empresa": empresa.strip() or cnpj,
            "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "xmls": len(linhas),
            # Oficiais armazenados para toda a raiz (podem incluir filiais).
            "oficiais": situacao_periodo["registros"] if situacao_periodo else 0,
            "oficiais_candidatos": situacao_periodo["candidatos_xml"] if situacao_periodo else 0,
            "conferem": contagens["CONFERE"],
            "diferencas": contagens["DIFERENCA_REVISAR"],
            "multiplos": contagens["MULTIPLOS_OFICIAIS_REVISAR"],
            "sem_retorno": contagens["SEM_DADO_NESTE_RETORNO"],
            "comparaveis": contagens["CONFERE"] + contagens["DIFERENCA_REVISAR"],
        }
        return {"resumo": resumo, "linhas": linhas}

    @staticmethod
    def _validar_destino(destino: str | Path, extensao: str) -> Path:
        path = Path(destino)
        if path.suffix.lower() != extensao:
            raise ValueError(f"Salve o relatorio no formato {extensao}.")
        return path

    def gerar_excel(
        self, cnpj: str, competencia: str, tipo: str,
        destino: str | Path, empresa: str = "",
    ) -> Path:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
        from openpyxl.workbook.properties import CalcProperties

        destino = self._validar_destino(destino, ".xlsx")
        dados = self.preparar(cnpj, competencia, tipo, empresa)
        resumo, linhas = dados["resumo"], dados["linhas"]
        azul = "134A77"
        azul_claro = "E9F2FA"
        amarelado = "FFF1CC"
        vermelho = "B23B33"
        verde = "DFF2E7"
        numfmt = '#,##0.00;[Red](#,##0.00);-'
        wb = Workbook()
        wb.calculation = CalcProperties(calcMode="auto", fullCalcOnLoad=True)
        aba = wb.active
        aba.title = "Resumo"
        aba.sheet_view.showGridLines = False
        aba.merge_cells("A1:L2")
        aba["A1"] = "FISCALPRO | CONCILIACAO CBS OFICIAL x XMLs LOCAIS"
        aba["A1"].font = Font(name="Calibri", bold=True, size=17, color="FFFFFF")
        aba["A1"].fill = PatternFill("solid", fgColor=azul)
        aba["A1"].alignment = Alignment(vertical="center")
        aba.row_dimensions[1].height = 30
        aba.row_dimensions[2].height = 18
        aba.merge_cells("A4:L4")
        aba["A4"] = (
            f"Empresa: {_texto_seguro(resumo['empresa'])} | CNPJ: {_br_cnpj(cnpj)} "
            f"| Competencia: {competencia} | Retorno: {tipo.upper()} "
            f"| Gerado em: {resumo['gerado_em']}"
        )
        aba["A4"].font = Font(bold=True, size=11, color=azul)
        aba.merge_cells("A6:L8")
        aba["A6"] = (
            "DOCUMENTO ANALITICO, NAO OFICIAL. Retornos da Receita sao INCREMENTAIS "
            "e consultados por RAIZ do CNPJ, podendo incluir filiais. "
            "Sem dado neste retorno NAO significa nota ausente na Receita. "
            "Nao representa apuracao definitiva, imposto a recolher, pagamento "
            "ou apropriacao automatica de credito."
        )
        aba["A6"].alignment = Alignment(wrap_text=True, vertical="center")
        aba["A6"].fill = PatternFill("solid", fgColor=amarelado)
        aba["A6"].font = Font(color="7A5000", bold=True)
        aba.row_dimensions[6].height = 20
        aba.row_dimensions[7].height = 22
        aba.row_dimensions[8].height = 20
        for c, titulo in enumerate(("Indicador", "Quantidade", "Interpretacao"), 1):
            cel = aba.cell(10, c, titulo)
            cel.fill = PatternFill("solid", fgColor=azul)
            cel.font = Font(bold=True, color="FFFFFF")
        metricas = [
            ("XMLs locais analisados", resumo["xmls"], "Notas da operacao selecionada"),
            ("Registros oficiais na raiz", resumo["oficiais"], "Retorno incremental, pode incluir filiais"),
            ("Conferem por chave e valor", resumo["conferem"], "Confronto com tolerancia de R$ 0,02"),
            ("Sem dado neste retorno", resumo["sem_retorno"], "Nao comprova ausencia na Receita"),
            ("Diferencas a revisar", resumo["diferencas"], "Valores distintos no confronto"),
            ("Multiplos oficiais a revisar", resumo["multiplos"], "Chaves com mais de um registro"),
        ]
        for linha_n, (rotulo, quantidade, interpretacao) in enumerate(metricas, 11):
            aba.cell(linha_n, 1, rotulo).font = Font(bold=True, color=azul)
            aba.cell(linha_n, 2, quantidade).font = Font(bold=True, color=azul, size=13)
            aba.cell(linha_n, 3, interpretacao)
            if linha_n % 2:
                for col in range(1, 13):
                    aba.cell(linha_n, col).fill = PatternFill("solid", fgColor=azul_claro)
        aba["A19"] = "Conclusao"
        aba["A19"].font = Font(bold=True, size=14, color=azul)
        aba.merge_cells("A20:L22")
        aba["A20"] = self._texto_conclusao(resumo)
        aba["A20"].alignment = Alignment(wrap_text=True, vertical="center")
        aba["A20"].font = Font(bold=True, color="166534")
        aba["A20"].fill = PatternFill("solid", fgColor=verde)
        aba["A24"] = "FiscalPro | Stephane Rhis + ChatGPT"
        aba["A24"].font = Font(bold=True, color=azul)
        aba.column_dimensions["A"].width = 36
        aba.column_dimensions["B"].width = 16
        aba.column_dimensions["C"].width = 57
        for col in range(4, 13):
            aba.column_dimensions[get_column_letter(col)].width = 11
        aba.freeze_panes = "B11"

        colunas = [
            ("Operacao", "tipo", 13), ("NF", "nf", 15),
            ("Emissao", "emissao", 16), ("Chave NF-e", "chave", 50),
            ("CBS XML (R$)", "cbs_xml", 18),
            ("CBS oficial (R$)", "cbs_oficial", 20),
            ("Diferenca XML - oficial (R$)", "diferenca", 25),
            ("Saldo devedor (R$)", "saldo_oficial", 21),
            ("Credito apropriado (R$)", "apropriado_oficial", 23),
            ("A apropriar (R$)", "a_apropriar_oficial", 21),
            ("Resultado", "status", 31),
            ("Observacao", "observacao", 77),
        ]

        def montar(nome: str, registros: list[dict]):
            ws = wb.create_sheet(nome)
            ws.sheet_view.showGridLines = False
            ws.merge_cells("A1:L2")
            ws["A1"] = f"FiscalPro | {nome} | CBS Oficial x XMLs Locais"
            ws["A1"].font = Font(bold=True, color="FFFFFF", size=15)
            ws["A1"].fill = PatternFill("solid", fgColor=azul)
            ws["A1"].alignment = Alignment(vertical="center")
            ws.row_dimensions[1].height = 28
            ws.merge_cells("A3:L3")
            ws["A3"] = (
                f"{_texto_seguro(resumo['empresa'])} | {_br_cnpj(cnpj)} "
                f"| {competencia} | {tipo.upper()} | {len(registros)} registro(s)"
            )
            ws["A3"].font = Font(bold=True, color=azul)
            ws.merge_cells("A4:L4")
            ws["A4"] = (
                "RETORNO INCREMENTAL E POR RAIZ DE CNPJ. "
                "Diferencas exigem revisao; ausencia nao significa documento omitido pela Receita."
            )
            ws["A4"].font = Font(color=vermelho, italic=True)
            for col, (titulo, _, largura) in enumerate(colunas, 1):
                cel = ws.cell(6, col, titulo)
                cel.fill = PatternFill("solid", fgColor=azul)
                cel.font = Font(bold=True, color="FFFFFF")
                cel.alignment = Alignment(vertical="center", wrap_text=True)
                ws.column_dimensions[get_column_letter(col)].width = largura
            ws.row_dimensions[6].height = 32
            for n, registro in enumerate(registros, 7):
                for col, (_titulo, chave, _largura) in enumerate(colunas, 1):
                    cel = ws.cell(n, col)
                    if chave == "diferenca":
                        # Valor derivado: formula editavel e recalculavel no Excel.
                        cel.value = f'=IF(OR(E{n}="",F{n}=""),"",ROUND(E{n}-F{n},2))'
                    elif chave in (
                        "cbs_xml", "cbs_oficial", "saldo_oficial",
                        "apropriado_oficial", "a_apropriar_oficial",
                    ):
                        cel.value = (
                            float(registro[chave]) if registro[chave] is not None else None
                        )
                    else:
                        cel.value = _texto_seguro(registro.get(chave))
                    if 5 <= col <= 10:
                        cel.number_format = numfmt
                    if col in (2, 4):
                        cel.number_format = "@"
                    if n % 2 == 0:
                        cel.fill = PatternFill("solid", fgColor="F5F9FC")
                    if col == 11:
                        estado = registro["status"]
                        if estado in STATUS_REVISAR:
                            cel.font = Font(bold=True, color=vermelho)
                            cel.fill = PatternFill("solid", fgColor="FFE3DF")
                        elif estado == "SEM_DADO_NESTE_RETORNO":
                            cel.fill = PatternFill("solid", fgColor=amarelado)
                        else:
                            cel.fill = PatternFill("solid", fgColor=verde)
            ws.freeze_panes = "E7"
            ws.auto_filter.ref = f"A6:L{max(6, len(registros) + 6)}"
            ws.sheet_properties.pageSetUpPr.fitToPage = True
            ws.page_setup.orientation = "landscape"
            ws.print_title_rows = "1:6"

        montar("Conciliacao", linhas)
        montar("Revisar", [x for x in linhas if x["status"] in STATUS_REVISAR])
        montar(
            "Sem retorno",
            [x for x in linhas if x["status"] == "SEM_DADO_NESTE_RETORNO"],
        )
        wb.properties.title = f"FiscalPro - conciliacao CBS {competencia}"
        wb.properties.subject = "Conferencia local incremental; nao e apuracao oficial"
        wb.properties.creator = "FiscalPro"
        destino.parent.mkdir(parents=True, exist_ok=True)
        wb.save(destino)
        return destino

    @staticmethod
    def _texto_conclusao(resumo: dict) -> str:
        if resumo["comparaveis"] == 0:
            return (
                "Ainda nao ha registros oficiais com correspondencia unica "
                "para os XMLs deste estabelecimento e competencia."
            )
        if resumo["diferencas"]:
            return (
                f"{_br_num(resumo['conferem'])} de "
                f"{_br_num(resumo['comparaveis'])} documentos comparaveis conferem. "
                f"Ha {_br_num(resumo['diferencas'])} diferenca(s) a revisar."
            )
        return (
            f"100% dos {_br_num(resumo['comparaveis'])} documentos comparaveis "
            "apresentaram CBS correspondente entre XML local e retorno oficial."
        )

    def gerar_pdf(
        self, cnpj: str, competencia: str, tipo: str,
        destino: str | Path, empresa: str = "",
        incluir_anexo: bool = True,
    ) -> Path:
        """Primeira pagina editorial + anexo paginado com todas as notas."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.utils import ImageReader, simpleSplit
        from reportlab.pdfgen import canvas

        destino = self._validar_destino(destino, ".pdf")
        dados = self.preparar(cnpj, competencia, tipo, empresa)
        r, linhas = dados["resumo"], dados["linhas"]
        azul = colors.HexColor("#114B7A")
        marinho = colors.HexColor("#0B3155")
        azul_claro = colors.HexColor("#E8F2FB")
        cinza = colors.HexColor("#25394D")
        verde = colors.HexColor("#187C52")
        verde_claro = colors.HexColor("#E9F7EF")
        amarelo = colors.HexColor("#FFF4D9")
        margem = 28
        w, h = A4
        destino.parent.mkdir(parents=True, exist_ok=True)
        c = canvas.Canvas(str(destino), pagesize=A4)
        c.setTitle(f"FiscalPro - Conciliacao CBS {competencia}")
        c.setAuthor("FiscalPro | Stephane Rhis + ChatGPT")

        def retangulo(x, y, largura, altura, fundo, contorno=None, raio=5):
            c.setFillColor(fundo)
            c.setStrokeColor(contorno or fundo)
            c.roundRect(x, y, largura, altura, raio, fill=1, stroke=int(contorno is not None))

        def texto(texto, x, y, fonte="Helvetica", tamanho=9, cor=cinza):
            c.setFont(fonte, tamanho)
            c.setFillColor(cor)
            c.drawString(x, y, str(texto))

        def texto_central(texto, x, y, fonte="Helvetica-Bold", tamanho=12, cor=marinho):
            c.setFont(fonte, tamanho)
            c.setFillColor(cor)
            c.drawCentredString(x, y, str(texto))

        def quebrar(texto_base, x, topo, largura, tamanho=9, passo=12, fonte="Helvetica", cor=cinza):
            linhas_texto = simpleSplit(str(texto_base), fonte, tamanho, largura)
            for linha in linhas_texto:
                texto(linha, x, topo, fonte, tamanho, cor)
                topo -= passo
            return topo

        def logo(x, y, largura=110, altura=48):
            img = pasta_recursos() / "assets" / "fiscalpro_logo_horizontal_white.png"
            if img.is_file():
                try:
                    c.drawImage(
                        ImageReader(str(img)), x, y,
                        width=largura, height=altura,
                        preserveAspectRatio=True, anchor="c", mask="auto",
                    )
                    return
                except (OSError, ValueError):
                    pass
            # Identidade vetorial de contingencia para instalacoes sem asset.
            retangulo(x, y + 4, 44, 38, marinho, raio=6)
            texto("FP", x + 7, y + 25, "Helvetica-Bold", 18, colors.white)
            c.setStrokeColor(colors.HexColor("#20C9A4"))
            c.setLineWidth(4)
            p = c.beginPath()
            p.moveTo(x + 8, y + 16)
            p.lineTo(x + 18, y + 10)
            p.lineTo(x + 30, y + 23)
            p.lineTo(x + 37, y + 18)
            c.drawPath(p, stroke=1)

        # Pagina 1: usa o mesmo estilo visual do modelo aprovado.
        c.setFillColor(azul)
        c.rect(0, h - 105, w, 105, fill=1, stroke=0)
        logo(margem + 6, h - 84, 110, 52)
        c.setStrokeColor(colors.HexColor("#8ECDE6"))
        c.setLineWidth(1)
        c.line(154, h - 88, 154, h - 18)
        quebrar(
            "Relatorio de Conciliacao - CBS Oficial x XMLs Locais",
            170, h - 43, w - 190, 16.2, 20, "Helvetica-Bold", colors.white,
        )
        texto("FiscalPro  |  Assistente Fiscal Inteligente", 171, h - 86, "Helvetica", 9.7, colors.white)

        def secao(titulo, y):
            retangulo(margem, y, w - 2 * margem, 24, azul_claro, raio=5)
            texto(titulo, margem + 12, y + 7, "Helvetica-Bold", 12, marinho)

        secao("Identificacao da consulta", 692)
        retangulo(margem, 625, w - 2 * margem, 63, colors.white, colors.HexColor("#C9DEEF"))
        campos = [
            ("Empresa", r["empresa"]),
            ("CNPJ", _br_cnpj(r["cnpj"])),
            ("Competencia", r["competencia"][5:7] + "/" + r["competencia"][:4]),
            ("Modulo", "CBS Oficial RTC 2"),
            ("Retorno", "Debitos" if tipo == "debitos" else "Creditos"),
        ]
        largura_campo = (w - 2 * margem) / 5
        for i, (rotulo, valor) in enumerate(campos):
            x = margem + i * largura_campo + 7
            if i:
                c.setStrokeColor(colors.HexColor("#D2E3F2"))
                c.line(x - 6, 634, x - 6, 679)
            texto(rotulo, x, 669, "Helvetica", 8, azul)
            quebrar(valor, x, 649, largura_campo - 12, 8.6, 11, "Helvetica-Bold", marinho)

        secao("Resumo executivo", 589)
        metricas = [
            ("XMLs locais", r["xmls"]),
            ("Oficiais na raiz", r["oficiais"]),
            ("Conferem", r["conferem"]),
            ("Sem retorno", r["sem_retorno"]),
            ("Divergencias", r["diferencas"]),
        ]
        espa = 6
        card_w = (w - margem * 2 - 4 * espa) / 5
        for i, (rotulo, valor) in enumerate(metricas):
            x = margem + i * (card_w + espa)
            destaque = i == 2 and r["comparaveis"] > 0 and not r["diferencas"]
            retangulo(x, 505, card_w, 75, verde_claro if destaque else azul_claro,
                      colors.HexColor("#C5DFEC"), raio=6)
            texto_central(rotulo, x + card_w / 2, 555, "Helvetica", 8.1, marinho)
            texto_central(
                _br_num(valor), x + card_w / 2, 522,
                "Helvetica-Bold", 19, verde if destaque else marinho,
            )

        secao("Resultados da conciliacao", 468)
        paragrafo = (
            f"Conferencia dos XMLs locais de {competencia[5:7]}/{competencia[:4]} "
            f"com retornos incrementais da CBS disponiveis para a raiz {r['cnpj_base']}. "
            f"Entre {_br_num(r['xmls'])} documentos locais, "
            f"{_br_num(r['comparaveis'])} possuem correspondencia oficial unica, "
            f"dos quais {_br_num(r['conferem'])} conferem e "
            f"{_br_num(r['diferencas'])} apresentam diferenca de CBS."
        )
        quebrar(paragrafo, margem + 8, 453, w - 2 * margem - 14, 9.2, 12.6)

        colunas_tabela = [
            ("Indicador", 0), ("Quantidade", 290), ("Observacao", 377),
        ]
        retangulo(margem, 357, w - 2 * margem, 27, azul, raio=2)
        texto("Indicador", margem + 10, 367, "Helvetica-Bold", 9, colors.white)
        texto("Quantidade", margem + 290, 367, "Helvetica-Bold", 9, colors.white)
        texto("Observacao", margem + 382, 367, "Helvetica-Bold", 9, colors.white)
        itens_tabela = [
            ("XMLs locais", r["xmls"], "Operacao selecionada"),
            ("Oficiais armazenados", r["oficiais"], "Retorno por raiz do CNPJ"),
            ("Conferem", r["conferem"], "CBS XML x oficial"),
            ("Sem retorno", r["sem_retorno"], "Nao implica ausencia na RFB"),
            ("Diferencas", r["diferencas"], "Revisar casos detectados"),
        ]
        for i, (rotulo, valor, detalhe) in enumerate(itens_tabela):
            y = 357 - (i + 1) * 22
            retangulo(margem, y, w - 2 * margem, 22,
                      colors.white if i % 2 == 0 else azul_claro, raio=0)
            texto(rotulo, margem + 10, y + 7, "Helvetica-Bold", 8.7)
            texto(_br_num(valor), margem + 290, y + 7, "Helvetica-Bold", 9)
            texto(detalhe, margem + 382, y + 7, "Helvetica", 7.9)
        secao("Observacoes tecnicas", 212)
        observacoes = [
            "Retorno oficial incremental e por raiz do CNPJ; pode conter documentos de filiais.",
            "Nota nao localizada neste retorno NAO significa que a Receita a desconheca.",
            "Valores nao representam apuracao definitiva, pagamento ou apropriacao de credito.",
            "Diferencas de ate R$ 0,02 sao classificadas como CONFERE pelo comparador.",
        ]
        y = 193
        for obs in observacoes:
            c.setFillColor(azul)
            c.circle(margem + 9, y + 2, 2.1, fill=1, stroke=0)
            y = quebrar(obs, margem + 20, y, w - 2 * margem - 28, 8.7, 11.5) - 5

        retangulo(margem, 67, w - 2 * margem, 58, verde_claro, verde, raio=7)
        c.setFillColor(verde)
        c.circle(margem + 29, 96, 16, fill=1, stroke=0)
        texto_central("OK", margem + 29, 92, "Helvetica-Bold", 9.5, colors.white)
        texto("Conclusao", margem + 59, 104, "Helvetica-Bold", 13, marinho)
        quebrar(self._texto_conclusao(r), margem + 59, 88, w - 2 * margem - 75, 9, 11, "Helvetica", cinza)
        c.setStrokeColor(azul)
        c.line(margem, 48, w - margem, 48)
        texto("FiscalPro | Stephane Rhis + ChatGPT", margem, 32, "Helvetica-Bold", 8, azul)
        texto("Relatorio analitico para conferencia interna", w - 214, 32, "Helvetica-Oblique", 7, cinza)
        texto("1", w - margem - 6, 19, "Helvetica", 7, cinza)
        c.showPage()

        # Anexo: lista completa dos XMLs locais, mesmo os sem retorno.
        if incluir_anexo:
            largura, altura = landscape(A4)
            c.setPageSize((largura, altura))
            tabela_x = 33
            pagina = 2
            blocos = 28
            for inicio in range(0, len(linhas), blocos):
                grupo = linhas[inicio:inicio + blocos]
                c.setFillColor(azul)
                c.rect(0, altura - 76, largura, 76, fill=1, stroke=0)
                logo(33, altura - 67, 95, 45)
                texto("Anexo documental | Conciliacao por chave", 148, altura - 39,
                      "Helvetica-Bold", 15, colors.white)
                texto(
                    f"{_texto_seguro(r['empresa'])} | {competencia} | {tipo.upper()} "
                    f"| {inicio + 1}-{inicio + len(grupo)} de {len(linhas)}",
                    148, altura - 57, "Helvetica", 9, colors.white,
                )
                texto(
                    "Valores em R$. Retorno incremental: sem retorno nao e ausencia na Receita. "
                    "Diferenca = CBS XML - CBS oficial.",
                    tabela_x, altura - 98, "Helvetica", 8.4,
                )
                larguras = [53, 48, 67, 238, 63, 63, 63, 148]
                nomes = ["NF", "Op.", "Emissao", "Chave do documento",
                         "CBS XML", "CBS oficial", "Diferenca", "Resultado"]
                tabela_y = altura - 129
                retangulo(tabela_x, tabela_y, sum(larguras), 24, azul, raio=2)
                px = tabela_x
                for titulo, tam in zip(nomes, larguras):
                    texto(titulo, px + 5, tabela_y + 8, "Helvetica-Bold", 8, colors.white)
                    px += tam
                for idx, doc in enumerate(grupo):
                    ylinha = tabela_y - 19 * (idx + 1)
                    retangulo(tabela_x, ylinha, sum(larguras), 19,
                              colors.white if idx % 2 == 0 else azul_claro, raio=0)
                    vals = [
                        doc["nf"], doc["tipo"], doc["emissao"], doc["chave"],
                        f"{doc['cbs_xml']:.2f}",
                        "" if doc["cbs_oficial"] is None else f"{doc['cbs_oficial']:.2f}",
                        "" if doc["diferenca"] is None else f"{doc['diferenca']:.2f}",
                        {
                            "CONFERE": "CONFERE",
                            "DIFERENCA_REVISAR": "DIFERENCA - REVISAR",
                            "MULTIPLOS_OFICIAIS_REVISAR": "MULTIPLOS - REVISAR",
                            "SEM_DADO_NESTE_RETORNO": "SEM RETORNO",
                        }[doc["status"]],
                    ]
                    px = tabela_x
                    for valor, tamanho_coluna in zip(vals, larguras):
                        # Evita ultrapassar a coluna em valores nao controlados.
                        texto(str(valor)[:45], px + 5, ylinha + 6,
                              "Helvetica", 7.8 if tamanho_coluna > 100 else 7.4,
                              colors.HexColor("#A12E27")
                              if doc["status"] in STATUS_REVISAR else cinza)
                        px += tamanho_coluna
                c.setStrokeColor(azul)
                c.line(33, 26, largura - 33, 26)
                texto("FiscalPro | Stephane Rhis + ChatGPT", 33, 12,
                      "Helvetica-Bold", 8, azul)
                texto(f"Pagina {pagina}", largura - 93, 12, "Helvetica", 8, azul)
                pagina += 1
                c.showPage()
        c.save()
        return destino
