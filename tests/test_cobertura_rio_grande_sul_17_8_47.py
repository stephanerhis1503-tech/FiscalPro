from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.icms_uf_service import ICMSUFService


def _ctx(ncm, origem="MG", destino="RS", **extra):
    contexto = {"uf_origem": origem, "uf_destino": destino, "data_operacao": "2026-08-21"}
    contexto.update(extra)
    return ICMSUFService.analisar(ncm, contexto=contexto)


def test_versao_17847():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 47)


def test_rs_modal_17_e_interestadual_mg_rs_12():
    r = _ctx("87141000")
    assert r["aliquota_operacao"] == 12.0
    assert r["aliquota_interna_destino"] == 17.0
    assert "17%" in r["aliquota_interna_status"]


def test_autopeca_rs_excluida_st_desde_2024():
    r = _ctx("87141000")
    assert r["cest"] == "01.076.00"
    assert r["st_confirmado"] is False
    assert r["st_decisao_confirmada"] is True
    assert r["mva_aplicada"] is None
    assert "EXCLUÍDA DA ST DESDE 01/11/2024" in r["st_status"]


def test_pneu_moto_rs_st_mva_7632_e_ampara_zero():
    r = _ctx("40114000")
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["mva_original"] == 66.31
    assert r["mva_ajustada"] == 76.32
    assert r["mva_aplicada"] == 76.32
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True
    assert "RS CONFIRMADO" in r["st_status"]


def test_pneu_interno_rs_usa_mva_original():
    r = _ctx("40114000", origem="RS", destino="RS")
    assert r["st_confirmado"] is True
    assert r["mva_original"] == 66.31
    assert r["mva_aplicada"] == 66.31
    assert r["mva_ajustada"] is None


def test_autopeca_rs_ampara_zero_confirmado():
    r = _ctx("87141000")
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True
    assert "AMPARA/RS" in r["fcp_status"]


def test_ampara_rs_2_porcento_no_rol_objetivo_consumidor_final():
    r = _ctx("33030010", consumidor_final=True)
    assert r["fcp"] == 2.0
    assert r["fcp_confirmado"] is True
    assert "AMPARA/RS 2%" in r["fcp_status"]


def test_mapa_rs_parcial():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "RS")
    assert linha["nivel"] == 2
    assert "17%" in linha["icms"]
    assert "Pneumáticos detalhados" in linha["st"]
    assert "17.8.47" in linha["observacao"]
