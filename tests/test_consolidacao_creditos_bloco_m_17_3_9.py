from pathlib import Path

from src.sped.consolidador_creditos_bloco_m import ConsolidadorCreditosBlocoM
from src.sped.corretor_assistido import CorretorAssistidoPVA
from src.sped.pre_validador import ApontamentoPVA, ResultadoPreValidacaoPVA


def _linhas_m():
    return [
        "|M001|0|\n",
        "|M100|101|0|100,00|1,6500|||1,65|0,00|0,00|0,00|1,65|0|1,65|0,00|\n",
        "|M105|14|50|100,00|0,00|100,00|100,00||||\n",
        "|M100|101|0|50,00|0,6500|||0,33|0,00|0,00|0,00|0,33|0|0,33|0,00|\n",
        "|M105|02|50|50,00|0,00|50,00|50,00||||\n",
        "|M100|101|0|200,00|1,6500|||3,30|0,00|0,00|0,00|3,30|0|3,30|0,00|\n",
        "|M105|03|50|200,00|0,00|200,00|200,00||||\n",
        "|M500|101|0|100,00|7,6000|||7,60|0,00|0,00|0,00|7,60|0|7,60|0,00|\n",
        "|M505|14|50|100,00|0,00|100,00|100,00||||\n",
        "|M500|101|0|200,00|7,6000|||15,20|0,00|0,00|0,00|15,20|0|15,20|0,00|\n",
        "|M505|03|50|200,00|0,00|200,00|200,00||||\n",
        "|M990|12|\n",
    ]


def test_consolida_m100_m500_e_preserva_filhos():
    linhas = _linhas_m()
    c = ConsolidadorCreditosBlocoM()
    planos = c.analisar(linhas)
    assert len(planos) == 2

    r = c.consolidar(linhas, {2, 8})
    assert r.grupos_consolidados == 2
    assert len(r.linhas) == len(linhas) - 2

    m100 = [l for l in r.linhas if l.startswith("|M100|")]
    m500 = [l for l in r.linhas if l.startswith("|M500|")]
    assert len(m100) == 2
    assert len(m500) == 1
    assert "|300,00|1,6500|||4,95|" in m100[0]
    assert "|300,00|7,6000|||22,80|" in m500[0]

    # Os filhos dos dois pais de 1,65% ficam juntos no pai consolidado,
    # antes do crédito de 0,65%.
    i = r.linhas.index(m100[0])
    assert r.linhas[i + 1].startswith("|M105|14|50|")
    assert r.linhas[i + 2].startswith("|M105|03|50|")
    assert r.linhas[i + 3].startswith("|M100|101|0|50,00|0,6500|")


def test_preparacao_transforma_duplicidade_m_em_acao_automatica_unica():
    linhas = _linhas_m()
    pre = ResultadoPreValidacaoPVA(
        tipo_sped="EFD Contribuições",
        total_linhas=len(linhas),
        apontamentos=[
            ApontamentoPVA(
                "ERRO", "Duplicidade PGE", "M100", 2,
                "Duplicidade da chave COD_CRED/IND_CRED_ORI/ALIQ_PIS/ALIQ_PIS_QUANT no M100.",
                campo="COD_CRED/IND_CRED_ORI/ALIQ",
            ),
            ApontamentoPVA(
                "ERRO", "Duplicidade PGE", "M100", 6,
                "Duplicidade da chave COD_CRED/IND_CRED_ORI/ALIQ_PIS/ALIQ_PIS_QUANT no M100.",
                campo="COD_CRED/IND_CRED_ORI/ALIQ",
            ),
            ApontamentoPVA(
                "ERRO", "Duplicidade PGE", "M500", 8,
                "Duplicidade da chave COD_CRED/IND_CRED_ORI/ALIQ_COFINS/ALIQ_COFINS_QUANT no M500.",
                campo="COD_CRED/IND_CRED_ORI/ALIQ",
            ),
            ApontamentoPVA(
                "ERRO", "Duplicidade PGE", "M500", 10,
                "Duplicidade da chave COD_CRED/IND_CRED_ORI/ALIQ_COFINS/ALIQ_COFINS_QUANT no M500.",
                campo="COD_CRED/IND_CRED_ORI/ALIQ",
            ),
        ],
    )
    prep = CorretorAssistidoPVA().preparar(linhas, pre)
    assert len(prep.propostas) == 2
    assert all(p.tipo_acao == "CONSOLIDAR_CREDITO_M" for p in prep.propostas)
    assert all(p.segura and p.selecionada for p in prep.propostas)
    assert {p.registro for p in prep.propostas} == {"M100", "M500"}
