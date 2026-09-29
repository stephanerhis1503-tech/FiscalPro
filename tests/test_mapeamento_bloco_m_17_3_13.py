from __future__ import annotations

from src.sped.exclusor_icms_creditos_piscofins import ExclusorICMSCreditosPISCOFINS


def linha(campos: list[str]) -> str:
    return "|" + "|".join(campos) + "|\n"


def a170(base: str) -> str:
    campos = ["A170"] + [""] * 15
    campos[8] = "50"
    campos[9] = base
    campos[10] = "1,6500"
    campos[12] = "50"
    campos[13] = base
    campos[14] = "7,6000"
    return linha(campos)


def c170(base: str) -> str:
    campos = ["C170"] + [""] * 35
    campos[24] = "50"
    campos[25] = base
    campos[26] = "1,6500"
    campos[30] = "50"
    campos[31] = base
    campos[32] = "7,6000"
    return linha(campos)


def d101(base: str) -> str:
    campos = ["D101"] + [""] * 7
    campos[3] = "50"
    campos[5] = base
    campos[6] = "1,6500"
    return linha(campos)


def m105(nat: str, base: str) -> str:
    return linha(["M105", nat, "50", base, "0,00", base, base, "", "", ""])


def test_identifica_m105_c170_por_origem_quando_comparacao_direta_falha():
    exclusor = ExclusorICMSCreditosPISCOFINS()

    # A170 e D101 fecham exatamente com dois filhos; o filho restante pertence
    # ao C170. A diferença de R$ 800 no filho C é grande o bastante para a
    # heurística antiga por base isolada bloquear (> R$ 500), mas pequena no
    # contexto da composição global do crédito (0,5%).
    antes = [
        a170("90000,00"),
        c170("100000,00"),
        d101("150000,00"),
        m105("03", "90000,00"),
        m105("02", "100800,00"),
        m105("14", "150000,00"),
    ]
    atuais = list(antes)
    filhos = [4, 5, 6]

    assert exclusor._escolher_child_por_base(atuais, filhos, exclusor._decimal("100000,00")) is None
    escolhido = exclusor._escolher_child_por_origem_documental(
        antes, atuais, filhos, "PIS", "1.6500", "50"
    )
    assert escolhido == 5


def test_nao_identifica_m105_por_origem_quando_composicao_global_nao_fecha():
    exclusor = ExclusorICMSCreditosPISCOFINS()
    antes = [
        a170("100000,00"),
        c170("100000,00"),
        d101("100000,00"),
        m105("03", "100000,00"),
        m105("02", "130000,00"),
        m105("14", "100000,00"),
    ]
    atuais = list(antes)
    escolhido = exclusor._escolher_child_por_origem_documental(
        antes, atuais, [4, 5, 6], "PIS", "1.6500", "50"
    )
    assert escolhido is None


def test_identifica_m505_c170_com_a170_e_d105():
    exclusor = ExclusorICMSCreditosPISCOFINS()
    a = a170("90000,00")
    c = c170("100000,00")
    campos_d = ["D105"] + [""] * 7
    campos_d[3] = "50"
    campos_d[5] = "150000,00"
    campos_d[6] = "7,6000"
    d = linha(campos_d)
    atuais = [
        a,
        c,
        d,
        linha(["M505", "03", "50", "90000,00", "0,00", "90000,00", "90000,00", "", "", ""]),
        linha(["M505", "02", "50", "100800,00", "0,00", "100800,00", "100800,00", "", "", ""]),
        linha(["M505", "14", "50", "150000,00", "0,00", "150000,00", "150000,00", "", "", ""]),
    ]
    escolhido = exclusor._escolher_child_por_origem_documental(
        atuais, atuais, [4, 5, 6], "COFINS", "7.6000", "50"
    )
    assert escolhido == 5
