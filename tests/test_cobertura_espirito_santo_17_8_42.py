from datetime import date

import pytest

from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.icms_uf_service import ICMSUFService


def _analisar(ncm: str, descricao: str, origem: str = "MG", data_operacao: str = "2026-08-21"):
    return ICMSUFService.analisar(
        ncm,
        contexto={
            "uf_origem": origem,
            "uf_destino": "ES",
            "data_operacao": data_operacao,
        },
        descricao=descricao,
    )


def test_versao_17_8_42():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 42)


def test_es_modal_17_e_fcp_zero_para_autopeca():
    r = _analisar("87141000", "Partes e acessórios de motocicletas")
    assert r["aliquota_operacao"] == pytest.approx(7.0)
    assert r["aliquota_interna_destino"] == pytest.approx(17.0)
    assert r["fcp"] == pytest.approx(0.0)
    assert r["fcp_confirmado"] is True
    assert "ART. 20-A" in r["fcp_status"]


def test_autopeca_es_2026_nao_confirma_st_generica_e_manda_revisar_antecipacao_parcial():
    r = _analisar("87141000", "Partes e acessórios de motocicletas")
    assert r["cest"] == "01.076.00"
    assert r["segmento_st"] == "AUTOPEÇAS"
    assert r["st_confirmado"] is False
    assert r["st_decisao_confirmada"] is False
    assert r["mva_original"] is None
    assert r["mva_ajustada"] is None
    assert r["mva_aplicada"] is None
    assert "ANTECIPAÇÃO PARCIAL" in r["st_status"]
    assert "41/08" in r["st_acordo_status"]
    assert "13-R/2022" in r["fundamento_st"]


def test_autopeca_es_historica_antes_da_denuncia_preserva_regra_legada():
    r = _analisar(
        "87141000",
        "Partes e acessórios de motocicletas",
        data_operacao="2022-02-02",
    )
    assert r["st_confirmado"] is True
    assert r["mva_original"] == pytest.approx(71.78)
    assert r["mva_ajustada"] == pytest.approx(92.47)
    assert r["st_vigencia_fim"] == "2022-02-02"
    assert "HISTÓRICO" in r["st_status"]


def test_pneu_moto_mg_para_es_confirma_cest_mva_e_fcp_zero():
    r = _analisar("40114000", "Pneu novo para motocicleta")
    assert r["aliquota_operacao"] == pytest.approx(7.0)
    assert r["aliquota_interna_destino"] == pytest.approx(17.0)
    assert r["fcp"] == pytest.approx(0.0)
    assert r["fcp_confirmado"] is True
    assert r["cest"] == "16.003.00"
    assert r["segmento_st"] == "PNEUMÁTICOS"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == pytest.approx(60.0)
    assert r["mva_ajustada"] == pytest.approx(79.28)
    assert r["mva_aplicada"] == pytest.approx(79.28)
    assert "PNEUMÁTICOS" in r["st_status"]
    assert "16-R/2019" in r["fundamento_st"]


def test_pneu_moto_es_interno_usa_mva_original_60():
    r = _analisar("40114000", "Pneu novo para motocicleta", origem="ES")
    assert r["aliquota_operacao"] == pytest.approx(17.0)
    assert r["mva_original"] == pytest.approx(60.0)
    assert r["mva_ajustada"] is None
    assert r["mva_aplicada"] == pytest.approx(60.0)


def test_fcp_es_permanece_2_porcento_para_bebida_alcoolica():
    r = ICMSUFService.analisar(
        "22030000",
        contexto={"uf_origem": "ES", "uf_destino": "ES", "data_operacao": "2026-08-21"},
        descricao="Cerveja",
    )
    assert r["fcp"] == pytest.approx(2.0)
    assert r["fcp_confirmado"] is True


def test_mapa_es_explica_pneumaticos_e_antecipacao_parcial_autopecas():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "ES")
    assert linha["status"] == "COBERTURA ESTADUAL PARCIAL"
    assert "17%" in linha["icms"]
    assert "Pneumáticos detalhados" in linha["st"]
    assert "antecipação parcial" in linha["st"]
    assert "automotivo 0%" in linha["fcp"]
    assert "17.8.42" in linha["observacao"]


def test_es_nao_transforma_segmento_fora_da_cobertura_em_falso_sem_st():
    r = _analisar("25232910", "Cimento Portland")
    assert r["st_decisao_confirmada"] is False
    assert "FORA DA COBERTURA" in r["st_status"] or "NÃO IDENTIFICADO" in r["st_status"]
