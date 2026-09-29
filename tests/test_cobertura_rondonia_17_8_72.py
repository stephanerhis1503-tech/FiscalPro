from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.icms_uf_service import ICMSUFService
from src.services.icms_st_uf_service import (
    CEST_PNEUMATICOS_RO,
    ICMSSTUFService,
    MVA_AUTOPECAS_RO,
    _mva_ajustada_formula,
)
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.consulta_oficial_service import ConsultaOficialService


def analisar(ncm, fidelidade=False):
    return ICMSUFService.analisar(
        ncm,
        contexto={
            "uf_origem": "MG",
            "uf_destino": "RO",
            "operacao": "SAIDA",
            "contrato_fidelidade": fidelidade,
            "data_operacao": "2026-08-25",
        },
    )


def test_versao_e_cobertura_ro():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 72)
    assert "RO" in ICMSSTUFService.UFS_COBERTAS


def test_autopeca_mg_ro_identifica_regime_e_responsabilidade_local():
    r = analisar("87141000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_interna_destino"] == 19.5
    assert r["cest"] == "01.076.00"
    assert r["mva_original"] == 30.0
    assert r["mva_aplicada"] == 50.19
    assert r["fcp"] == 0.0
    assert r["st_confirmado"] is False
    assert r["st_decisao_confirmada"] is False
    assert "DESTINATÁRIO RO" in r["st_responsabilidade"]
    assert "AUTOPEÇAS" in r["st_modelo_calculo"]


def test_autopeca_ro_nao_reduz_por_fidelidade():
    r = analisar("87141000", True)
    assert r["mva_original"] == 30.0
    assert r["mva_aplicada"] == 50.19


def test_pneu_moto_mg_ro():
    r = analisar("40114000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_interna_destino"] == 19.5
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == 50.0
    assert r["mva_aplicada"] == 73.29
    assert r["fcp"] == 2.0
    assert "PNEUMÁTICOS" in r["st_modelo_calculo"]
    assert "CONVÊNIO 102/17" in r["st_modelo_calculo"]


def test_tabelas_ro_e_formula():
    assert MVA_AUTOPECAS_RO["demais"]["ajustada"][7.0] == 50.19
    assert CEST_PNEUMATICOS_RO["16.003.00"]["ajustada"][7.0] == 73.29
    assert _mva_ajustada_formula(30.0, 7.0, 19.5) == 50.19
    assert _mva_ajustada_formula(50.0, 7.0, 19.5) == 73.29


def test_fonte_contextual_ro():
    r = analisar("87141000")
    ctx = ConsultaOficialService.st_contextual({"icms_uf": r})
    assert ctx["fonte_codigo"] == "SEFIN_RO_DEC_29048"
    assert "SEFIN/RO" in ctx["fonte_nome"]
    assert ctx["regra_aplicada"] == "ICMS-ST/RO — AUTOPEÇAS — RESPONSABILIDADE LOCAL"


def test_mapa_cobertura_ro_e_totais():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "RO")
    assert linha["nivel"] == 2
    assert "19,5%" in linha["icms"]
    assert "50,19%" in linha["observacao"]
    assert "73,29%" in linha["observacao"]
    d = CoberturaTributariaService.diagnostico()
    assert d["totais"] == {"ampliada": 1, "parcial": 25, "geral": 1}


def test_configurador_olist_nao_cria_tabela_ro_paralela():
    fonte = Path("src/services/configurador_olist_service.py").read_text(encoding="utf-8")
    assert "ICMSUFService.analisar" in fonte
    assert '"RO": {' not in fonte
