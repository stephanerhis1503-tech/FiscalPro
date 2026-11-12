"""Regressoes para exclusao ICMS SAIDAS no Lucro Real nao cumulativo."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.sped.exclusor_icms_saidas_real import ExclusorICMSSaidasLucroReal

CNPJ = "12345678000190"
CHAVE = "31261012345678000190550010000000011000000011"


def reg(c):
    return "|" + "|".join(c) + "|\n"


def contrib(
    cst="01", base="100,00", icms_excluido=False,
    cfop="5102", pis="1,65", cofins="7,60",
    cod_inc="1", tipo_cont="1", credito_pis="0,00",
    credito_cofins="0,00", com_m=True,
):
    c100 = ["C100"] + [""] * 28
    c100[1], c100[4], c100[5], c100[8] = "1", "55", "00", CHAVE
    c100[25], c100[26] = pis, cofins
    c170 = ["C170"] + [""] * 35
    c170[1], c170[2], c170[6], c170[7], c170[10] = "1", "ABC", "100,00", "0,00", cfop
    c170[24], c170[25], c170[26], c170[29] = cst, base, "1,6500", pis
    c170[30], c170[31], c170[32], c170[35] = cst, base, "7,6000", cofins
    linhas = [
        reg(["0000", "006", "0", "", "", "01102026", "31102026",
             "MATRIZ", CNPJ, "MG", "3100000", "", "00", "0"]),
        reg(["0110", cod_inc, "", tipo_cont, ""]),
        reg(["C010", CNPJ]),
        reg(c100), reg(c170),
    ]
    if com_m:
        m200 = [
            "M200", "1,65", credito_pis, "0,00",
            f"{Decimal('1.65')-Decimal(credito_pis.replace(',', '.')):.2f}".replace(".", ","),
            "0,00", "0,00",
            f"{Decimal('1.65')-Decimal(credito_pis.replace(',', '.')):.2f}".replace(".", ","),
            "0,00", "0,00", "0,00", "0,00",
            f"{Decimal('1.65')-Decimal(credito_pis.replace(',', '.')):.2f}".replace(".", ","),
        ]
        m600 = [
            "M600", "7,60", credito_cofins, "0,00",
            f"{Decimal('7.60')-Decimal(credito_cofins.replace(',', '.')):.2f}".replace(".", ","),
            "0,00", "0,00",
            f"{Decimal('7.60')-Decimal(credito_cofins.replace(',', '.')):.2f}".replace(".", ","),
            "0,00", "0,00", "0,00", "0,00",
            f"{Decimal('7.60')-Decimal(credito_cofins.replace(',', '.')):.2f}".replace(".", ","),
        ]
        m210 = ["M210", "01", "100,00", "100,00", "0,00", "0,00",
                "100,00", "1,6500", "0,00", "0,00", "1,65",
                "0,00", "0,00", "0,00", "0,00", "1,65"]
        m610 = ["M610", "01", "100,00", "100,00", "0,00", "0,00",
                "100,00", "7,6000", "0,00", "0,00", "7,60",
                "0,00", "0,00", "0,00", "0,00", "7,60"]
        linhas.extend([
            reg(m200), reg(m210), reg([
                "M205", "08", "810902", m200[7]
            ]),
            reg(m600), reg(m610), reg([
                "M605", "08", "217201", m600[7]
            ]),
        ])
    return linhas


def fiscal(icms="18,00", valor="100,00", cnpj=CNPJ, com_item=True):
    c100 = ["C100"] + [""] * 28
    c100[1], c100[4], c100[5], c100[8] = "1", "55", "00", CHAVE
    c100[21] = icms
    c170 = ["C170"] + [""] * 20
    c170[1], c170[2], c170[6], c170[7], c170[10], c170[14] = (
        "1", "ABC", valor, "0,00", "5102", icms
    )
    c190 = ["C190", "000", "5102", "18,00", valor, valor, icms, "", "", "", "", ""]
    return [
        reg(["0000", "020", "0", "01102026", "31102026",
             "FILIAL", cnpj, "", "MG", "001", "3100000", "", "", "B", "1"]),
        reg(c100), reg(c170 if com_item else c190),
    ]


def analisar(tmp_path, contrib_lines=None, fiscal_lines=None):
    caminho = tmp_path / "fiscal.txt"
    caminho.write_text("".join(fiscal_lines or fiscal()), encoding="utf-8")
    return ExclusorICMSSaidasLucroReal().analisar(
        contrib_lines or contrib(), "EFD Contribuições", caminho
    )


def test_real_c170_icms_saida_aliquotas_basicas(tmp_path):
    r = analisar(tmp_path)
    assert r.pode_gerar
    assert len(r.ajustes) == 1
    assert r.icms == Decimal("18.00")
    assert r.pis == Decimal("0.30")
    assert r.cofins == Decimal("1.37")


def test_real_gera_copia_com_m210_m610_e_preserva_creditos(tmp_path):
    linhas = contrib(credito_pis="0,20", credito_cofins="1,00")
    origem = list(linhas)
    r = analisar(tmp_path, linhas)
    assert r.pode_gerar
    motor = ExclusorICMSSaidasLucroReal()
    motor.pre_validador = type(
        "SemErros", (), {"validar": lambda self, *args: SimpleNamespace(erros=[])}
    )()
    destino = tmp_path / "saida.txt"
    gerado = motor.gerar(linhas, "utf-8", "EFD Contribuições", r, destino)
    assert gerado.caminho_sped.exists()
    assert gerado.caminho_relatorio.exists()
    registros = {
        c[0]: c for c in (
            l.strip().split("|")[1:-1]
            for l in destino.read_text(encoding="utf-8").splitlines()
        )
    }
    assert registros["C170"][25] == "82,00"
    assert registros["C170"][31] == "82,00"
    assert registros["C170"][29] == "1,35"
    assert registros["C170"][35] == "6,23"
    assert registros["C100"][25] == "1,35"
    assert registros["M210"][2] == "100,00"  # receita bruta
    assert registros["M210"][3] == "82,00"   # base
    assert registros["M210"][10] == "1,35"
    assert registros["M610"][10] == "6,23"
    assert registros["M200"][2] == "0,20"  # credito preservado
    assert registros["M600"][2] == "1,00"
    assert registros["M200"][4] == "1,15"
    assert registros["M600"][4] == "5,23"
    assert linhas == origem
    with pytest.raises(FileExistsError):
        motor.gerar(linhas, "utf-8", "EFD Contribuições", r, destino)


@pytest.mark.parametrize("cod_inc", ["2", "3"])
def test_regimes_cumulativo_misto_nao_usam_motor_real(tmp_path, cod_inc):
    with pytest.raises(RuntimeError, match="NAO cumulativa"):
        analisar(tmp_path, contrib(cod_inc=cod_inc))


def test_aliquota_diferenciada_bloqueada(tmp_path):
    with pytest.raises(RuntimeError, match="diferenciadas"):
        analisar(tmp_path, contrib(tipo_cont="2"))


def test_outra_raiz_cnpj_bloqueada(tmp_path):
    with pytest.raises(RuntimeError, match="raizes diferentes"):
        analisar(tmp_path, fiscal_lines=fiscal(cnpj="99999999000199"))


def test_nao_excluir_duas_vezes(tmp_path):
    r = analisar(
        tmp_path, contrib(base="82,00", pis="1,35", cofins="6,23")
    )
    assert not r.pode_gerar
    assert len(r.ja_excluidos) == 1


def test_base_previamente_ajustada_bloqueia(tmp_path):
    r = analisar(tmp_path, contrib(base="95,00"))
    assert not r.pode_gerar
    assert any("outra exclusao" in x for x in r.revisar)


def test_cfop_nao_venda_bloqueia(tmp_path):
    r = analisar(tmp_path, contrib(cfop="5949"))
    assert not r.pode_gerar
    assert any("CFOP" in x for x in r.revisar)


def test_cst_mono_aliquota_zero_nao_gera_credito(tmp_path):
    r = analisar(
        tmp_path, contrib(cst="04", base="0,00", pis="0,00", cofins="0,00")
    )
    assert not r.pode_gerar
    assert not r.ajustes


def test_documento_fiscal_nao_conciliado_bloqueia(tmp_path):
    r = analisar(tmp_path, fiscal_lines=fiscal(valor="120,00"))
    assert not r.pode_gerar
    assert any("difere do Fiscal" in x for x in r.revisar)


def test_bloco_m_com_credito_superior_ao_saldo_bloqueia(tmp_path):
    r = analisar(
        tmp_path, contrib(credito_pis="1,50", credito_cofins="7,00")
    )
    assert not r.pode_gerar
    assert any("Bloco M" in x for x in r.revisar)


def test_nao_modifica_efd_com_creditos_se_analise_pendente(tmp_path):
    linhas = contrib(credito_pis="1,50", credito_cofins="7,00")
    r = analisar(tmp_path, linhas)
    destino = tmp_path / "proibido.txt"
    with pytest.raises(RuntimeError, match="REVISAR"):
        ExclusorICMSSaidasLucroReal().gerar(
            linhas, "utf-8", "EFD Contribuições", r, destino
        )
    assert not destino.exists()


def test_consolidado_c800_bloqueia(tmp_path):
    linhas = contrib()
    linhas.insert(5, reg(["C800", "65", "100,00"]))
    r = analisar(tmp_path, linhas)
    assert not r.pode_gerar
    assert any("consolidados" in x for x in r.revisar)


def test_c190_unico_so_com_conciliacao_total(tmp_path):
    r = analisar(tmp_path, fiscal_lines=fiscal(com_item=False))
    assert r.pode_gerar


def test_efd_contrib_alterada_apos_analise_nao_gera(tmp_path):
    linhas = contrib()
    r = analisar(tmp_path, linhas)
    assert r.pode_gerar
    with pytest.raises(RuntimeError, match="mudou"):
        ExclusorICMSSaidasLucroReal().gerar(
            linhas + [reg(["9999", "0"])], "utf-8",
            "EFD Contribuições", r, tmp_path / "saida.txt"
        )
