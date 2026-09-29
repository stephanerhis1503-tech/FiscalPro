"""Exportador XLSX da conferência de ICMS-ST por XML.

Sprint 14.7
- Mostra o ICMS-ST informado no XML e o calculado pelo FiscalPro.
- Apresenta diferença, situação por item e resumo da nota.
- Mantém a coluna Valor do item + IPI e a memória de cálculo aprovada.
- Usa apenas a biblioteca padrão para evitar nova dependência no computador.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
from xml.sax.saxutils import escape
import zipfile


HEADERS = [
    "Item", "Código", "Descrição", "NCM", "CEST", "CFOP", "Quantidade", "Unidade",
    "Valor dos produtos", "Desconto", "Frete", "Seguro", "Outros", "IPI",
    "Valor do item + IPI", "MVA original %", "MVA ajustada %", "MVA utilizada %",
    "Alíquota interestadual %", "Alíquota interna MG %", "FCP-ST %",
    "Base ICMS-ST", "Dedução ICMS operação própria", "ICMS-ST calculado", "ICMS-ST no XML",
    "Diferença (calc. - XML)", "Conferência", "FCP-ST", "Total ST + FCP",
    "Status do cálculo", "Observação", "Base legal", "Fonte oficial",
    "Aplicabilidade NCM 7318",
]

COL_WIDTHS = [
    7, 15, 42, 12, 13, 9, 12, 10,
    17, 14, 13, 13, 13, 13, 19, 14, 14, 14,
    18, 18, 12, 17, 15, 17, 17, 20, 31, 14, 16,
    28, 52, 42, 52, 42,
]


def _coluna(indice: int) -> str:
    indice += 1
    letras = ""
    while indice:
        indice, resto = divmod(indice - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor)


def _numero(valor: Any) -> float:
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def _cell_inline(ref: str, valor: Any, estilo: int = 0) -> str:
    texto = escape(_texto(valor))
    preserve = ' xml:space="preserve"' if texto.startswith(" ") or texto.endswith(" ") or "\n" in texto else ""
    return f'<c r="{ref}" s="{estilo}" t="inlineStr"><is><t{preserve}>{texto}</t></is></c>'


def _cell_num(ref: str, valor: Any, estilo: int = 0) -> str:
    return f'<c r="{ref}" s="{estilo}"><v>{_numero(valor):.10f}</v></c>'


def _cell_formula(ref: str, formula: str, valor_cache: Any, estilo: int = 0) -> str:
    return (
        f'<c r="{ref}" s="{estilo}"><f>{escape(formula)}</f>'
        f'<v>{_numero(valor_cache):.10f}</v></c>'
    )


def _linha(numero: int, celulas: Iterable[str], altura: float | None = None) -> str:
    atributo = f' ht="{altura}" customHeight="1"' if altura else ""
    return f'<row r="{numero}"{atributo}>{"".join(celulas)}</row>'


def _estilo_conferencia(status: Any) -> int:
    texto = str(status or "").upper()
    if texto == "CORRETO":
        return 10
    if texto in {"VALOR MENOR QUE O CALCULADO", "VALOR MAIOR QUE O CALCULADO"}:
        return 11
    if texto in {
        "ST NÃO DESTACADO",
        "NÃO APLICÁVEL — USO EXCLUSIVO AUTOMOTIVO",
    }:
        return 12
    return 8


class ExportadorXMLICMSSTXLSX:
    @classmethod
    def exportar(cls, resultado: Dict[str, Any], caminho: str) -> str:
        destino = Path(caminho)
        if destino.suffix.lower() != ".xlsx":
            destino = destino.with_suffix(".xlsx")
        destino.parent.mkdir(parents=True, exist_ok=True)

        nota = dict(resultado.get("nota") or {})
        resumo = dict(resultado.get("resumo") or {})
        itens = list(resultado.get("itens") or [])
        agora = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as pacote:
            pacote.writestr("[Content_Types].xml", cls._content_types())
            pacote.writestr("_rels/.rels", cls._rels_raiz())
            pacote.writestr("docProps/app.xml", cls._app())
            pacote.writestr("docProps/core.xml", cls._core(agora))
            pacote.writestr("xl/workbook.xml", cls._workbook())
            pacote.writestr("xl/_rels/workbook.xml.rels", cls._workbook_rels())
            pacote.writestr("xl/styles.xml", cls._styles())
            pacote.writestr("xl/worksheets/sheet1.xml", cls._sheet(resultado, nota, resumo, itens))

        return str(destino)

    @staticmethod
    def _content_types() -> str:
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

    @staticmethod
    def _rels_raiz() -> str:
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

    @staticmethod
    def _app() -> str:
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>FiscalPro</Application><AppVersion>14.0700</AppVersion>
</Properties>"""

    @staticmethod
    def _core(agora: str) -> str:
        return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>FiscalPro — Conferência de ICMS-ST por XML</dc:title>
<dc:creator>FiscalPro</dc:creator><cp:lastModifiedBy>FiscalPro</cp:lastModifiedBy>
<dcterms:created xsi:type="dcterms:W3CDTF">{agora}</dcterms:created>
<dcterms:modified xsi:type="dcterms:W3CDTF">{agora}</dcterms:modified>
</cp:coreProperties>"""

    @staticmethod
    def _workbook() -> str:
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<fileVersion appName="xl"/><workbookPr/>
<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="24000" windowHeight="14000"/></bookViews>
<sheets><sheet name="Conferência ICMS-ST" sheetId="1" r:id="rId1"/></sheets>
<calcPr calcId="191029" calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1"/>
</workbook>"""

    @staticmethod
    def _workbook_rels() -> str:
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

    @staticmethod
    def _styles() -> str:
        # 0 normal; 1 título; 2 subtítulo; 3 cabeçalho; 4 moeda; 5 percentual;
        # 6 texto; 7 moeda negrito; 8 revisão; 9 decimal; 10 correto;
        # 11 divergência; 12 não destacado.
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="3">
<numFmt numFmtId="164" formatCode="R$ #,##0.00"/>
<numFmt numFmtId="165" formatCode="0.00&quot;%&quot;"/>
<numFmt numFmtId="166" formatCode="0.0000"/>
</numFmts>
<fonts count="4">
<font><sz val="10"/><name val="Segoe UI"/></font>
<font><b/><sz val="16"/><color rgb="FF1F4E78"/><name val="Segoe UI"/></font>
<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Segoe UI"/></font>
<font><b/><sz val="10"/><name val="Segoe UI"/></font>
</fonts>
<fills count="8">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFD9EAF7"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFF2CC"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE2F0D9"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFF4CCCC"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFCE5CD"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFD9E2F3"/></left><right style="thin"><color rgb="FFD9E2F3"/></right><top style="thin"><color rgb="FFD9E2F3"/></top><bottom style="thin"><color rgb="FFD9E2F3"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="13">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>
<xf numFmtId="0" fontId="3" fillId="3" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
<xf numFmtId="165" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="164" fontId="3" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
<xf numFmtId="0" fontId="3" fillId="4" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="166" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
<xf numFmtId="0" fontId="3" fillId="5" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="3" fillId="6" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="3" fillId="7" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""

    @classmethod
    def _sheet(cls, resultado: Dict[str, Any], nota: Dict[str, Any], resumo: Dict[str, Any], itens: List[Dict[str, Any]]) -> str:
        linhas: List[str] = []
        linhas.append(_linha(1, [_cell_inline("A1", "FiscalPro — Conferência de ICMS-ST/MG por XML", 1)], 28))
        linhas.append(_linha(2, [_cell_inline(
            "A2",
            "Diferença = ICMS-ST calculado pelo FiscalPro menos ICMS-ST informado no XML. Confira enquadramento, MVA, alíquotas e responsabilidade tributária.",
            2,
        )], 40))

        metadados: List[Tuple[str, Any, str, Any, bool, bool]] = [
            ("NF-e", f"{nota.get('numero', '')}/{nota.get('serie', '')}", "Chave", nota.get("chave", ""), False, False),
            ("Emitente", nota.get("emitente_nome", ""), "Origem / destino", f"{resultado.get('uf_origem', '')} → {resultado.get('uf_destino', '')}", False, False),
            ("Total produtos + IPI", resumo.get("total_produtos_com_ipi", 0), "Total base ICMS-ST", resumo.get("total_base_st", 0), True, True),
            ("ICMS-ST no XML", resumo.get("total_icms_st_xml", 0), "ICMS-ST calculado", resumo.get("total_icms_st", 0), True, True),
            ("Diferença calc. - XML", resumo.get("diferenca_total_st", 0), "Itens corretos / pendentes", f"{resumo.get('itens_corretos', 0)} / {resumo.get('itens_pendentes', 0)}", True, False),
        ]
        for idx, (rot1, val1, rot2, val2, num1, num2) in enumerate(metadados, start=3):
            celulas = [
                _cell_inline(f"A{idx}", rot1, 2),
                _cell_num(f"B{idx}", val1, 7) if num1 else _cell_inline(f"B{idx}", val1, 6),
                _cell_inline(f"E{idx}", rot2, 2),
                _cell_num(f"F{idx}", val2, 7) if num2 else _cell_inline(f"F{idx}", val2, 6),
            ]
            linhas.append(_linha(idx, celulas, 22))

        header_row = 9
        header_cells = [_cell_inline(f"{_coluna(i)}{header_row}", cab, 3) for i, cab in enumerate(HEADERS)]
        linhas.append(_linha(header_row, header_cells, 48))

        data_start = header_row + 1
        for offset, resultado_item in enumerate(itens):
            row = data_start + offset
            item = dict(resultado_item.get("item") or {})
            st = dict(resultado_item.get("st_oficial") or {})
            legal = f"{st.get('fundamento') or 'RICMS/MG/2023 — Anexo VII'} — {st.get('artigo_item') or ''}".strip(" —")
            complemento = str(st.get("fundamento_complementar") or "").strip()
            if complemento:
                legal = f"{legal} | {complemento}"
            fonte = st.get("fonte_url") or "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/ricms2023/anexovii2023.pdf"
            fonte_complementar = str(st.get("fonte_complementar_url") or "").strip()
            if fonte_complementar:
                fonte = f"{fonte} | {fonte_complementar}"
            observacao = " ".join(
                parte for parte in [
                    str(resultado_item.get("observacao") or "").strip(),
                    str(resultado_item.get("deducao_icms_observacao") or "").strip(),
                    (f"Origem da dedução ICMS: {resultado_item.get('deducao_icms_origem')}" if resultado_item.get("deducao_icms_origem") else ""),
                    str(resultado_item.get("conferencia_observacao") or "").strip(),
                ] if parte
            )

            valores = [
                item.get("numero_item", row - header_row),
                item.get("codigo", ""),
                item.get("descricao", ""),
                item.get("ncm", ""),
                resultado_item.get("cest", ""),
                item.get("cfop", ""),
                item.get("quantidade", 0),
                item.get("unidade", ""),
                item.get("valor_produtos", 0),
                item.get("desconto", 0),
                item.get("frete", 0),
                item.get("seguro", 0),
                item.get("outros", 0),
                item.get("ipi", 0),
                resultado_item.get("valor_total_com_ipi", 0),
                resultado_item.get("mva_original", 0),
                resultado_item.get("mva_ajustada", 0) if resultado_item.get("mva_ajustada") is not None else 0,
                resultado_item.get("mva_utilizada", resultado_item.get("mva_original", 0)),
                resultado_item.get("aliquota_interestadual", 0),
                resultado_item.get("aliquota_interna", 0),
                resultado_item.get("aliquota_fcp", resultado_item.get("aliquota_fcp_st", 0)),
                resultado_item.get("base_calculo_st", 0),
                resultado_item.get("icms_proprio", resultado_item.get("icms_proprio_deduzir", 0)),
                resultado_item.get("icms_st", 0),
                resultado_item.get("icms_st_xml", item.get("icms_st_xml", 0)),
                resultado_item.get("diferenca_st", 0),
                resultado_item.get("conferencia_status", "REVISAR"),
                resultado_item.get("fcp_st", 0),
                resultado_item.get("total_st_fcp", 0),
                resultado_item.get("status", ""),
                observacao,
                legal,
                fonte,
                resultado_item.get("aplicabilidade_7318", ""),
            ]

            calculado = bool(resultado_item.get("calculado"))
            celulas: List[str] = []
            for i, valor in enumerate(valores):
                ref = f"{_coluna(i)}{row}"
                if i == 14:  # Valor item + IPI
                    celulas.append(_cell_formula(ref, f"ROUND(I{row}+N{row},2)", valor, 4))
                elif i == 21:  # Base ST
                    if calculado:
                        celulas.append(_cell_formula(ref, f"ROUND((I{row}+K{row}+L{row}+M{row}+N{row})*(1+R{row}/100),2)", valor, 4))
                    else:
                        celulas.append(_cell_num(ref, valor, 4))
                elif i == 23:  # ST calculado
                    if calculado:
                        celulas.append(_cell_formula(ref, f"MAX(0,ROUND(V{row}*T{row}/100-W{row},2))", valor, 4))
                    else:
                        celulas.append(_cell_num(ref, valor, 4))
                elif i == 25:  # Diferença
                    if calculado:
                        celulas.append(_cell_formula(ref, f"ROUND(X{row}-Y{row},2)", valor, 4))
                    else:
                        celulas.append(_cell_num(ref, valor, 4))
                elif i == 27:  # FCP-ST
                    if calculado:
                        celulas.append(_cell_formula(ref, f"ROUND(V{row}*U{row}/100,2)", valor, 4))
                    else:
                        celulas.append(_cell_num(ref, valor, 4))
                elif i == 28:  # Total ST + FCP
                    if calculado:
                        celulas.append(_cell_formula(ref, f"ROUND(X{row}+AB{row},2)", valor, 4))
                    else:
                        celulas.append(_cell_num(ref, valor, 4))
                elif i in {8, 9, 10, 11, 12, 13, 22, 24}:
                    celulas.append(_cell_num(ref, valor, 4))
                elif i in {15, 16, 17, 18, 19, 20}:
                    celulas.append(_cell_num(ref, valor, 5))
                elif i in {0, 6}:
                    celulas.append(_cell_num(ref, valor, 9))
                elif i == 26:
                    celulas.append(_cell_inline(ref, valor, _estilo_conferencia(valor)))
                elif i == 29:
                    celulas.append(_cell_inline(ref, valor, 8))
                else:
                    celulas.append(_cell_inline(ref, valor, 6))
            linhas.append(_linha(row, celulas, 48))

        last_data = data_start + max(len(itens), 1) - 1
        total_row = last_data + 1
        total_cells = [
            _cell_inline(f"A{total_row}", "TOTAL", 2),
            _cell_formula(f"I{total_row}", f"SUM(I{data_start}:I{last_data})", resumo.get("total_produtos", 0), 7),
            _cell_formula(f"N{total_row}", f"SUM(N{data_start}:N{last_data})", resumo.get("total_ipi", 0), 7),
            _cell_formula(f"O{total_row}", f"SUM(O{data_start}:O{last_data})", resumo.get("total_produtos_com_ipi", 0), 7),
            _cell_formula(f"V{total_row}", f"SUM(V{data_start}:V{last_data})", resumo.get("total_base_st", 0), 7),
            _cell_formula(f"X{total_row}", f"SUM(X{data_start}:X{last_data})", resumo.get("total_icms_st", 0), 7),
            _cell_formula(f"Y{total_row}", f"SUM(Y{data_start}:Y{last_data})", resumo.get("total_icms_st_xml", 0), 7),
            _cell_formula(f"Z{total_row}", f"ROUND(X{total_row}-Y{total_row},2)", resumo.get("diferenca_total_st", 0), 7),
            _cell_formula(f"AB{total_row}", f"SUM(AB{data_start}:AB{last_data})", resumo.get("total_fcp_st", 0), 7),
            _cell_formula(f"AC{total_row}", f"SUM(AC{data_start}:AC{last_data})", resumo.get("total_st_fcp", 0), 7),
        ]
        linhas.append(_linha(total_row, total_cells, 25))

        colunas = "".join(
            f'<col min="{i + 1}" max="{i + 1}" width="{largura}" customWidth="1"/>'
            for i, largura in enumerate(COL_WIDTHS)
        )
        dimensao = f"A1:AH{total_row}"
        merges = ["A1:H1", "A2:J2"]
        for row in range(3, 8):
            merges.extend([f"B{row}:D{row}", f"F{row}:AH{row}"])
        merge_cells = (
            f'<mergeCells count="{len(merges)}">'
            + "".join(f'<mergeCell ref="{ref}"/>' for ref in merges)
            + "</mergeCells>"
        )
        return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="{dimensao}"/>
<sheetViews><sheetView workbookViewId="0"><pane xSplit="4" ySplit="9" topLeftCell="E10" activePane="bottomRight" state="frozen"/><selection pane="topRight" activeCell="E1" sqref="E1"/><selection pane="bottomLeft" activeCell="A10" sqref="A10"/><selection pane="bottomRight" activeCell="E10" sqref="E10"/></sheetView></sheetViews>
<sheetFormatPr defaultRowHeight="18"/>
<cols>{colunas}</cols>
<sheetData>{''.join(linhas)}</sheetData>
<autoFilter ref="A9:AH{last_data}"/>
{merge_cells}
<pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>
</worksheet>"""
