"""RTC: exportacao de conferencia local IBS/CBS em Excel.

A planilha espelha apenas os XMLs armazenados, por estabelecimento e periodo.
NAO representa apuracao oficial, imposto a pagar ou credito apropriado.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from src.services.apuracao_assistida_local_service import ServicoApuracaoLocalRTC


AZUL = "143A5F"
AZUL_CLARO = "E9F2FA"
CINZA = "F2F4F7"
TEXTO = "243449"
AMARELO = "FFF4D6"
VERMELHO = "A33B2B"
FORMATO_DINHEIRO = '#,##0.00'
CABECALHOS = (
    "Tipo", "Numero NF", "Emissao", "Chave NF-e", "CNPJ emitente",
    "CNPJ destinatario", "Base IBS/CBS (XML)", "IBS (XML)", "CBS (XML)",
    "Conferencia local", "Protocolo no XML", "Situacao do credito",
    "Observacoes", "Arquivo de origem",
)
COLUNAS_MONETARIAS = (7, 8, 9)
ALERTA = (
    "APURACAO LOCAL / DADOS DOS XMLs - NAO OFICIAL. "
    "2026: periodo de transicao. Nao representa tributo a pagar, "
    "credito apropriado, recolhimento ou apuracao assistida da Receita. "
    "A completude depende da importacao de todos os XMLs e da verificacao "
    "de eventos posteriores de cancelamento, devolucao e complemento."
)


def _texto_seguro(valor) -> str:
    """Evita interpretacao de campos controlados por XML como formulas Excel."""
    s = str(valor if valor is not None else "")
    if s.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + s
    return s


def _valor(valor) -> float:
    return float(Decimal(str(valor or "0")))


def _titulos(ws, cnpj: str, periodo: str, nome_empresa: str, subtitulo: str):
    ws.sheet_view.showGridLines = False
    ws.merge_cells("A1:N1")
    topo = ws["A1"]
    topo.value = f"FiscalPro | {subtitulo}"
    topo.font = Font(bold=True, color="FFFFFF", size=15)
    topo.fill = PatternFill("solid", fgColor=AZUL)
    topo.alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 30

    ws.merge_cells("A2:N2")
    ws["A2"] = f"Empresa: {_texto_seguro(nome_empresa)} | CNPJ: {cnpj} | Competencia: {periodo}"
    ws["A2"].font = Font(bold=True, color=TEXTO, size=11)
    ws.row_dimensions[2].height = 24

    ws.merge_cells("A3:N4")
    aviso = ws["A3"]
    aviso.value = ALERTA
    aviso.font = Font(color=VERMELHO, bold=True, size=10)
    aviso.fill = PatternFill("solid", fgColor=AMARELO)
    aviso.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[3].height = 21
    ws.row_dimensions[4].height = 31


def _tabela(ws, documentos: list[dict], cnpj: str, periodo: str, nome_empresa: str):
    _titulos(ws, cnpj, periodo, nome_empresa, ws.title)
    ws.append([])  # linha 5
    for col, titulo in enumerate(CABECALHOS, 1):
        cell = ws.cell(row=6, column=col, value=titulo)
        cell.fill = PatternFill("solid", fgColor=AZUL)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[6].height = 30
    for idx, doc in enumerate(documentos, 7):
        valores = (
            doc.get("direcao"), doc.get("numero_nf"),
            doc.get("emissao"), doc.get("chave_nfe"),
            doc.get("cnpj_emitente"), doc.get("cnpj_destinatario"),
            _valor(doc.get("base_ibs_cbs")), _valor(doc.get("valor_ibs")),
            _valor(doc.get("valor_cbs")), doc.get("status_conferencia"),
            doc.get("status_protocolo"), doc.get("status_credito"),
            doc.get("observacao"), doc.get("arquivo_origem"),
        )
        for coluna, original in enumerate(valores, 1):
            celula = ws.cell(
                row=idx, column=coluna,
                value=original if coluna in COLUNAS_MONETARIAS else _texto_seguro(original)
            )
            celula.font = Font(color=TEXTO, size=10)
            if idx % 2 == 0:
                celula.fill = PatternFill("solid", fgColor="F6F9FC")
            if coluna in COLUNAS_MONETARIAS:
                celula.number_format = FORMATO_DINHEIRO
            if coluna in (4, 5, 6):
                celula.number_format = "@"
            if coluna == 10 and doc.get("status_conferencia") == "REVISAR":
                celula.fill = PatternFill("solid", fgColor=AMARELO)
                celula.font = Font(color=VERMELHO, bold=True)
    larguras = (12, 15, 14, 49, 22, 22, 19, 17, 17, 21, 29, 29, 73, 65)
    for coluna, largura in enumerate(larguras, 1):
        ws.column_dimensions[get_column_letter(coluna)].width = largura
    ws.freeze_panes = "D7"
    ws.auto_filter.ref = f"A6:N{max(6, len(documentos) + 6)}"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = "landscape"
    ws.print_title_rows = "1:6"


class ServicoRelatorioApuracaoLocalRTC:
    def __init__(self, servico: ServicoApuracaoLocalRTC | None = None):
        self.servico = servico or ServicoApuracaoLocalRTC()

    def gerar(self, cnpj: str, competencia: str, destino: str | Path, nome_empresa: str = "") -> Path:
        cnpj = self.servico.validar_cnpj(cnpj)
        competencia = self.servico.validar_competencia(competencia)
        destino = Path(destino)
        if destino.suffix.lower() != ".xlsx":
            raise ValueError("O relatorio deve ser salvo no formato .xlsx.")
        documentos = self.servico.listar(cnpj, competencia)
        if not documentos:
            raise ValueError("Nao ha XMLs importados para a empresa e competencia selecionadas.")

        entrada = [d for d in documentos if d["direcao"] == "ENTRADA"]
        saida = [d for d in documentos if d["direcao"] == "SAIDA"]
        revisar = [d for d in documentos if d["status_conferencia"] == "REVISAR"]
        sem_protocolo = sum(d["status_protocolo"] == "SEM_PROTOCOLO" for d in documentos)

        # Snapshot unico: os valores sao estritamente os dos XMLs.
        def soma(registros: list[dict], campo: str) -> float:
            return float(sum((Decimal(d.get(campo) or "0") for d in registros), Decimal("0")))

        wb = Workbook()
        resumo = wb.active
        resumo.title = "Resumo"
        _titulos(resumo, cnpj, competencia, nome_empresa, "Conferencia local mensal")
        resumo.column_dimensions["A"].width = 42
        resumo.column_dimensions["B"].width = 24
        resumo.column_dimensions["C"].width = 30
        resumo.column_dimensions["D"].width = 23
        resumo.freeze_panes = "B7"
        linhas = [
            ("Notas importadas", len(documentos), "Total por CNPJ e competencia", False),
            ("Saidas", len(saida), "Emitente = empresa", False),
            ("Entradas", len(entrada), "Destinatario = empresa", False),
            ("Notas para revisar", len(revisar), "Auditoria local ou protocolo pendente", False),
            ("XMLs sem protocolo SEFAZ", sem_protocolo, "Nao comprova situacao atual", False),
            ("Base IBS/CBS das saidas (XML)", soma(saida, "base_ibs_cbs"), "Valor nos XMLs", True),
            ("IBS destacado nas saidas (XML)", soma(saida, "valor_ibs"), "Nao e valor oficial a recolher", True),
            ("CBS destacada nas saidas (XML)", soma(saida, "valor_cbs"), "Nao e valor oficial a recolher", True),
            ("Base IBS/CBS das entradas (XML)", soma(entrada, "base_ibs_cbs"), "Valor nos XMLs", True),
            ("IBS potencial das entradas (XML)", soma(entrada, "valor_ibs"), "Nao apropriado automaticamente", True),
            ("CBS potencial das entradas (XML)", soma(entrada, "valor_cbs"), "Nao apropriado automaticamente", True),
        ]
        for n, (rotulo, valor, descricao, moeda) in enumerate(linhas, 7):
            resumo.cell(n, 1, rotulo)
            celula = resumo.cell(n, 2, valor)
            resumo.cell(n, 3, descricao)
            resumo.merge_cells(start_row=n, start_column=3, end_row=n, end_column=6)
            if moeda:
                celula.number_format = FORMATO_DINHEIRO
            if n % 2:
                for col in range(1, 7):
                    resumo.cell(n, col).fill = PatternFill("solid", fgColor=AZUL_CLARO)
            resumo.cell(n, 1).font = Font(bold=True, color=TEXTO)
            resumo.cell(n, 3).font = Font(italic=True, color="687789")
        resumo["A20"] = "Criterios:"
        resumo["A20"].font = Font(bold=True, color=AZUL)
        resumo.merge_cells("A21:N21")
        resumo["A21"] = (
            "Sem compensacao entre entradas e saidas. Compras sao creditos POTENCIAIS, "
            "nao reconhecidos nem apropriados. Valores sao apenas somatorios dos XMLs."
        )
        resumo["A21"].alignment = Alignment(wrap_text=True)
        resumo.row_dimensions[21].height = 32

        for nome, registros in (
            ("Entradas", entrada),
            ("Saidas", saida),
            ("Revisar", revisar),
        ):
            aba = wb.create_sheet(nome)
            _tabela(aba, registros, cnpj, competencia, nome_empresa)
        wb.properties.title = f"FiscalPro - conferencia local IBS CBS {competencia}"
        wb.properties.subject = "Auditoria local de XMLs, sem homologacao tributaria"
        wb.properties.creator = "FiscalPro"
        destino.parent.mkdir(parents=True, exist_ok=True)
        wb.save(destino)
        return destino
