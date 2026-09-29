from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.icms_uf_service import ICMSUFService
from src.services.icms_st_uf_service import (
    ICMSSTUFService, CEST_PNEUMATICOS_PI, MVA_AUTOPECAS_PI, _mva_ajustada_formula,
)
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.consulta_oficial_service import ConsultaOficialService


def analisar(ncm, fidelidade=False):
    return ICMSUFService.analisar(
        ncm,
        contexto={
            "uf_origem": "MG",
            "uf_destino": "PI",
            "operacao": "SAIDA",
            "contrato_fidelidade": fidelidade,
            "data_operacao": "2026-08-25",
        },
    )


def test_versao_e_cobertura_pi():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 67)
    assert "PI" in ICMSSTUFService.UFS_COBERTAS


def test_autopeca_mg_pi_padrao():
    r = analisar("87141000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_interna_destino"] == 22.5
    assert r["cest"] == "01.076.00"
    assert r["st_confirmado"] is True
    assert r["mva_original"] == 40.0
    assert r["mva_aplicada"] == 68.0
    assert r["fcp"] == 0.0
    assert "PI" in r["st_modelo_calculo"]
    assert "PROTOCOLO 41/08" in r["st_modelo_calculo"]
    assert "REMETENTE" in r["st_responsabilidade"]


def test_autopeca_fidelidade_pi_condicional():
    r = analisar("87141000", True)
    assert r["mva_original"] == 26.5
    assert r["mva_aplicada"] == 51.8
    assert "FIDELIDADE" in r["st_status"]
    assert "26,50" in r["observacao"]


def test_pneu_moto_mg_pi():
    r = analisar("40114000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_interna_destino"] == 22.5
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["mva_original"] == 60.0
    assert r["mva_aplicada"] == 92.0
    assert r["fcp"] == 0.0
    assert "PNEUMÁTICOS" in r["st_modelo_calculo"]


def test_tabelas_pi_e_formula():
    assert MVA_AUTOPECAS_PI["demais"]["ajustada"][7.0] == 68.0
    assert MVA_AUTOPECAS_PI["fidelidade"]["ajustada"][7.0] == 51.8
    assert CEST_PNEUMATICOS_PI["16.003.00"]["ajustada"][7.0] == 92.0
    assert _mva_ajustada_formula(40.0, 7.0, 22.5) == 68.0
    assert _mva_ajustada_formula(60.0, 7.0, 22.5) == 92.0


def test_fonte_contextual_pi():
    r = analisar("87141000")
    ctx = ConsultaOficialService.st_contextual({"icms_uf": r})
    assert ctx["fonte_codigo"] == "SEFAZ_PI_RICMS"
    assert "RICMS/PI" in ctx["fonte_nome"]
    assert ctx["regra_aplicada"] == "ICMS-ST/PI — AUTOPEÇAS — PROTOCOLO 41/08"


def test_mapa_cobertura_pi():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "PI")
    assert linha["nivel"] == 2
    assert "22,5%" in linha["icms"]
    assert "40,00%" in linha["observacao"]
    assert "92%" in linha["observacao"]
    d = CoberturaTributariaService.diagnostico()
    assert d["totais"] == {"ampliada": 1, "parcial": 25, "geral": 1}


def test_configurador_olist_nao_cria_tabela_pi_paralela():
    fonte = Path("src/services/configurador_olist_service.py").read_text(encoding="utf-8")
    assert "ICMSUFService.analisar" in fonte
    assert '"PI": {' not in fonte
