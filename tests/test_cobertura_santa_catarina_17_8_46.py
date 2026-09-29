from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.icms_uf_service import ICMSUFService


def _ctx(ncm, origem="MG", destino="SC", **extra):
    contexto = {"uf_origem": origem, "uf_destino": destino, "data_operacao": "2026-08-21"}
    contexto.update(extra)
    return ICMSUFService.analisar(ncm, contexto=contexto)


def test_versao_17846():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 46)


def test_sc_interestadual_mg_sc_12_e_interna_contribuinte_12():
    r = _ctx("87141000")
    assert r["aliquota_operacao"] == 12.0
    assert r["aliquota_interna_destino"] == 12.0
    assert "CONTRIBUINTE" in r["aliquota_interna_status"]


def test_autopeca_sc_excluida_st_desde_2020():
    r = _ctx("87141000")
    assert r["cest"] == "01.076.00"
    assert r["st_confirmado"] is False
    assert r["st_decisao_confirmada"] is True
    assert r["mva_aplicada"] is None
    assert "EXCLUÍDA DA ST DESDE 01/04/2020" in r["st_status"]


def test_pneu_moto_sc_st_mva_6964_e_fcp_zero():
    r = _ctx("40114000")
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["mva_original"] == 69.64
    assert r["mva_ajustada"] == 69.64
    assert r["mva_aplicada"] == 69.64
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True
    assert "SC CONFIRMADO" in r["st_status"]


def test_pneu_interno_sc_usa_mva_original():
    r = _ctx("40114000", origem="SC", destino="SC")
    assert r["st_confirmado"] is True
    assert r["mva_aplicada"] == 69.64
    assert r["mva_ajustada"] is None


def test_autopeca_sc_fcp_zero_confirmado():
    r = _ctx("87141000")
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True
    assert "0%" in r["fcp_status"]


def test_sc_consumidor_final_retorna_modal_17_e_revisao():
    r = _ctx("87141000", consumidor_final=True)
    assert r["aliquota_interna_destino"] == 17.0
    assert r["aliquota_interna_confirmada"] is False
    assert "17%" in r["aliquota_interna_status"]


def test_mapa_sc_parcial():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "SC")
    assert linha["nivel"] == 2
    assert "12%" in linha["icms"]
    assert "Pneumáticos detalhados" in linha["st"]
    assert "17.8.46" in linha["observacao"]
