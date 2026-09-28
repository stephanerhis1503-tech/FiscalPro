"""FiscalPro 18.2.17 - Memoria de Calculo do DIFAL.

Patch leve e isolado: acrescenta automaticamente uma aba "Memória de Cálculo"
aos arquivos XLSX de Auditoria DIFAL gerados pelo FiscalPro, sem alterar a
metodologia principal aprovada na 18.2.16.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

try:
    from openpyxl.workbook.workbook import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except Exception:
    Workbook = None


_PATCH_APLICADO = False
_ORIGINAL_SAVE = None


def _norm(valor) -> str:
    texto = "" if valor is None else str(valor)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _numero(valor):
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float, Decimal)):
        try:
            return Decimal(str(valor))
        except InvalidOperation:
            return None
    texto = str(valor).strip()
    if not texto:
        return None
    texto = texto.replace("R$", "").replace("%", "").replace(" ", "")
    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def _q2(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _fmt_brl(valor) -> str:
    n = _numero(valor) or Decimal("0")
    s = f"{_q2(n):,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_pct(valor) -> str:
    n = _numero(valor)
    if n is None:
        return "-"
    s = f"{n.quantize(Decimal('0.01')):.2f}".replace(".", ",")
    return s + "%"


def _achar_cabecalho(ws):
    limite = min(ws.max_row or 1, 30)
    for linha in range(1, limite + 1):
        valores = [_norm(ws.cell(linha, c).value) for c in range(1, (ws.max_column or 1) + 1)]
        conjunto = " | ".join(valores)
        tem_nf = any(v in {"nf", "nfe", "nf e", "numero nf", "numero nfe"} or "numero nf" in v for v in valores)
        tem_uf = any("uf destino" in v or v == "uf" for v in valores)
        tem_cfop = any(v == "cfop" or "cfop" in v for v in valores)
        if tem_nf and tem_uf and tem_cfop:
            return linha
        if "difal" in conjunto and tem_cfop and tem_uf:
            return linha
    return 1


def _mapear_cabecalhos(ws, linha):
    mapa = {}
    for c in range(1, (ws.max_column or 1) + 1):
        nome = _norm(ws.cell(linha, c).value)
        if nome:
            mapa[nome] = c
    return mapa


def _coluna(mapa, *aliases):
    for alias in aliases:
        alvo = _norm(alias)
        if alvo in mapa:
            return mapa[alvo]
    for nome, col in mapa.items():
        for alias in aliases:
            alvo = _norm(alias)
            if alvo and (alvo in nome or nome in alvo):
                return col
    return None


def _valor(ws, linha, mapa, *aliases):
    c = _coluna(mapa, *aliases)
    return ws.cell(linha, c).value if c else None


def _achar_detalhes(wb):
    preferidas = []
    demais = []
    for ws in wb.worksheets:
        n = _norm(ws.title)
        if "memoria" in n:
            continue
        if "difal" in n and "detalh" in n:
            preferidas.append(ws)
        elif "difal" in n and "resumo" not in n:
            demais.append(ws)
    return (preferidas or demais or [None])[0]


def _status_memoria(inter_sped, inter_xml, diferenca):
    a = _numero(inter_sped)
    b = _numero(inter_xml)
    d = _numero(diferenca) or Decimal("0")
    if a is not None and b is not None and abs(a - b) >= Decimal("0.01"):
        return "REVISAR ORIGEM - SPED x XML"
    if abs(d) <= Decimal("0.01"):
        return "OK"
    return "DIVERGÊNCIA"


def _adicionar_memoria(wb):
    origem = _achar_detalhes(wb)
    if origem is None:
        return

    nome_memoria = "Memória de Cálculo"
    if nome_memoria in wb.sheetnames:
        wb.remove(wb[nome_memoria])

    cab_linha = _achar_cabecalho(origem)
    mapa = _mapear_cabecalhos(origem, cab_linha)

    saida = wb.create_sheet(nome_memoria)
    cabecalhos = [
        "NF", "Chave NF-e", "UF destino", "CFOP", "Linha SPED",
        "CST / Origem", "Base do cálculo", "Origem da base",
        "Alíquota interna vigente (%)", "Origem alíquota interna",
        "Alíquota interestadual SPED/CST (%)",
        "Alíquota interestadual XML (%)",
        "Diferença de alíquotas (%)", "Fórmula / memória",
        "DIFAL recalculado - SPED/CST", "DIFAL C101 / SPED",
        "Diferença recalculado x C101", "DIFAL XML",
        "FCP SPED", "FCP XML", "Status", "Evidência / detalhamento C190"
    ]
    for c, titulo in enumerate(cabecalhos, 1):
        cel = saida.cell(1, c, titulo)
        cel.font = Font(bold=True)
        cel.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cel.fill = PatternFill("solid", fgColor="D9EAF7")

    linha_saida = 2
    for r in range(cab_linha + 1, (origem.max_row or cab_linha) + 1):
        nf = _valor(origem, r, mapa, "NF", "NFe", "Número NF", "Número NFe")
        uf = _valor(origem, r, mapa, "UF destino", "UF")
        cfop = _valor(origem, r, mapa, "CFOP")
        if (nf in (None, "")) and (uf in (None, "")) and (cfop in (None, "")):
            continue

        chave = _valor(origem, r, mapa, "Chave NF-e", "Chave NFe", "Chave")
        linha_sped = _valor(origem, r, mapa, "Linha", "Linha SPED")
        cst_origem = _valor(
            origem, r, mapa,
            "CST / Origem", "CST/Origem", "Origem CST", "CST", "Origem"
        )
        base = _valor(
            origem, r, mapa,
            "Base cálculo", "Base do cálculo", "Base XML", "Base SPED",
            "Base DIFAL", "Base"
        )
        aliq_interna = _valor(
            origem, r, mapa,
            "Alíq. interna devida", "Alíquota interna devida",
            "Alíq. interna", "Alíquota interna"
        )
        inter_sped = _valor(
            origem, r, mapa,
            "Alíq. inter. SPED/CST", "Alíquota interestadual SPED/CST",
            "Alíq interestadual SPED/CST", "Inter SPED/CST"
        )
        inter_xml = _valor(
            origem, r, mapa,
            "Alíq. inter. XML", "Alíquota interestadual XML",
            "Alíq interestadual XML", "Inter XML"
        )
        difal_cenario = _valor(
            origem, r, mapa,
            "DIFAL cenário SPED/CST", "DIFAL cenario SPED/CST",
            "DIFAL recalculado", "DIFAL devido"
        )
        c101 = _valor(
            origem, r, mapa,
            "DIFAL SPED", "DIFAL C101", "C101", "DIFAL escriturado"
        )
        difal_xml = _valor(origem, r, mapa, "DIFAL XML")
        fcp_sped = _valor(origem, r, mapa, "FCP SPED", "FCP C101")
        fcp_xml = _valor(origem, r, mapa, "FCP XML")
        evidencia = _valor(
            origem, r, mapa,
            "Detalhamento SPED/CST", "Detalhe SPED/CST",
            "Evidência", "Evidencia", "Observação", "Observacao"
        )

        b = _numero(base)
        ai = _numero(aliq_interna)
        ae = _numero(inter_sped)
        calc = _numero(difal_cenario)
        if calc is None and b is not None and ai is not None and ae is not None:
            calc = _q2(b * max(ai - ae, Decimal("0")) / Decimal("100"))

        c101n = _numero(c101) or Decimal("0")
        calcn = calc or Decimal("0")
        diferenca = _q2(calcn - c101n)

        if ai is not None and ae is not None:
            dif_aliq = max(ai - ae, Decimal("0"))
            formula = (
                f"{_fmt_brl(b or 0)} × ({_fmt_pct(ai)} - {_fmt_pct(ae)})"
                f" = {_fmt_brl(calcn)}"
            )
        else:
            dif_aliq = None
            formula = "Dados insuficientes para montar a fórmula completa."

        status = _status_memoria(inter_sped, inter_xml, diferenca)

        valores = [
            nf, chave, uf, cfop, linha_sped, cst_origem,
            float(b) if b is not None else None,
            "C190/C100 do SPED",
            float(ai) if ai is not None else None,
            "Regra estadual vigente na data da NF-e",
            float(ae) if ae is not None else None,
            float(_numero(inter_xml)) if _numero(inter_xml) is not None else None,
            float(dif_aliq) if dif_aliq is not None else None,
            formula,
            float(calcn),
            float(c101n),
            float(diferenca),
            float(_numero(difal_xml)) if _numero(difal_xml) is not None else None,
            float(_numero(fcp_sped)) if _numero(fcp_sped) is not None else None,
            float(_numero(fcp_xml)) if _numero(fcp_xml) is not None else None,
            status,
            evidencia,
        ]
        for c, valor in enumerate(valores, 1):
            saida.cell(linha_saida, c, valor)
        linha_saida += 1

    saida.freeze_panes = "A2"
    saida.auto_filter.ref = saida.dimensions
    saida.row_dimensions[1].height = 34

    larguras = {
        1: 12, 2: 48, 3: 12, 4: 10, 5: 12, 6: 16, 7: 16, 8: 22,
        9: 20, 10: 34, 11: 24, 12: 22, 13: 20, 14: 48, 15: 22,
        16: 20, 17: 24, 18: 18, 19: 16, 20: 16, 21: 28, 22: 70
    }
    for idx, largura in larguras.items():
        saida.column_dimensions[get_column_letter(idx)].width = largura

    for row in saida.iter_rows(min_row=2):
        row[6].number_format = 'R$ #,##0.00'
        row[8].number_format = '0.00%'
        row[10].number_format = '0.00%'
        row[11].number_format = '0.00%'
        row[12].number_format = '0.00%'
        for idx in (14, 15, 16, 17, 18, 19):
            row[idx].number_format = 'R$ #,##0.00'
        for cel in row:
            cel.alignment = Alignment(vertical="top", wrap_text=True)

    # Observação metodológica preserva a lógica aprovada na 18.2.16:
    # XML continua como evidência; a memória SPED/CST usa a origem/CST por C190.
    saida.sheet_view.showGridLines = False


def _save_com_memoria(self, filename):
    try:
        nome = str(filename or "")
        base = nome.upper()
        if "DIFAL" in base and (base.endswith(".XLSX") or base.endswith(".XLSM")):
            _adicionar_memoria(self)
    except Exception:
        # Nunca impedir o usuário de exportar por causa da memória adicional.
        pass
    return _ORIGINAL_SAVE(self, filename)


def aplicar_patch():
    global _PATCH_APLICADO, _ORIGINAL_SAVE
    if _PATCH_APLICADO or Workbook is None:
        return
    _ORIGINAL_SAVE = Workbook.save
    Workbook.save = _save_com_memoria
    _PATCH_APLICADO = True


aplicar_patch()
