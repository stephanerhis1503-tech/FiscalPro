from datetime import date
from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.icms_uf_service import ICMSUFService, UFS_COBERTURA
from src.services.icms_st_uf_service import ICMSSTUFService, CEST_PNEUMATICOS_PB, MVA_AUTOPECAS_PB


def analisar(ncm: str, *, fidelidade: bool = False):
    return ICMSUFService.analisar(
        ncm,
        contexto={
            "uf_origem": "MG",
            "uf_destino": "PB",
            "data_operacao": date(2026, 8, 23).isoformat(),
            "contrato_fidelidade": fidelidade,
        },
    )


def test_versao_e_cobertura_paraiba_ativas():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 56)
    assert "PB" in UFS_COBERTURA
    assert "PB" in ICMSSTUFService.UFS_COBERTAS


def test_mg_pb_usa_7_interna_20_e_funcep_zero_automotivo():
    r = analisar("87141000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_interna_destino"] == 20.0
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True
    assert "FUNCEP/PB" in r["fcp_status"]


def test_autopeca_87141000_mg_pb_st_confirmada_mva_99_69_e_remetente():
    r = analisar("87141000")
    assert r["cest"] == "01.076.00"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == 71.78
    assert r["mva_ajustada"] == 99.69
    assert r["mva_aplicada"] == 99.69
    assert "REMETENTE" in r["st_responsabilidade"]
    assert "PROTOCOLO ICMS 41/08" in r["st_responsabilidade"]


def test_autopeca_pb_fidelidade_usa_36_56_e_58_75_com_alerta():
    r = analisar("87141000", fidelidade=True)
    assert r["mva_original"] == 36.56
    assert r["mva_ajustada"] == 58.75
    assert r["mva_aplicada"] == 58.75
    assert r["st_confirmado"] is True
    assert "FIDELIDADE" in r["st_status"]
    assert "requisitos" in r["observacao"].lower()


def test_pneu_40114000_mg_pb_mva_60_86_conv_102_e_funcep_zero():
    r = analisar("40114000")
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == 60.0
    assert r["mva_ajustada"] == 86.0
    assert r["mva_aplicada"] == 86.0
    assert r["fcp"] == 0.0
    assert "CONVÊNIO ICMS 102/17" in r["st_acordo_status"]


def test_tabelas_pb_oficiais_referencia():
    assert MVA_AUTOPECAS_PB["demais"]["ajustada"][7.0] == 99.69
    assert MVA_AUTOPECAS_PB["fidelidade"]["ajustada"][7.0] == 58.75
    assert CEST_PNEUMATICOS_PB["16.003.00"]["ajustada"][7.0] == 86.0


def test_cobertura_mapa_paraiba_e_novos_totais():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "PB")
    assert linha["nivel"] == 2
    assert "20%" in linha["icms"]
    assert "FUNCEP 0%" in linha["fcp"]
    assert "17.8.56" in linha["observacao"]
    d = CoberturaTributariaService.diagnostico()
    assert d["totais"] == {"ampliada": 1, "parcial": 25, "geral": 1}


def test_olist_continua_usando_motor_unico_sem_tabela_pb_paralela():
    fonte = Path("src/services/configurador_olist_service.py").read_text(encoding="utf-8")
    assert "ICMSUFService.analisar" in fonte
    assert '"PB": {' not in fonte
