from src.sped.auditor_difal import AuditorDIFALSPED

CHAVE = "31250712345678000190550010000012341000012345"


def _sped_misto():
    return [
        "|0000|020|0|01072025|31072025|EMPRESA TESTE|12345678000190||MG|123|3106200|||B|1|\n",
        "|0150|CLI|CLIENTE CPF|1058||12345678909||2927408||RUA A|1|||\n",
        f"|C100|1|0|CLI|55|00|1|1234|{CHAVE}|01072025|01072025|200,00|0|0,00|0,00|200,00|0|0,00|0,00|0,00|200,00|7,00|0,00|0,00|0,00|1,65|7,60|0,00|0,00|\n",
        "|C190|000|6108|7,00|100,00|100,00|7,00|0,00|0,00|0,00|0,00||\n",
        "|C190|100|6108|4,00|100,00|100,00|4,00|0,00|0,00|0,00|0,00||\n",
    ]


def test_memoria_calculo_difal_por_segmento_c190_cst():
    r = AuditorDIFALSPED().auditar(_sped_misto(), "EFD ICMS/IPI (Fiscal)", importacao_xml=None)
    a = r.apontamentos[0]
    assert len(a.segmentos_memoria_sped) == 2
    assert float(a.difal_sped_origem) == 30.0
    assert "CST 000 origem 0" in a.memoria_calculo_sped
    assert "CST 100 origem 1" in a.memoria_calculo_sped
    assert "20,5% - 7%" in a.memoria_calculo_sped
    assert "20,5% - 4%" in a.memoria_calculo_sped
    assert float(a.segmentos_memoria_sped[0]["difal"]) == 13.5
    assert float(a.segmentos_memoria_sped[1]["difal"]) == 16.5


def test_memoria_mantem_total_consolidado_da_nf():
    r = AuditorDIFALSPED().auditar(_sped_misto(), "EFD ICMS/IPI (Fiscal)", importacao_xml=None)
    a = r.apontamentos[0]
    soma = sum(seg["difal"] for seg in a.segmentos_memoria_sped)
    assert soma == a.difal_sped_origem == a.difal_devido
    assert a.data_documento == "01072025"
