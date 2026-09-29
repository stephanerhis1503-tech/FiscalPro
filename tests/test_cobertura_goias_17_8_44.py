from datetime import date

from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.icms_uf_service import ICMSUFService


def _ctx(ncm, origem="MG", destino="GO"):
    return ICMSUFService.analisar(
        ncm,
        contexto={"uf_origem": origem, "uf_destino": destino, "data_operacao": "2026-08-21"},
    )


def test_versao_17844():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 44)


def test_go_modal_19_e_interestadual_mg_go_7():
    r = _ctx("87141000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_interna_destino"] == 19.0
    assert "19%" in r["aliquota_interna_status"]


def test_autopeca_go_nao_confirma_st_generica_desde_2018():
    r = _ctx("87141000")
    assert r["cest"] == "01.076.00"
    assert r["st_confirmado"] is False
    assert r["st_decisao_confirmada"] is True
    assert "EXCLUÍDA DA ST" in r["st_status"]
    assert r["mva_aplicada"] is None


def test_pneu_moto_go_st_mva_atualizada_2025():
    r = _ctx("40114000")
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["mva_original"] == 60.0
    assert r["mva_ajustada"] == 83.70
    assert r["mva_aplicada"] == 83.70
    assert "GO CONFIRMADO" in r["st_status"]


def test_pneu_interno_go_usa_mva_60():
    r = _ctx("40114000", origem="GO", destino="GO")
    assert r["st_confirmado"] is True
    assert r["mva_aplicada"] == 60.0


def test_mapa_go_parcial():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "GO")
    assert linha["nivel"] == 2
    assert "19%" in linha["icms"]
    assert "Pneumáticos" in linha["st"]
    assert "01/03/2018" in linha["st"]
    assert "17.8.44" in linha["observacao"]
