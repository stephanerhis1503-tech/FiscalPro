from src.services.icms_st_mg_service import ICMSSTMGService


def test_escova_arranque_moto_residual_autopecas_mg():
    r = ICMSSTMGService.analisar(
        "85452000", {"uf_origem": "MG", "uf_destino": "MG"},
        "ESCOVA DE ARRANQUE DO MOTOR DE MOTO",
    )
    assert r["confirmado"] is True
    assert r["cest"] == "01.999.00"
    assert r["mva_original"] == 71.78


def test_sensor_hibrido_moto_residual_autopecas_mg():
    r = ICMSSTMGService.analisar(
        "90268000", {"uf_origem": "MG", "uf_destino": "MG"},
        "SENSOR HIBRIDO",
    )
    assert r["confirmado"] is True
    assert r["cest"] == "01.999.00"
    assert r["mva_original"] == 71.78


def test_ncm_85365090_mantem_enquadramento_especifico():
    r = ICMSSTMGService.analisar(
        "85365090", {"uf_origem": "MG", "uf_destino": "MG"}, "INTERRUPTOR DE MOTO"
    )
    assert r["cest"] != "01.999.00"
