from datetime import date
from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.consulta_oficial_service import ConsultaOficialService
from src.services.icms_uf_service import ICMSUFService, UFS_COBERTURA
from src.services.icms_st_uf_service import (
    ICMSSTUFService, CEST_PNEUMATICOS_MA, MVA_AUTOPECAS_MA, _mva_ajustada_formula,
)


def analisar(ncm: str, *, fidelidade: bool = False):
    return ICMSUFService.analisar(
        ncm,
        contexto={
            "uf_origem": "MG",
            "uf_destino": "MA",
            "data_operacao": date(2026, 8, 24).isoformat(),
            "contrato_fidelidade": fidelidade,
        },
    )


def test_versao_e_cobertura_maranhao_ativas():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 63)
    assert "MA" in UFS_COBERTURA
    assert "MA" in ICMSSTUFService.UFS_COBERTAS


def test_mg_ma_usa_7_interna_23_e_fumacop_zero_automotivo():
    r = analisar("87141000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_interna_destino"] == 23.0
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True
    assert "FUMACOP/MA" in r["fcp_status"]


def test_autopeca_87141000_mg_ma_st_confirmada_mva_107_47_e_remetente():
    r = analisar("87141000")
    assert r["cest"] == "01.076.00"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == 71.78
    assert r["mva_ajustada"] == 107.47
    assert r["mva_aplicada"] == 107.47
    assert "REMETENTE" in r["st_responsabilidade"]
    assert "PROTOCOLO ICMS 41/08" in r["st_responsabilidade"]
    assert r["st_modelo_calculo"] == "ICMS-ST/MA — AUTOPEÇAS — PROTOCOLO 41/08"


def test_autopeca_ma_fidelidade_usa_36_56_e_64_94_com_alerta():
    r = analisar("87141000", fidelidade=True)
    assert r["mva_original"] == 36.56
    assert r["mva_ajustada"] == 64.94
    assert r["mva_aplicada"] == 64.94
    assert r["st_confirmado"] is True
    assert "FIDELIDADE" in r["st_status"]
    assert "requisitos" in r["observacao"].lower()


def test_pneu_40114000_mg_ma_mva_60_93_25_conv_102_e_fumacop_zero():
    r = analisar("40114000")
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == 60.0
    assert r["mva_ajustada"] == 93.25
    assert r["mva_aplicada"] == 93.25
    assert r["fcp"] == 0.0
    assert "CONVÊNIO ICMS 102/17" in r["st_responsabilidade"]


def test_tabelas_e_formula_ma_usam_23_no_ajuste():
    assert MVA_AUTOPECAS_MA["demais"]["ajustada"][7.0] == 107.47
    assert MVA_AUTOPECAS_MA["fidelidade"]["ajustada"][7.0] == 64.94
    assert CEST_PNEUMATICOS_MA["16.003.00"]["ajustada"][7.0] == 93.25
    assert _mva_ajustada_formula(71.78, 7.0, 23.0) == 107.47
    assert _mva_ajustada_formula(60.0, 7.0, 23.0) == 93.25


def test_fonte_contextual_ma_e_regra_aplicada_corretas():
    auto = analisar("87141000")
    st_auto = ConsultaOficialService.st_contextual({"icms_uf": auto})
    assert st_auto["fonte_codigo"] == "SEFAZ_MA_RICMS"
    assert "RICMS/MA" in st_auto["fonte_nome"]
    assert st_auto["regra_aplicada"] == "ICMS-ST/MA — AUTOPEÇAS — PROTOCOLO 41/08"

    pneu = analisar("40114000")
    st_pneu = ConsultaOficialService.st_contextual({"icms_uf": pneu})
    assert st_pneu["regra_aplicada"] == "ICMS-ST/MA — PNEUMÁTICOS — CONVÊNIO 102/17"


def test_cobertura_mapa_maranhao_e_novos_totais():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "MA")
    assert linha["nivel"] == 2
    assert "23%" in linha["icms"]
    assert "FUMACOP 0%" in linha["fcp"]
    assert "17.8.63" in linha["observacao"]
    d = CoberturaTributariaService.diagnostico()
    assert d["totais"] == {"ampliada": 1, "parcial": 25, "geral": 1}


def test_olist_continua_usando_motor_unico_sem_tabela_ma_paralela():
    fonte = Path("src/services/configurador_olist_service.py").read_text(encoding="utf-8")
    assert "ICMSUFService.analisar" in fonte
    assert '"MA": {' not in fonte
