"""Cruzamento deterministico e conservador do SPED Fiscal com o RTC."""
from openpyxl import load_workbook
import pytest

from src.services.rtc_destinacao_efd_service import ler_efd_icms_ipi
from src.services.rtc_relatorio_lote_2027_service import ServicoRelatorioLoteRTC2027

CNPJ = "11809691000195"
CHAVE_A = "31" + "2610" + "11809691000195" + "55" + "001" + "000000021" + "1" + "12345678" + "9"
CHAVE_B = "31" + "2610" + "11809691000195" + "55" + "001" + "000029761" + "1" + "87654321" + "0"
assert len(CHAVE_A) == len(CHAVE_B) == 44


def criar_efd(tmp_path, *, cnpj=CNPJ, competencia="2026-10"):
    inicio = "01" + competencia[5:7] + competencia[:4]
    fim = "31" + competencia[5:7] + competencia[:4]
    dados = [
        f"|0000|019|0|{inicio}|{fim}|EMPRESA|{cnpj}|",
        f"|C100|0|1|1|55|00|1|21|{CHAVE_A}|",
        "|C170|1|PROD01|Produto|1|UN|10|0|0|060|1556|",
        "|C170|2|PROD02|Produto|1|UN|20|0|0|060|2556|",
        f"|C100|0|1|1|55|00|1|29761|{CHAVE_B}|",
        "|C170|1|PROD03|Produto|1|UN|30|0|0|060|1102|",
    ]
    caminho = tmp_path / "sped_fiscal.txt"
    caminho.write_text("\n".join(dados), encoding="utf-8")
    return caminho


def item(chave, num, *, direcao="ENTRADA"):
    return {
        "chave_nfe": chave, "numero_nf": "21", "numero_item": str(num),
        "direcao": direcao, "cfop": "5102", "base_ibs_cbs": "10.00",
        "cst_ibscbs": "000", "cclass_trib": "000001",
        "status_auditoria": "REVISAR", "motivos": "Sem grupo IBS/CBS",
        "descricao": "Produto", "ncm": "12345678", "emissao": "2026-10-01",
    }


def test_cfop_efd_confirmado_sem_usar_cfop_fornecedor(tmp_path):
    mapa = ler_efd_icms_ipi(
        criar_efd(tmp_path), cnpj_esperado=CNPJ, competencia_esperada="2026-10"
    )
    assert mapa.localizar(item(CHAVE_A, 1)) == {
        "cfop_entrada": "1556",
        "destinacao": "USO E CONSUMO (CFOP EFD)",
        "situacao": "CHAVE + ITEM CONFERIDOS NO SPED",
    }
    assert mapa.localizar(item(CHAVE_A, 2))["cfop_entrada"] == "2556"
    assert mapa.localizar(item(CHAVE_B, 1))["destinacao"] == "REVENDA (CFOP EFD)"
    assert mapa.localizar(item(CHAVE_A, 7))["destinacao"] == "A CONFERIR"
    assert mapa.localizar(item("9" * 44, 1))["destinacao"] == "A CONFERIR"
    assert mapa.localizar(item(CHAVE_A, 1, direcao="SAIDA"))["cfop_entrada"] == ""


@pytest.mark.parametrize("cnpj,competencia", [
    ("00000000000000", "2026-10"), (CNPJ, "2026-11"),
])
def test_arquivo_outra_empresa_periodo_bloqueado(tmp_path, cnpj, competencia):
    with pytest.raises(ValueError):
        ler_efd_icms_ipi(
            criar_efd(tmp_path), cnpj_esperado=cnpj, competencia_esperada=competencia
        )


def test_duplo_cfop_no_mesmo_item_fica_pendente(tmp_path):
    caminho = criar_efd(tmp_path)
    caminho.write_text(
        caminho.read_text() + "\n|C170|1|PROD04|Produto|1|UN|10|0|0|060|1556|\n",
        encoding="utf-8",
    )
    mapa = ler_efd_icms_ipi(
        caminho, cnpj_esperado=CNPJ, competencia_esperada="2026-10"
    )
    assert mapa.localizar(item(CHAVE_B, 1))["situacao"].startswith("CFOP DIVERGENTE")
    assert mapa.localizar(item(CHAVE_B, 1))["destinacao"] == "A CONFERIR"


def test_excel_destinacao_apenas_com_sped_fiscal_correspondente(tmp_path):
    class Falso:
        itens = [item(CHAVE_A, 1), item(CHAVE_A, 7), item(CHAVE_B, 1)]
        def listar_itens(self, cnpj, comp, *, limite=None):
            return self.itens
        def contar_itens(self, cnpj, comp):
            return len(self.itens)

    svc = ServicoRelatorioLoteRTC2027(Falso())
    caminho_sped = criar_efd(tmp_path)
    sem = svc.preparar(CNPJ, "2026-10", regime="Lucro Real")
    assert all(l["destinacao"] == "A CONFERIR" for l in sem["linhas"])
    com = svc.preparar(
        CNPJ, "2026-10", regime="Lucro Real", arquivo_sped_fiscal=caminho_sped
    )
    assert com["destinacoes"]["USO E CONSUMO (CFOP EFD)"] == 1
    assert com["destinacoes"]["A CONFERIR"] == 1
    assert com["destinacoes"]["REVENDA (CFOP EFD)"] == 1
    assert com["linhas"][0]["item"]["cfop"] == "5102"
    assert com["linhas"][0]["cfop_entrada"] == "1556"
    assert com["linhas"][0]["simulacao"]["efeito_fiscal"] is False
    caminho = svc.gerar(
        CNPJ, "2026-10", tmp_path / "vinculo.xlsx",
        regime="Lucro Real", arquivo_sped_fiscal=caminho_sped
    )
    wb = load_workbook(caminho)
    ws = wb["Alertas XML"]
    assert ws["Z8"].value == "1556"
    assert ws["AA8"].value == "USO E CONSUMO (CFOP EFD)"
    assert ws["AB8"].value == "CHAVE + ITEM CONFERIDOS NO SPED"
    assert wb["Resumo"]["E21"].value == 1
    assert wb["Resumo"]["E24"].value == 1
    assert wb["Resumo"]["B34"].value == "sped_fiscal.txt"
