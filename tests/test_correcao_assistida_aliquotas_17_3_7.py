from pathlib import Path

from src.sped.corretor_assistido import CorretorAssistidoPVA
from src.sped.pre_validador import ApontamentoPVA, ResultadoPreValidacaoPVA


def _linhas():
    return [
        "|0000|006|0|||01072026|31072026|EMPRESA TESTE|54304208000123|MG|3168606||00|2|\n",
        "|0110|1|1|1||\n",
        "|C100|1|0|195|55|00|1|30476|31260754304208000123550010000304761897054690|02072026|02072026|185,26|0|0,00|0,00|185,26|1|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|0,00|\n",
        "|C170|1|203292||1,00|UN|185,26|0,00|0|060|6403|1070529377|185,26|12,00|22,23|0,00|18,00|0,00|0|50||185,26|0,00|0,00|01|185,26|0,0000|||0,00|01|185,26|0,0000|||0,00|1|\n",
    ]


def _pre():
    return ResultadoPreValidacaoPVA(
        tipo_sped="EFD Contribuições",
        total_linhas=4,
        apontamentos=[
            ApontamentoPVA(
                nivel="ERRO", categoria="Alíquota básica", registro="C170", numero_linha=4,
                mensagem="CST_PIS = 01 exige alíquota básica de 1,65% para o indicador 0110 atual.",
                sugestao="Preencher ALIQ_PIS com a alíquota básica da incidência do período.",
                codigo_item="203292", campo="ALIQ_PIS",
            ),
            ApontamentoPVA(
                nivel="ERRO", categoria="Alíquota básica", registro="C170", numero_linha=4,
                mensagem="CST_COFINS = 01 exige alíquota básica de 7,60% para o indicador 0110 atual.",
                sugestao="Preencher ALIQ_COFINS com a alíquota básica da incidência do período.",
                codigo_item="203292", campo="ALIQ_COFINS",
            ),
        ],
    )


def test_aliquotas_basicas_0110_viram_automaticas_seguras():
    preparacao = CorretorAssistidoPVA().preparar(_linhas(), _pre())
    por_campo = {p.campo: p for p in preparacao.propostas}
    assert por_campo["ALIQ_PIS"].valor_sugerido == "1,6500"
    assert por_campo["ALIQ_COFINS"].valor_sugerido == "7,6000"
    assert por_campo["ALIQ_PIS"].modo == "Automática segura"
    assert por_campo["ALIQ_COFINS"].modo == "Automática segura"
    assert por_campo["ALIQ_PIS"].selecionada is True
    assert por_campo["ALIQ_COFINS"].selecionada is True


def test_aplicar_aliquotas_recalcula_item_e_c100(tmp_path: Path):
    corretor = CorretorAssistidoPVA()
    linhas = _linhas()
    pre = _pre()
    preparacao = corretor.preparar(linhas, pre)
    destino = tmp_path / "corrigido.txt"
    resultado = corretor.aplicar(
        linhas, "utf-8", "EFD Contribuições", pre, preparacao, destino
    )
    novas = destino.read_text(encoding="utf-8").splitlines()
    c100 = novas[2].split("|")
    c170 = novas[3].split("|")
    assert c170[27] == "1,6500"
    assert c170[30] == "3,06"
    assert c170[33] == "7,6000"
    assert c170[36] == "14,08"
    assert c100[26] == "3,06"
    assert c100[27] == "14,08"
    assert resultado.total_aplicadas >= 6
