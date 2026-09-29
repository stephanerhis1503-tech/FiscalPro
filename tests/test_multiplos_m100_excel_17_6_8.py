from decimal import Decimal

from src.sped.sincronizador_bloco_m_excel import SincronizadorBlocoMExcel


def linha(campos):
    return "|" + "|".join(campos) + "|"


def a170(base: str) -> str:
    campos = ["A170"] + [""] * 15
    campos[8] = "50"
    campos[9] = base
    campos[10] = "1,6500"
    return linha(campos)


def c170(base: str) -> str:
    campos = ["C170"] + [""] * 35
    campos[10] = "1102"
    campos[24] = "50"
    campos[25] = base
    campos[26] = "1,6500"
    return linha(campos)


def d101(base: str) -> str:
    campos = ["D101"] + [""] * 7
    campos[3] = "50"
    campos[5] = base
    campos[6] = "1,6500"
    return linha(campos)


def m100(cod_cred: str, base: str) -> str:
    credito = (Decimal(base.replace(",", ".")) * Decimal("0.0165")).quantize(Decimal("0.01"))
    cr = f"{credito:.2f}".replace(".", ",")
    return linha(["M100", cod_cred, "0", base, "1,6500", "", "", cr, "0,00", "0,00", "0,00", cr, "0", cr, "0,00"])


def m105(nat: str, base: str) -> str:
    return linha(["M105", nat, "50", base, "0,00", base, base, "", "", ""])


def test_multiplos_m100_mesma_aliquota_identifica_pai_pelo_filho_c170():
    sync = SincronizadorBlocoMExcel()
    antes = [
        a170("147454,11"),
        c170("217708,88"),
        d101("108875,00"),
        m100("201", "108875,00"),
        m105("14", "108875,00"),
        m100("101", "365162,99"),
        m105("03", "147454,11"),
        m105("02", "217708,88"),
    ]
    atuais = list(antes)
    pais = sync.exclusor._mapear_pais_bloco_m(atuais, "M100", "M105")

    resolvido = sync._identificar_pai_e_filho_credito(
        linhas_antes=antes,
        linhas_atuais=atuais,
        pais=pais,
        tributo="PIS",
        taxa="1.6500",
        cst="50",
        base_c170=Decimal("217708.88"),
    )

    assert resolvido is not None
    linha_pai, _filhos, linha_child = resolvido
    assert linha_pai == 6
    assert linha_child == 8
    assert sync.exclusor._campo_linha(atuais[linha_child - 1], 1) == "02"


def test_multiplos_m100_mesma_aliquota_nao_chuta_quando_filhos_sao_indistinguiveis():
    sync = SincronizadorBlocoMExcel()
    antes = [
        c170("100000,00"),
        m100("101", "100000,00"),
        m105("02", "100000,00"),
        m100("201", "100000,00"),
        m105("02", "100000,00"),
    ]
    atuais = list(antes)
    pais = sync.exclusor._mapear_pais_bloco_m(atuais, "M100", "M105")

    resolvido = sync._identificar_pai_e_filho_credito(
        linhas_antes=antes,
        linhas_atuais=atuais,
        pais=pais,
        tributo="PIS",
        taxa="1.6500",
        cst="50",
        base_c170=Decimal("100000.00"),
    )

    assert resolvido is None


def test_pai_unico_continua_funcionando():
    sync = SincronizadorBlocoMExcel()
    antes = [
        c170("100000,00"),
        m100("101", "100000,00"),
        m105("02", "100000,00"),
    ]
    atuais = list(antes)
    pais = sync.exclusor._mapear_pais_bloco_m(atuais, "M100", "M105")

    resolvido = sync._identificar_pai_e_filho_credito(
        linhas_antes=antes,
        linhas_atuais=atuais,
        pais=pais,
        tributo="PIS",
        taxa="1.6500",
        cst="50",
        base_c170=Decimal("100000.00"),
    )

    assert resolvido is not None
    assert resolvido[0] == 2
    assert resolvido[2] == 3
