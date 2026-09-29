import pytest

from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.icms_uf_service import ICMSUFService


def _analisar(ncm: str, descricao: str, origem: str = "MG", fidelidade: bool = False):
    return ICMSUFService.analisar(
        ncm,
        contexto={
            "uf_origem": origem,
            "uf_destino": "BA",
            "data_operacao": "2026-08-21",
            "contrato_fidelidade": fidelidade,
        },
        descricao=descricao,
    )


def test_versao_17_8_41():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 41)


def test_autopeca_mg_para_ba_usa_modal_20_5_mva_oficial_e_fecop_zero():
    r = _analisar("87141000", "Partes e acessórios de motocicletas")
    assert r["aliquota_operacao"] == pytest.approx(7.0)
    assert r["aliquota_interna_destino"] == pytest.approx(20.5)
    assert r["fcp"] == pytest.approx(0.0)
    assert r["fcp_confirmado"] is True
    assert "NÃO APLICÁVEL" in r["fcp_status"]
    assert r["cest"] == "01.076.00"
    assert r["segmento_st"] == "AUTOPEÇAS"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == pytest.approx(71.78)
    assert r["mva_ajustada"] == pytest.approx(100.95)
    assert r["mva_aplicada"] == pytest.approx(100.95)
    assert "Anexo 1" in r["fundamento_st"]


def test_autopeca_ba_interna_usa_mva_original_71_78():
    r = _analisar("87141000", "Partes e acessórios de motocicletas", origem="BA")
    assert r["aliquota_operacao"] == pytest.approx(20.5)
    assert r["mva_original"] == pytest.approx(71.78)
    assert r["mva_ajustada"] is None
    assert r["mva_aplicada"] == pytest.approx(71.78)


def test_autopeca_fidelidade_mg_para_ba_usa_tabela_oficial_59_75():
    r = _analisar("87141000", "Partes e acessórios de motocicletas", fidelidade=True)
    assert r["mva_original"] == pytest.approx(36.56)
    assert r["mva_ajustada"] == pytest.approx(59.75)
    assert r["mva_aplicada"] == pytest.approx(59.75)


def test_pneu_moto_mg_para_ba_confirma_cest_mva_e_fecop_zero():
    r = _analisar("40114000", "Pneu novo para motocicleta")
    assert r["aliquota_operacao"] == pytest.approx(7.0)
    assert r["aliquota_interna_destino"] == pytest.approx(20.5)
    assert r["fcp"] == pytest.approx(0.0)
    assert r["fcp_confirmado"] is True
    assert r["cest"] == "16.003.00"
    assert r["segmento_st"] == "PNEUMÁTICOS"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == pytest.approx(60.0)
    assert r["mva_ajustada"] == pytest.approx(87.17)
    assert r["mva_aplicada"] == pytest.approx(87.17)
    assert "PNEUMÁTICOS" in r["st_status"]


def test_pneu_moto_ba_interno_usa_mva_original_60():
    r = _analisar("40114000", "Pneu novo para motocicleta", origem="BA")
    assert r["mva_original"] == pytest.approx(60.0)
    assert r["mva_ajustada"] is None
    assert r["mva_aplicada"] == pytest.approx(60.0)


def test_fecop_ba_permanece_2_porcento_em_hipotese_reconhecida():
    r = ICMSUFService.analisar(
        "22030000",
        contexto={"uf_origem": "BA", "uf_destino": "BA", "data_operacao": "2026-08-21"},
        descricao="Cerveja",
    )
    assert r["fcp"] == pytest.approx(2.0)
    assert r["fcp_confirmado"] is True


def test_mapa_bahia_mostra_autopecas_pneumaticos_e_fecop_objetivo():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "BA")
    assert linha["status"] == "COBERTURA ESTADUAL PARCIAL"
    assert "20,5%" in linha["icms"]
    assert "Autopeças + pneumáticos" in linha["st"]
    assert "0% confirmado" in linha["fcp"]
    assert "17.8.41" in linha["observacao"]


def test_bahia_nao_transforma_segmento_fora_da_cobertura_em_falso_sem_st():
    r = _analisar("25232910", "Cimento Portland")
    assert r["st_decisao_confirmada"] is False
    assert "FORA DA COBERTURA" in r["st_status"] or "NÃO IDENTIFICADO" in r["st_status"]
