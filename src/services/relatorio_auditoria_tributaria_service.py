"""Relatorio visual da Auditoria Tributaria do SPED Inteligente.

Exibe fielmente os apontamentos produzidos pela auditoria (sem recalcular
impostos nem sugerir creditos). Formatos PDF e XLSX; TXT legado permanece
no auditor para compatibilidade. Nenhum arquivo fiscal original e alterado.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from src.core.caminhos import pasta_recursos

AZUL = "164B78"
AZUL_ESCURO = "10395E"
AZUL_CLARO = "EAF2F8"
VERMELHO = "A52A39"
ROSA = "FCECEF"
AMARELO = "FFF2D9"
CINZA = "526478"
TEXTO = "243449"
AVISO = (
    "CONFERENCIA INFORMATIVA: resultado limitado aos registros, XMLs e regras "
    "realmente utilizados. Divergencias da ficha nao comprovam, isoladamente, "
    "infracao fiscal. Este relatorio nao substitui a validacao no PVA, a "
    "revisao da legislacao nem autoriza correcao ou aproveitamento de creditos."
)
CABECALHOS = (
    "Nivel", "Origem", "Linha SPED", "NF", "Chave NF-e", "Item",
    "Cod. produto", "Descricao", "NCM", "Campo", "Valor no SPED",
    "Valor de referencia", "Regra ID", "Aderencia (%)",
    "Problema / divergencia", "Orientacao",
)


def _logo() -> Path:
    return pasta_recursos() / "assets" / "fiscalpro_logo_horizontal.png"


def _texto_seguro(valor: Any) -> str:
    """Neutraliza formula injection em campos derivados de XML ou SPED."""
    texto = str(valor if valor is not None else "")
    return ("'" + texto) if texto.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else texto


def _resumo(resultado: Any) -> dict[str, Any]:
    apontamentos = tuple(resultado.apontamentos)
    return {
        "itens": resultado.total_itens,
        "erros": sum(a.nivel == "ERRO" for a in apontamentos),
        "avisos": sum(a.nivel == "AVISO" for a in apontamentos),
        "total": len(apontamentos),
        "por_origem": Counter((a.origem or "Outros") for a in apontamentos),
    }


def _dados_linha(a: Any) -> tuple:
    return (
        a.nivel, a.origem, a.linha, a.documento, a.chave, a.item,
        a.codigo, a.descricao, a.ncm, a.campo, a.atual, a.esperado,
        a.regra_id, a.aderencia, a.mensagem, a.orientacao,
    )


class ServicoRelatorioAuditoriaTributaria:
    """Exporta a auditoria ja executada, sem qualquer acesso aos XMLs/bancos."""

    def gerar(self, resultado: Any, caminho_sped: str | Path, destino: str | Path) -> Path:
        caminho = Path(destino)
        sufixo = caminho.suffix.lower()
        if sufixo not in {".pdf", ".xlsx"}:
            raise ValueError("Selecione formato PDF (.pdf) ou Excel (.xlsx).")
        if resultado is None:
            raise ValueError("Execute primeiro a Auditoria Tributaria.")
        caminho.parent.mkdir(parents=True, exist_ok=True)
        if sufixo == ".pdf":
            self._pdf(resultado, caminho_sped, caminho)
        else:
            self._excel(resultado, caminho_sped, caminho)
        return caminho

    @staticmethod
    def _excel(resultado: Any, caminho_sped: str | Path, destino: Path) -> None:
        from openpyxl import Workbook
        from openpyxl.drawing.image import Image
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        wb = Workbook()
        resumo_ws = wb.active
        resumo_ws.title = "Resumo"
        resumo_ws.sheet_view.showGridLines = False

        def cabecalho(ws, subtitulo: str) -> None:
            ws.sheet_view.showGridLines = False
            ws.merge_cells("D1:P3")
            titulo = ws["D1"]
            titulo.value = "FiscalPro  |  " + subtitulo
            titulo.font = Font(name="Aptos Display", size=17, bold=True, color=AZUL)
            titulo.alignment = Alignment(vertical="center", wrap_text=True)
            ws.row_dimensions[1].height = 24
            ws.row_dimensions[2].height = 24
            ws.row_dimensions[3].height = 24
            logotipo = _logo()
            if logotipo.is_file():
                try:
                    imagem = Image(str(logotipo))
                    fator = min(173 / imagem.width, 60 / imagem.height)
                    imagem.width = int(imagem.width * fator)
                    imagem.height = int(imagem.height * fator)
                    ws.add_image(imagem, "A1")
                except (OSError, ValueError, ImportError):
                    ws["A1"] = "FiscalPro"
            else:
                ws["A1"] = "FiscalPro"
            ws.merge_cells("A4:P4")
            c = ws["A4"]
            c.value = (
                f"Empresa: {_texto_seguro(resultado.contexto.get('empresa', ''))}  |  "
                f"Regime: {_texto_seguro(resultado.contexto.get('regime', ''))}  |  "
                f"SPED: {_texto_seguro(Path(caminho_sped).name)}  |  "
                f"Gerado: {datetime.now():%d/%m/%Y %H:%M}"
            )
            c.font = Font(size=10, bold=True, color=TEXTO)
            c.alignment = Alignment(vertical="center", wrap_text=True)
            ws.row_dimensions[4].height = 25
            ws.merge_cells("A5:P6")
            aviso = ws["A5"]
            aviso.value = AVISO
            aviso.fill = PatternFill("solid", fgColor=AMARELO)
            aviso.font = Font(size=10, bold=True, color="765012")
            aviso.alignment = Alignment(wrap_text=True, vertical="center")
            ws.row_dimensions[5].height = 23
            ws.row_dimensions[6].height = 24

        cabecalho(resumo_ws, "Auditoria Tributaria | Visao Geral")
        resumo = _resumo(resultado)
        metricas = [
            ("A8:D8", "A9:D10", "Itens C170 auditados", resumo["itens"]),
            ("E8:H8", "E9:H10", "Erros identificados", resumo["erros"]),
            ("I8:L8", "I9:L10", "Avisos e pendencias", resumo["avisos"]),
            ("M8:P8", "M9:P10", "Apontamentos totais", resumo["total"]),
        ]
        for titulo_area, numero_area, titulo, numero in metricas:
            resumo_ws.merge_cells(titulo_area)
            a = resumo_ws[titulo_area.split(":")[0]]
            a.value = titulo
            a.font = Font(size=10, bold=True, color="FFFFFF")
            a.fill = PatternFill("solid", fgColor=AZUL_ESCURO)
            a.alignment = Alignment(horizontal="center", vertical="center")
            resumo_ws.merge_cells(numero_area)
            b = resumo_ws[numero_area.split(":")[0]]
            b.value = numero
            b.font = Font(size=19, bold=True, color=AZUL)
            b.fill = PatternFill("solid", fgColor=AZUL_CLARO)
            b.alignment = Alignment(horizontal="center", vertical="center")
        resumo_ws.row_dimensions[8].height = 24
        resumo_ws.row_dimensions[9].height = 26
        resumo_ws.row_dimensions[10].height = 22

        indicadores = [
            ("Com cadastro 0200", resultado.itens_com_0200),
            ("Sem cadastro 0200", resultado.itens_sem_0200),
            ("Com regra tributaria", resultado.itens_com_regra),
            ("Sem regra tributaria", resultado.itens_sem_regra),
            ("Itens com XML localizado", resultado.itens_com_xml),
            ("Itens sem XML correspondente", resultado.itens_sem_xml),
            ("NF-e validas importadas", resultado.xml_validos_importados),
            ("NFC-e validas (sem C170)", resultado.nfce_validas_importadas),
            ("NF-e com C170 (chaves)", resultado.notas_c170_chaves_unicas),
            ("NF-e com C170 / XML", resultado.notas_c170_chaves_coincidentes),
            ("Chaves C100 com XML (geral)", resultado.notas_sped_chaves_coincidentes),
            ("Cobertura das regras (%)", resultado.cobertura_regras),
            ("Conformidade avaliavel", resultado.conformidade_exibicao),
        ]
        resumo_ws["A12"] = "Cobertura da auditoria"
        resumo_ws["A12"].font = Font(size=12, bold=True, color=AZUL)
        for idx, (nome, valor) in enumerate(indicadores, 14):
            resumo_ws.merge_cells(start_row=idx, start_column=1, end_row=idx, end_column=5)
            resumo_ws.cell(idx, 1, nome)
            resumo_ws.cell(idx, 6, valor)
            if idx % 2 == 0:
                resumo_ws.cell(idx, 1).fill = PatternFill("solid", fgColor="F4F8FB")
                resumo_ws.cell(idx, 6).fill = PatternFill("solid", fgColor="F4F8FB")
        resumo_ws["H12"] = "Apontamentos por origem"
        resumo_ws["H12"].font = Font(size=12, bold=True, color=AZUL)
        for idx, (origem, contagem) in enumerate(
            sorted(resumo["por_origem"].items(), key=lambda x: (-x[1], x[0])), 14
        ):
            resumo_ws.merge_cells(start_row=idx, start_column=8, end_row=idx, end_column=13)
            resumo_ws.cell(idx, 8, _texto_seguro(origem))
            resumo_ws.cell(idx, 14, contagem)

        resumo_ws.merge_cells("A24:P25")
        aviso_detalhe = resumo_ws["A24"]
        aviso_detalhe.value = (
            (resultado.diagnostico_regras + " " if resultado.diagnostico_regras else "")
            + (resultado.diagnostico_xml + " " if resultado.diagnostico_xml else "")
            + "A aba Todos preserva cada apontamento, inclusive linha, NF, chave, "
            "produto, valores atuais e de referencia, regra, problema e orientacao. "
            "Erros e Avisos permitem filtragem separada. A conformidade e apenas "
            "indicador dos testes executados: nao representa homologacao fiscal."
        )
        aviso_detalhe.font = Font(color=CINZA, italic=True, size=10)
        aviso_detalhe.alignment = Alignment(wrap_text=True, vertical="center")
        resumo_ws.row_dimensions[24].height = 28
        resumo_ws.row_dimensions[25].height = 28
        for coluna in range(1, 17):
            resumo_ws.column_dimensions[get_column_letter(coluna)].width = 13.5
        resumo_ws.freeze_panes = "A8"
        resumo_ws.page_setup.orientation = "landscape"
        resumo_ws.sheet_properties.pageSetUpPr.fitToPage = True

        apontamentos = tuple(resultado.apontamentos)
        for nome, filtrados in (
            ("Todos", apontamentos),
            ("Erros", tuple(a for a in apontamentos if a.nivel == "ERRO")),
            ("Avisos", tuple(a for a in apontamentos if a.nivel == "AVISO")),
        ):
            ws = wb.create_sheet(nome)
            cabecalho(ws, f"Auditoria Tributaria | {nome}")
            for coluna, nome_campo in enumerate(CABECALHOS, 1):
                celula = ws.cell(8, coluna, nome_campo)
                celula.fill = PatternFill("solid", fgColor=AZUL)
                celula.font = Font(color="FFFFFF", bold=True, size=10)
                celula.alignment = Alignment(wrap_text=True, vertical="center")
            ws.row_dimensions[8].height = 31
            for linha, apontamento in enumerate(filtrados, 9):
                for coluna, valor in enumerate(_dados_linha(apontamento), 1):
                    numero = coluna in {3, 14}
                    celula = ws.cell(
                        linha, coluna, valor if numero else _texto_seguro(valor)
                    )
                    celula.font = Font(size=10, color=TEXTO)
                    celula.alignment = Alignment(vertical="center")
                    if linha % 2 == 0:
                        celula.fill = PatternFill("solid", fgColor="F5F9FC")
                    if coluna == 1:
                        celula.font = Font(bold=True, color=VERMELHO if apontamento.nivel == "ERRO" else "916019")
                        celula.fill = PatternFill(
                            "solid", fgColor=ROSA if apontamento.nivel == "ERRO" else AMARELO
                        )
                    if coluna in {5, 7, 9, 13}:
                        celula.number_format = "@"
                # Problema/orientacao sao longos; habilitar wrap sem truncar os dados.
                for col in (15, 16):
                    ws.cell(linha, col).alignment = Alignment(wrap_text=True, vertical="center")
            larguras = (
                12, 23, 14, 13, 51, 9, 24, 44, 14, 23,
                23, 23, 14, 15, 80, 80,
            )
            for i, largura in enumerate(larguras, 1):
                ws.column_dimensions[get_column_letter(i)].width = largura
            ws.freeze_panes = "H9"
            ws.auto_filter.ref = f"A8:P{max(8, len(filtrados) + 8)}"
            ws.page_setup.orientation = "landscape"
            ws.sheet_properties.pageSetUpPr.fitToPage = True
            ws.print_title_rows = "1:8"

        # Rastreabilidade documental detalhada: somente dados existentes
        # no SPED e nos XMLs. Nao pressupoe ausencia fiscal nem atualiza EFD.
        planilhas_documentos = (
            (
                "NF-e com C170",
                (
                    "Operacao", "Numero NF", "Serie", "Chave de acesso",
                    "Mes da chave", "CNPJ emitente", "Itens C170",
                    "Conferencia", "Origem do XML",
                ),
                (
                    (
                        item.get("operacao"), item.get("numero"), item.get("serie"),
                        item.get("chave"), item.get("mes_chave"),
                        item.get("cnpj_emitente"), item.get("itens_c170"),
                        item.get("situacao"), item.get("origem_xml"),
                    )
                    for item in resultado.documentos_c170
                ),
                (7,),
            ),
            (
                "XMLs importados",
                (
                    "Numero NF", "Serie", "Chave de acesso", "Mes da chave",
                    "CNPJ emitente", "CNPJ destinatario", "Itens no XML",
                    "Conferencia no SPED", "Pasta ou arquivo de origem",
                ),
                (
                    (
                        item.get("numero"), item.get("serie"), item.get("chave"),
                        item.get("mes_chave"), item.get("emitente"),
                        item.get("destinatario"), item.get("itens_xml"),
                        item.get("situacao"), item.get("origem_xml"),
                    )
                    for item in resultado.documentos_xml_importados
                ),
                (7,),
            ),
        )
        for nome, cabecalhos, linhas, numericas in planilhas_documentos:
            ws = wb.create_sheet(nome)
            ws.sheet_view.showGridLines = False
            ws.append(cabecalhos)
            for celula in ws[1]:
                celula.font = Font(color="FFFFFF", bold=True)
                celula.fill = PatternFill("solid", fgColor=AZUL)
                celula.alignment = Alignment(wrap_text=True, vertical="center")
            ws.row_dimensions[1].height = 28
            for linha in linhas:
                linha_excel = ws.max_row + 1
                for coluna, valor in enumerate(linha, start=1):
                    valor_seguro = (
                        valor if coluna in numericas else _texto_seguro(valor)
                    )
                    celula = ws.cell(linha_excel, coluna, valor_seguro)
                    celula.font = Font(size=10, color=TEXTO)
                    if linha_excel % 2 == 0:
                        celula.fill = PatternFill("solid", fgColor="F5F9FC")
                    # Números, CNPJs e chaves sao documentos, nao quantidades.
                    if coluna not in numericas:
                        celula.number_format = "@"
            widths = (15, 18, 52, 17, 23, 23, 17, 28, 73)
            if nome == "NF-e com C170":
                widths = (17, 18, 13, 52, 17, 23, 17, 28, 73)
            for coluna, largura in enumerate(widths, 1):
                ws.column_dimensions[get_column_letter(coluna)].width = largura
            ws.freeze_panes = "D2"
            ws.auto_filter.ref = f"A1:I{max(2, ws.max_row)}"
            ws.print_title_rows = "1:1"
            ws.sheet_properties.pageSetUpPr.fitToPage = True
            ws.page_setup.orientation = "landscape"

        # Referencias oficiais ficam em aba independente da Ficha.
        # Nao sao regras operacionais nem autorizam credito/correcao.
        ws_ref = wb.create_sheet("Referencias fiscais")
        ws_ref.sheet_view.showGridLines = False
        colunas_ref = (
            ("linha_sped", "Linha SPED"), ("nota", "NF"),
            ("chave", "Chave NF-e"), ("item", "Item C170"),
            ("codigo_produto", "Codigo produto"), ("descricao_sped", "Descricao"),
            ("ncm", "NCM"), ("ncm_status", "NCM na base oficial"),
            ("ncm_descricao_oficial", "Descricao NCM oficial"),
            ("ncm_fonte", "Fonte NCM"), ("tipi_status", "Referencia TIPI"),
            ("regime", "Regime"), ("operacao", "Operacao"),
            ("finalidade", "Finalidade"), ("uf_origem", "UF origem"),
            ("uf_destino", "UF destino"), ("data_operacao", "Data operacao"),
            ("pis_status", "PIS/Cofins: status referencial"),
            ("pis_confirmado", "Enquadramento PIS/Cofins confirmado"),
            ("pis_fundamento", "Fundamento PIS/Cofins"),
            ("pis_fonte", "Fonte PIS/Cofins"),
            ("icms_status", "ICMS/MG: status referencial"),
            ("icms_confirmado", "Aliquota ICMS confirmada"),
            ("st_status", "ST/MG: status referencial"),
            ("st_decisao_confirmada", "Decisao ST confirmada"),
            ("st_cest", "CEST referencial (NAO automatico)"),
            ("icms_fonte", "Fonte ICMS/MG"),
            ("falha_tecnica", "Falha tecnica na consulta"),
            ("restricao_uso", "Restricoes de uso"),
        )
        for col, (_chave, titulo_celula) in enumerate(colunas_ref, 1):
            celula = ws_ref.cell(1, col, titulo_celula)
            celula.font = Font(bold=True, color="FFFFFF", size=10)
            celula.fill = PatternFill("solid", fgColor=AZUL)
            celula.alignment = Alignment(vertical="center", wrap_text=True)
        ws_ref.row_dimensions[1].height = 38
        for indice, ref in enumerate(resultado.referencias_fiscais, start=2):
            for col, (chave, _titulo) in enumerate(colunas_ref, start=1):
                valor = ref.get(chave)
                if isinstance(valor, bool):
                    valor = "SIM" if valor else "NAO"
                celula = ws_ref.cell(
                    indice, col, valor if col == 1 and isinstance(valor, int)
                    else _texto_seguro(valor),
                )
                celula.font = Font(size=10, color=TEXTO)
                if indice % 2 == 0:
                    celula.fill = PatternFill("solid", fgColor="F5F9FC")
                if col in (3, 5, 7, 26):
                    celula.number_format = "@"
                if chave == "falha_tecnica" and valor == "SIM":
                    celula.fill = PatternFill("solid", fgColor=AMARELO)
        for col, largura in enumerate((
            13, 15, 51, 12, 24, 48, 15, 29, 55, 19, 32,
            20, 16, 20, 14, 14, 17, 48, 20, 68, 62, 44,
            18, 48, 18, 17, 58, 16, 90,
        ), start=1):
            ws_ref.column_dimensions[get_column_letter(col)].width = largura
        ws_ref.freeze_panes = "H2"
        ws_ref.auto_filter.ref = f"A1:AC{max(ws_ref.max_row, 2)}"
        ws_ref.print_title_rows = "1:1"

        wb.properties.title = "FiscalPro | Auditoria Tributaria SPED"
        wb.properties.subject = "Conferencia documental de regras e XMLs - sem correcao automatica"
        wb.properties.creator = "FiscalPro"
        wb.save(destino)

    @staticmethod
    def _pdf(resultado: Any, caminho_sped: str | Path, destino: Path) -> None:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.platypus import (
            CondPageBreak, LongTable, Paragraph,
            SimpleDocTemplate, Spacer, Table, TableStyle,
        )

        pagina = landscape(A4)
        larg, alt = pagina
        pdf = SimpleDocTemplate(
            str(destino), pagesize=pagina, leftMargin=30, rightMargin=30,
            topMargin=73, bottomMargin=42,
            title="FiscalPro | Auditoria Tributaria SPED",
            author="FiscalPro",
        )
        estilos = getSampleStyleSheet()
        titulo = ParagraphStyle(
            "SecaoAudit", parent=estilos["Heading2"], fontSize=12,
            leading=16, spaceBefore=14, spaceAfter=7,
            textColor=colors.HexColor("#164B78"),
        )
        corpo = ParagraphStyle(
            "CorpoAudit", parent=estilos["BodyText"], fontSize=9, leading=13,
            textColor=colors.HexColor("#243449"),
        )
        celula = ParagraphStyle(
            "CelulaAudit", parent=estilos["BodyText"], fontSize=7.5,
            leading=10.4, splitLongWords=1,
            textColor=colors.HexColor("#243449"),
        )
        aviso = ParagraphStyle(
            "NotaAudit", parent=corpo, fontSize=8.5, leading=12,
            textColor=colors.HexColor("#825312"),
        )
        def p(texto: Any, *, strong: bool = False, branco: bool = False):
            s = escape(str(texto if texto not in (None, "") else "-"))
            if strong:
                s = f"<b>{s}</b>"
            if branco:
                s = f'<font color="#FFFFFF">{s}</font>'
            return Paragraph(s, celula)

        r = _resumo(resultado)
        c = resultado.contexto
        story = [
            Paragraph(
                f"<b>Empresa:</b> {escape(str(c.get('empresa', '') or '-'))}  |  "
                f"<b>Regime:</b> {escape(str(c.get('regime', '') or '-'))}",
                corpo,
            ),
            Spacer(1, 4),
            Paragraph(
                f"<b>Arquivo SPED:</b> {escape(Path(caminho_sped).name)}  |  "
                f"<b>Emissão:</b> {datetime.now():%d/%m/%Y %H:%M}",
                corpo,
            ),
            Spacer(1, 11),
            Paragraph(escape(AVISO), aviso),
        ]
        if resultado.diagnostico_regras:
            story.append(Spacer(1, 7))
            story.append(Paragraph(
                "<b>COBERTURA INSUFICIENTE:</b> " + escape(resultado.diagnostico_regras),
                aviso,
            ))
        if resultado.diagnostico_xml:
            story.append(Spacer(1, 7))
            story.append(Paragraph(
                "<b>COBERTURA XML:</b> " + escape(resultado.diagnostico_xml),
                aviso,
            ))
        story.append(Paragraph("Resumo da auditoria", titulo))
        kpis = [
            ("Itens C170", str(r["itens"])),
            ("Erros", str(r["erros"])),
            ("Avisos", str(r["avisos"])),
            ("Total de apontamentos", str(r["total"])),
        ]
        quadro = Table(
            [
                [p(nome, strong=True) for nome, _ in kpis],
                [Paragraph(
                    f'<font size="15" color="#164B78"><b>{valor}</b></font>', corpo
                ) for _, valor in kpis],
            ],
            colWidths=[195, 195, 195, 195],
        )
        quadro.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF2F8")),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F8FAFC")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(quadro)
        story.append(Paragraph("Cobertura e rastreabilidade", titulo))
        cobertura = [
            ("Com / sem cadastro 0200", f"{resultado.itens_com_0200} / {resultado.itens_sem_0200}"),
            ("Com / sem regra tributaria", f"{resultado.itens_com_regra} / {resultado.itens_sem_regra}"),
            ("Itens com / sem XML associado", f"{resultado.itens_com_xml} / {resultado.itens_sem_xml}"),
            ("NF-e 55 com C170 / XML localizado", f"{resultado.notas_c170_chaves_unicas} / {resultado.notas_c170_chaves_coincidentes}"),
            ("Chaves C100 gerais / localizadas", f"{resultado.notas_sped_chaves_unicas} / {resultado.notas_sped_chaves_coincidentes}"),
            ("NFC-e separadas (modelo 65)", str(resultado.nfce_validas_importadas)),
            ("Cobertura de regras", f"{resultado.cobertura_regras:.2f}%".replace(".", ",")),
            ("Conformidade parcial", resultado.conformidade_exibicao),
        ]
        tab = Table([[p(a), p(b, strong=True)] for a, b in cobertura], colWidths=[270, 180])
        tab.setStyle(TableStyle([
            ("ROWBACKGROUNDS", (0, 0), (-1, -1),
             [colors.white, colors.HexColor("#F3F7FB")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(tab)
        if r["por_origem"]:
            story.append(Paragraph("Distribuicao por origem", titulo))
            origens = [[p(nome), p(qtde, strong=True)] for nome, qtde in
                       sorted(r["por_origem"].items(), key=lambda x: (-x[1], x[0]))]
            t = Table(origens, colWidths=[310, 80], hAlign="LEFT")
            t.setStyle(TableStyle([
                ("ROWBACKGROUNDS", (0, 0), (-1, -1),
                 [colors.white, colors.HexColor("#F3F7FB")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(t)
        story.append(CondPageBreak(120))
        story.append(Paragraph("Detalhamento dos apontamentos", titulo))
        if not resultado.apontamentos:
            story.append(Paragraph(
                "Nenhum apontamento foi gerado nas regras executadas. "
                "Isso nao comprova a conformidade integral da escrituracao.", corpo
            ))
        else:
            cab = [
                p("Nivel / origem", strong=True, branco=True),
                p("Documento / produto", strong=True, branco=True),
                p("Campo / valores", strong=True, branco=True),
                p("Problema / orientacao", strong=True, branco=True),
            ]
            linhas = [cab]
            for a in resultado.apontamentos:
                chave = str(a.chave or "")
                # A chave fiscal de 44 digitos e quebrada sem perda de conteudo.
                chave = escape(chave[:22]) + "<br/>" + escape(chave[22:]) if len(chave) > 22 else escape(chave or "-")
                detalhe = Paragraph(
                    f"<b>NF:</b> {escape(str(a.documento or '-'))} | "
                    f"<b>item:</b> {escape(str(a.item or '-'))}<br/>"
                    f"<b>Codigo:</b> {escape(str(a.codigo or '-'))}<br/>"
                    f"<b>NCM:</b> {escape(str(a.ncm or '-'))}<br/>"
                    f"<b>Linha:</b> {a.linha}<br/>"
                    f"<b>Chave:</b> {chave}",
                    celula,
                )
                valores = Paragraph(
                    f"<b>{escape(str(a.campo or '-'))}</b><br/>"
                    f"SPED: {escape(str(a.atual or '-'))}<br/>"
                    f"Ref.: {escape(str(a.esperado or '-'))}<br/>"
                    f"Regra: {escape(str(a.regra_id or '-'))}<br/>"
                    f"Aderencia: {a.aderencia:.0f}%",
                    celula,
                )
                explicacao = Paragraph(
                    f"<b>Problema</b><br/>{escape(str(a.mensagem or '-'))}<br/>"
                    f"<b>Orientacao</b><br/>{escape(str(a.orientacao or '-'))}",
                    celula,
                )
                linhas.append([
                    Paragraph(
                        f"<b>{escape(str(a.nivel or '-'))}</b><br/>"
                        f"{escape(str(a.origem or '-'))}",
                        celula,
                    ), detalhe, valores, explicacao,
                ])
            tabela = LongTable(
                linhas, repeatRows=1, colWidths=[98, 176, 164, 342],
                hAlign="LEFT", splitByRow=1,
            )
            estilo = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#164B78")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#F4F8FB")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#164B78")),
            ]
            for linha, a in enumerate(resultado.apontamentos, 1):
                if a.nivel == "ERRO":
                    estilo.append(("BACKGROUND", (0, linha), (0, linha),
                                   colors.HexColor("#FCECEF")))
                elif a.nivel == "AVISO":
                    estilo.append(("BACKGROUND", (0, linha), (0, linha),
                                   colors.HexColor("#FFF2D9")))
            tabela.setStyle(TableStyle(estilo))
            story.append(tabela)

        def moldura(canvas, documento):
            canvas.saveState()
            caminho = _logo()
            if caminho.is_file():
                try:
                    canvas.drawImage(
                        str(caminho), 30, alt - 50, width=132, height=34,
                        preserveAspectRatio=True, mask="auto",
                    )
                except (OSError, ValueError):
                    canvas.setFillColor(colors.HexColor("#164B78"))
                    canvas.setFont("Helvetica-Bold", 13)
                    canvas.drawString(30, alt - 32, "FiscalPro")
            else:
                canvas.setFillColor(colors.HexColor("#164B78"))
                canvas.setFont("Helvetica-Bold", 13)
                canvas.drawString(30, alt - 32, "FiscalPro")
            canvas.setFillColor(colors.HexColor("#164B78"))
            canvas.setFont("Helvetica-Bold", 13)
            canvas.drawString(185, alt - 30, "Auditoria Tributaria | SPED Inteligente")
            canvas.setStrokeColor(colors.HexColor("#C7D9E7"))
            canvas.line(30, alt - 60, larg - 30, alt - 60)
            canvas.setFillColor(colors.HexColor("#526478"))
            canvas.setFont("Helvetica", 8)
            canvas.drawString(30, 21, "FiscalPro | Documento de conferencia, sem correcao automatica")
            canvas.drawRightString(larg - 30, 21, f"Pagina {documento.page}")
            canvas.restoreState()

        pdf.build(story, onFirstPage=moldura, onLaterPages=moldura)
