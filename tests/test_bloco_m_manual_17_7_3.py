from pathlib import Path

from openpyxl import load_workbook

from src.sped.exportador_excel import ExportadorSPEDExcel
from src.sped.importador_excel import ImportadorExcelSPED
from src.sped.motor_sped import MotorSPED


def _linhas_base():
    return [
        "|0000|006|0|||01072026|31072026|EMPRESA|51957099000155|MG||||2|",
        "|0001|0|",
        "|0110|1||1|9|",
        "|C001|0|",
        "|C010|51957099000155|2|",
        "|C100|0|1|FORN|55|00|1|1|CHAVE|01072026|01072026|100,00|0|0|0|100,00|0|0|0|0|0|0|0|0|0|1,65|7,60|0|0|",
        "|C170|1|ITEM||1,00000|UN|100,00|0,00|0|060|2102||100,00|0,00|0,00|0,00|0,00|0,00|0|50||100,00|0,00|0,00|50|100,00|1,6500|||1,65|50|100,00|7,6000|||7,60|1|",
        "|C990|4|",
        "|M001|0|",
        "|M100|101|0|100,00|1,6500|||1,65|0,00|0,00|0,00|1,65|0|1,65|0,00|",
        "|M105|01|50|100,00|0,00|100,00|100,00|",
        "|M200|1,65|1,65|0,00|1,65|0,00|0,00|1,65|0,00|0,00|0,00|0,00|1,65|",
        "|M500|101|0|100,00|7,6000|||7,60|0,00|0,00|0,00|7,60|0|7,60|0,00|",
        "|M505|01|50|100,00|0,00|100,00|100,00|",
        "|M600|7,60|7,60|0,00|7,60|0,00|0,00|7,60|0,00|0,00|0,00|0,00|7,60|",
        "|M990|7|",
        "|9001|0|",
        "|9990|2|",
        "|9999|19|",
    ]


def _exportar(tmp_path: Path) -> Path:
    txt = tmp_path / "base.txt"
    txt.write_text("\n".join(_linhas_base()) + "\n", encoding="utf-8")
    resultado = MotorSPED().abrir(txt)
    xlsx = tmp_path / "base.xlsx"
    ExportadorSPEDExcel().exportar(resultado, xlsx)
    return xlsx


def test_exclusao_manual_m100_m105_nao_e_mais_bloqueada(tmp_path):
    xlsx = _exportar(tmp_path)
    wb = load_workbook(xlsx)
    wb["M100"].delete_rows(2, 1)
    wb["M105"].delete_rows(2, 1)
    wb.save(xlsx)
    wb.close()

    resultado = ImportadorExcelSPED().validar(xlsx)

    assert resultado.modo_bloco_m_manual is True
    assert resultado.total_registros_bloco_m_removidos == 2
    assert not any("linha original não foi encontrada" in e.mensagem.lower() for e in resultado.erros)
    assert not any(linha.startswith("|M100|") for linha in resultado.linhas_geradas)
    assert not any(linha.startswith("|M105|") for linha in resultado.linhas_geradas)
    assert "|M990|6|" in resultado.linhas_geradas


def test_modo_manual_recalcula_credito_simples_ao_mudar_aliquota(tmp_path):
    xlsx = _exportar(tmp_path)
    wb = load_workbook(xlsx)
    ws = wb["M100"]
    headers = [ws.cell(1, col).value for col in range(1, ws.max_column + 1)]
    coluna_aliq = headers.index("ALIQ_PIS") + 1
    ws.cell(2, coluna_aliq).value = "0,6500"
    wb.save(xlsx)
    wb.close()

    resultado = ImportadorExcelSPED().validar(xlsx)

    assert resultado.modo_bloco_m_manual is True
    assert resultado.total_ajustes_automaticos_bloco_m > 0
    assert not resultado.erros
    m100 = next(linha for linha in resultado.linhas_geradas if linha.startswith("|M100|"))
    assert "|100,00|0,6500|||0,65|" in m100
    assert "|0,65|0|0,65|0,00|" in m100
