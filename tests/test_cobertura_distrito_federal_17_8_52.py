from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.icms_uf_service import ICMSUFService


def _ctx(ncm, origem="MG", destino="DF", descricao="", **extra):
    contexto = {"uf_origem": origem, "uf_destino": destino, "data_operacao": "2026-08-21"}
    contexto.update(extra)
    return ICMSUFService.analisar(ncm, contexto=contexto, descricao=descricao)


def test_versao_17852():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 52)


def test_df_modal_20_e_interestadual_mg_df_7():
    r = _ctx("87141000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_operacao_confirmada"] is True
    assert r["aliquota_interna_destino"] == 20.0
    assert "20%" in r["aliquota_interna_status"]


def test_autopeca_df_st_mva_padrao_ajustada_e_fcp_zero():
    r = _ctx("87141000")
    assert r["cest"] == "01.076.00"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == 71.78
    assert r["mva_ajustada"] == 99.69
    assert r["mva_aplicada"] == 99.69
    assert "DEMAIS CASOS" in r["mva_tipo"]
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True
    assert "ICMS-ST/DF" in r["st_status"]


def test_autopeca_df_fidelidade_usa_3656_com_alerta_de_requisitos():
    r = _ctx("87141000", contrato_fidelidade=True)
    assert r["mva_original"] == 36.56
    assert r["mva_ajustada"] == 58.75
    assert r["mva_aplicada"] == 58.75
    assert "FIDELIDADE" in r["mva_tipo"]
    assert "CONFIRMAR REQUISITOS" in r["mva_tipo"]
    assert "CONDICIONAL" in r["st_status"]


def test_autopeca_df_origem_go_aplica_inter_12_e_mva_8896():
    r = _ctx("87141000", origem="GO")
    assert r["aliquota_operacao"] == 12.0
    assert r["mva_original"] == 71.78
    assert r["mva_ajustada"] == 88.96
    assert r["mva_aplicada"] == 88.96


def test_autopeca_interna_df_usa_mva_original_sem_ajuste():
    r = _ctx("87141000", origem="DF")
    assert r["aliquota_operacao"] == 20.0
    assert r["mva_original"] == 71.78
    assert r["mva_ajustada"] is None
    assert r["mva_aplicada"] == 71.78


def test_pneu_moto_df_st_mva_60_ajustada_para_86():
    r = _ctx("40114000")
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == 60.0
    assert r["mva_ajustada"] == 86.0
    assert r["mva_aplicada"] == 86.0
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True


def test_pneu_df_origem_go_inter_12_resulta_76():
    r = _ctx("40114000", origem="GO")
    assert r["aliquota_operacao"] == 12.0
    assert r["mva_original"] == 60.0
    assert r["mva_ajustada"] == 76.0
    assert r["mva_aplicada"] == 76.0


def test_pneu_interno_df_usa_mva_original_60():
    r = _ctx("40114000", origem="DF")
    assert r["mva_original"] == 60.0
    assert r["mva_ajustada"] is None
    assert r["mva_aplicada"] == 60.0


def test_mapa_df_parcial_e_totais_atualizados():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "DF")
    assert linha["nivel"] == 2
    assert "20%" in linha["icms"]
    assert "Autopeças + pneumáticos" in linha["st"]
    assert "17.8.52" in linha["observacao"]
    d = CoberturaTributariaService.diagnostico()
    assert d["totais"] == {"ampliada": 1, "parcial": 25, "geral": 1}


def test_configurador_olist_continua_usando_motor_icms_uf_sem_tabela_df_paralela():
    fonte = Path("src/services/configurador_olist_service.py").read_text(encoding="utf-8")
    assert "ICMSUFService.analisar" in fonte
    assert "UFS_COBERTURA" not in fonte
    assert '"DF": {' not in fonte
