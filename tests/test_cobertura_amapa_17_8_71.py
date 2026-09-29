from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.icms_uf_service import ICMSUFService
from src.services.icms_st_uf_service import (
    CEST_PNEUMATICOS_AP,
    ICMSSTUFService,
    MVA_AUTOPECAS_AP,
    _mva_ajustada_formula,
)
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.consulta_oficial_service import ConsultaOficialService


def analisar(ncm, fidelidade=False):
    return ICMSUFService.analisar(
        ncm,
        contexto={
            "uf_origem": "MG",
            "uf_destino": "AP",
            "operacao": "SAIDA",
            "contrato_fidelidade": fidelidade,
            "data_operacao": "2026-08-25",
        },
    )


def test_versao_e_cobertura_ap():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 71)
    assert "AP" in ICMSSTUFService.UFS_COBERTAS


def test_autopeca_mg_ap_confirma_st_e_tabela_oficial():
    r = analisar("87141000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_interna_destino"] == 18.0
    assert r["cest"] == "01.076.00"
    assert r["mva_original"] == 71.78
    assert r["mva_aplicada"] == 94.82
    assert r["fcp"] == 0.0
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert "PROTOCOLO ICMS 41/08" in r["st_responsabilidade"]
    assert "PROTOCOLO 41/08" in r["st_modelo_calculo"]


def test_autopeca_ap_fidelidade_condicional():
    r = analisar("87141000", True)
    assert r["mva_original"] == 36.56
    assert r["mva_aplicada"] == 54.88
    assert "fidelidade" in r["observacao"].lower()


def test_pneu_moto_mg_ap():
    r = analisar("40114000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_interna_destino"] == 18.0
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == 60.0
    assert r["mva_aplicada"] == 81.46
    assert r["fcp"] == 0.0
    assert "PNEUMÁTICOS" in r["st_modelo_calculo"]
    assert "CONVÊNIO 102/17" in r["st_modelo_calculo"]


def test_tabelas_ap_e_formula():
    assert MVA_AUTOPECAS_AP["demais"]["ajustada"][7.0] == 94.82
    assert MVA_AUTOPECAS_AP["fidelidade"]["ajustada"][7.0] == 54.88
    assert CEST_PNEUMATICOS_AP["16.003.00"]["ajustada"][7.0] == 81.46
    assert _mva_ajustada_formula(71.78, 7.0, 18.0) == 94.82
    assert _mva_ajustada_formula(60.0, 7.0, 18.0) == 81.46


def test_fonte_contextual_ap():
    r = analisar("87141000")
    ctx = ConsultaOficialService.st_contextual({"icms_uf": r})
    assert ctx["fonte_codigo"] == "SEFAZ_AP_RICMS"
    assert "SEFAZ/AP" in ctx["fonte_nome"]
    assert ctx["regra_aplicada"] == "ICMS-ST/AP — AUTOPEÇAS — PROTOCOLO 41/08"


def test_mapa_cobertura_ap_e_totais():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "AP")
    assert linha["nivel"] == 2
    assert "18%" in linha["icms"]
    assert "94,82%" in linha["observacao"]
    assert "81,46%" in linha["observacao"]
    d = CoberturaTributariaService.diagnostico()
    assert d["totais"] == {"ampliada": 1, "parcial": 25, "geral": 1}


def test_configurador_olist_nao_cria_tabela_ap_paralela():
    fonte = Path("src/services/configurador_olist_service.py").read_text(encoding="utf-8")
    assert "ICMSUFService.analisar" in fonte
    assert '"AP": {' not in fonte
