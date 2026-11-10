"""Testes de exportacao do relatorio mensal RTC (sem valores oficiais)."""

from pathlib import Path

import pytest
from openpyxl import load_workbook

from src.services.rtc_relatorio_local_excel_service import (
    ServicoRelatorioApuracaoLocalRTC,
)

EMPRESA = "11809691000195"


class FalsoServico:
    validar_cnpj = staticmethod(lambda x: x)
    validar_competencia = staticmethod(lambda x: x)

    def __init__(self, docs):
        self.docs = docs
        self.consultas = []

    def listar(self, cnpj, competencia):
        self.consultas.append((cnpj, competencia))
        return self.docs


def doc(chave, direcao, ibs, cbs, status="CONFERIDO_XML", num="1"):
    return {
        "direcao": direcao,
        "numero_nf": num,
        "emissao": "2026-10-10",
        "chave_nfe": chave,
        "cnpj_emitente": EMPRESA if direcao == "SAIDA" else "99887766000155",
        "cnpj_destinatario": EMPRESA if direcao == "ENTRADA" else "99887766000155",
        "base_ibs_cbs": "100.00",
        "valor_ibs": ibs,
        "valor_cbs": cbs,
        "status_conferencia": status,
        "status_protocolo": "SEM_PROTOCOLO" if status == "REVISAR" else "PROTOCOLO_100_150_XML",
        "status_credito": "POTENCIAL_NAO_APROPRIADO" if direcao == "ENTRADA" else "NAO_APLICAVEL",
        "observacao": "XML sem protocolo" if status == "REVISAR" else "",
        "arquivo_origem": "nota.xml",
    }


def test_exporta_4_abas_com_creditos_apenas_potenciais(tmp_path):
    fake = FalsoServico([
        doc("1" * 44, "SAIDA", "0.10", "0.90", num="101"),
        doc("2" * 44, "ENTRADA", "0.20", "1.80", num="202"),
        doc("3" * 44, "SAIDA", "0.03", "0.27", "REVISAR", num="303"),
    ])
    caminho = tmp_path / "rtc.xlsx"
    gerado = ServicoRelatorioApuracaoLocalRTC(fake).gerar(
        EMPRESA, "2026-10", caminho, "MEGA MOTOS TRILHA"
    )
    assert gerado == caminho
    wb = load_workbook(gerado, data_only=False)
    assert wb.sheetnames == ["Resumo", "Entradas", "Saidas", "Revisar"]
    resumo = wb["Resumo"]
    assert resumo["B7"].value == 3
    assert resumo["B8"].value == 2
    assert resumo["B9"].value == 1
    assert resumo["B10"].value == 1
    assert resumo["B11"].value == 1
    assert resumo["B13"].value == pytest.approx(0.13)
    assert resumo["B14"].value == pytest.approx(1.17)
    assert resumo["B16"].value == pytest.approx(100)
    assert resumo["B17"].value == pytest.approx(0.20)
    assert resumo["B18"].value == pytest.approx(1.80)
    assert "NAO OFICIAL" in resumo["A3"].value
    assert "NAO representa" not in resumo["A1"].value
    assert wb["Entradas"]["D7"].value == "2" * 44
    assert wb["Entradas"]["L7"].value == "POTENCIAL_NAO_APROPRIADO"
    assert wb["Entradas"]["I7"].value == pytest.approx(1.80)
    assert len(list(wb["Revisar"].iter_rows(min_row=7, values_only=True))) == 1
    assert fake.consultas == [(EMPRESA, "2026-10")]


def test_protege_de_formula_em_campos_texto(tmp_path):
    documento = doc("3" * 44, "ENTRADA", "0.03", "0.27")
    documento["arquivo_origem"] = "=HYPERLINK(\"https://exemplo.test\", \"abrir\")"
    documento["observacao"] = "+SOMA(1;2)"
    destino = tmp_path / "rtc.xlsx"
    ServicoRelatorioApuracaoLocalRTC(FalsoServico([documento])).gerar(
        EMPRESA, "2026-10", destino, "Mega"
    )
    aba = load_workbook(destino).get_sheet_by_name("Entradas")
    assert aba["N7"].data_type != "f"
    assert aba["M7"].data_type != "f"


def test_nao_exporta_relatorio_vazio(tmp_path):
    with pytest.raises(ValueError, match="Nao ha XMLs"):
        ServicoRelatorioApuracaoLocalRTC(FalsoServico([])).gerar(
            EMPRESA, "2026-10", tmp_path / "rtc.xlsx", "Mega"
        )


def test_relatorio_exige_xlsx(tmp_path):
    with pytest.raises(ValueError, match=".xlsx"):
        ServicoRelatorioApuracaoLocalRTC(FalsoServico([])).gerar(
            EMPRESA, "2026-10", tmp_path / "rtc.csv", "Mega"
        )
