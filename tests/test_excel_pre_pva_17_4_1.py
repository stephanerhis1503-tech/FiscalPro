from pathlib import Path

from src.sped.importador_excel import ImportadorExcelSPED, ResultadoValidacaoExcel


def _base(corpo):
    return [
        "|0000|006|0|||01072026|31072026|EMPRESA|54304208000123|MG||||2|",
        "|0001|0|",
        "|0110|1||1|9|",
        "|0190|UN|Unidade|",
        "|0200|ITEM|ITEM TESTE|||UN|00|65061090||||0,00|",
        *corpo,
        "|9999|1|",
    ]


def _c170(cst_pis="50", aliq_pis="1,6500", cst_cofins="50", aliq_cofins="7,6000"):
    return (
        "|C170|1|ITEM||1,00000|UN|185,26|0,00|0|060|2102|NAT|185,26|12,00|22,23|"
        "0,00|18,00|0,00|0|50||185,26|0,00|0,00|"
        f"{cst_pis}|185,26|{aliq_pis}|||3,06|{cst_cofins}|185,26|{aliq_cofins}|||14,08|1|"
    )


def test_pre_pva_comparativo_nao_bloqueia_erro_que_ja_existia():
    # O 9999 propositalmente não fecha a quantidade real; esse erro já existe
    # no arquivo de origem e não deve ser atribuído à planilha sem alteração.
    originais = _base([_c170()])
    resultado = ResultadoValidacaoExcel(caminho=Path("teste.xlsx"))
    resultado.linhas_geradas = list(originais)

    ImportadorExcelSPED()._pre_validar_reconstrucao(resultado, originais)

    assert resultado.pre_pva_executado is True
    assert resultado.pre_pva_tipo_sped == "EFD Contribuições"
    assert resultado.pre_pva_erros_origem == resultado.pre_pva_erros_reconstruido
    assert resultado.pre_pva_novos_erros == 0
    assert resultado.valido is True


def test_pre_pva_comparativo_bloqueia_nova_pendencia_criada_no_excel():
    originais = _base([_c170()])
    reconstruidas = _base([_c170(cst_pis="01", aliq_pis="0,0000")])
    resultado = ResultadoValidacaoExcel(caminho=Path("teste.xlsx"))
    resultado.linhas_geradas = reconstruidas

    ImportadorExcelSPED()._pre_validar_reconstrucao(resultado, originais)

    assert resultado.pre_pva_novos_erros >= 1
    assert resultado.valido is False
    assert any(
        p.nivel == "ERRO" and "Pré-PVA criou nova pendência" in p.mensagem
        for p in resultado.problemas
    )


def test_identificacao_tipo_sped_no_pre_pva_comparativo():
    linhas_fiscal = [
        "|0000|020|0|01072026|31072026|EMPRESA|54304208000123||MG|IE|3168606|||B|1|",
        "|0001|0|",
        "|9999|3|",
    ]
    assert (
        ImportadorExcelSPED()._identificar_tipo_sped_linhas(linhas_fiscal)
        == "EFD ICMS/IPI (Fiscal)"
    )
