from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from src.sped.estatisticas import CalculadorEstatisticasSPED
from src.sped.exportador_excel import ExportadorSPEDExcel
from src.sped.importador_excel import ImportadorExcelSPED
from src.sped.indice import IndiceSPED
from src.sped.motor_sped import ResultadoSPED


def _resultado(linhas: list[str]) -> ResultadoSPED:
    indice = IndiceSPED().construir(linhas)
    estatisticas = CalculadorEstatisticasSPED().calcular(linhas, indice)
    return ResultadoSPED(
        caminho=Path("teste.txt"),
        encoding="utf-8",
        linhas=linhas,
        indice=indice,
        estatisticas=estatisticas,
        alertas=[],
        tempo_processamento=0.0,
    )


def test_17_7_7_precisao_tecnica_campos_principais():
    casas = ExportadorSPEDExcel._casas_decimais

    assert casas("QTD") == 5
    assert casas("VL_ITEM") == 2
    assert casas("VL_BC_PIS") == 2
    assert casas("ALIQ_ICMS") == 2
    assert casas("ALIQ_PIS") == 4
    assert casas("ALIQ_COFINS") == 4
    assert casas("QUANT_BC_PIS") == 3
    assert casas("QUANT_BC_COFINS") == 3
    assert casas("ALIQ_PIS_QUANT") == 4
    assert casas("ALIQ_COFINS_QUANT") == 4
    assert casas("QTD_LIN_M") == 0


def test_17_7_7_serializacao_excel_txt_reconstroi_casas_do_sped():
    fmt = ImportadorExcelSPED._formatar_decimal_sped

    assert fmt(Decimal("1"), "QTD") == "1,00000"
    assert fmt(Decimal("10.41"), "VL_BC_PIS") == "10,41"
    assert fmt(Decimal("18"), "ALIQ_ICMS") == "18,00"
    assert fmt(Decimal("0.65"), "ALIQ_PIS") == "0,6500"
    assert fmt(Decimal("3"), "ALIQ_COFINS") == "3,0000"
    assert fmt(Decimal("2"), "QUANT_BC_PIS") == "2,000"
    assert fmt(Decimal("0.12345"), "ALIQ_PIS_QUANT") == "0,1235"


def test_17_7_7_exportacao_aplica_formatos_visiveis_corretos(tmp_path):
    linhas = [
        "|0000|006|0|||01072026|31072026|EMPRESA|12345678000190|MG|3168606|||1|\n",
        "|C001|0|\n",
        "|C010|12345678000190|2|\n",
        "|C100|0|1|1|55|00|1|123|CHAVE|01072026|01072026|100,00|0|0,00|0,00|100,00|9|0,00|0,00|0,00|0,00|0,00||||0,00|0,00|0,00|0,00|\n",
        "|C170|1|ABC|ITEM|1,00000|UN|100,00|0,00|0|000|5102||100,00|18,00|18,00||||||||||99|10,41|0,6500|||0,07|99|10,41|3,0000|||0,31||\n",
        "|C175|5102|10,41|0,00|99|10,41|0,6500|||0,07|99|10,41|3,0000|||0,31|||\n",
        "|C990|4|\n",
        "|9999|8|\n",
    ]
    destino = tmp_path / "teste.xlsx"
    ExportadorSPEDExcel().exportar(_resultado(linhas), destino)

    wb = load_workbook(destino, data_only=False)
    try:
        ws_c170 = wb["C170 - Itens da Nota"]
        cab = {cell.value: cell.column for cell in ws_c170[1]}
        assert ws_c170.cell(2, cab["QTD"]).number_format == "#,##0.00000"
        assert ws_c170.cell(2, cab["VL_ITEM"]).number_format == "#,##0.00"
        assert ws_c170.cell(2, cab["ALIQ_PIS"]).number_format == "#,##0.0000"
        assert ws_c170.cell(2, cab["ALIQ_COFINS"]).number_format == "#,##0.0000"

        ws_c175 = wb["C175"] if "C175" in wb.sheetnames else wb["C175 - Analítico"]
        cab175 = {cell.value: cell.column for cell in ws_c175[1]}
        assert ws_c175.cell(2, cab175["ALIQ_PIS"]).number_format == "#,##0.0000"
        assert ws_c175.cell(2, cab175["VL_BC_PIS"]).number_format == "#,##0.00"
    finally:
        wb.close()


def test_17_7_7_celula_inalterada_preserva_texto_original_com_casas():
    # A comparação de equivalência deve continuar numérica para que uma célula
    # 0,65 exibida no Excel não marque alteração quando o original é 0,6500.
    assert ImportadorExcelSPED._valores_equivalentes(0.65, 0.65)
    original = "0,6500"
    esperado_excel = ExportadorSPEDExcel._valor_excel("ALIQ_PIS", original)
    assert esperado_excel == 0.65
