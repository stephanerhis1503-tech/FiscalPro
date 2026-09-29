import pytest

from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.consulta_oficial_service import ConsultaOficialService
from src.services.icms_st_uf_service import ICMSSTUFService
from src.services.icms_uf_service import ICMSUFService


def test_base_sp_preservada_na_17_8_41():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 40)


def test_autopeca_mg_para_sp_usa_modal_18_e_iva_ajustado_ate_setembro():
    r = ICMSUFService.analisar(
        "87141000",
        contexto={"uf_origem": "MG", "uf_destino": "SP", "data_operacao": "2026-08-21"},
        descricao="Partes e acessórios de motocicletas",
    )
    assert r["aliquota_operacao"] == pytest.approx(12.0)
    assert r["aliquota_interna_destino"] == pytest.approx(18.0)
    assert r["fcp"] == pytest.approx(0.0)
    assert r["fcp_confirmado"] is True
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["cest"] == "01.076.00"
    assert r["mva_original"] == pytest.approx(72.15)
    assert r["mva_ajustada"] == pytest.approx(84.75)
    assert r["mva_aplicada"] == pytest.approx(84.75)
    assert r["st_vigencia_fim"] == "2026-09-30"
    assert "AUTOPEÇAS" in r["st_status"]


def test_autopeca_sp_com_fidelidade_nao_usa_iva_padrao():
    r = ICMSUFService.analisar(
        "87141000",
        contexto={
            "uf_origem": "MG",
            "uf_destino": "SP",
            "data_operacao": "2026-08-21",
            "contrato_fidelidade": True,
        },
        descricao="Partes e acessórios de motocicletas",
    )
    assert r["st_confirmado"] is True
    assert r["mva_original"] == pytest.approx(47.19)
    assert r["mva_ajustada"] == pytest.approx(57.96)


def test_pneu_moto_mg_para_sp_confirma_cest_e_iva_77_12_ajustado():
    r = ICMSUFService.analisar(
        "40114000",
        contexto={"uf_origem": "MG", "uf_destino": "SP", "data_operacao": "2026-08-21"},
        descricao="Pneu novo para motocicleta",
    )
    assert r["aliquota_operacao"] == pytest.approx(12.0)
    assert r["aliquota_interna_destino"] == pytest.approx(18.0)
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["cest"] == "16.003.00"
    assert r["segmento_st"] == "PNEUMÁTICOS"
    assert r["mva_original"] == pytest.approx(77.12)
    assert r["mva_ajustada"] == pytest.approx(90.08)
    assert r["mva_aplicada"] == pytest.approx(90.08)
    assert "Convênio ICMS 102/17" in r["fundamento_st"]


def test_sp_revoga_st_autopecas_e_pneumaticos_em_01_10_2026():
    for ncm, descricao in [
        ("87141000", "Partes e acessórios de motocicletas"),
        ("40114000", "Pneu novo para motocicleta"),
    ]:
        r = ICMSUFService.analisar(
            ncm,
            contexto={"uf_origem": "MG", "uf_destino": "SP", "data_operacao": "2026-10-01"},
            descricao=descricao,
        )
        assert r["st_confirmado"] is False
        assert r["st_decisao_confirmada"] is True
        assert r["mva_aplicada"] is None
        assert "A PARTIR DE 01/10/2026" in r["st_status"]
        assert "Portaria SRE 34/2026" in r["fundamento_st"]


def test_vidro_cest_01_015_ja_nao_tem_st_sp_em_2026():
    r = ICMSUFService.analisar(
        "70071100",
        contexto={"uf_origem": "MG", "uf_destino": "SP", "data_operacao": "2026-08-21"},
        descricao="Vidros temperados para veículos",
    )
    assert r["cest"] == "01.015.00"
    assert r["st_confirmado"] is False
    assert r["st_decisao_confirmada"] is True
    assert "REVOGADO EM 01/01/2026" in r["st_status"]


def test_bateria_sp_fica_em_revisao_e_nao_recebe_iva_generico_72_15():
    r = ICMSUFService.analisar(
        "85071000",
        contexto={"uf_origem": "MG", "uf_destino": "SP", "data_operacao": "2026-08-21"},
        descricao="Acumulador elétrico de chumbo para partida",
    )
    assert r["cest"] == "01.053.00"
    assert r["st_confirmado"] is False
    assert r["st_decisao_confirmada"] is False
    assert r["mva_original"] is None
    assert r["mva_aplicada"] is None
    assert "BATERIAS/SP" in r["st_status"]


def test_consulta_oficial_expoe_sp_com_uf_correta_e_st_contextual():
    r = ConsultaOficialService.consultar(
        "87141000",
        contexto={
            "empresa": "Mega Motos Comércio",
            "operacao": "SAÍDA",
            "finalidade": "REVENDA",
            "uf_origem": "MG",
            "uf_destino": "SP",
            "data_operacao": "2026-08-21",
        },
        descricao="Partes e acessórios de motocicletas",
    )
    st = ConsultaOficialService.st_contextual(r)
    icms = ConsultaOficialService.icms_contextual(r)
    assert st["confirmado"] is True
    assert st["uf"] == "SP"
    assert st["mva_aplicada"] == pytest.approx(84.75)
    assert icms["uf"] == "SP"
    assert icms["aliquota_nominal"] == pytest.approx(12.0)


def test_mapa_sp_expoe_transicao_ate_30_09_2026():
    d = CoberturaTributariaService.diagnostico()
    sp = next(x for x in d["ufs"] if x["uf"] == "SP")
    assert sp["nivel"] == 2
    assert "18%" in sp["icms"]
    assert "Autopeças + pneumáticos" in sp["st"]
    assert "30/09/2026" in sp["st"]
    assert "2203" in sp["fcp"] and "24" in sp["fcp"]
    assert "01/10/2026" in sp["observacao"]
    assert d["totais"] == {"ampliada": 1, "parcial": 25, "geral": 1}
