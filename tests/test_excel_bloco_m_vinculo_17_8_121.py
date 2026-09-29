from decimal import Decimal

from openpyxl import Workbook

from src.sped.importador_excel import (
    ImportadorExcelSPED,
    ResultadoValidacaoExcel,
    _ReferenciaLinha,
)
from src.sped.sincronizador_bloco_m_excel import SincronizadorBlocoMExcel


def test_recupera_aba_legada_sem_fp_id_quando_conteudo_original_esta_intacto(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "0206"
    ws.append(["REG", "POSICAO_02_SEM_MAPEAMENTO"])
    ws.append(["0206", "620501001"])

    ref = _ReferenciaLinha(
        sequencia=206,
        tipo="REGISTRO",
        id_tecnico="FP000000206",
        registro="0206",
        aba_original="0206",
        linha_excel_original=2,
        qtd_contexto=0,
        qtd_campos=2,
        linha_original="|0206|620501001|",
    )
    resultado = ResultadoValidacaoExcel(caminho=tmp_path / "teste.xlsx")
    mapa = ImportadorExcelSPED()._mapear_ids(wb, resultado, [ref])

    assert "FP000000206" in mapa
    assert not resultado.erros
    assert any("recuperou com segurança" in p.mensagem for p in resultado.avisos)


def test_delta_de_revenda_st_atualiza_m105_01_sem_tocar_m105_02():
    sync = SincronizadorBlocoMExcel()
    originais = [
        "|C170|1|A|||UN|100|||060|1403||||||||||||||50|100|1,65||||50|100|7,6|||||",
        "|C170|2|B|||UN|200|||060|2403||||||||||||||50|200|1,65||||50|200|7,6|||||",
        "|C170|3|C|||UN|5,82|||060|1407||||||||||||||50|5,82|1,65||||50|5,82|7,6|||||",
        "|C170|4|D|||UN|10|||060|2949||||||||||||||50|10|1,65||||50|10|7,6|||||",
        "|M100|101|0|305,82|1,65|0||5,05|0|0|0|5,05|0|5,05|0|",
        "|M105|01|50|300||300|300||0||",
        "|M105|02|50|5,82||5,82|5,82||0||",
        "|M200|100,00|0|0|100,00|0|0|100,00|0|0|0|0|100,00|",
    ]
    atuais = list(originais)
    sync._deltas_familia_cache = {
        ("PIS", "1.6500", "50", "REVENDA"): Decimal("30.00")
    }

    qtd, _ = sync._sincronizar_creditos_assinados(
        atuais,
        originais,
        {("PIS", "1.6500", "50"): Decimal("30.00")},
    )

    assert qtd > 0
    assert atuais[5] == "|M105|01|50|330,00||330,00|330,00||0||"
    assert atuais[6] == "|M105|02|50|5,82||5,82|5,82||0||"
    assert atuais[4].startswith("|M100|101|0|335,82|1,65|")
