from dataclasses import dataclass
from decimal import Decimal

from src.sped.sincronizador_bloco_m_excel import SincronizadorBlocoMExcel


def linha(campos):
    return "|" + "|".join(campos) + "|"


def c170(cst_pis, base_pis, aliq_pis, cst_cofins="", base_cofins="", aliq_cofins=""):
    c = ["C170"] + [""] * 35
    c[24] = cst_pis
    c[25] = base_pis
    c[26] = aliq_pis
    c[30] = cst_cofins
    c[31] = base_cofins
    c[32] = aliq_cofins
    return linha(c)


@dataclass
class Ref:
    sequencia: int
    registro: str
    linha_original: str


def test_delta_credito_suporta_entrada_e_saida_do_cst_de_credito():
    sync = SincronizadorBlocoMExcel()
    antigo_1 = c170("01", "100,00", "1,6500")
    novo_1 = c170("50", "100,00", "1,6500")
    antigo_2 = c170("50", "40,00", "1,6500")
    novo_2 = c170("73", "0,00", "0,0000")
    refs = [Ref(1, "C170", antigo_1), Ref(2, "C170", antigo_2)]

    deltas, erros = sync._deltas_creditos_c170(
        refs, [novo_1, novo_2], {1: 0, 2: 1}
    )

    assert not erros
    assert deltas[("PIS", "1.6500", "50")] == Decimal("60.00")


def test_retotaliza_m400_m800_preservando_nat_rec():
    sync = SincronizadorBlocoMExcel()
    c100 = ["C100"] + [""] * 28
    c100[1] = "1"
    item = ["C170"] + [""] * 35
    item[6] = "125,50"
    item[24] = "04"
    item[30] = "04"
    linhas = [
        linha(c100),
        linha(item),
        "|M400|04|100,00|1||",
        "|M410|999|100,00|1||",
        "|M800|04|100,00|1||",
        "|M810|999|100,00|1||",
    ]

    ajustes, avisos = sync._retotalizar_m400_m800(linhas)

    assert not avisos
    assert "|M400|04|125,50|1||" in linhas
    assert "|M410|999|125,50|1||" in linhas
    assert "|M800|04|125,50|1||" in linhas
    assert "|M810|999|125,50|1||" in linhas
    assert len(ajustes) == 4
    assert all("999" in linhas[i] for i in (3, 5))
