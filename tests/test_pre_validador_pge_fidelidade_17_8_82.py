from collections import defaultdict
from decimal import Decimal

from src.sped.pre_validador import PreValidadorPVA, ResultadoPreValidacaoPVA, _Registro


def _preparar_validador(tipo="EFD Contribuições"):
    validador = PreValidadorPVA()
    validador._resultado = ResultadoPreValidacaoPVA(tipo_sped=tipo, total_linhas=0)
    validador._chaves_apontamentos = set()
    return validador


def test_a010_d010_contam_como_dados_para_ind_mov_zero():
    validador = _preparar_validador()
    registros = validador._ler_registros([
        "|A001|0|\n",
        "|A010|11809691000195|\n",
        "|A990|3|\n",
        "|D001|0|\n",
        "|D010|11809691000195|\n",
        "|D990|3|\n",
    ])
    por_codigo = defaultdict(list)
    for registro in registros:
        por_codigo[registro.codigo].append(registro)

    validador._validar_indicadores_movimento(por_codigo)

    assert not [
        item for item in validador._resultado.erros
        if item.categoria == "Movimento do bloco"
    ]


def test_bloco_sem_qualquer_dado_ainda_e_inconsistente():
    validador = _preparar_validador()
    registros = validador._ler_registros(["|A001|0|\n", "|A990|2|\n"])
    por_codigo = defaultdict(list)
    for registro in registros:
        por_codigo[registro.codigo].append(registro)

    validador._validar_indicadores_movimento(por_codigo)

    assert len(validador._resultado.erros) == 1
    assert validador._resultado.erros[0].campo == "IND_MOV"


def test_diferenca_c100_c170_pode_ser_revisao_sem_virar_erro_pge():
    validador = _preparar_validador("EFD Contribuições")
    campos = [""] * 29
    campos[0] = "C100"
    campos[15] = "2065,87"
    registro = _Registro(9342, "C100", tuple(campos), "")

    validador._comparar_total_com_nivel(
        registro,
        15,
        Decimal("2053.40"),
        "VL_MERC",
        "Nº 5069",
        "soma dos C170",
        nivel="REVISAO",
    )

    resultado = validador._resultado
    assert len(resultado.erros) == 0
    assert len(resultado.avisos) == 0
    assert len(resultado.revisoes) == 1
    assert resultado.revisoes[0].nivel == "REVISÃO FISCALPRO"
    assert resultado.revisoes[0].campo == "VL_MERC"
    assert resultado.aprovado is True


def test_revisao_fiscalpro_nao_entra_na_equivalencia_pge():
    validador = _preparar_validador("EFD Contribuições")
    validador._revisao(
        "Totais do documento", "C100", 10,
        "Diferença para conferência interna.", campo="VL_MERC"
    )
    validador._calcular_equivalencia_pge([], defaultdict(list))

    resultado = validador._resultado
    assert resultado.erros_pge_estimados == 0
    assert resultado.avisos_pge_estimados == 0
    assert len(resultado.revisoes) == 1
