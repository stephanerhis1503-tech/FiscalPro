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
        # Grupo antigo que será removido; o filho será reaproveitado.
        "|M100|101|0|50,00|0,6500|||0,33|0,00|0,00|0,00|0,33|0|0,33|0,00|",
        "|M105|01|50|50,00|0,00|50,00|50,00|",
        # Grupo sobrevivente.
        "|M100|101|0|100,00|1,6500|||1,65|0,00|0,00|0,00|1,65|0|1,65|0,00|",
        "|M105|01|50|100,00|0,00|100,00|100,00|",
        "|M200|1,65|1,65|0,00|1,65|0,00|0,00|1,65|0,00|0,00|0,00|0,00|1,65|",
        "|M500|101|0|50,00|3,0000|||1,50|0,00|0,00|0,00|1,50|0|1,50|0,00|",
        "|M505|01|50|50,00|0,00|50,00|50,00|",
        "|M500|101|0|100,00|7,6000|||7,60|0,00|0,00|0,00|7,60|0|7,60|0,00|",
        "|M505|01|50|100,00|0,00|100,00|100,00|",
        "|M600|7,60|7,60|0,00|7,60|0,00|0,00|7,60|0,00|0,00|0,00|0,00|7,60|",
        "|M990|11|",
        "|9001|0|",
        "|9990|2|",
        "|9999|23|",
    ]


def _exportar(tmp_path: Path) -> Path:
    txt = tmp_path / "base.txt"
    txt.write_text("\n".join(_linhas_base()) + "\n", encoding="utf-8")
    resultado = MotorSPED().abrir(txt)
    xlsx = tmp_path / "base.xlsx"
    ExportadorSPEDExcel().exportar(resultado, xlsx)
    return xlsx


def _alterar_base_filho(ws, linha: int, valor: float) -> None:
    cabecalhos = {str(c.value): c.column for c in ws[1]}
    # Campo oficial do registro M105/M505 usado como base efetiva do crédito.
    # O exportador pode usar o nome específico de PIS ou COFINS.
    coluna = cabecalhos.get("VL_BC_PIS") or cabecalhos.get("VL_BC_COFINS")
    assert coluna is not None
    ws.cell(linha, coluna).value = valor


def test_filho_editado_de_pai_excluido_e_reposicionado_apos_novo_pai(tmp_path):
    xlsx = _exportar(tmp_path)
    wb = load_workbook(xlsx)

    # Exclui o primeiro pai e o filho do segundo grupo. O filho do primeiro
    # grupo é conscientemente reaproveitado para a base do pai sobrevivente.
    wb["M100"].delete_rows(2, 1)
    wb["M105"].delete_rows(3, 1)
    _alterar_base_filho(wb["M105"], 2, 100.00)

    wb["M500"].delete_rows(2, 1)
    wb["M505"].delete_rows(3, 1)
    _alterar_base_filho(wb["M505"], 2, 100.00)

    wb.save(xlsx)
    wb.close()

    resultado = ImportadorExcelSPED().validar(xlsx)
    linhas = resultado.linhas_geradas

    assert resultado.valido is True
    assert resultado.total_registros_bloco_m_removidos == 4

    indice_m100 = next(i for i, l in enumerate(linhas) if l.startswith("|M100|"))
    indice_m105 = next(i for i, l in enumerate(linhas) if l.startswith("|M105|"))
    indice_m500 = next(i for i, l in enumerate(linhas) if l.startswith("|M500|"))
    indice_m505 = next(i for i, l in enumerate(linhas) if l.startswith("|M505|"))

    assert indice_m105 == indice_m100 + 1
    assert indice_m505 == indice_m500 + 1
    assert "|100|" in linhas[indice_m105].replace(",00", "") or "100,00" in linhas[indice_m105]
    assert "100,00" in linhas[indice_m505]
    assert sum(1 for l in linhas if l.startswith("|M100|")) == 1
    assert sum(1 for l in linhas if l.startswith("|M105|")) == 1
    assert sum(1 for l in linhas if l.startswith("|M500|")) == 1
    assert sum(1 for l in linhas if l.startswith("|M505|")) == 1

    movimentos = [
        item for item in resultado.conferencia
        if item.tipo == "Reposicionamento hierárquico"
    ]
    assert {item.registro for item in movimentos} == {"M105", "M505"}


def test_reordenacao_nao_muda_valores_digitados():
    linhas = [
        "|M001|0|",
        "|M105|01|50|130142,26||130142,26|130142,26||0||",
        "|M100|101|0|130142,26|1,65|0||2147,35|0|0|0|2147,35|0|2147,35|0|",
        "|M200|8844,07|2288,81|0|6555,26|0|0|6555,26|0|0|0|0|6555,26|",
        "|M505|01|50|130142,26||130142,26|130142,26||0||",
        "|M500|101|0|130142,26|7,6|0||9890,79|0|0|0|9890,79|0|9890,79|0|",
        "|M600|40736,33|10554,85|0|30181,48|0|0|30181,48|0|0|0|0|30181,48|",
        "|M990|8|",
    ]

    novas, movimentos, avisos = ImportadorExcelSPED._reordenar_filhos_reaproveitados_bloco_m(linhas)

    assert not avisos
    assert [l.split("|")[1] for l in novas] == [
        "M001", "M100", "M105", "M200", "M500", "M505", "M600", "M990"
    ]
    lines_m500 = "|M500|101|0|130142,26|7,6|0||9890,79|0|0|0|9890,79|0|9890,79|0|"
    assert next(l for l in novas if l.startswith("|M500|")) == lines_m500
    assert {m[0] for m in movimentos} == {"M105", "M505"}
