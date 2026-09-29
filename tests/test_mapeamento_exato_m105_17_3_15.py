from decimal import Decimal

from src.sped.exclusor_icms_creditos_piscofins import ExclusorICMSCreditosPISCOFINS


def linha(campos):
    return "|" + "|".join(campos) + "|\n"


def c170(cfop, base, cst="50", aliq="1,6500"):
    c = ["C170"] + [""] * 36
    c[10] = cfop
    c[24] = cst
    c[25] = base
    c[26] = aliq
    c[30] = cst
    c[31] = base
    c[32] = "7,6000"
    return linha(c)


def test_fonte_segura_separa_compras_revenda_de_outros_c170_mesmo_cst():
    ex = ExclusorICMSCreditosPISCOFINS()
    linhas = [
        c170("1102", "200000,00"),
        c170("2102", "238899,98"),
        c170("2202", "21161,56"),
    ]
    grupos = ex._agrupar_bases_c170_fonte_segura(linhas, "PIS")
    assert grupos[("1.6500", "50")] == Decimal("438899.98")


def test_m100_quantidade_zero_nao_bloqueia_credito_por_aliquota():
    ex = ExclusorICMSCreditosPISCOFINS()
    # QUANT_BC_PIS = 0 e ALIQ_PIS_QUANT vazia: representação válida de crédito por alíquota.
    m100 = linha(["M100", "101", "0", "706083,83", "1,65", "0", "", "11650,38", "0", "0", "0", "11650,38", "0", "11650,38", "0"])
    ex._validar_pai_credito_simples(m100, "M100", 1)


def test_m205_unico_acompanha_novo_total_m200_quando_espelhava_total_anterior():
    ex = ExclusorICMSCreditosPISCOFINS()
    linhas = [
        linha(["M100", "101", "0", "100,00", "1,65", "0", "", "1,65", "0", "0", "0", "1,65", "0", "1,65", "0"]),
        linha(["M200", "10,00", "1,65", "0", "8,35", "0", "0", "8,35", "0", "0", "0", "0", "8,35"]),
        linha(["M205", "12", "691201", "8,35"]),
    ]
    # Recalcula usando o M100 como crédito simples; o detalhe deve espelhar o novo total.
    ex._recalcular_consolidacao(linhas, "PIS", "M100", "M200")
    assert ex._decimal(ex._campo_linha(linhas[2], 3)) == ex._decimal(ex._campo_linha(linhas[1], 12))
