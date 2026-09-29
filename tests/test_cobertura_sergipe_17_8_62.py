from datetime import date
from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.consulta_oficial_service import ConsultaOficialService
from src.services.icms_uf_service import ICMSUFService, UFS_COBERTURA
from src.services.icms_st_uf_service import (
    ICMSSTUFService,
    CEST_PNEUMATICOS_SE,
    MVA_AUTOPECAS_SE,
    _mva_ajustada_formula,
)


def analisar(ncm: str, *, origem: str = "MG", fidelidade: bool = False):
    return ICMSUFService.analisar(
        ncm,
        contexto={
            "uf_origem": origem,
            "uf_destino": "SE",
            "data_operacao": date(2026, 8, 24).isoformat(),
            "contrato_fidelidade": fidelidade,
        },
    )


def test_versao_e_cobertura_sergipe_ativas():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 62)
    assert "SE" in UFS_COBERTURA
    assert "SE" in ICMSSTUFService.UFS_COBERTAS


def test_mg_se_usa_7_interna_19_e_fecoep_1_automotivo():
    r = analisar("87141000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_interna_destino"] == 19.0
    assert r["fcp"] == 1.0
    assert r["fcp_confirmado"] is True
    assert "FECOEP/SE 1%" in r["fcp_status"]


def test_autopeca_87141000_mg_se_mva_99_69_mas_sem_st_automatica_do_remetente():
    r = analisar("87141000")
    assert r["cest"] == "01.076.00"
    assert r["st_potencial"] is True
    assert r["st_confirmado"] is False
    assert r["st_decisao_confirmada"] is False
    assert r["mva_original"] == 71.78
    assert r["mva_ajustada"] == 99.69
    assert r["mva_aplicada"] == 99.69
    assert "ANTECIPAÇÃO" in r["st_status"]
    assert "DESTINATÁRIO SE" in r["st_responsabilidade"]
    assert "ORIGEM MG" in r["st_acordo_status"]
    assert r["st_modelo_calculo"] == "ANTECIPAÇÃO ICMS/SE — ART. 784, II, d"


def test_autopeca_se_fidelidade_usa_36_56_e_58_75_com_alerta():
    r = analisar("87141000", fidelidade=True)
    assert r["mva_original"] == 36.56
    assert r["mva_ajustada"] == 58.75
    assert r["mva_aplicada"] == 58.75
    assert r["st_confirmado"] is False
    assert "fidelidade" in r["observacao"].lower()


def test_origem_signataria_al_se_confirma_st_autopecas():
    r = analisar("87141000", origem="AL")
    assert r["aliquota_operacao"] == 12.0
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == 71.78
    assert r["mva_aplicada"] == 88.96
    assert "PROTOCOLO ICMS 97/10" in r["st_responsabilidade"]


def test_pneu_40114000_mg_se_mva_60_86_conv_102_e_fecoep_1():
    r = analisar("40114000")
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == 60.0
    assert r["mva_ajustada"] == 86.0
    assert r["mva_aplicada"] == 86.0
    assert r["fcp"] == 1.0
    assert "CONVÊNIO ICMS 102/17" in r["st_responsabilidade"]
    assert "ICMS + FECOEP" in r["mva_tipo"]


def test_tabelas_e_formula_se_usam_20_no_ajuste_por_icms_19_mais_fecoep_1():
    assert MVA_AUTOPECAS_SE["demais"]["ajustada"][7.0] == 99.69
    assert MVA_AUTOPECAS_SE["fidelidade"]["ajustada"][7.0] == 58.75
    assert CEST_PNEUMATICOS_SE["16.003.00"]["ajustada"][7.0] == 86.0
    assert _mva_ajustada_formula(71.78, 7.0, 20.0) == 99.69
    assert _mva_ajustada_formula(60.0, 7.0, 20.0) == 86.0


def test_fonte_contextual_se_e_regra_aplicada_corretas():
    auto = analisar("87141000")
    st_auto = ConsultaOficialService.st_contextual({"icms_uf": auto})
    assert st_auto["fonte_codigo"] == "SEFAZ_SE_RICMS"
    assert "RICMS/SE" in st_auto["fonte_nome"]
    assert st_auto["regra_aplicada"] == "ANTECIPAÇÃO ICMS/SE — ART. 784, II, d"

    pneu = analisar("40114000")
    st_pneu = ConsultaOficialService.st_contextual({"icms_uf": pneu})
    assert st_pneu["regra_aplicada"] == "ICMS-ST/SE — PNEUMÁTICOS — CONVÊNIO 102/17"


def test_cobertura_mapa_sergipe_e_novos_totais():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "SE")
    assert linha["nivel"] == 2
    assert "19%" in linha["icms"]
    assert "FECOEP 1%" in linha["fcp"]
    assert "17.8.62" in linha["observacao"]
    d = CoberturaTributariaService.diagnostico()
    assert d["totais"] == {"ampliada": 1, "parcial": 25, "geral": 1}


def test_olist_continua_usando_motor_unico_sem_tabela_se_paralela():
    fonte = Path("src/services/configurador_olist_service.py").read_text(encoding="utf-8")
    assert "ICMSUFService.analisar" in fonte
    assert '"SE": {' not in fonte
