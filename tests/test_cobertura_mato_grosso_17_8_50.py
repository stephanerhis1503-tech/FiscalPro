from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.icms_uf_service import ICMSUFService


def _ctx(ncm, origem="MG", destino="MT", **extra):
    contexto = {"uf_origem": origem, "uf_destino": destino, "data_operacao": "2026-08-21"}
    contexto.update(extra)
    return ICMSUFService.analisar(ncm, contexto=contexto)


def test_versao_17850():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 50)


def test_mt_modal_17_e_interestadual_mg_mt_7():
    r = _ctx("87141000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_interna_destino"] == 17.0
    assert "17%" in r["aliquota_interna_status"]


def test_autopeca_mt_st_mva_condicional_e_fcp_zero():
    r = _ctx("87141000")
    assert r["cest"] == "01.076.00"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == 50.39
    assert r["mva_ajustada"] is None
    assert r["mva_aplicada"] == 65.29
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True
    assert "MT CONFIRMADO" in r["st_status"]
    assert "CONDICIONAL" in r["st_status"]


def test_autopeca_mt_nao_calcula_mva_ajustada_por_origem():
    r_mg = _ctx("87141000", origem="MG")
    r_sp = _ctx("87141000", origem="SP")
    r_mt = _ctx("87141000", origem="MT", destino="MT")
    assert r_mg["mva_aplicada"] == 65.29
    assert r_sp["mva_aplicada"] == 65.29
    assert r_mt["mva_aplicada"] == 65.29
    assert r_mg["mva_ajustada"] is None
    assert "independentemente" in r_mg["observacao"].lower()


def test_pneu_moto_mt_st_mva_condicional():
    r = _ctx("40114000")
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["mva_original"] == 62.27
    assert r["mva_ajustada"] is None
    assert r["mva_aplicada"] == 78.79
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True


def test_pneu_mt_nao_muda_mva_por_aliquota_interestadual():
    r7 = _ctx("40114000", origem="MG")
    r12 = _ctx("40114000", origem="GO")
    assert r7["mva_aplicada"] == 78.79
    assert r12["mva_aplicada"] == 78.79
    assert r7["mva_ajustada"] is None
    assert r12["mva_ajustada"] is None


def test_mapa_mt_parcial():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "MT")
    assert linha["nivel"] == 2
    assert "17%" in linha["icms"]
    assert "Autopeças + pneumáticos" in linha["st"]
    assert "17.8.50" in linha["observacao"]


def test_totais_mapa_com_mt():
    d = CoberturaTributariaService.diagnostico()
    assert d["totais"] == {"ampliada": 1, "parcial": 25, "geral": 1}
