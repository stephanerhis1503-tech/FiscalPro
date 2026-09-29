from datetime import date
from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.icms_uf_service import ICMSUFService, UFS_COBERTURA
from src.services.icms_st_uf_service import ICMSSTUFService, CEST_PNEUMATICOS_RN


def analisar(ncm: str):
    return ICMSUFService.analisar(
        ncm,
        contexto={
            "uf_origem": "MG",
            "uf_destino": "RN",
            "data_operacao": date(2026, 8, 24).isoformat(),
        },
    )


def test_versao_e_cobertura_rn_ativas():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 58)
    assert "RN" in UFS_COBERTURA
    assert "RN" in ICMSSTUFService.UFS_COBERTAS


def test_mg_rn_usa_7_interna_20_e_fecop_zero_automotivo():
    r = analisar("87141000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_interna_destino"] == 20.0
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True
    assert "FECOP/RN" in r["fcp_status"]


def test_autopeca_87141000_mg_rn_e_antecipacao_40_nao_st_remetente():
    r = analisar("87141000")
    assert r["cest"] == "01.076.00"
    assert r["st_potencial"] is True
    assert r["st_confirmado"] is False
    assert r["st_decisao_confirmada"] is True
    assert r["antecipacao_percentual"] == 40.0
    assert "ANTECIPAÇÃO" in r["st_status"]
    assert "DESTINATÁRIO" in r["st_responsabilidade"]
    assert "NÃO É DESTINO DO PROTOCOLO ICMS 41/08" in r["st_acordo_status"]
    assert r["mva_aplicada"] is None


def test_autopeca_rn_nao_forca_cfop_st_no_motor_de_configuracao():
    r = analisar("87141000")
    assert r["st_confirmado"] is False
    assert r["st_modelo_calculo"] == "ANTECIPAÇÃO ICMS/RN — ANEXO 005"


def test_pneu_40114000_mg_rn_mva_60_86_conv_102_e_fecop_zero():
    r = analisar("40114000")
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == 60.0
    assert r["mva_ajustada"] == 86.0
    assert r["mva_aplicada"] == 86.0
    assert r["fcp"] == 0.0
    assert "CONVÊNIO ICMS 102/17" in r["st_acordo_status"]


def test_tabela_pneumaticos_rn_atualizada_para_20_porcento():
    assert CEST_PNEUMATICOS_RN["16.003.00"]["ajustada"][7.0] == 86.0
    assert CEST_PNEUMATICOS_RN["16.001.00"]["ajustada"][7.0] == 65.08


def test_cobertura_mapa_rn_e_novos_totais():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "RN")
    assert linha["nivel"] == 2
    assert "20%" in linha["icms"]
    assert "antecipação" in linha["st"].lower()
    assert "17.8.58" in linha["observacao"]
    d = CoberturaTributariaService.diagnostico()
    assert d["totais"] == {"ampliada": 1, "parcial": 25, "geral": 1}


def test_olist_usa_motor_unico_e_expoe_antecipacao_sem_tabela_rn_paralela():
    fonte = Path("src/services/configurador_olist_service.py").read_text(encoding="utf-8")
    assert "ICMSUFService.analisar" in fonte
    assert "Antecipação / percentual de agregação" in fonte
    assert '"RN": {' not in fonte

def test_ficha_expoe_antecipacao_sem_chamar_percentual_de_mva():
    fonte = Path("src/ui/janela_ficha_tributaria.py").read_text(encoding="utf-8")
    assert "REVISAR • Antecipação" in fonte
    assert "Antecipação/Agregação" in fonte
