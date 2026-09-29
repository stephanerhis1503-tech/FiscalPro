from pathlib import Path

from src.sped.campos_oficiais_excel import (
    CAMPOS_EFD_CONTRIBUICOES,
    CAMPOS_EFD_FISCAL,
)
from src.sped.estatisticas import CalculadorEstatisticasSPED
from src.sped.exportador_excel import ExportadorSPEDExcel
from src.sped.indice import IndiceSPED
from src.sped.motor_sped import ResultadoSPED


def _resultado(linhas: list[str]) -> ResultadoSPED:
    indice = IndiceSPED().construir(linhas)
    estat = CalculadorEstatisticasSPED().calcular(linhas, indice)
    return ResultadoSPED(
        caminho=Path("teste.txt"),
        encoding="utf-8",
        linhas=linhas,
        indice=indice,
        estatisticas=estat,
        alertas=[],
        tempo_processamento=0.0,
    )


def test_efd_contribuicoes_usa_campos_tecnicos_exatos_no_c170():
    linhas = [
        "|0000|006|0|||01072026|31072026|EMPRESA TESTE|12345678000190|MG|3168606|||1|\n",
        "|C001|0|\n",
        "|C100|0|1|1|55|00|1|123|CHAVE|01072026|01072026|100,00|0|0|0|100,00|9|0|0|0|0|0|0|0|0|0|0|0|0|\n",
        "|C170|1|ABC|ITEM TESTE|1|UN|100,00|0|0|000|5102||100,00|18|18,00|0|0|0|0|99||0|0|0|50|100,00|1,6500|||1,65|50|100,00|7,6000|||7,60|1|\n",
    ]
    resultado = _resultado(linhas)
    assert resultado.estatisticas.tipo_sped == "EFD Contribuições"

    _, _, layouts, cabecalhos, _ = ExportadorSPEDExcel()._preparar_dados(resultado)
    qtd_ctx = len(layouts["C170"].contexto)
    proprios = cabecalhos["C170"][qtd_ctx:]

    assert proprios == list(CAMPOS_EFD_CONTRIBUICOES["C170"])
    assert proprios[24:30] == [
        "CST_PIS", "VL_BC_PIS", "ALIQ_PIS", "QUANT_BC_PIS", "ALIQ_PIS_QUANT", "VL_PIS"
    ]
    assert all(not nome.startswith("CAMPO_") for nome in proprios)


def test_mesmo_registro_tem_leiaute_diferente_no_fiscal_e_contribuicoes():
    # C170 Fiscal possui VL_ABAT_NT no fim; C170 da EFD-Contribuições não.
    assert CAMPOS_EFD_FISCAL["C170"][-1] == "VL_ABAT_NT"
    assert CAMPOS_EFD_CONTRIBUICOES["C170"][-1] == "COD_CTA"

    # 0200 Fiscal possui CEST; no leiaute da EFD-Contribuições usado pelo
    # FiscalPro o registro termina em ALIQ_ICMS.
    assert CAMPOS_EFD_FISCAL["0200"][-1] == "CEST"
    assert CAMPOS_EFD_CONTRIBUICOES["0200"][-1] == "ALIQ_ICMS"


def test_bloco_m_tem_nomes_reais_em_vez_de_campos_genericos():
    assert CAMPOS_EFD_CONTRIBUICOES["M100"][:8] == (
        "REG", "COD_CRED", "IND_CRED_ORI", "VL_BC_PIS", "ALIQ_PIS", "QUANT_BC_PIS",
        "ALIQ_PIS_QUANT", "VL_CRED",
    )
    assert CAMPOS_EFD_CONTRIBUICOES["M105"][5:7] == ("VL_BC_PIS_NC", "VL_BC_PIS")
    assert CAMPOS_EFD_CONTRIBUICOES["M500"][3:5] == ("VL_BC_COFINS", "ALIQ_COFINS")
    assert CAMPOS_EFD_CONTRIBUICOES["M505"][5:7] == ("VL_BC_COFINS_NC", "VL_BC_COFINS")



def test_c175_tem_campos_oficiais_e_nao_campos_genericos():
    assert CAMPOS_EFD_CONTRIBUICOES["C175"] == (
        "REG", "CFOP", "VL_OPR", "VL_DESC", "CST_PIS", "VL_BC_PIS",
        "ALIQ_PIS", "QUANT_BC_PIS", "ALIQ_PIS_QUANT", "VL_PIS",
        "CST_COFINS", "VL_BC_COFINS", "ALIQ_COFINS", "QUANT_BC_COFINS",
        "ALIQ_COFINS_QUANT", "VL_COFINS", "COD_CTA", "INFO_COMPL",
    )
    assert all(not nome.startswith("CAMPO_") for nome in CAMPOS_EFD_CONTRIBUICOES["C175"])

def test_registros_do_fluxo_atual_contribuicoes_estao_mapeados():
    registros = {
        "0000", "0001", "0100", "0110", "0140", "0150", "0190", "0200", "0400", "0450",
        "0500", "0990", "1001", "1990", "9001", "9900", "9990", "9999",
        "A001", "A010", "A100", "A170", "A990",
        "C001", "C010", "C100", "C110", "C170", "C175", "C990",
        "D001", "D010", "D100", "D101", "D105", "D990",
        "F001", "F990",
        "M001", "M100", "M105", "M200", "M210", "M400", "M410", "M500", "M505",
        "M600", "M610", "M800", "M810", "M990",
    }
    faltantes = sorted(registros - set(CAMPOS_EFD_CONTRIBUICOES))
    assert faltantes == []
