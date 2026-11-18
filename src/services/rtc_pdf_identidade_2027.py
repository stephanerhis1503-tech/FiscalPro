"""Identidade PDF RTC 2027, alinhada ao modelo aprovado de Conciliacao CBS.

Capa A4 retrato com logo oficial em fundo azul, indicadores, resultados,
destinacoes do SPED e conclusao cautelar. Anexos A4 paisagem com logo, titulo
e rodape conforme relatorio de reconciliacao CBS.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import re

from src.core.caminhos import pasta_recursos


def _quantidade(valor) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _dinheiro(valor) -> str:
    numero = Decimal(str(valor or "0")).quantize(Decimal("0.01"))
    return f"R$ {numero:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _cnpj(valor) -> str:
    d = "".join(c for c in str(valor or "") if c.isdigit())
    if len(d) != 14:
        return str(valor or "")
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def _seguro(valor) -> str:
    """Nomes vindos de XML nunca sao usados como markup no PDF."""
    return re.sub(r"[\x00-\x1f]", " ", str(valor or "")).strip()


def desenhar_logo(c, x, y, largura=110, altura=48):
    """Usa o MESMO asset e fallback do relatorio aprovado da CBS Oficial."""
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader

    img = pasta_recursos() / "assets" / "fiscalpro_logo_horizontal_white.png"
    if img.is_file():
        try:
            c.drawImage(
                ImageReader(str(img)), x, y, width=largura, height=altura,
                preserveAspectRatio=True, anchor="c", mask="auto",
            )
            return True
        except (OSError, ValueError):
            pass

    # Fallback reconhecivel caso a instalacao esteja sem o asset.
    marinho = colors.HexColor("#0B3155")
    c.setFillColor(marinho)
    c.roundRect(x, y + 4, 44, 38, 6, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(colors.white)
    c.drawString(x + 7, y + 25, "FP")
    c.setStrokeColor(colors.HexColor("#20C9A4"))
    c.setLineWidth(4)
    p = c.beginPath()
    p.moveTo(x + 8, y + 16)
    p.lineTo(x + 18, y + 10)
    p.lineTo(x + 30, y + 23)
    p.lineTo(x + 37, y + 18)
    c.drawPath(p, stroke=1)
    return False


def capa_conciliacao_visual(dados: dict, *, completo: bool) -> BytesIO:
    """Gera a primeira pagina em A4 retrato, sem escrever arquivos de dados."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfgen import canvas

    azul = colors.HexColor("#114B7A")
    marinho = colors.HexColor("#0B3155")
    azul_claro = colors.HexColor("#E8F2FB")
    cinza = colors.HexColor("#25394D")
    verde = colors.HexColor("#187C52")
    verde_claro = colors.HexColor("#E9F7EF")
    amarelo = colors.HexColor("#FFF4D9")
    margem = 28
    w, h = A4
    memoria = BytesIO()
    c = canvas.Canvas(memoria, pagesize=A4)
    c.setTitle("FiscalPro - Auditoria IBS/CBS em lote - Simulacao 2027")
    c.setAuthor("FiscalPro | Stephane Rhis + ChatGPT")

    def retangulo(x, y, largura, altura, fundo, contorno=None, raio=5):
        c.setFillColor(fundo)
        c.setStrokeColor(contorno or fundo)
        c.roundRect(x, y, largura, altura, raio, fill=1,
                    stroke=int(contorno is not None))

    def texto(valor, x, y, fonte="Helvetica", tamanho=9, cor=cinza):
        c.setFont(fonte, tamanho)
        c.setFillColor(cor)
        c.drawString(x, y, _seguro(valor))

    def central(valor, x, y, fonte="Helvetica-Bold", tamanho=12, cor=marinho):
        c.setFont(fonte, tamanho)
        c.setFillColor(cor)
        c.drawCentredString(x, y, _seguro(valor))

    def quebrar(valor, x, topo, largura, tamanho=9, passo=12,
                fonte="Helvetica", cor=cinza, max_linhas=4):
        linhas = simpleSplit(_seguro(valor), fonte, tamanho, largura)
        for linha in linhas[:max_linhas]:
            texto(linha, x, topo, fonte, tamanho, cor)
            topo -= passo
        return topo

    def secao(rotulo, y):
        retangulo(margem, y, w - 2 * margem, 24, azul_claro, raio=5)
        texto(rotulo, margem + 12, y + 7, "Helvetica-Bold", 12, marinho)

    # Capa - mesma barra azul, divisoria, logo e assinatura visual da CBS.
    c.setFillColor(azul)
    c.rect(0, h - 105, w, 105, fill=1, stroke=0)
    desenhar_logo(c, margem + 6, h - 84, 110, 52)
    c.setStrokeColor(colors.HexColor("#8ECDE6"))
    c.setLineWidth(1)
    c.line(154, h - 88, 154, h - 18)
    quebrar("Auditoria em Lote - IBS/CBS 2027", 170, h - 43,
            w - 190, 16.2, 20, "Helvetica-Bold", colors.white, max_linhas=2)
    texto("FiscalPro  |  Assistente Fiscal Inteligente", 171, h - 86,
          "Helvetica", 9.7, colors.white)

    secao("Identificacao da auditoria", 692)
    retangulo(margem, 625, w - 2 * margem, 63, colors.white,
              colors.HexColor("#C9DEEF"))
    campos = [
        ("Empresa", dados["empresa"], 0.29),
        ("CNPJ", _cnpj(dados["cnpj"]), 0.27),
        ("Competencia", str(dados["competencia"])[5:7] + "/" +
         str(dados["competencia"])[:4], 0.19),
        ("Regime", dados["regime"], 0.25),
    ]
    x = margem
    total = w - 2 * margem
    for i, (rotulo, valor, proporcao) in enumerate(campos):
        tam = total * proporcao
        if i:
            c.setStrokeColor(colors.HexColor("#D2E3F2"))
            c.line(x, 634, x, 679)
        texto(rotulo, x + 8, 668, "Helvetica", 8, azul)
        quebrar(valor, x + 8, 646, tam - 16, 8.3, 11,
                "Helvetica-Bold", marinho, max_linhas=2)
        x += tam

    secao("Resumo executivo", 589)
    indicadores = [
        ("Itens XML", dados["itens"]),
        ("Notas NF-e", dados["notas"]),
        ("Alertas XML", dados["alertas_xml"]),
        ("Revisar", dados["revisar"]),
        ("ST condicional", dados["st_condicionais"]),
    ]
    espac = 6
    largura_card = (w - 2 * margem - 4 * espac) / 5
    for i, (rotulo, quantidade) in enumerate(indicadores):
        x = margem + i * (largura_card + espac)
        destaque = i == 2 and quantidade == 0
        retangulo(x, 505, largura_card, 75,
                  verde_claro if destaque else azul_claro,
                  colors.HexColor("#C5DFEC"), raio=6)
        central(rotulo, x + largura_card / 2, 555,
                "Helvetica", 8.1, marinho)
        central(_quantidade(quantidade), x + largura_card / 2, 522,
                "Helvetica-Bold", 18, verde if destaque else marinho)

    secao("Resultados da simulacao - SEM EFEITO FISCAL", 468)
    retangulo(margem, 435, w - 2 * margem, 25, azul, raio=2)
    texto("Indicador", margem + 10, 443, "Helvetica-Bold", 9, colors.white)
    texto("Valor", margem + 265, 443, "Helvetica-Bold", 9, colors.white)
    texto("Observacao", margem + 373, 443, "Helvetica-Bold", 9, colors.white)

    ibs_uf = Decimal("0.00")
    ibs_mun = Decimal("0.00")
    cbs = Decimal("0.00")
    for linha in dados["linhas"]:
        sim = linha["simulacao"]
        for campo, acum in (("ibs_uf", "uf"), ("ibs_municipal", "municipal"),
                            ("cbs", "cbs")):
            if sim.get(campo) is not None:
                valor = Decimal(str(sim[campo]))
                if acum == "uf":
                    ibs_uf += valor
                elif acum == "municipal":
                    ibs_mun += valor
                else:
                    cbs += valor

    linhas = [
        ("IBS estadual", _dinheiro(ibs_uf), "0,05% ref. 2027"),
        ("IBS municipal", _dinheiro(ibs_mun), "0,05% ref. 2027"),
        ("Total demonstrativo IBS", _dinheiro(ibs_uf + ibs_mun), "Nao e debito fiscal"),
        ("CBS 2027" if not dados["usar_cenario_tcu"] else "CBS TCU 11,2%",
         "NAO SIMULADA" if not dados["usar_cenario_tcu"] else _dinheiro(cbs),
         "Nao oficial" if dados["usar_cenario_tcu"] else "A definir"),
        ("Hipotese CFOP 5405",
         "SIM" if dados["permitir_venda_icms_st"] else "NAO",
         "Simulacao condicional"),
    ]
    for i, (rotulo, valor, obs) in enumerate(linhas):
        y = 435 - 22 * (i + 1)
        retangulo(margem, y, w - 2 * margem, 22,
                  colors.white if i % 2 == 0 else azul_claro, raio=0)
        texto(rotulo, margem + 10, y + 7, "Helvetica-Bold", 8.6)
        texto(valor, margem + 265, y + 7, "Helvetica-Bold", 8.7, marinho)
        texto(obs, margem + 373, y + 7, "Helvetica", 8.1)

    secao("Destinacao das entradas no SPED Fiscal", 295)
    retangulo(margem, 268, w - 2 * margem, 22, azul, raio=2)
    texto("Destinacao", margem + 10, 275, "Helvetica-Bold", 8.8, colors.white)
    texto("Itens", margem + 285, 275, "Helvetica-Bold", 8.8, colors.white)
    texto("Observacao", margem + 369, 275, "Helvetica-Bold", 8.8, colors.white)

    cont = dados["destinacoes"]
    uso = cont["USO E CONSUMO (CFOP EFD)"] + cont["USO E CONSUMO COM ST (CFOP EFD)"]
    rev = cont["REVENDA (CFOP EFD)"] + cont["REVENDA COM ST (CFOP EFD)"]
    ativo = cont["ATIVO IMOBILIZADO (CFOP EFD)"] + cont["ATIVO IMOBILIZADO COM ST (CFOP EFD)"]
    combustivel = cont["COMBUSTIVEL USUARIO FINAL (CFOP EFD)"]
    outros = sum(cont.values()) - uso - rev - ativo - combustivel
    dados_destino = [
        ("Uso e consumo (CFOP EFD)", uso,
         f"1556 / 1407; ST: {_quantidade(cont['USO E CONSUMO COM ST (CFOP EFD)'])}"),
        ("Revenda", rev,
         f"1102 / 1403; ST: {_quantidade(cont['REVENDA COM ST (CFOP EFD)'])}"),
        ("Ativo imobilizado", ativo, "1551 / 1406"),
        ("Combustivel usuario final", combustivel, "1653 / 2653"),
        ("Outras entradas / sem vinculo", outros, "A conferir"),
    ]
    for i, (rotulo, quantidade, obs) in enumerate(dados_destino):
        y = 268 - (i + 1) * 22
        retangulo(margem, y, w - 2 * margem, 22,
                  colors.white if i % 2 == 0 else azul_claro, raio=0)
        texto(rotulo, margem + 10, y + 7, "Helvetica-Bold", 8.5)
        texto(_quantidade(quantidade), margem + 285, y + 7,
              "Helvetica-Bold", 9, marinho)
        texto(obs, margem + 369, y + 7, "Helvetica", 8.1)

    quebrar(
        "SPED Fiscal: " + (dados["arquivo_sped_fiscal"] or "NAO SELECIONADO") +
        "  |  Creditos IBS/CBS NAO reconhecidos automaticamente.",
        margem + 5, 142, w - 2 * margem - 10, 7.7, 10,
        "Helvetica", cinza, max_linhas=2,
    )

    retangulo(margem, 66, w - 2 * margem, 58, amarelo,
              colors.HexColor("#E5C87A"), raio=7)
    texto("Conclusao e observacoes tecnicas", margem + 13, 103,
          "Helvetica-Bold", 12, marinho)
    conclusao = (
        "RELATORIO DEMONSTRATIVO - SEM EFEITO FISCAL. "
        "Alertas de XML e entradas de uso e consumo NAO comprovam erros "
        "ou geram creditos automaticamente. "
        "CBS: " + ("SIM - NAO OFICIAL (TCU)" if dados["usar_cenario_tcu"]
                    else "NAO SIMULADA") + ". "
        "Anexo: " + ("todos os itens" if completo else "alertas e demais revisoes") + "."
    )
    quebrar(conclusao, margem + 13, 86, w - 2 * margem - 27,
            8.8, 11, "Helvetica", cinza, max_linhas=3)
    c.setStrokeColor(azul)
    c.line(margem, 48, w - margem, 48)
    texto("FiscalPro | Stephane Rhis + ChatGPT", margem, 32,
          "Helvetica-Bold", 8, azul)
    texto("Relatorio analitico para conferencia interna", w - 214, 32,
          "Helvetica-Oblique", 7, cinza)
    texto("1", w - margem - 6, 19, "Helvetica", 7, cinza)
    c.showPage()
    c.save()
    memoria.seek(0)
    return memoria


def cabecalho_anexo(c, doc, dados: dict):
    """Cabeçalho do anexo em A4 paisagem, identico ao modelo CBS aprovado."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape

    azul = colors.HexColor("#114B7A")
    cinza = colors.HexColor("#25394D")
    w, h = landscape(A4)
    c.saveState()
    c.setFillColor(azul)
    c.rect(0, h - 76, w, 76, fill=1, stroke=0)
    desenhar_logo(c, 33, h - 67, 95, 45)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(148, h - 39, "Anexo documental | Auditoria IBS/CBS 2027")
    c.setFont("Helvetica", 9)
    resumo = (
        f"{_seguro(dados['empresa'])} | {_seguro(dados['competencia'])} "
        f"| {_quantidade(dados['revisar'])} itens a revisar"
    )
    c.drawString(148, h - 57, resumo[:130])
    c.setFillColor(cinza)
    c.setFont("Helvetica", 8.2)
    c.drawString(
        33, h - 93,
        "Conferencia local, nao oficial. CFOP da EFD refere-se a entrada do adquirente."
    )
    c.setStrokeColor(azul)
    c.setLineWidth(0.7)
    c.line(33, 26, w - 33, 26)
    c.setFillColor(azul)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(33, 12, "FiscalPro | Stephane Rhis + ChatGPT")
    c.setFont("Helvetica", 8)
    c.drawRightString(w - 33, 12, f"Pagina {doc.page + 1}")
    c.restoreState()
