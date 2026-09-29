from decimal import Decimal

from src.sped.corretor_assistido import CorretorAssistidoPVA
from src.sped.pre_validador import ApontamentoPVA, ResultadoPreValidacaoPVA
from src.sped.reapurador_bloco_m import ReapuradorBlocoM


def _c170(cst_pis="08", aliq_pis="0,0000", vl_pis="0,00", cst_cofins="08", aliq_cofins="0,0000", vl_cofins="0,00", cfop="2949"):
    campos = [""] * 36
    campos[0] = "C170"
    campos[1] = "1"
    campos[2] = "ITEM1"
    campos[6] = "100,00"
    campos[10] = cfop
    campos[24] = cst_pis
    campos[25] = "100,00" if cst_pis == "01" else "0,00"
    campos[26] = aliq_pis
    campos[29] = vl_pis
    campos[30] = cst_cofins
    campos[31] = "100,00" if cst_cofins == "01" else "0,00"
    campos[32] = aliq_cofins
    campos[35] = vl_cofins
    return "|" + "|".join(campos) + "|\n"


def test_cst_08_de_entrada_vira_74_automaticamente_em_lote():
    linhas = ["|0110|1|1|1||\n", _c170()]
    pre = ResultadoPreValidacaoPVA(
        tipo_sped="EFD Contribuições",
        total_linhas=len(linhas),
        apontamentos=[
            ApontamentoPVA("ERRO", "CST de entrada", "C170", 2, "CST inválido", campo="CST_PIS"),
            ApontamentoPVA("ERRO", "CST de entrada", "C170", 2, "CST inválido", campo="CST_COFINS"),
        ],
    )
    prep = CorretorAssistidoPVA().preparar(linhas, pre)
    assert len(prep.propostas) == 2
    assert all(p.valor_sugerido == "74" for p in prep.propostas)
    assert all(p.segura for p in prep.propostas)
    assert all(p.selecionada for p in prep.propostas)
    assert all(p.modo == "Automática segura" for p in prep.propostas)


def test_reapurar_bloco_m_por_delta_e_criar_cofins_quando_seguro():
    antes = [
        _c170("01", "0,0000", "0,00", "01", "0,0000", "0,00", "6102"),
        "|M001|0|\n",
        "|M200|10,00|0,00|0,00|10,00|0,00|0,00|10,00|0,00|0,00|0,00|0,00|10,00|\n",
        "|M210|01|606,06|606,06|0|0|606,06|1,6500|||10,00|0|0|0|0|10,00|\n",
        "|M990|4|\n",
    ]
    depois = list(antes)
    depois[0] = _c170("01", "1,6500", "1,65", "01", "7,6000", "7,60", "6102")

    r = ReapuradorBlocoM().sincronizar(antes, depois, "EFD Contribuições")
    m210 = next(l for l in r.linhas if l.startswith("|M210|"))
    m200 = next(l for l in r.linhas if l.startswith("|M200|"))
    m600 = next(l for l in r.linhas if l.startswith("|M600|"))
    m610 = next(l for l in r.linhas if l.startswith("|M610|"))

    assert "|706,06|706,06|" in m210
    assert m200.startswith("|M200|11,65|")
    assert "|706,06|706,06|" in m610
    assert "|7,6000|" in m610
    assert r.estrutura_alterada is True
    assert any(a.registro == "M600" for a in r.alteracoes)
    assert any(a.registro == "M610" for a in r.alteracoes)
