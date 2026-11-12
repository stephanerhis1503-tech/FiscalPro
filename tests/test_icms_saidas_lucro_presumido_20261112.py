"""Regressoes da exclusao de ICMS de SAIDAS no lucro presumido."""
from decimal import Decimal

import pytest

from src.sped.exclusor_icms_saidas_presumido import ExclusorICMSSaidasLucroPresumido


def reg(campos):
    return "|" + "|".join(campos) + "|\n"


CNPJ = "12345678000190"
CHAVE = "31261012345678000190550010000000011000000011"


def contrib(modo="2", com_f550=True, base="100,00", cfop="5102", cst="01"):
    linhas = [
        reg(["0000", "006", "0", "", "", "01102026", "31102026",
             "EMPRESA MATRIZ", CNPJ, "MG", "3100000", "", "00", "0"]),
        reg(["0110", "2", "", "1", modo]),
        reg(["F010", CNPJ]),
    ]
    if com_f550:
        linhas.append(reg([
            "F550", "100,00", cst, "0,00", base, "0,6500", "0,65",
            cst, "0,00", base, "3,0000", "3,00", "55", cfop,
            "CONTABIL", ""
        ]))
    return linhas


def fiscal(cfop="5102", icms="18,00", cnpj=CNPJ, valor="100,00"):
    c100 = ["C100"] + [""] * 29
    c100[1], c100[4], c100[5] = "1", "55", "00"
    c100[7], c100[8], c100[21] = "1", CHAVE, icms
    c190 = ["C190", "000", cfop, "18,00", valor, valor, icms, "", "", "", "", ""]
    return [
        reg(["0000", "020", "0", "01102026", "31102026", "FILIAL",
             cnpj, "", "MG", "001", "3100000", "", "", "B", "1"]),
        reg(c100), reg(c190)
    ]


def analisar(tmp_path, contribuicoes, f=None):
    arq = tmp_path / "fiscal.txt"
    arq.write_text("".join(f or fiscal()), encoding="utf-8")
    return ExclusorICMSSaidasLucroPresumido().analisar(
        contribuicoes, "EFD Contribuições", arq
    )


def test_f550_cumulativo_segregado_cst_basico(tmp_path):
    r = analisar(tmp_path, contrib())
    assert r.pode_gerar
    assert len(r.ajustes) == 1
    assert r.icms == Decimal("18.00")
    assert r.pis == Decimal("0.12")
    assert r.cofins == Decimal("0.54")


def test_lucro_presumido_nao_pode_usar_regime_nao_cumulativo(tmp_path):
    lines = contrib()
    lines[1] = reg(["0110", "1", "", "1", "2"])
    with pytest.raises(RuntimeError, match="cumulativa"):
        analisar(tmp_path, lines)


def test_bloqueia_outra_raiz_cnpj(tmp_path):
    with pytest.raises(RuntimeError, match="raiz"):
        analisar(tmp_path, contrib(), fiscal(cnpj="99999999000199"))


def test_bloqueia_cfop_fora_vendas_tributadas(tmp_path):
    r = analisar(tmp_path, contrib(cfop="5949"), fiscal(cfop="5949"))
    assert not r.pode_gerar
    assert r.revisar


def test_f500_regime_caixa_so_relatorio(tmp_path):
    r = analisar(tmp_path, contrib(modo="1", com_f550=False))
    assert not r.pode_gerar
    assert "F500" in " ".join(r.revisar)


def test_f550_nao_rateia_icms_em_csts_mistos(tmp_path):
    linhas = contrib()
    linhas.append(reg([
        "F550", "20,00", "04", "0,00", "0,00", "0,0000", "0,00",
        "04", "0,00", "0,00", "0,0000", "0,00", "55", "5102", "CONTABIL", ""
    ]))
    r = analisar(tmp_path, linhas)
    assert not r.pode_gerar
    assert any("CSTs/grupos distintos" in msg for msg in r.revisar)


def test_f550_base_ja_liquida_sem_comprovacao_nao_subtrai_duas_vezes(tmp_path):
    r = analisar(tmp_path, contrib(base="82,00"))
    assert not r.pode_gerar
    assert r.revisar


def test_f550_receita_divergente_bloqueia(tmp_path):
    r = analisar(tmp_path, contrib(), fiscal(valor="120,00"))
    assert not r.pode_gerar
    assert "diferente" in " ".join(r.revisar)


def test_geracao_bloqueada_com_pendencia(tmp_path):
    linhas = contrib(modo="1", com_f550=False)
    r = analisar(tmp_path, linhas)
    with pytest.raises(RuntimeError, match="pendencias"):
        ExclusorICMSSaidasLucroPresumido().gerar(
            linhas, "utf-8", "EFD Contribuições", r, tmp_path / "saida.txt"
        )
    assert not (tmp_path / "saida.txt").exists()


def test_gera_copia_f550_e_bloco_m_sem_alterar_receita_bruta(tmp_path):
    from types import SimpleNamespace

    linhas = contrib()
    m210 = ["M210", "51", "100,00", "100,00", "0,00", "0,00",
            "100,00", "0,6500", "", "", "0,65", "0,00",
            "0,00", "0,00", "0,00", "0,65"]
    m610 = ["M610", "51", "100,00", "100,00", "0,00", "0,00",
            "100,00", "3,0000", "", "", "3,00", "0,00",
            "0,00", "0,00", "0,00", "3,00"]
    m200 = ["M200", "0,00", "0,00", "0,00", "0,00", "0,00", "0,00",
            "0,00", "0,65", "0,00", "0,00", "0,65", "0,65"]
    m600 = ["M600", "0,00", "0,00", "0,00", "0,00", "0,00", "0,00",
            "0,00", "3,00", "0,00", "0,00", "3,00", "3,00"]
    linhas.extend([
        reg(m200), reg(m210), reg(["M205", "12", "810902", "0,65"]),
        reg(m600), reg(m610), reg(["M605", "12", "217201", "3,00"]),
    ])
    origem = list(linhas)
    analise = analisar(tmp_path, linhas)
    assert analise.pode_gerar
    motor = ExclusorICMSSaidasLucroPresumido()
    motor.pre_validador = type(
        "SemAlertas", (), {"validar": lambda self, *a: SimpleNamespace(erros=[])}
    )()
    destino = tmp_path / "ajustado.txt"
    gerado = motor.gerar(linhas, "utf-8", "EFD Contribuições", analise, destino)
    assert gerado.caminho_sped.exists()
    assert gerado.caminho_relatorio.exists()
    saida = destino.read_text(encoding="utf-8").splitlines()
    reg_saida = {linha.split("|")[1]: linha.split("|")[2:-1] for linha in saida}
    assert reg_saida["F550"][0] == "100,00"  # VL_REC_COMP preservada
    assert reg_saida["F550"][2] == "18,00"   # VL_DESC_PIS
    assert reg_saida["F550"][3] == "82,00"
    assert reg_saida["F550"][5] == "0,53"
    assert reg_saida["F550"][7] == "18,00"   # VL_DESC_COFINS
    assert reg_saida["F550"][8] == "82,00"
    assert reg_saida["F550"][10] == "2,46"
    assert reg_saida["M210"][1] == "100,00"  # VL_REC_BRT preservada
    assert reg_saida["M210"][2] == "82,00"
    assert reg_saida["M210"][9] == "0,53"
    assert reg_saida["M200"][7] == "0,53"
    assert reg_saida["M610"][1] == "100,00"
    assert reg_saida["M610"][9] == "2,46"
    assert reg_saida["M600"][7] == "2,46"
    assert linhas == origem

    with pytest.raises(FileExistsError):
        motor.gerar(linhas, "utf-8", "EFD Contribuições", analise, destino)
