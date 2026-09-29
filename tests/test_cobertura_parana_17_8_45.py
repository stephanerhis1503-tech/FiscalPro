from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.icms_uf_service import ICMSUFService


def _ctx(ncm, origem="MG", destino="PR", **extra):
    contexto = {"uf_origem": origem, "uf_destino": destino, "data_operacao": "2026-08-21"}
    contexto.update(extra)
    return ICMSUFService.analisar(ncm, contexto=contexto)


def test_versao_17845():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 45)


def test_pr_modal_195_e_interestadual_mg_pr_12():
    r = _ctx("87141000")
    assert r["aliquota_operacao"] == 12.0
    assert r["aliquota_interna_destino"] == 19.5
    assert "19,5%" in r["aliquota_interna_status"]


def test_autopeca_pr_st_mva_ajustada():
    r = _ctx("87141000")
    assert r["cest"] == "01.076.00"
    assert r["st_confirmado"] is True
    assert r["mva_original"] == 71.78
    assert r["mva_ajustada"] == 87.78
    assert r["mva_aplicada"] == 87.78
    assert "PR CONFIRMADO" in r["st_status"]


def test_autopeca_pr_fidelidade_mva_reduzida():
    r = _ctx("87141000", contrato_fidelidade=True)
    assert r["st_confirmado"] is True
    assert r["mva_original"] == 36.56
    assert r["mva_ajustada"] == 49.28


def test_pneu_moto_pr_st_mva_ajustada_e_fecop_zero():
    r = _ctx("40114000")
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["mva_original"] == 65.58
    assert r["mva_ajustada"] == 81.01
    assert r["mva_aplicada"] == 81.01
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True
    assert "PR CONFIRMADO" in r["st_status"]


def test_pneu_interno_pr_usa_mva_original():
    r = _ctx("40114000", origem="PR", destino="PR")
    assert r["st_confirmado"] is True
    assert r["mva_aplicada"] == 65.58
    assert r["mva_ajustada"] is None


def test_autopeca_pr_fecop_zero_confirmado():
    r = _ctx("87141000")
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True
    assert "AUTOMOTIVO" in r["fcp_status"]


def test_mapa_pr_parcial():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "PR")
    assert linha["nivel"] == 2
    assert "19,5%" in linha["icms"]
    assert "Autopeças + pneumáticos" in linha["st"]
    assert "17.8.45" in linha["observacao"]
