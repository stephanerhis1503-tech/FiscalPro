"""Auditoria RTC 2027 em lote: segregacao, formulas e seguranca fiscal."""
from copy import deepcopy
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from src.services.rtc_relatorio_lote_2027_service import ServicoRelatorioLoteRTC2027


CNPJ = "11809691000195"
COMPETENCIA = "2026-10"


def item(n, *, cfop="5102", direcao="SAIDA", cst="000", cclass="000001",
         status="OK", base="1000.00"):
    return {
        "numero_nf": f"{10000+n}", "numero_item": "1",
        "emissao": "2026-10-10",
        "chave_nfe": f"{n:044d}",
        "descricao": f"Produto teste {n}", "ncm": "87141000",
        "cfop": cfop, "direcao": direcao, "cst_ibscbs": cst,
        "cclass_trib": cclass, "base_ibs_cbs": base, "valor_ibs": "1.00",
        "valor_cbs": "9.00", "status_auditoria": status, "motivos": "",
    }


class LocalFalso:
    def __init__(self, itens):
        self.itens = itens
        self.chamadas = []

    def listar_itens(self, cnpj, competencia, *, limite=None):
        self.chamadas.append((cnpj, competencia, limite))
        return deepcopy(self.itens)

    def contar_itens(self, cnpj, competencia):
        return len(self.itens)


@pytest.fixture
def dados():
    return [
        item(1),
        item(2, cfop="5405"),
        item(3, direcao="ENTRADA", cfop="1102"),
        item(4, cst="200", cclass="200001"),
        item(5, cfop="5152"),
        item(6, cfop="5102", status="REVISAR"),
    ]


def test_preparar_sem_limite_visual_e_segura_cfop_st(dados):
    local = LocalFalso(dados)
    svc = ServicoRelatorioLoteRTC2027(local)
    res = svc.preparar(CNPJ, COMPETENCIA, regime="Lucro Real")
    assert local.chamadas == [(CNPJ, COMPETENCIA, None)]
    assert res["itens"] == 6
    assert res["notas"] == 6
    assert res["grupos"] == {
        "VENDA COMUM": 1,
        "VENDA ICMS-ST 5405": 1,
        "REVISAR OUTROS": 4,
    }
    assert res["revisar"] == 5
    assert res["linhas"][0]["simulacao"]["ibs_uf"] == Decimal("0.50")
    assert res["linhas"][1]["status"] == "REVISAR_CFOP_ST"
    assert res["linhas"][1]["simulacao"]["cbs"] is None
    assert all(not linha["simulacao"]["efeito_fiscal"] for linha in res["linhas"])
    assert dados[0]["base_ibs_cbs"] == "1000.00"


def test_excel_abas_e_formulas_condicionais(dados, tmp_path):
    local = LocalFalso(dados)
    svc = ServicoRelatorioLoteRTC2027(local)
    destino = svc.gerar(
        CNPJ, COMPETENCIA, tmp_path / "rtc_lote.xlsx",
        regime="Lucro Real", empresa="Mega Motos Trilha",
        permitir_venda_icms_st=True, usar_cenario_tcu=True,
    )
    book = load_workbook(destino)
    assert book.sheetnames == [
        "Resumo", "Todos os itens", "Vendas comuns", "CFOP 5405", "Revisar"
    ]
    assert book["Resumo"]["B12"].value == 6
    assert book["Resumo"]["B14"].value == 1
    assert book["Resumo"]["B15"].value == 1
    assert book["Resumo"]["B16"].value == 4
    assert book["Resumo"]["B17"].value == 5
    assert book["Resumo"]["B31"].value == "SIM"
    assert book["Resumo"]["B32"].value == "SIM (NAO OFICIAL)"
    ws = book["Todos os itens"]
    assert ws.max_row == 13
    assert ws["F8"].value == f"{1:044d}"
    assert ws["C8"].value == "10001"
    assert ws["L8"].value == 1000
    assert ws["M8"].value == 0.05
    assert ws["O8"].value == "=ROUND(L8*M8/100,2)"
    assert ws["R8"].value == "=ROUND(L8*Q8/100,2)"
    assert ws["S8"].value == "=ROUND(O8+P8+R8,2)"
    assert ws["T9"].value == "CENARIO_CONDICIONAL_CFOP_5405"
    assert ws["R9"].value == "=ROUND(L9*Q9/100,2)"
    assert ws["O10"].value is None  # entrada
    assert ws["R10"].value is None
    assert ws["R11"].value is None  # regra especial
    assert len([r for r in ws.iter_rows(min_row=8) if r[0].value]) == 6
    assert book["CFOP 5405"]["T8"].value == "CENARIO_CONDICIONAL_CFOP_5405"
    assert book["Revisar"]["T8"].value == "CENARIO_CONDICIONAL_CFOP_5405"
    assert book["Resumo"]["B21"].value == "=SUM('Todos os itens'!O8:O13)"


def test_excel_padrao_nao_aplica_cbs_tcu_ou_5405(dados, tmp_path):
    arquivo = ServicoRelatorioLoteRTC2027(LocalFalso(dados)).gerar(
        CNPJ, COMPETENCIA, tmp_path / "seguro.xlsx", regime="Lucro Real",
    )
    wb = load_workbook(arquivo)
    todos = wb["Todos os itens"]
    assert todos["O8"].value == "=ROUND(L8*M8/100,2)"
    assert todos["R8"].value is None
    assert todos["O9"].value is None
    assert todos["R9"].value is None
    assert wb["Resumo"]["B23"].value == "NAO SIMULADA"
    assert wb["Resumo"]["B31"].value == "NAO"
    assert wb["Resumo"]["B32"].value == "NAO"
    assert "REVISAR_CFOP_ST" == todos["T9"].value


def test_competencia_sem_itens_nao_exporta(tmp_path):
    with pytest.raises(ValueError, match="Nenhum item"):
        ServicoRelatorioLoteRTC2027(LocalFalso([])).gerar(
            CNPJ, COMPETENCIA, tmp_path / "sem.xlsx", regime="Lucro Real"
        )


def test_limite_visual_nao_trunca_relatorio(tmp_path):
    local = LocalFalso([item(i) for i in range(5002)])
    dados = ServicoRelatorioLoteRTC2027(local).preparar(
        CNPJ, COMPETENCIA, regime="Lucro Real"
    )
    assert dados["itens"] == 5002
    assert local.chamadas[0][2] is None
    assert dados["grupos"]["VENDA COMUM"] == 5002
    assert dados["revisar"] == 0


def test_inconsistencia_contagem_interrompe():
    class BancoInconsistente(LocalFalso):
        def contar_itens(self, cnpj, competencia):
            return len(self.itens) + 1

    with pytest.raises(ValueError, match="quantidade de itens mudou"):
        ServicoRelatorioLoteRTC2027(BancoInconsistente([item(1)])).preparar(
            CNPJ, COMPETENCIA, regime="Lucro Real"
        )
