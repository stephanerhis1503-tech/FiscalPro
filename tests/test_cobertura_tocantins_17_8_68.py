from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.icms_uf_service import ICMSUFService
from src.services.icms_st_uf_service import (
    ICMSSTUFService, CEST_PNEUMATICOS_TO, MVA_AUTOPECAS_TO, _mva_ajustada_formula,
)
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.consulta_oficial_service import ConsultaOficialService


def analisar(ncm, fidelidade=False):
    return ICMSUFService.analisar(
        ncm,
        contexto={
            "uf_origem": "MG",
            "uf_destino": "TO",
            "operacao": "SAIDA",
            "contrato_fidelidade": fidelidade,
            "data_operacao": "2026-08-25",
        },
    )


def test_versao_e_cobertura_to():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 68)
    assert "TO" in ICMSSTUFService.UFS_COBERTAS


def test_autopeca_mg_to_preserva_mva_sem_forcar_st_remetente():
    r = analisar("87141000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_interna_destino"] == 20.0
    assert r["cest"] == "01.076.00"
    assert r["mva_original"] == 71.78
    assert r["mva_aplicada"] == 99.69
    assert r["fcp"] == 0.0
    assert r["st_confirmado"] is False
    assert r["st_decisao_confirmada"] is False
    assert "RETENÇÃO PELO REMETENTE MG NÃO AUTOMÁTICA" in r["st_status"]
    assert "NÃO SIGNATÁRIO" in r["st_responsabilidade"]
    assert "PROTOCOLO 97/10" in r["st_modelo_calculo"]


def test_autopeca_to_fidelidade_condicional():
    r = analisar("87141000", True)
    assert r["mva_original"] == 36.56
    assert r["mva_aplicada"] == 58.75
    assert "36,56" in r["observacao"]
    assert "fidelidade" in r["observacao"].lower()


def test_pneu_moto_mg_to():
    r = analisar("40114000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_interna_destino"] == 20.0
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == 60.0
    assert r["mva_aplicada"] == 86.0
    assert r["fcp"] == 0.0
    assert "PNEUMÁTICOS" in r["st_modelo_calculo"]
    assert "CONVÊNIO 102/17" in r["st_modelo_calculo"]


def test_tabelas_to_e_formula():
    assert MVA_AUTOPECAS_TO["demais"]["ajustada"][7.0] == 99.69
    assert MVA_AUTOPECAS_TO["fidelidade"]["ajustada"][7.0] == 58.75
    assert CEST_PNEUMATICOS_TO["16.003.00"]["ajustada"][7.0] == 86.0
    assert _mva_ajustada_formula(71.78, 7.0, 20.0) == 99.69
    assert _mva_ajustada_formula(60.0, 7.0, 20.0) == 86.0


def test_fonte_contextual_to():
    r = analisar("87141000")
    ctx = ConsultaOficialService.st_contextual({"icms_uf": r})
    assert ctx["fonte_codigo"] == "SEFAZ_TO_ANEXO_XXI"
    assert "RICMS/TO" in ctx["fonte_nome"]
    assert ctx["regra_aplicada"] == "ICMS-ST/TO — AUTOPEÇAS — PROTOCOLO 97/10"


def test_mapa_cobertura_to_e_totais():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "TO")
    assert linha["nivel"] == 2
    assert "20%" in linha["icms"]
    assert "99,69%" in linha["observacao"]
    assert "86%" in linha["observacao"]
    d = CoberturaTributariaService.diagnostico()
    assert d["totais"] == {"ampliada": 1, "parcial": 25, "geral": 1}


def test_configurador_olist_nao_cria_tabela_to_paralela():
    fonte = Path("src/services/configurador_olist_service.py").read_text(encoding="utf-8")
    assert "ICMSUFService.analisar" in fonte
    assert '"TO": {' not in fonte
