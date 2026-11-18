"""Adiciona aba de antecipacao SEM alterar memoria de ICMS-ST existente."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from pathlib import Path

from src.services.antecipacao_simples_mg_service import (
    calcular_lote, FONTE,
)


def adicionar_aba_antecipacao(
    arquivo: str | Path, resultado: dict, *, destinatario_simples: bool,
    finalidade: str, aliquota_interna: object,
    aliquota_interestadual: object,
) -> dict:
    """A planilha ST original permanece; segunda aba e demonstrativa."""
    from openpyxl import load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    caminho = Path(arquivo)
    if not caminho.is_file() or caminho.suffix.lower() != ".xlsx":
        raise ValueError("Gere primeiro a planilha ICMS-ST XLSX.")
    linhas = calcular_lote(
        resultado, destinatario_simples=destinatario_simples,
        finalidade=finalidade, aliquota_interna=aliquota_interna,
        aliquota_interestadual=aliquota_interestadual,
    )
    wb = load_workbook(caminho)
    if "Antecipacao SN MG" in wb.sheetnames:
        del wb["Antecipacao SN MG"]
    ws = wb.create_sheet("Antecipacao SN MG")
    ws.sheet_view.showGridLines = False
    ws.merge_cells("A1:O1")
    ws["A1"] = "FISCALPRO | ANTECIPACAO DO ICMS - SIMPLES NACIONAL / MG"
    ws["A1"].font = Font(size=16, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor="114B7A")
    ws.row_dimensions[1].height = 34
    ws.merge_cells("A2:O2")
    ws["A2"] = (
        "SIMULACAO CONDICIONAL - NAO E GUIA/DAE OU APURACAO. "
        "ANTECIPACAO SEM ENCERRAMENTO NAO SE CONFUNDE COM ICMS-ST. "
        "Conferir regras, produtos, beneficios, destino e base."
    )
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="center")
    ws["A2"].font = Font(color="8C5B00", bold=True)
    ws.row_dimensions[2].height = 34
    for col, valor in [
        ("A4", "Regime do destinatario"), ("B4", "SIMPLES NACIONAL" if destinatario_simples else "NAO CONFIRMADO"),
        ("D4", "Finalidade da entrada"), ("E4", finalidade),
        ("G4", "UF origem"), ("H4", resultado.get("uf_origem", "")),
        ("J4", "UF destino"), ("K4", resultado.get("uf_destino", "")),
        ("A5", "Al. interna MG %"), ("B5", aliquota_interna),
        ("D5", "Al. interestadual %"), ("E5", aliquota_interestadual),
    ]:
        ws[col] = valor
        ws[col].font = Font(color="114B7A", bold=col[0] in ("A", "D", "G", "J"))
    ws.merge_cells("A6:O6")
    ws["A6"] = (
        "Metodologia: excluir ICMS interestadual da operacao; recompor base "
        "pela aliquota interna; ICMS interno menos ICMS interestadual. "
        "Nao somar aos valores ST; revisar inclusao de IPI."
    )
    ws["A6"].alignment = Alignment(wrap_text=True)
    ws.row_dimensions[6].height = 32
    heads = [
        "Item", "Codigo", "Descricao", "NCM", "CFOP XML (fornecedor)",
        "Status da antecipacao", "Base operacao R$", "Aliq. int. MG %",
        "Aliq. interestadual %", "ICMS inter. R$", "Base recomposta R$",
        "ICMS interno R$", "Antecipacao estimada R$", "Observacao",
        "Fonte legal",
    ]
    header_row = 8
    for col, h in enumerate(heads, 1):
        cell = ws.cell(header_row, col, h)
        cell.fill = PatternFill("solid", fgColor="114B7A")
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[header_row].height = 34

    statuses = Counter()
    for num, linha in enumerate(linhas, header_row + 1):
        item, dados = linha["item"], linha["resultado"]
        statuses[dados["status"]] += 1
        valores = [
            item.get("numero_item"), item.get("codigo"), item.get("descricao"),
            item.get("ncm"), item.get("cfop"), dados["status"],
            dados["base_operacao"], dados["aliquota_interna"],
            dados["aliquota_interestadual"], dados["icms_interestadual"],
            dados["base_recomposta"], dados["icms_interno"],
            dados["antecipacao_estimada"], dados["motivo"], dados["fonte"],
        ]
        for col, valor in enumerate(valores, 1):
            cell = ws.cell(num, col, float(valor) if isinstance(valor, Decimal) else valor)
            cell.alignment = Alignment(vertical="top", wrap_text=col in (3, 6, 14))
            if col in (7, 10, 11, 12, 13) and valor is not None:
                cell.number_format = 'R$ #,##0.00'
            if col in (8, 9) and valor is not None:
                cell.number_format = '0.00"%"'
        cor = "E7F2FD" if dados["status"] == "SIMULACAO CONDICIONAL" else "FFF2D7"
        ws.cell(num, 6).fill = PatternFill("solid", fgColor=cor)
        ws.cell(num, 6).font = Font(color="114B7A" if cor == "E7F2FD" else "945F00", bold=True)

    primeira = header_row + 1
    ultima = max(primeira, header_row + len(linhas))
    total = ultima + 2
    ws.cell(total, 12, "TOTAL SIMULADO (NAO RECOLHER)")
    ws.cell(total, 12).font = Font(bold=True, color="114B7A")
    ws.cell(total, 13, f"=SUM(M{primeira}:M{ultima})")
    ws.cell(total, 13).number_format = 'R$ #,##0.00'
    ws.cell(total, 13).font = Font(bold=True, color="114B7A")
    ws.merge_cells(start_row=total+2, start_column=1, end_row=total+2, end_column=15)
    ws.cell(total+2, 1, "Fonte oficial: " + FONTE)
    ws.cell(total+2, 1).hyperlink = FONTE
    ws.cell(total+2, 1).font = Font(color="2266AA", underline="single")
    for i, width in enumerate([8, 15, 40, 13, 18, 27, 19, 14, 17, 19, 20, 19, 24, 72, 65], 1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "F9"
    ws.auto_filter.ref = f"A8:O{ultima}"
    wb.calculation.fullCalcOnLoad = True
    wb.save(caminho)
    return {"arquivo": str(caminho), "total_itens": len(linhas), "status": dict(statuses)}
