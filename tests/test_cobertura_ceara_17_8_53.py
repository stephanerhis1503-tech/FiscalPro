from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.consulta_oficial_service import ConsultaOficialService
from src.services.icms_uf_service import ICMSUFService


def _ctx(ncm, origem="MG", destino="CE", descricao="", **extra):
    contexto = {"uf_origem": origem, "uf_destino": destino, "data_operacao": "2026-08-21"}
    contexto.update(extra)
    return ICMSUFService.analisar(ncm, contexto=contexto, descricao=descricao)


def test_versao_17853():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 53)


def test_ce_modal_20_e_interestadual_mg_ce_7():
    r = _ctx("87141000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_operacao_confirmada"] is True
    assert r["aliquota_interna_destino"] == 20.0
    assert "20%" in r["aliquota_interna_status"]


def test_autopeca_ce_nao_inventa_mva_e_mostra_carga_liquida_21_condicional():
    r = _ctx("87141000")
    assert r["cest"] == "01.076.00"
    assert r["st_potencial"] is True
    assert r["st_decisao_confirmada"] is False
    assert r["mva_original"] is None
    assert r["mva_aplicada"] is None
    assert r["carga_liquida_st"] == 21.0
    assert "CARGA LÍQUIDA" in r["st_modelo_calculo"]
    assert "CNAE" in r["st_status"]
    assert "PROTOCOLO ICMS 41/08 NÃO INCLUI CE" in r["st_acordo_status"]
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True


def test_autopeca_ce_origem_ba_usa_carga_liquida_1971():
    r = _ctx("87141000", origem="BA")
    assert r["aliquota_operacao"] == 12.0
    assert r["carga_liquida_st"] == 19.71


def test_autopeca_interna_ce_referencia_carga_liquida_8():
    r = _ctx("87141000", origem="CE")
    assert r["aliquota_operacao"] == 20.0
    assert r["carga_liquida_st"] == 8.0


def test_pneu_moto_ce_confirma_st_mas_exige_revisao_do_modelo_de_calculo():
    r = _ctx("40114000")
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is False
    assert r["mva_aplicada"] is None
    assert r["carga_liquida_st"] == 21.0
    assert "CONDICIONAL" in r["st_modelo_calculo"]
    assert "REDUÇÃO DE BASE" in r["st_acordo_status"]
    assert r["fcp"] == 0.0


def test_st_contextual_propaga_modelo_e_carga_liquida_ce():
    consulta = {"icms_uf": _ctx("87141000")}
    st = ConsultaOficialService.st_contextual(consulta)
    assert st["uf"] == "CE"
    assert st["carga_liquida_st"] == 21.0
    assert "CARGA LÍQUIDA" in st["st_modelo_calculo"]


def test_mapa_ce_parcial_e_totais_atualizados():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "CE")
    assert linha["nivel"] == 2
    assert "20%" in linha["icms"]
    assert "carga líquida" in linha["st"]
    assert "17.8.53" in linha["observacao"]
    d = CoberturaTributariaService.diagnostico()
    assert d["totais"] == {"ampliada": 1, "parcial": 25, "geral": 1}


def test_olist_exibe_modelo_e_carga_sem_tabela_ce_paralela():
    fonte = Path("src/services/configurador_olist_service.py").read_text(encoding="utf-8")
    assert "ICMSUFService.analisar" in fonte
    assert '"Modelo de cálculo ST"' in fonte
    assert '"Carga líquida ST / entrada"' in fonte
    assert '"CE": {' not in fonte
