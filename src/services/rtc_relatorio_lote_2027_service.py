"""Auditoria IBS/CBS em lote - projecao demonstrativa 2027 (Excel).

Nao altera XMLs, banco, apuracao local, CBS oficial, SPED ou creditos.
O motor individual do FiscalPro decide, item a item, quando a projecao
e permitida e quando a classificacao deve permanecer em revisao.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from src.services.apuracao_assistida_local_service import ServicoApuracaoLocalRTC
from src.services.rtc_aliquotas_service import (
    ServicoAliquotasRTC, _dinheiro,
)


VENDA_COMUM = frozenset({"5101", "5102", "6101", "6102"})
STATUS_COMUM = frozenset({"CBS_PENDENTE_DEFINICAO", "CENARIO_TCU_NAO_OFICIAL"})
STATUS_CONDICIONAL = "CENARIO_CONDICIONAL_CFOP_5405"
AZUL = "124A79"
AZUL_CLARO = "EAF2F9"
AMARELO = "FFF1C7"
VERMELHO = "C23732"
VERDE = "E0F3E7"
MONEY_FMT = '#,##0.00;[Red](#,##0.00);-'
PCT_FMT = '0.00"%"'
COLUNAS = (
    ("Grupo", 24),
    ("Operacao", 12),
    ("NF", 15),
    ("Item", 9),
    ("Emissao", 16),
    ("Chave NF-e", 49),
    ("Descricao do produto", 55),
    ("NCM", 12),
    ("CFOP", 10),
    ("CST IBS/CBS", 13),
    ("cClassTrib", 13),
    ("Base IBS/CBS do XML (R$)", 24),
    ("IBS UF ref. 2027 (%)", 19),
    ("IBS mun. ref. 2027 (%)", 20),
    ("IBS UF simulado (R$)", 21),
    ("IBS municipal simulado (R$)", 25),
    ("CBS TCU NAO oficial (%)", 25),
    ("CBS TCU simulada (R$)", 24),
    ("Total hipotetico TCU (R$)", 25),
    ("Situacao da projecao", 35),
    ("Auditoria original XML", 24),
    ("Motivos no XML", 63),
    ("Observacao fiscal da simulacao", 110),
)


def _texto(valor) -> str:
    texto = str(valor or "").replace("\r", " ").replace("\n", " ").strip()
    # Exportacao de XML nao pode executar formulas no Excel.
    if texto.startswith(("=", "+", "-", "@")):
        return "'" + texto
    return texto


def _base_xml(valor) -> Decimal | None:
    try:
        return _dinheiro(valor)
    except (ValueError, TypeError):
        return None


class ServicoRelatorioLoteRTC2027:
    """Exporta todos os itens da base local, sem o limite visual de 5000."""

    def __init__(self, servico: ServicoApuracaoLocalRTC | None = None):
        self.servico = servico or ServicoApuracaoLocalRTC()

    def preparar(
        self, cnpj: str, competencia: str, *,
        regime: str, permitir_venda_icms_st: bool = False,
        usar_cenario_tcu: bool = False, empresa: str = "",
    ) -> dict:
        if type(permitir_venda_icms_st) is not bool or type(usar_cenario_tcu) is not bool:
            raise ValueError("As hipoteses de simulacao precisam de marcacao explicita.")
        cnpj = ServicoApuracaoLocalRTC.validar_cnpj(cnpj)
        competencia = ServicoApuracaoLocalRTC.validar_competencia(competencia)
        regra = ServicoAliquotasRTC.consultar(2027)

        # Nao fornecer limite para incluir todos os itens, inclusive os 22050
        # de uma competencia grande. A consulta e apenas leitura.
        itens = self.servico.listar_itens(cnpj, competencia)
        if not itens:
            raise ValueError(
                "Nenhum item detalhado encontrado nesta competencia. "
                "Importe os XMLs na Apuracao Local antes de exportar."
            )
        if hasattr(self.servico, "contar_itens"):
            total = self.servico.contar_itens(cnpj, competencia)
            if total != len(itens):
                raise ValueError(
                    "A quantidade de itens mudou durante a consulta. "
                    "Consulte a base novamente antes de exportar."
                )

        linhas = []
        agrupamentos = Counter()
        situacoes = Counter()
        chaves = set()
        for item in itens:
            simulacao = ServicoAliquotasRTC.simular_item_2027(
                item, regime=regime, permitir_venda_icms_st=permitir_venda_icms_st,
                usar_cenario_tcu=usar_cenario_tcu,
            )
            cfop = str(item.get("cfop") or "").strip()
            direcao = str(item.get("direcao") or "").upper().strip()
            status = simulacao["status"]
            if direcao == "SAIDA" and cfop == "5405":
                grupo = "VENDA ICMS-ST 5405"
            elif direcao == "SAIDA" and cfop in VENDA_COMUM and status in STATUS_COMUM:
                grupo = "VENDA COMUM"
            else:
                grupo = "REVISAR OUTROS"
            chaves.add(str(item.get("chave_nfe") or ""))
            agrupamentos[grupo] += 1
            situacoes[status] += 1
            linhas.append({
                "grupo": grupo,
                "item": item,
                "status": status,
                "base": _base_xml(item.get("base_ibs_cbs")),
                "simulacao": simulacao,
                "revisar": status not in STATUS_COMUM,
            })

        if len(linhas) != sum(agrupamentos.values()):
            raise ValueError("Falha na conciliacao das quantidades de itens.")
        return {
            "empresa": empresa.strip() or cnpj,
            "cnpj": cnpj, "competencia": competencia,
            "regime": regime,
            "referencia": regra,
            "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "permitir_venda_icms_st": permitir_venda_icms_st,
            "usar_cenario_tcu": usar_cenario_tcu,
            "linhas": linhas,
            "itens": len(linhas),
            "notas": len(chaves),
            "grupos": agrupamentos,
            "situacoes": situacoes,
            "revisar": sum(linha["revisar"] for linha in linhas),
        }

    @staticmethod
    def _montar_detalhe(ws, dados: dict, linhas: list[dict], titulo: str):
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        ws.sheet_view.showGridLines = False
        ws.merge_cells("A1:W2")
        ws["A1"] = "FiscalPro | " + titulo
        ws["A1"].fill = PatternFill("solid", fgColor=AZUL)
        ws["A1"].font = Font(bold=True, color="FFFFFF", size=15)
        ws["A1"].alignment = Alignment(vertical="center")
        ws.row_dimensions[1].height = 28
        ws.row_dimensions[2].height = 17
        ws.merge_cells("A3:W3")
        ws["A3"] = (
            f"Empresa: {_texto(dados['empresa'])} | CNPJ: {dados['cnpj']} | "
            f"Origem: {dados['competencia']} | Projecao: 2027 | "
            f"Regime: {dados['regime']} | Itens nesta aba: {len(linhas)}"
        )
        ws["A3"].font = Font(color=AZUL, bold=True)
        ws.merge_cells("A4:W5")
        ws["A4"] = (
            "NAO E APURACAO OFICIAL NEM ALIQUOTA DEFINITIVA. Bases e CST/cClassTrib "
            "extraidos de XMLs historicos nao comprovam tratamento fiscal de 2027. "
            "CBS 2027 ainda depende de norma definitiva. IBS e CBS exibidos sao "
            "PROJECOES; CFOP 5405 e hipotese condicional; valores NAO alteram os XMLs."
        )
        ws["A4"].fill = PatternFill("solid", fgColor=AMARELO)
        ws["A4"].font = Font(color="805400", bold=True, size=10)
        ws["A4"].alignment = Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[4].height = 28
        ws.row_dimensions[5].height = 22

        for col, (nome, largura) in enumerate(COLUNAS, 1):
            cel = ws.cell(row=7, column=col, value=nome)
            cel.fill = PatternFill("solid", fgColor=AZUL)
            cel.font = Font(bold=True, color="FFFFFF")
            cel.alignment = Alignment(wrap_text=True, vertical="center")
            ws.column_dimensions[get_column_letter(col)].width = largura
        ws.row_dimensions[7].height = 36

        for idx, linha in enumerate(linhas, 8):
            item, sim = linha["item"], linha["simulacao"]
            calculavel = sim.get("ibs_uf") is not None
            tem_tcu = sim.get("cbs") is not None and dados["usar_cenario_tcu"]
            base = linha["base"]
            valores = [
                linha["grupo"],
                _texto(item.get("direcao")),
                _texto(item.get("numero_nf")),
                _texto(item.get("numero_item")),
                _texto(item.get("emissao")),
                _texto(item.get("chave_nfe")),
                _texto(item.get("descricao")),
                _texto(item.get("ncm")),
                _texto(item.get("cfop")),
                _texto(item.get("cst_ibscbs")),
                _texto(item.get("cclass_trib")),
                float(base) if base is not None else None,
                float(dados["referencia"].ibs_uf) if calculavel else None,
                float(dados["referencia"].ibs_municipal) if calculavel else None,
                f"=ROUND(L{idx}*M{idx}/100,2)" if calculavel else None,
                f"=ROUND(L{idx}*N{idx}/100,2)" if calculavel else None,
                float(sim["p_cbs_usado"]) if tem_tcu else None,
                f"=ROUND(L{idx}*Q{idx}/100,2)" if tem_tcu else None,
                f"=ROUND(O{idx}+P{idx}+R{idx},2)" if tem_tcu else None,
                _texto(linha["status"]),
                _texto(item.get("status_auditoria")),
                _texto(item.get("motivos")),
                _texto(sim.get("observacao")),
            ]
            for col, valor in enumerate(valores, 1):
                cel = ws.cell(idx, col, valor)
                if col in (12, 15, 16, 18, 19):
                    cel.number_format = MONEY_FMT
                if col in (13, 14, 17):
                    cel.number_format = PCT_FMT
                if col in (3, 4, 6, 8, 9, 10, 11):
                    cel.number_format = "@"
                if col in (15, 16, 18, 19) and valor is not None:
                    cel.font = Font(color="000000")
                if idx % 2 == 0 and col in (1, 2, 3, 9, 10, 11, 20):
                    cel.fill = PatternFill("solid", fgColor=AZUL_CLARO)
            resultado = ws.cell(idx, 20)
            if linha["revisar"]:
                resultado.fill = PatternFill("solid", fgColor=AMARELO)
                resultado.font = Font(bold=True, color=VERMELHO)
            else:
                resultado.fill = PatternFill("solid", fgColor=VERDE)
                resultado.font = Font(bold=True, color="157347")

        ws.freeze_panes = "L8"
        ws.auto_filter.ref = f"A7:W{max(7, len(linhas) + 7)}"
        ws.print_title_rows = "1:7"
        ws.page_setup.orientation = "landscape"
        ws.sheet_properties.pageSetUpPr.fitToPage = True

    @staticmethod
    def _montar_resumo(ws, dados: dict):
        from openpyxl.styles import Alignment, Font, PatternFill

        ws.sheet_view.showGridLines = False
        ws.merge_cells("A1:H2")
        ws["A1"] = "FISCALPRO | AUDITORIA EM LOTE IBS/CBS - CENARIO 2027"
        ws["A1"].font = Font(bold=True, color="FFFFFF", size=16)
        ws["A1"].fill = PatternFill("solid", fgColor=AZUL)
        ws["A1"].alignment = Alignment(vertical="center")
        ws.row_dimensions[1].height = 28
        ws.row_dimensions[2].height = 18
        ws.merge_cells("A4:H4")
        ws["A4"] = (
            f"Empresa: {_texto(dados['empresa'])} | CNPJ: {dados['cnpj']} | "
            f"XMLs: {dados['competencia']} | Projecao para 2027 | "
            f"Regime cadastrado: {dados['regime']}"
        )
        ws["A4"].font = Font(color=AZUL, bold=True)
        ws.merge_cells("A6:H9")
        ws["A6"] = (
            "RELATORIO DEMONSTRATIVO SEM EFEITO FISCAL. Usa XMLs da competencia "
            "selecionada como referencia, sem determinar tratamento futuro de cada "
            "produto. 2027: IBS UF 0,05% e IBS mun. 0,05% para o cenario padrao. "
            "CBS definitiva A DEFINIR; 11,2% somente hipotese TCU, se selecionada. "
            "Nao gera tributos, credito, SPED ou consulta oficial."
        )
        ws["A6"].font = Font(bold=True, color="805400")
        ws["A6"].fill = PatternFill("solid", fgColor=AMARELO)
        ws["A6"].alignment = Alignment(vertical="center", wrap_text=True)
        for row in range(6, 10):
            ws.row_dimensions[row].height = 22

        indicadores = [
            ("Itens analisados (total, sem limite visual)", dados["itens"]),
            ("Notas distintas de origem", dados["notas"]),
            ("Vendas comuns (possiveis projecoes)", dados["grupos"]["VENDA COMUM"]),
            ("Vendas CFOP 5405 (ICMS-ST)", dados["grupos"]["VENDA ICMS-ST 5405"]),
            ("Outras operacoes / classificacoes", dados["grupos"]["REVISAR OUTROS"]),
            ("Itens que exigem revisao", dados["revisar"]),
        ]
        ws["A11"] = "Indicador"
        ws["B11"] = "Quantidade"
        for col in (1, 2):
            ws.cell(11, col).fill = PatternFill("solid", fgColor=AZUL)
            ws.cell(11, col).font = Font(bold=True, color="FFFFFF")
        for row, (titulo, valor) in enumerate(indicadores, 12):
            ws.cell(row, 1, titulo).font = Font(bold=True, color=AZUL)
            ws.cell(row, 2, valor).font = Font(bold=True, color="222222")
            if row % 2:
                for col in (1, 2):
                    ws.cell(row, col).fill = PatternFill("solid", fgColor=AZUL_CLARO)

        ws["A20"] = "Valores apenas simulados"
        ws["A20"].font = Font(bold=True, size=12, color=AZUL)
        ws["A21"] = "IBS estadual - total estimado (R$)"
        ws["A22"] = "IBS municipal - total estimado (R$)"
        ws["A23"] = "CBS cenario TCU NAO OFICIAL (R$)"
        ws["A24"] = "Total hipotetico TCU (R$)"
        ultima = 7 + dados["itens"]
        for linha, coluna in ((21, "O"), (22, "P")):
            ws.cell(linha, 2, f"=SUM('Todos os itens'!{coluna}8:{coluna}{ultima})")
            ws.cell(linha, 2).number_format = MONEY_FMT
        if dados["usar_cenario_tcu"]:
            for linha, coluna in ((23, "R"), (24, "S")):
                ws.cell(linha, 2, f"=SUM('Todos os itens'!{coluna}8:{coluna}{ultima})")
                ws.cell(linha, 2).number_format = MONEY_FMT
        else:
            ws["B23"] = "NAO SIMULADA"
            ws["B24"] = "NAO CALCULADO"
        ws.merge_cells("A26:H28")
        ws["A26"] = (
            "O CFOP 5405 refere-se a operacao com ICMS-ST na sistematica atual, "
            "mas nao define, por si, isencao ou incidencia de IBS/CBS. "
            "Sem marcacao explicita, seus valores de projecao permanecem vazios. "
            "Mesmo com a hipotese habilitada, requer revisao fiscal. "
            "Entradas nao geram credito automaticamente. "
            "Um item pode aparecer em 'CFOP 5405' e tambem em 'Revisar'; "
            "os totais sao contados uma unica vez em 'Todos os itens'."
        )
        ws["A26"].alignment = Alignment(wrap_text=True, vertical="center")
        ws["A26"].fill = PatternFill("solid", fgColor=AZUL_CLARO)
        ws["A26"].font = Font(color=AZUL)
        for row in (26, 27, 28):
            ws.row_dimensions[row].height = 28

        ws["A30"] = "Configuracao da exportacao"
        ws["A30"].font = Font(bold=True, size=12, color=AZUL)
        ws["A31"] = "Hipotese CFOP 5405 autorizada"
        ws["B31"] = "SIM" if dados["permitir_venda_icms_st"] else "NAO"
        ws["A32"] = "Cenario CBS TCU 11,2% selecionado"
        ws["B32"] = "SIM (NAO OFICIAL)" if dados["usar_cenario_tcu"] else "NAO"
        ws["A33"] = "Gerado em"
        ws["B33"] = dados["gerado_em"]
        ws["A35"] = "Fontes para conferencia"
        ws["A35"].font = Font(bold=True, color=AZUL)
        ws.merge_cells("A36:H36")
        ws["A36"] = "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/reforma-tributaria-do-consumo/entenda"
        ws.merge_cells("A37:H37")
        ws["A37"] = "https://www12.senado.leg.br/noticias/"
        ws["A39"] = "FiscalPro | Stephane Rhis + ChatGPT"
        ws["A39"].font = Font(bold=True, color=AZUL)
        ws.column_dimensions["A"].width = 46
        ws.column_dimensions["B"].width = 24
        for letra in "CDEFGH":
            ws.column_dimensions[letra].width = 13
        ws.freeze_panes = "A11"

    def gerar(
        self, cnpj: str, competencia: str, destino: str | Path, *,
        regime: str, empresa: str = "",
        permitir_venda_icms_st: bool = False,
        usar_cenario_tcu: bool = False,
    ) -> Path:
        from openpyxl import Workbook
        from openpyxl.workbook.properties import CalcProperties

        destino = Path(destino)
        if destino.suffix.lower() != ".xlsx":
            raise ValueError("O relatorio de auditoria em lote deve ser salvo em .xlsx.")
        dados = self.preparar(
            cnpj, competencia, regime=regime, empresa=empresa,
            permitir_venda_icms_st=permitir_venda_icms_st,
            usar_cenario_tcu=usar_cenario_tcu,
        )
        wb = Workbook()
        wb.calculation = CalcProperties(calcMode="auto", fullCalcOnLoad=True)
        resumo = wb.active
        resumo.title = "Resumo"
        self._montar_resumo(resumo, dados)
        todos = dados["linhas"]
        categorias = (
            ("Todos os itens", todos),
            ("Vendas comuns", [l for l in todos if l["grupo"] == "VENDA COMUM"]),
            ("CFOP 5405", [l for l in todos if l["grupo"] == "VENDA ICMS-ST 5405"]),
            ("Revisar", [l for l in todos if l["revisar"]]),
        )
        for nome, linhas in categorias:
            ws = wb.create_sheet(nome)
            self._montar_detalhe(ws, dados, linhas, nome)
        wb.properties.title = "FiscalPro | Auditoria de IBS/CBS em lote - 2027"
        wb.properties.subject = "Simulacao de leitura; CBS definitiva ainda pendente"
        wb.properties.creator = "FiscalPro"
        destino.parent.mkdir(parents=True, exist_ok=True)
        wb.save(destino)
        return destino
