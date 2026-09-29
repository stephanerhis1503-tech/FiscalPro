import pytest

from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.icms_st_mg_service import ICMSSTMGService
from src.services.icms_uf_service import ICMSUFService


def _pista(ncm: str):
    if ncm == "87141000":
        return {
            "encontrado": True,
            "confirmado": True,
            "cest": "01.076.00",
            "segmento": "AUTOPEÇAS",
            "ambito": "1.1",
            "descricao_legal": "Partes e acessórios de motocicletas",
        }
    if ncm == "40114000":
        return {
            "encontrado": True,
            "confirmado": True,
            "cest": "16.003.00",
            "segmento": "PNEUMÁTICOS",
            "ambito": "16.1",
            "descricao_legal": "Pneus novos para motocicletas",
        }
    if ncm == "40111000":
        return {
            "encontrado": True,
            "confirmado": True,
            "cest": "16.001.00",
            "segmento": "PNEUMÁTICOS",
            "ambito": "16.1",
            "descricao_legal": "Pneus novos para automóveis",
        }
    return {
        "encontrado": False,
        "confirmado": False,
        "cest": "",
        "segmento": "",
        "ambito": "",
        "descricao_legal": "",
    }


@pytest.fixture(autouse=True)
def _mock_pista_mg(monkeypatch):
    def fake_analisar(cls, ncm, contexto=None, descricao=""):
        return _pista(str(ncm))
    monkeypatch.setattr(ICMSSTMGService, "analisar", classmethod(fake_analisar))


def _analisar(ncm: str, descricao: str, origem: str = "MG", importada: bool = False):
    return ICMSUFService.analisar(
        ncm,
        contexto={
            "uf_origem": origem,
            "uf_destino": "RJ",
            "data_operacao": "2026-08-21",
            "mercadoria_importada": importada,
        },
        descricao=descricao,
    )


def test_versao_17_8_43():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 43)


def test_autopeca_mg_para_rj_modal_20_fecp_2_e_mva_88_96():
    r = _analisar("87141000", "Partes e acessórios de motocicletas")
    assert r["aliquota_operacao"] == pytest.approx(12.0)
    assert r["aliquota_interna_destino"] == pytest.approx(20.0)
    assert r["fcp"] == pytest.approx(2.0)
    assert r["fcp_confirmado"] is True
    assert "AUTOMOTIVO" in r["fcp_status"]
    assert r["cest"] == "01.076.00"
    assert r["segmento_st"] == "AUTOPEÇAS"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == pytest.approx(71.78)
    assert r["mva_ajustada"] == pytest.approx(88.96)
    assert r["mva_aplicada"] == pytest.approx(88.96)
    assert "AUTOPEÇAS" in r["st_status"]


def test_autopeca_rj_interna_usa_mva_original_71_78():
    r = _analisar("87141000", "Partes e acessórios de motocicletas", origem="RJ")
    assert r["aliquota_operacao"] == pytest.approx(20.0)
    assert r["mva_original"] == pytest.approx(71.78)
    assert r["mva_ajustada"] is None
    assert r["mva_aplicada"] == pytest.approx(71.78)


def test_autopeca_importada_4_porcento_usa_mva_106_14():
    r = _analisar("87141000", "Partes e acessórios de motocicletas", importada=True)
    assert r["aliquota_operacao"] == pytest.approx(4.0)
    assert r["mva_ajustada"] == pytest.approx(106.14)


def test_pneu_moto_mg_para_rj_confirma_cest_mva_76_e_fecp_2():
    r = _analisar("40114000", "Pneu novo para motocicleta")
    assert r["aliquota_operacao"] == pytest.approx(12.0)
    assert r["aliquota_interna_destino"] == pytest.approx(20.0)
    assert r["fcp"] == pytest.approx(2.0)
    assert r["fcp_confirmado"] is True
    assert r["cest"] == "16.003.00"
    assert r["segmento_st"] == "PNEUMÁTICOS"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == pytest.approx(60.0)
    assert r["mva_ajustada"] == pytest.approx(76.0)
    assert r["mva_aplicada"] == pytest.approx(76.0)
    assert "PNEUMÁTICOS" in r["st_status"]
    assert "102/17" in r["fundamento_st"]


def test_pneu_moto_rj_interno_usa_mva_original_60():
    r = _analisar("40114000", "Pneu novo para motocicleta", origem="RJ")
    assert r["mva_original"] == pytest.approx(60.0)
    assert r["mva_ajustada"] is None
    assert r["mva_aplicada"] == pytest.approx(60.0)


def test_pneu_importado_4_porcento_usa_mva_92():
    r = _analisar("40114000", "Pneu novo para motocicleta", importada=True)
    assert r["aliquota_operacao"] == pytest.approx(4.0)
    assert r["mva_ajustada"] == pytest.approx(92.0)


def test_pneu_fora_da_tabela_estruturada_nao_vira_falso_sem_st(monkeypatch):
    def fake_excluido(cls, ncm, contexto=None, descricao=""):
        return {
            "encontrado": True,
            "confirmado": False,
            "cest": "16.005.00",
            "segmento": "PNEUMÁTICOS",
            "ambito": "16.1",
            "descricao_legal": "Pneu fora da tabela RJ estruturada",
        }
    monkeypatch.setattr(ICMSSTMGService, "analisar", classmethod(fake_excluido))
    r = _analisar("40119090", "Pneu especial")
    assert r["st_confirmado"] is False
    assert r["st_decisao_confirmada"] is False
    assert "FORA DA COBERTURA" in r["st_status"] or "FORA DA TABELA" in r["st_status"]


def test_mapa_rj_mostra_autopecas_pneumaticos_e_fecp(monkeypatch):
    monkeypatch.setattr(CoberturaTributariaService, "resumo_bases", classmethod(lambda cls: {
        "ncm_oficial": 11423,
        "tipi_oficial": 11102,
        "piscofins": "Motor federal nacional ativo",
        "st_mg_registros": 247,
        "st_mg_ncm": 229,
        "st_mg_segmentos": ["AUTOPEÇAS", "PNEUMÁTICOS", "MATERIAIS DE CONSTRUÇÃO E CONGÊNERES"],
        "st_mg_atualizado_em": "",
        "base_nacional_versao": "",
        "base_nacional_referencia": "",
        "base_nacional_data": "",
    }))
    monkeypatch.setattr(CoberturaTributariaService, "_ufs_recentes", classmethod(lambda cls: set()))
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "RJ")
    assert linha["status"] == "COBERTURA ESTADUAL PARCIAL"
    assert "20%" in linha["icms"]
    assert "Autopeças + pneumáticos" in linha["st"]
    assert "2%" in linha["fcp"]
    assert "17.8.43" in linha["observacao"]
