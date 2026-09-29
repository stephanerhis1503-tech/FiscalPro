from src.sped.importador_excel import ImportadorExcelSPED
from src.sped.pre_validador import PreValidadorPVA


def _linha(campos):
    return "|" + "|".join(campos) + "|"


def test_17_7_6_limpa_aliq_pis_quant_orfa_no_c175_ad_valorem():
    linha = _linha([
        "C175", "5405", "3,75", "0,25", "01", "0,68", "0,6500", "",
        "0,00442", "0,00", "01", "0,68", "3,0000", "", "", "0,02", "", "",
    ])

    novas, ajustes, avisos = ImportadorExcelSPED._normalizar_c175_aliquota_por_quantidade([linha])
    campos = ImportadorExcelSPED._separar_campos(novas[0])

    assert campos[8] == ""
    assert campos[5] == "0,68"
    assert campos[6] == "0,6500"
    assert campos[9] == "0,00"
    assert len(ajustes) == 1
    assert ajustes[0].campo == "ALIQ_PIS_QUANT"
    assert ajustes[0].original == "0,00442"
    assert avisos == []


def test_17_7_6_limpa_aliq_cofins_quant_orfa_no_c175_ad_valorem():
    linha = _linha([
        "C175", "5102", "10,00", "0,00", "01", "10,00", "0,6500", "",
        "", "0,07", "01", "10,00", "3,0000", "", "0,3000", "0,30", "", "",
    ])

    novas, ajustes, avisos = ImportadorExcelSPED._normalizar_c175_aliquota_por_quantidade([linha])
    campos = ImportadorExcelSPED._separar_campos(novas[0])

    assert campos[14] == ""
    assert campos[11] == "10,00"
    assert campos[12] == "3,0000"
    assert campos[15] == "0,30"
    assert len(ajustes) == 1
    assert ajustes[0].campo == "ALIQ_COFINS_QUANT"
    assert avisos == []


def test_17_7_6_nao_apaga_modalidade_incompleta_quando_nao_ha_ad_valorem():
    linha = _linha([
        "C175", "5102", "10,00", "0,00", "03", "", "", "",
        "0,1234", "1,23", "03", "", "", "", "", "0,00", "", "",
    ])

    novas, ajustes, avisos = ImportadorExcelSPED._normalizar_c175_aliquota_por_quantidade([linha])
    campos = ImportadorExcelSPED._separar_campos(novas[0])

    assert campos[8] == "0,1234"
    assert ajustes == []
    assert len(avisos) == 1
    assert "sem QUANT_BC_PIS" in avisos[0]


def test_17_7_6_pre_validador_detecta_aliq_quant_sem_quantidade():
    linhas = [
        "|0000|006|0|||01072026|31072026|EMPRESA|54304208000123|MG||||2|",
        "|0001|0|",
        "|0110|1||1|9|",
        "|C001|0|",
        "|C010|54304208000123|2|",
        _linha([
            "C175", "5405", "3,75", "0,25", "01", "0,68", "0,6500", "",
            "0,00442", "0,00", "01", "0,68", "3,0000", "", "", "0,02", "", "",
        ]),
        "|C990|3|",
        "|9999|7|",
    ]

    resultado = PreValidadorPVA().validar(linhas, "EFD Contribuições")
    assert any(
        item.registro == "C175"
        and item.campo == "ALIQ_PIS_QUANT"
        and "sem QUANT_BC_PIS" in item.mensagem
        for item in resultado.erros
    )
