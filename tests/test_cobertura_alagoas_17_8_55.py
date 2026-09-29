from datetime import date
from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.icms_uf_service import ICMSUFService, UFS_COBERTURA
from src.services.icms_st_uf_service import ICMSSTUFService, _mva_ajustada_formula


def analisar(ncm: str, *, fidelidade: bool = False):
    return ICMSUFService.analisar(
        ncm,
        contexto={
            "uf_origem": "MG",
            "uf_destino": "AL",
            "data_operacao": date(2026, 8, 23).isoformat(),
            "contrato_fidelidade": fidelidade,
        },
    )


def test_versao_e_cobertura_alagoas_ativas():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 55)
    assert "AL" in UFS_COBERTURA
    assert "AL" in ICMSSTUFService.UFS_COBERTAS


def test_mg_al_usa_7_e_interna_20_5_com_fecoep_1():
    r = analisar("87141000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_interna_destino"] == 20.5
    assert r["fcp"] == 1.0
    assert r["fcp_confirmado"] is True
    assert "FECOEP/AL 1%" in r["fcp_status"]


def test_autopeca_87141000_mg_al_st_confirmada_e_mva_100_95():
    r = analisar("87141000")
    assert r["cest"] == "01.076.00"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == 71.78
    assert r["mva_ajustada"] == 100.95
    assert r["mva_aplicada"] == 100.95
    assert "PROTOCOLO ICMS 41/08" in r["st_responsabilidade"]
    assert "REMETENTE" in r["st_responsabilidade"]
    assert "PROTOCOLO" in r["st_acordo_status"]


def test_autopeca_al_fidelidade_usa_36_56_e_59_75_com_alerta():
    r = analisar("87141000", fidelidade=True)
    assert r["mva_original"] == 36.56
    assert r["mva_ajustada"] == 59.75
    assert r["mva_aplicada"] == 59.75
    assert r["st_confirmado"] is True
    assert "FIDELIDADE" in r["st_status"]
    assert "requisitos" in r["observacao"].lower()


def test_pneu_40114000_mg_al_mva_60_87_17_e_fecoep_1():
    r = analisar("40114000")
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == 60.0
    assert r["mva_ajustada"] == 87.17
    assert r["mva_aplicada"] == 87.17
    assert r["fcp"] == 1.0
    assert "CONVÊNIO ICMS 102/17" in r["st_acordo_status"]


def test_formula_al_confere_valores_referencia():
    assert _mva_ajustada_formula(71.78, 7.0, 20.5) == 100.95
    assert _mva_ajustada_formula(36.56, 7.0, 20.5) == 59.75
    assert _mva_ajustada_formula(60.0, 7.0, 20.5) == 87.17


def test_cobertura_mapa_alagoas_e_novos_totais():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "AL")
    assert linha["nivel"] == 2
    assert "20,5%" in linha["icms"]
    assert "FECOEP 1%" in linha["fcp"]
    assert "17.8.55" in linha["observacao"]
    d = CoberturaTributariaService.diagnostico()
    assert d["totais"] == {"ampliada": 1, "parcial": 25, "geral": 1}


def test_olist_continua_usando_motor_unico_sem_tabela_al_paralela():
    fonte = Path("src/services/configurador_olist_service.py").read_text(encoding="utf-8")
    assert "ICMSUFService.analisar" in fonte
    assert '"AL": {' not in fonte
