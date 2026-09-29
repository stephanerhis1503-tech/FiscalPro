from src.sped.corretor_assistido import CorretorAssistidoPVA
from src.sped.pre_validador import ApontamentoPVA, ResultadoPreValidacaoPVA
from src.sped.saneador_cod_item import SaneadorCODItem


def test_remove_copia_0200_integralmente_identica():
    linhas = [
        "|0200|1|GASOLINA COMUM|||L|00|27101259||27||18,00|\n",
        "|0200|1|GASOLINA COMUM|||L|00|27101259||27||18,00|\n",
        "|0400|1|VENDA|\n",
    ]
    saneador = SaneadorCODItem()
    planos = saneador.analisar(linhas)
    assert len(planos) == 1
    assert planos[0].linhas_remover == (2,)
    assert planos[0].renomeacoes == ()

    resultado = saneador.sanear(linhas)
    assert resultado.removidos == 1
    assert resultado.renomeados == 0
    assert sum(l.startswith("|0200|1|") for l in resultado.linhas) == 1


def test_preserva_produtos_diferentes_e_renomeia_o_segundo():
    linhas = [
        "|0200|ABC|CAPACETE BEGE|||UN|00|65061090||65||18,00|\n",
        "|0200|ABC|CAPACETE BRANCO|7890000000000||UN|00|65061090||65||18,00|\n",
    ]
    resultado = SaneadorCODItem().sanear(linhas)
    assert resultado.removidos == 0
    assert resultado.renomeados == 1
    assert resultado.linhas[0].startswith("|0200|ABC|CAPACETE BEGE|")
    assert resultado.linhas[1].startswith("|0200|ABC-D2|CAPACETE BRANCO|")


def test_duplicata_com_filhos_iguais_remove_bloco_inteiro():
    linhas = [
        "|0200|A|ITEM A|||UN|00|12345678||||0,00|\n",
        "|0205|ITEM ANTIGO|01012025|31012025||\n",
        "|0200|A|ITEM A|||UN|00|12345678||||0,00|\n",
        "|0205|ITEM ANTIGO|01012025|31012025||\n",
        "|0400|1|VENDA|\n",
    ]
    resultado = SaneadorCODItem().sanear(linhas)
    assert resultado.removidos == 1
    assert len([l for l in resultado.linhas if l.startswith("|0200|")]) == 1
    assert len([l for l in resultado.linhas if l.startswith("|0205|")]) == 1


def test_preparacao_substitui_varias_pendencias_por_uma_acao_em_lote():
    linhas = [
        "|0200|ABC|ITEM A|||UN|00|12345678||||0,00|\n",
        "|0200|ABC|ITEM B|||UN|00|12345678||||0,00|\n",
    ]
    pre = ResultadoPreValidacaoPVA(
        tipo_sped="EFD Contribuições",
        total_linhas=len(linhas),
        apontamentos=[
            ApontamentoPVA(
                "ERRO", "Duplicidade PGE", "0200", 1,
                "Duplicidade de ocorrência da chave COD_ITEM: ABC.",
                codigo_item="ABC", campo="COD_ITEM",
            ),
            ApontamentoPVA(
                "ERRO", "Duplicidade PGE", "0200", 2,
                "Duplicidade de ocorrência da chave COD_ITEM: ABC.",
                codigo_item="ABC", campo="COD_ITEM",
            ),
            ApontamentoPVA(
                "AVISO", "Coerência COD_ITEM", "0200", 1,
                "O COD_ITEM 'ABC' aparece 2 vezes no 0200.",
                codigo_item="ABC", campo="COD_ITEM",
            ),
        ],
    )
    prep = CorretorAssistidoPVA().preparar(linhas, pre)
    assert len(prep.propostas) == 1
    proposta = prep.propostas[0]
    assert proposta.tipo_acao == "SANEAR_COD_ITEM_DUPLICADO"
    assert proposta.segura is True
    assert proposta.selecionada is True
    assert "renomear 1" in proposta.valor_sugerido.lower()


def test_sufixo_nao_colide_com_codigo_ja_existente():
    linhas = [
        "|0200|ABC|ITEM A|||UN|00|12345678||||0,00|\n",
        "|0200|ABC|ITEM B|||UN|00|12345678||||0,00|\n",
        "|0200|ABC-D2|OUTRO ITEM|||UN|00|12345678||||0,00|\n",
    ]
    resultado = SaneadorCODItem().sanear(linhas)
    assert any(l.startswith("|0200|ABC-D3|ITEM B|") for l in resultado.linhas)
