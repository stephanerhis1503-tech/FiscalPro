from pathlib import Path

from src.sped.corretor_assistido import CorretorAssistidoPVA
from src.sped.pre_validador import ApontamentoPVA, PreValidadorPVA, ResultadoPreValidacaoPVA


def _c170(cfop="1929", cod_item="1"):
    campos = [""] * 36
    campos[0] = "C170"
    campos[1] = "1"
    campos[2] = cod_item
    campos[4] = "6,87"
    campos[5] = "L"
    campos[6] = "42,87"
    campos[10] = cfop
    campos[24] = "98"
    campos[26] = "0,0000"
    campos[29] = "0,00"
    campos[30] = "98"
    campos[32] = "0,0000"
    campos[35] = "0,00"
    return "|" + "|".join(campos) + "|\n"


def _pre(linha=5):
    return ResultadoPreValidacaoPVA(
        tipo_sped="EFD Contribuições",
        total_linhas=5,
        apontamentos=[
            ApontamentoPVA(
                "ERRO", "CFOP PGE", "C170", linha,
                "CFOP 1929 rejeitado pelo PGE 6.1.2.",
                "Revisar o CFOP.", codigo_item="1", campo="CFOP",
            )
        ],
    )


def test_cfop_1929_gasolina_mesma_uf_vira_1653_automatico():
    linhas = [
        "|0000|006|0|||01072026|31072026|EMPRESA|12345678000100|MG|3168606||00|2|\n",
        "|0110|1|1|1||\n",
        "|0200|1|GASOLINA COMUM|||L|00|27101259||27||18,00|\n",
        "|C100|0|1|1072|55|00|1|12383|31260708058107000100550010000123831000927403|07072026|09072026|42,87|0|0,00|0,00|42,87|1|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|\n",
        _c170(),
    ]
    prep = CorretorAssistidoPVA().preparar(linhas, _pre())
    assert len(prep.propostas) == 1
    p = prep.propostas[0]
    assert p.valor_sugerido == "1653"
    assert p.modo == "Automática segura"
    assert p.segura is True
    assert p.selecionada is True


def test_cfop_1929_gasolina_outra_uf_vira_2653_automatico():
    linhas = [
        "|0000|006|0|||01072026|31072026|EMPRESA|12345678000100|MG|3168606||00|2|\n",
        "|0200|1|GASOLINA COMUM|||L|00|27101259||27||18,00|\n",
        "|C100|0|1|1072|55|00|1|12383|35260708058107000100550010000123831000927403|07072026|09072026|42,87|0|0,00|0,00|42,87|1|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|\n",
        _c170(),
    ]
    pre = _pre(linha=4)
    prep = CorretorAssistidoPVA().preparar(linhas, pre)
    assert prep.propostas[0].valor_sugerido == "2653"
    assert prep.propostas[0].segura is True


def test_cfop_1929_item_nao_combustivel_continua_manual():
    linhas = [
        "|0000|006|0|||01072026|31072026|EMPRESA|12345678000100|MG|3168606||00|2|\n",
        "|0200|1|CAPACETE|||UN|00|65061090||65||18,00|\n",
        "|C100|0|1|1072|55|00|1|12383|31260708058107000100550010000123831000927403|07072026|09072026|42,87|0|0,00|0,00|42,87|1|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|\n",
        _c170(),
    ]
    prep = CorretorAssistidoPVA().preparar(linhas, _pre(linha=4))
    p = prep.propostas[0]
    assert p.valor_sugerido == ""
    assert p.modo == "Preencher manualmente"
    assert p.selecionada is False


def test_pre_validador_nao_acusa_cfop_depois_de_1653():
    linhas = [
        "|0000|006|0|||01072026|31072026|EMPRESA|12345678000100|MG|3168606||00|2|\n",
        "|0110|1|1|1||\n",
        "|0200|1|GASOLINA COMUM|||L|00|27101259||27||18,00|\n",
        "|C100|0|1|1072|55|00|1|12383|31260708058107000100550010000123831000927403|07072026|09072026|42,87|0|0,00|0,00|42,87|1|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|\n",
        _c170(cfop="1653"),
    ]
    resultado = PreValidadorPVA().validar(linhas, "EFD Contribuições")
    assert not any(a.categoria == "CFOP PGE" for a in resultado.apontamentos)
