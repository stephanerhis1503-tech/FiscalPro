from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.icms_uf_service import ICMSUFService


def _ctx(ncm, origem="MG", destino="MS", **extra):
    contexto = {"uf_origem": origem, "uf_destino": destino, "data_operacao": "2026-08-21"}
    contexto.update(extra)
    return ICMSUFService.analisar(ncm, contexto=contexto)


def test_versao_17849():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 49)


def test_ms_modal_17_e_interestadual_mg_ms_7():
    r = _ctx("87141000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_interna_destino"] == 17.0
    assert "17%" in r["aliquota_interna_status"]


def test_autopeca_ms_st_mva_6807_e_fecomp_zero():
    r = _ctx("87141000")
    assert r["cest"] == "01.076.00"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == 50.0
    assert r["mva_ajustada"] == 68.07
    assert r["mva_aplicada"] == 68.07
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True
    assert "MS CONFIRMADO" in r["st_status"]


def test_autopeca_interna_ms_mva_50():
    r = _ctx("87141000", origem="MS", destino="MS")
    assert r["st_confirmado"] is True
    assert r["mva_original"] == 50.0
    assert r["mva_aplicada"] == 50.0
    assert r["mva_ajustada"] is None


def test_pneu_moto_ms_st_mva_7928_e_monofasico_preservado():
    r = _ctx("40114000")
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["mva_original"] == 60.0
    assert r["mva_ajustada"] == 79.28
    assert r["mva_aplicada"] == 79.28
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True


def test_pneu_interno_ms_usa_mva_original_60():
    r = _ctx("40114000", origem="MS", destino="MS")
    assert r["st_confirmado"] is True
    assert r["mva_original"] == 60.0
    assert r["mva_aplicada"] == 60.0
    assert r["mva_ajustada"] is None


def test_fecomp_ms_2_porcento_para_bebida_alcoolica():
    r = _ctx("22083020")
    assert r["fcp"] == 2.0
    assert r["fcp_confirmado"] is True
    assert "FECOMP/MS 2%" in r["fcp_status"]


def test_mapa_ms_parcial():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "MS")
    assert linha["nivel"] == 2
    assert "17%" in linha["icms"]
    assert "Autopeças + pneumáticos" in linha["st"]
    assert "17.8.49" in linha["observacao"]
