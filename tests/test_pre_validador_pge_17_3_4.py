from src.sped.correcoes import AuditorCorrecoesSPED
from src.sped.pre_validador import PreValidadorPVA


def _base(corpo):
    return [
        "|0000|006|0|||01072026|31072026|EMPRESA|54304208000123|MG||||2|\n",
        "|0001|0|\n",
        "|0110|1||1|9|\n",
        "|0190|UN|Unidade|\n",
        "|0200|ITEM|ITEM TESTE|||UN|00|65061090||||0,00|\n",
        *corpo,
        "|9999|1|\n",
    ]


def test_pge_c170_aliquotas_basicas_e_cst_entrada():
    linhas = _base([
        "|C170|1|ITEM||1,00000|UN|185,26|0,00|0|060|6403|NAT|185,26|12,00|22,23|0,00|18,00|0,00|0|50||185,26|0,00|0,00|01|185,26|0,0000|||0,00|01|185,26|0,0000|||0,00|1|\n",
        "|C170|2|ITEM||1,00000|UN|93,62|0,00|0|090|2949|NAT|0,00|0,00|0,00|0,00|0,00|0,00|0|03||0,00|0,00|0,00|08|0,00|0,0000|||0,00|08|0,00|0,0000|||0,00|1|\n",
    ])

    resultado = PreValidadorPVA().validar(linhas, "EFD Contribuições")
    campos = {(a.categoria, a.campo) for a in resultado.erros}
    assert ("Alíquota básica", "ALIQ_PIS") in campos
    assert ("Alíquota básica", "ALIQ_COFINS") in campos
    assert ("CST de entrada", "CST_PIS") in campos
    assert ("CST de entrada", "CST_COFINS") in campos

    auditor = AuditorCorrecoesSPED()
    analise = auditor.analisar(linhas)
    automaticas = {(c.indice_campo, c.valor_novo) for c in analise.automaticas}
    assert (27, "1,6500") in automaticas
    assert (33, "7,6000") in automaticas
    assert (25, "74") in automaticas
    assert (31, "74") in automaticas


def test_pge_bloco_m_duplicidade_base_conta_e_filho():
    linhas = _base([
        "|M100|101|0|730864,80|1,6500|0,000||12059,27|0,00|0,00|0,00|12059,27|0|12059,27|0,00|\n",
        "|M105|14|50|155857,71|0,00|155857,71|155857,71||0,000||\n",
        "|M100|101|0|730864,80|1,6500|0,000||12059,27|0,00|0,00|0,00|12059,27|1|5907,01|6152,26|\n",
        "|M105|14|50|155857,71||155857,71|155857,71||0,000||\n",
        "|M400|08|11194,54|||\n",
        "|M500|101|0|730864,80|7,6000|0,000||55545,72|0,00|0,00|0,00|55545,72|0|55545,72|0,00|\n",
        "|M505|14|50|155857,71|0,00|155857,71|155857,71||0,000||\n",
        "|M500|101|0|730864,80|7,6000|0,000||55545,72|0,00|0,00|0,00|55545,72|1|27202,67|28343,05|\n",
        "|M505|14|50|155857,71||155857,71|155857,71||0,000||\n",
        "|M800|08|11194,54|||\n",
    ])
    resultado = PreValidadorPVA().validar(linhas, "EFD Contribuições")
    categorias = [a.categoria for a in resultado.erros]
    assert categorias.count("Duplicidade PGE") >= 4
    assert categorias.count("Base de crédito PGE") >= 4
    assert categorias.count("Conta contábil") == 2
    assert categorias.count("Hierarquia Bloco M") == 2


def test_0205_c175_e_ind_mov_reais():
    linhas = _base([
        "|0200|X|OUTRO ITEM|||UN|00|87141000||||0,00|\n",
        "|0205|DESCR ANTIGA|01012026|10082026||\n",
        "|A001|0|\n",
        "|A010|54304208000123|\n",
        "|A990|3|\n",
        "|C175|5102|110,00|0,00|49|19,80|0,6500|||0,13|49|16,24|3,0000|||0,49|||\n",
        "|D001|0|\n",
        "|D010|54304208000123|\n",
        "|D990|3|\n",
    ])
    resultado = PreValidadorPVA().validar(linhas, "EFD Contribuições")
    assert any(a.categoria == "Vigência 0205" and a.campo == "DT_FIM" for a in resultado.erros)
    assert any(a.categoria == "Base PIS/COFINS" for a in resultado.erros)
    # 17.8.82: A010/D010 são dados válidos dos blocos A/D e o PGE oficial
    # aceita IND_MOV=0 nesses cenários. A regra antiga gerava falso positivo.
    assert sum(1 for a in resultado.erros if a.categoria == "Movimento do bloco") == 0


def test_recalculo_encadeado_apos_corrigir_aliquota_cst01():
    from src.sped.recalculador_piscofins import RecalculadorPISCOFINS

    c100 = [""] * 30
    c100[0] = "C100"
    c100[25] = "0,00"
    c100[26] = "0,00"

    c170 = [""] * 37
    valores = {
        0: "C170", 1: "1", 2: "ITEM", 4: "1,00000", 5: "UN",
        6: "185,26", 7: "0,00", 8: "0", 9: "060", 10: "6403",
        11: "NAT", 12: "185,26", 13: "12,00", 14: "22,23", 15: "0,00",
        16: "18,00", 17: "0,00", 18: "0", 19: "50", 21: "185,26",
        22: "0,00", 23: "0,00", 24: "01", 25: "185,26", 26: "0,0000",
        29: "0,00", 30: "01", 31: "185,26", 32: "0,0000", 35: "0,00", 36: "1",
    }
    for indice, valor in valores.items():
        c170[indice] = valor

    linhas = _base([
        "|" + "|".join(c100) + "|\n",
        "|" + "|".join(c170) + "|\n",
    ])

    auditor = AuditorCorrecoesSPED()
    analise = auditor.analisar(linhas)
    corrigidas = auditor.aplicar_automaticas(linhas, analise)
    afetadas = {
        (c.numero_linha, "PIS" if c.indice_campo == 27 else "COFINS")
        for c in analise.automaticas
        if c.registro == "C170" and c.indice_campo in {27, 33}
    }
    resultado = RecalculadorPISCOFINS().recalcular(
        corrigidas, afetadas, "EFD CONTRIBUIÇÕES"
    )

    linha_c170 = next(l for l in resultado.linhas if l.startswith("|C170|"))
    campos_c170 = linha_c170.rstrip("\n").split("|")
    assert campos_c170[27] == "1,6500"
    assert campos_c170[30] == "3,06"
    assert campos_c170[33] == "7,6000"
    assert campos_c170[36] == "14,08"

    linha_c100 = next(l for l in resultado.linhas if l.startswith("|C100|"))
    campos_c100 = linha_c100.rstrip("\n").split("|")
    assert campos_c100[26] == "3,06"
    assert campos_c100[27] == "14,08"
    assert resultado.requer_reapuracao_bloco_m is True


def test_17_3_5_equivalencia_pge_sem_duplicar_tabela():
    linhas = _base([
        # COD_ITEM duplicado -> 2 erros de chave + 1 aviso consolidado.
        "|0200|DUP|ITEM A|||UN|00|65061090||||0,00|\n",
        "|0200|DUP|ITEM B|||UN|00|65061090||||0,00|\n",
        # CST 08 em entrada: duas causas raiz, mas o PGE repete as duas regras
        # e ainda cria M400/M410/M800/M810 na apuração.
        "|C170|1|ITEM||1,00000|UN|93,62|0,00|0|090|2949|NAT|0,00|0,00|0,00|0,00|0,00|0,00|0|03||0,00|0,00|0,00|08|0,00|0,0000|||0,00|08|0,00|0,0000|||0,00|1|\n",
        # Chaves M100/M500 duplicadas com três filhos por tributo, padrão que
        # no gabarito real gerou 8 erros de base por tributo.
        "|M100|101|0|10,00|1,6500|||0,17|0,00|0,00|0,00|0,17|0|0,17|0,00|\n",
        "|M105|14|50|10,00|0,00|10,00|10,00||||\n",
        "|M100|101|0|20,00|1,6500|||0,33|0,00|0,00|0,00|0,33|0|0,33|0,00|\n",
        "|M105|03|50|5,00|0,00|5,00|5,00||||\n",
        "|M105|02|50|15,00|0,00|15,00|15,00||||\n",
        "|M500|101|0|10,00|7,6000|||0,76|0,00|0,00|0,00|0,76|0|0,76|0,00|\n",
        "|M505|14|50|10,00|0,00|10,00|10,00||||\n",
        "|M500|101|0|20,00|7,6000|||1,52|0,00|0,00|0,00|1,52|0|1,52|0,00|\n",
        "|M505|03|50|5,00|0,00|5,00|5,00||||\n",
        "|M505|02|50|15,00|0,00|15,00|15,00||||\n",
    ])

    resultado = PreValidadorPVA().validar(linhas, "EFD Contribuições")
    # A tabela mantém causas únicas e o resumo calcula as ocorrências que o PGE
    # tende a mostrar após repetir regras e gerar cascatas.
    assert resultado.erros_pge_estimados > len(resultado.erros)
    assert resultado.equivalencia_pge["Repetições da regra de CST de entrada no PGE"] == 2
    assert resultado.equivalencia_pge["Pendências encadeadas de base M105/M505"] == 16
    assert resultado.equivalencia_pge["Pendências encadeadas M400/M410/M800/M810"] == 4
    assert sum(1 for a in resultado.avisos if a.categoria == "Coerência COD_ITEM") == 1
