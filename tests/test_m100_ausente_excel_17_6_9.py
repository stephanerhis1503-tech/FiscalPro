from decimal import Decimal

import pytest

from src.sped.sincronizador_bloco_m_excel import SincronizadorBlocoMExcel


def linha(campos):
    return "|" + "|".join(campos) + "|"


def c170_credito(base: str) -> str:
    campos = ["C170"] + [""] * 35
    campos[10] = "1102"
    campos[24] = "50"
    campos[25] = base
    campos[26] = "1,6500"
    return linha(campos)


def test_reducao_credito_sem_m100_no_original_nao_cria_pai_e_nao_bloqueia():
    sync = SincronizadorBlocoMExcel()
    antes = [c170_credito("100,00")]
    atuais = list(antes)

    qtd, avisos = sync._sincronizar_creditos_assinados(
        atuais,
        antes,
        {("PIS", "1.6500", "50"): Decimal("-100.00")},
    )

    assert qtd == 0
    assert atuais == antes
    assert any("não possuía M100" in aviso for aviso in avisos)


def test_aumento_credito_sem_m100_continua_bloqueado():
    sync = SincronizadorBlocoMExcel()
    antes = [c170_credito("0,00")]
    atuais = list(antes)

    with pytest.raises(RuntimeError, match="não há M100.*aumentaria crédito"):
        sync._sincronizar_creditos_assinados(
            atuais,
            antes,
            {("PIS", "1.6500", "50"): Decimal("100.00")},
        )


def test_m100_existia_no_original_e_sumiu_na_reconstrucao_continua_bloqueado():
    sync = SincronizadorBlocoMExcel()
    pai = linha([
        "M100", "101", "0", "100,00", "1,6500", "", "", "1,65",
        "0,00", "0,00", "0,00", "1,65", "0", "1,65", "0,00",
    ])
    filho = linha(["M105", "02", "50", "100,00", "0,00", "100,00", "100,00", "", "", ""])
    antes = [c170_credito("100,00"), pai, filho]
    atuais = [c170_credito("100,00")]

    with pytest.raises(RuntimeError, match="SPED original possuía M100"):
        sync._sincronizar_creditos_assinados(
            atuais,
            antes,
            {("PIS", "1.6500", "50"): Decimal("-100.00")},
        )
