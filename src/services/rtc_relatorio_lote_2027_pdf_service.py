"""Relatorio PDF demonstrativo da auditoria em lote IBS/CBS - cenario 2027.

Reutiliza exatamente a triagem do Excel, inclusive o cruzamento opcional
de CFOPs de entrada por chave e numero do item na EFD ICMS/IPI.
Por padrao imprime resumo + TODAS as pendencias; as vendas sem alerta
podem entrar em um anexo completo por escolha expressa do usuario.
Nunca altera XML, banco, SPED, creditos ou apuracao.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from pathlib import Path
import re
from xml.sax.saxutils import escape

from src.services.rtc_relatorio_lote_2027_service import ServicoRelatorioLoteRTC2027
from src.services.rtc_pdf_identidade_2027 import capa_conciliacao_visual, cabecalho_anexo


AZUL = "#143A5F"
AZUL_MEDIO = "#245A84"
AZUL_CLARO = "#EEF4F9"
LARANJA_CLARO = "#FFF1D6"
CINZA = "#637287"
TEXTO = "#263546"
VERMELHO = "#9C3933"
CENTAVO = Decimal("0.01")


def _limpo(valor, limite=240):
    """Escapa conteudo de XML/SPED para nao injetar tags no Paragraph."""
    texto = str(valor if valor is not None else "")
    texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", texto)
    texto = " ".join(texto.split())
    if len(texto) > limite:
        texto = texto[: limite - 3].rstrip() + "..."
    return escape(texto, {'"': "&quot;", "'": "&#39;"})


def _real(valor):
    numero = Decimal(str(valor or "0")).quantize(CENTAVO)
    texto = f"{numero:,.2f}"
    return "R$ " + texto.replace(",", "_").replace(".", ",").replace("_", ".")


def _inteiro(valor):
    return f"{int(valor):,}".replace(",", ".")


def _somar(dados: dict, campo: str, grupo: str | None = None) -> Decimal:
    resultado = Decimal("0.00")
    for linha in dados["linhas"]:
        if grupo and linha["classificacao"] != grupo:
            continue
        valor = linha["simulacao"].get(campo)
        if valor is not None:
            resultado += Decimal(str(valor))
    return resultado.quantize(CENTAVO)


class ServicoRelatorioLoteRTC2027PDF:
    """PDF legivel: resumo e pendencias, opcionalmente todos os itens."""

    def __init__(self, servico=None):
        self.servico = servico

    def gerar(
        self, cnpj: str, competencia: str, destino: str | Path, *,
        regime: str, empresa: str = "",
        permitir_venda_icms_st: bool = False,
        usar_cenario_tcu: bool = False,
        arquivo_sped_fiscal: str | Path | None = None,
        incluir_todos_itens: bool = False,
    ) -> Path:
        if type(incluir_todos_itens) is not bool:
            raise ValueError("A opcao de PDF completo deve ser SIM ou NAO.")
        destino = Path(destino)
        if destino.suffix.lower() != ".pdf":
            raise ValueError("O relatorio PDF deve ter extensao .pdf.")

        dados = ServicoRelatorioLoteRTC2027(self.servico).preparar(
            cnpj, competencia, regime=regime, empresa=empresa,
            permitir_venda_icms_st=permitir_venda_icms_st,
            usar_cenario_tcu=usar_cenario_tcu,
            arquivo_sped_fiscal=arquivo_sped_fiscal,
        )

        # Os dados de saida sao sempre apenas uma simulacao; se um item
        # possui alerta original, ele nao e somado duas vezes em detalhes.
        alertas = [l for l in dados["linhas"] if l["alerta_xml"]]
        outras = [
            l for l in dados["linhas"]
            if l["classificacao"] == "REVISAR OPERACAO"
        ]
        restantes = [
            l for l in dados["linhas"]
            if not l["alerta_xml"] and l["classificacao"] != "REVISAR OPERACAO"
        ]
        assert len(alertas) + len(outras) + len(restantes) == dados["itens"]
        assert len(alertas) + len(outras) == dados["revisar"]

        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            HRFlowable, KeepTogether, LongTable, Paragraph, SimpleDocTemplate,
            Spacer, Table, TableStyle, PageBreak,
        )

        pagina = landscape(A4)
        documento = SimpleDocTemplate(
            str(destino), pagesize=pagina,
            leftMargin=17 * mm, rightMargin=17 * mm,
            topMargin=20 * mm, bottomMargin=17 * mm,
            title="FiscalPro - Auditoria IBS/CBS em lote - Simulacao 2027",
            author="FiscalPro",
            subject="Conferencia de XMLs e EFD; sem efeito fiscal",
        )
        largura = documento.width
        estilos = {
            "sobre": ParagraphStyle(
                "sobre_rtc_pdf", fontName="Helvetica-Bold",
                fontSize=8, leading=11, textColor=colors.HexColor(AZUL_MEDIO),
                spaceAfter=5,
            ),
            "titulo": ParagraphStyle(
                "titulo_rtc_pdf", fontName="Helvetica-Bold",
                fontSize=21, leading=25, textColor=colors.HexColor(AZUL),
                spaceAfter=7,
            ),
            "subtitulo": ParagraphStyle(
                "subtitulo_rtc_pdf", fontName="Helvetica",
                fontSize=9.4, leading=14, textColor=colors.HexColor(TEXTO),
                spaceAfter=10,
            ),
            "secao": ParagraphStyle(
                "secao_rtc_pdf", fontName="Helvetica-Bold",
                fontSize=12.4, leading=16, textColor=colors.HexColor(AZUL),
                spaceBefore=13, spaceAfter=6, keepWithNext=True,
            ),
            "texto": ParagraphStyle(
                "texto_rtc_pdf", fontName="Helvetica",
                fontSize=8.4, leading=12.2, textColor=colors.HexColor(TEXTO),
                spaceAfter=6,
            ),
            "aviso": ParagraphStyle(
                "aviso_rtc_pdf", fontName="Helvetica-Bold",
                fontSize=9, leading=13.4,
                textColor=colors.HexColor("#805314"),
            ),
            "celula": ParagraphStyle(
                "celula_rtc_pdf", fontName="Helvetica",
                fontSize=7.2, leading=10,
                textColor=colors.HexColor(TEXTO),
            ),
            "celula_centro": ParagraphStyle(
                "celula_centro_rtc_pdf", fontName="Helvetica",
                fontSize=7.2, leading=10, alignment=TA_CENTER,
                textColor=colors.HexColor(TEXTO),
            ),
            "cabecalho": ParagraphStyle(
                "cabecalho_rtc_pdf", fontName="Helvetica-Bold",
                fontSize=7.2, leading=9.7, alignment=TA_CENTER,
                textColor=colors.white,
            ),
            "celula_num": ParagraphStyle(
                "celula_num_rtc_pdf", fontName="Helvetica",
                fontSize=8.6, leading=12, alignment=TA_RIGHT,
                textColor=colors.HexColor(AZUL),
            ),
        }
        p = lambda valor, estilo="texto", limite=240: Paragraph(
            _limpo(valor, limite), estilos[estilo]
        )
        story = []

        def tabela_padrao(linhas, widths, *, primeira_linha=True):
            dados_tabela = [
                [
                    p(valor, "cabecalho") if primeira_linha and i == 0 else
                    (valor if isinstance(valor, Paragraph) else p(valor, "celula"))
                    for valor in linha
                ]
                for i, linha in enumerate(linhas)
            ]
            tabela = LongTable(
                dados_tabela, colWidths=widths, repeatRows=1 if primeira_linha else 0,
                hAlign="LEFT", splitByRow=1,
            )
            estilizar = [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDE5EB")),
            ]
            if primeira_linha:
                estilizar.extend([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(AZUL)),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                        colors.white, colors.HexColor("#F7FAFC")]),
                ])
            tabela.setStyle(TableStyle(estilizar))
            return tabela

        def secao(titulo, conteudo):
            story.append(Paragraph(_limpo(titulo), estilos["secao"]))
            story.extend(conteudo)

        def texto_legal(texto):
            story.append(p(texto))

        story.append(Paragraph("FISCALPRO  /  RELATORIOS FISCAIS", estilos["sobre"]))
        story.append(Paragraph("Auditoria IBS/CBS - Projecao 2027", estilos["titulo"]))
        story.append(p(
            f"Empresa: {dados['empresa']}  |  CNPJ: {dados['cnpj']}  |  "
            f"XMLs da competencia: {dados['competencia']}  |  "
            f"Regime informado: {dados['regime']}  |  "
            f"Gerado em: {dados['gerado_em']}",
            "subtitulo", 560,
        ))

        aviso = p(
            "RELATORIO DEMONSTRATIVO - SEM EFEITO FISCAL. "
            "Bases e classificacoes dos XMLs historicos nao comprovam "
            "o enquadramento de 2027. Os valores exibidos NAO sao apuracao "
            "oficial, tributos a recolher nem creditos apropriados. "
            "CBS 2027 definitiva nao cadastrada neste modulo. "
            "CFOP 5405 so pode ser simulado em hipotese condicional.",
            "aviso", 700,
        )
        nota = Table([[aviso]], colWidths=[largura], hAlign="LEFT")
        nota.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(LARANJA_CLARO)),
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#E5D19F")),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.extend([nota, Spacer(1, 10)])

        # Indicadores sem duplicacao: as abas de revisao nao incluem
        # apenas por CFOP as vendas ST simuladas condicionalmente.
        resumos = [
            ("Itens analisados", _inteiro(dados["itens"])),
            ("NF-e distintas", _inteiro(dados["notas"])),
            ("Alertas XML", _inteiro(dados["alertas_xml"])),
            ("Outras revisoes", _inteiro(dados["outras_revisoes"])),
            ("ST 5405 condicional", _inteiro(dados["st_condicionais"])),
            ("ST 5405 nao simulado", _inteiro(dados["st_sem_cenario"])),
            ("Itens na fila de revisao", _inteiro(dados["revisar"])),
        ]
        secao("Panorama da competencia", [
            tabela_padrao(
                [["Indicador", "Quantidade"]] + resumos,
                [largura * 0.70, largura * 0.30],
            ),
        ])

        dest = dados["destinacoes"]
        labels = (
            ("Uso e consumo (CFOP EFD)", "USO E CONSUMO (CFOP EFD)"),
            ("Uso e consumo com ICMS-ST", "USO E CONSUMO COM ST (CFOP EFD)"),
            ("Ativo imobilizado", "ATIVO IMOBILIZADO (CFOP EFD)"),
            ("Ativo imobilizado com ICMS-ST", "ATIVO IMOBILIZADO COM ST (CFOP EFD)"),
            ("Revenda", "REVENDA (CFOP EFD)"),
            ("Revenda com ICMS-ST", "REVENDA COM ST (CFOP EFD)"),
            ("Combustivel - usuario final", "COMBUSTIVEL USUARIO FINAL (CFOP EFD)"),
        )
        conhecidos = {k for _, k in labels}
        outros = sum(n for k, n in dest.items() if k not in conhecidos)
        secao("Destinacao das entradas no SPED Fiscal", [
            p(
                "Vinculo opcional por chave da NF-e e numero do item C170. "
                "O CFOP do fornecedor (XML) e o CFOP de entrada do adquirente "
                "sao diferentes. Classificacao de uso e consumo nao determina "
                "automaticamente direito ao credito IBS/CBS."
            ),
            p("SPED Fiscal utilizado: " + (dados["arquivo_sped_fiscal"] or
              "NAO SELECIONADO - destinacao pendente.")),
            tabela_padrao(
                [["Destinacao escriturada", "Itens"]] +
                [[titulo, _inteiro(dest[k])] for titulo, k in labels] +
                [["Outras entradas / sem correspondencia", _inteiro(outros)]],
                [largura * 0.70, largura * 0.30],
            ),
        ])

        regra = dados["referencia"]
        ibs_uf = _somar(dados, "ibs_uf")
        ibs_mun = _somar(dados, "ibs_municipal")
        cbs = _somar(dados, "cbs")
        linhas_valores = [
            ["IBS estadual - vendas comuns", _real(_somar(dados, "ibs_uf", "PROJECAO COMUM"))],
            ["IBS municipal - vendas comuns", _real(_somar(dados, "ibs_municipal", "PROJECAO COMUM"))],
            ["IBS estadual - ST condicional", _real(_somar(dados, "ibs_uf", "ST CONDICIONAL"))],
            ["IBS municipal - ST condicional", _real(_somar(dados, "ibs_municipal", "ST CONDICIONAL"))],
            ["IBS estadual - total da simulacao", _real(ibs_uf)],
            ["IBS municipal - total da simulacao", _real(ibs_mun)],
            ["Total demonstrativo IBS 2027", _real(ibs_uf + ibs_mun)],
        ]
        if dados["usar_cenario_tcu"]:
            linhas_valores.extend([
                ["CBS TCU 11,2% - NAO oficial", _real(cbs)],
                ["Total hipotetico IBS + CBS TCU", _real(ibs_uf + ibs_mun + cbs)],
            ])
        else:
            linhas_valores.append(["CBS 2027", "NAO SIMULADA"])

        secao("Valores projetados - nao oficiais", [
            p(
                f"Referencia do simulador: IBS estadual {regra.ibs_uf}% e "
                f"municipal {regra.ibs_municipal}% em 2027; "
                "resultados arredondados por item, iguais ao motor do Excel. "
                "Nao representa debito nem credito tributario."
            ),
            tabela_padrao(
                [["Indicador", "Valor demonstrativo"]] + linhas_valores,
                [largura * 0.70, largura * 0.30],
            ),
        ])

        secao("Parametros do relatorio", [
            p("Cenario ICMS-ST 5405 habilitado: " +
              ("SIM - hipotetico" if dados["permitir_venda_icms_st"] else "NAO")),
            p("CBS 11,2% do TCU habilitada: " +
              ("SIM - NAO OFICIAL" if dados["usar_cenario_tcu"] else "NAO")),
            p("Modalidade PDF: " + (
                "COMPLETO - todos os itens da competencia" if incluir_todos_itens
                else "RESUMIDO - todas as pendencias, sem repetir vendas sem alerta")),
            p(
                "Um alerta no XML nao comprova erro fiscal. As entradas nao "
                "geram credito IBS/CBS automaticamente; operacoes especificas "
                "exigem conferencia de CST, cClassTrib, regime e vigencia."
            ),
        ])

        # Detalhe das pendencias com 100% dos respectivos itens.
        # Cada chave+item consta apenas uma vez entre as secoes.
        larguras = [
            largura * 0.080, largura * 0.055, largura * 0.080,
            largura * 0.082, largura * 0.225, largura * 0.210,
            largura * 0.268,
        ]
        cabecalho = [
            "NF-e", "Item", "CFOP XML", "CFOP EFD",
            "Descricao", "Destinacao", "Alerta ou proxima acao",
        ]

        def detalhe_linhas(itens, texto_alerta):
            for linha in itens:
                item = linha["item"]
                observacao = item.get("motivos") if texto_alerta else linha["acao"]
                if not observacao:
                    observacao = linha["simulacao"].get("observacao") or linha["status"]
                yield [
                    p(item.get("numero_nf"), "celula_centro", 25),
                    p(item.get("numero_item"), "celula_centro", 12),
                    p(item.get("cfop"), "celula_centro", 7),
                    p(linha["cfop_entrada"] or "-", "celula_centro", 7),
                    p(item.get("descricao"), "celula", 95),
                    p(linha["destinacao"], "celula", 78),
                    p(observacao, "celula", 160),
                ]

        def tabela_itens(titulo, itens, *, alerta=False):
            story.append(Paragraph(_limpo(titulo), estilos["secao"]))
            if not itens:
                story.append(p("Nenhum item nesta categoria."))
                return
            story.append(p(
                f"{_inteiro(len(itens))} item(ns). O CFOP XML pertence ao fornecedor; "
                "CFOP EFD, quando presente, e da entrada do adquirente."
            ))
            # Lotes moderados evitam montar um unico quadro gigante
            # quando o usuario solicitar PDF completo (~22 mil itens).
            for inicio in range(0, len(itens), 120):
                grupo = itens[inicio : inicio + 120]
                tabela = LongTable(
                    [[p(t, "cabecalho") for t in cabecalho]] +
                    list(detalhe_linhas(grupo, texto_alerta=alerta)),
                    colWidths=larguras, repeatRows=1, hAlign="LEFT",
                    splitByRow=1,
                )
                tabela.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(AZUL)),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                        colors.white, colors.HexColor("#F7FAFC")]),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.2, colors.HexColor("#DDE5EB")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]))
                story.append(tabela)
                story.append(Spacer(1, 5))

        story.append(PageBreak())
        tabela_itens("1. Alertas originais dos XMLs", alertas, alerta=True)
        tabela_itens("2. Outras operacoes a revisar", outras)
        if incluir_todos_itens:
            story.append(PageBreak())
            tabela_itens("3. Demais itens - anexo completo", restantes)
        else:
            story.append(p(
                f"As demais {_inteiro(len(restantes))} linhas sem pendencia nesta "
                "triagem nao integram o PDF resumido. Para consultar cada "
                "item, gere o Excel completo ou ative 'PDF completo'."
            ))

        story.append(Spacer(1, 9))
        story.append(HRFlowable(
            width="100%", thickness=0.5, color=colors.HexColor("#BBC8D4")
        ))
        story.append(p(
            "FiscalPro - Stephane Rhis + ChatGPT. "
            "Relatorio para revisao interna. Fonte primaria: XMLs importados e "
            "SPED Fiscal TXT opcional. Referencias gerais: LC 214/2025 e "
            "documentacao da Reforma Tributaria do Consumo da Receita Federal. "
            "Nunca usar esta projeção como DARF, SPED, recolhimento ou apuracao.",
            "texto", 800,
        ))

        def pagina_pdf(canvas, doc):
            cabecalho_anexo(canvas, doc, dados)

        # A capa segue o PDF de Conciliacao CBS Oficial ja aprovado:
        # A4 retrato, logo branca, indicadores e conclusao.
        # O detalhamento continua em A4 paisagem, com logo em cada pagina.
        # O PDF preexistente so e substituido depois de tudo concluido.
        from pypdf import PdfReader, PdfWriter

        destino.parent.mkdir(parents=True, exist_ok=True)
        provisoria = destino.with_name(destino.stem + ".gerando.pdf")
        anexo = destino.with_name(destino.stem + ".anexo-gerando.pdf")
        try:
            documento.filename = str(anexo)
            documento.topMargin = 31 * mm
            documento.bottomMargin = 20 * mm
            documento.build(story, onFirstPage=pagina_pdf, onLaterPages=pagina_pdf)
            capa = capa_conciliacao_visual(dados, completo=incluir_todos_itens)
            juntar = PdfWriter()
            juntar.append(PdfReader(capa))
            juntar.append(PdfReader(str(anexo)))
            juntar.add_metadata({
                "/Title": "FiscalPro - Auditoria IBS/CBS em lote - Simulacao 2027",
                "/Author": "FiscalPro | Stephane Rhis + ChatGPT",
                "/Subject": "Projecao demonstrativa com dados de XML e EFD; sem efeito fiscal",
            })
            with provisoria.open("wb") as arquivo_final:
                juntar.write(arquivo_final)
            provisoria.replace(destino)
        finally:
            anexo.unlink(missing_ok=True)
            provisoria.unlink(missing_ok=True)
        return destino
