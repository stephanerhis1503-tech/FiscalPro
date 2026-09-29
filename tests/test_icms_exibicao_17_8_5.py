import pytest

from src.services.consulta_oficial_service import ConsultaOficialService


CONTEXTO_MG = {
    "regime": "LUCRO REAL",
    "operacao": "SAÍDA",
    "finalidade": "REVENDA",
    "uf_origem": "MG",
    "uf_destino": "MG",
    "contribuinte": "TODOS",
    "data_operacao": "2026-08-12",
}


def _consulta_87141000():
    return ConsultaOficialService.consultar(
        "87141000",
        contexto=CONTEXTO_MG,
        descricao="Partes e acessórios de motocicletas",
    )


def test_87141000_exibe_aliquota_mg_sem_inventar_cst():
    consulta = _consulta_87141000()
    tributacao = {
        "CST/CSOSN ICMS": "Não informado",
        "ICMS": 0.0,
        "FCP": 0.0,
    }

    exibicao = ConsultaOficialService.icms_para_exibicao(consulta, tributacao)

    assert consulta["ncm_confirmado"] is True
    assert consulta["icms_mg"]["aliquota_nominal"] == pytest.approx(18.0)
    assert consulta["icms_st_mg"]["confirmado"] is True
    assert consulta["icms_st_mg"]["cest"] == "01.076.00"
    assert consulta["icms_st_mg"]["mva_original"] == pytest.approx(71.78)

    assert exibicao["origem"] == "ICMS/MG OFICIAL"
    assert exibicao["cst_definido"] is False
    assert exibicao["cst"] == ""
    assert exibicao["aliquota"] == pytest.approx(18.0)
    assert "ICMS-ST" in exibicao["observacao"]
    assert "não presume o CST" in exibicao["observacao"]


def test_cst_local_real_continua_prevalecendo_inclusive_com_aliquota_zero():
    consulta = _consulta_87141000()
    tributacao = {
        "CST/CSOSN ICMS": "60",
        "ICMS": 0.0,
    }

    exibicao = ConsultaOficialService.icms_para_exibicao(consulta, tributacao)

    assert exibicao["origem"] == "CADASTRO LOCAL"
    assert exibicao["cst_definido"] is True
    assert exibicao["cst"] == "60"
    assert exibicao["aliquota"] == pytest.approx(0.0)


def test_aliquota_local_sem_cst_fica_explicita_como_pendente_quando_nao_ha_oficial():
    consulta = {"icms_mg": {}, "icms_st_mg": {}}
    tributacao = {
        "CST/CSOSN ICMS": "Não informado",
        "ICMS": 12.0,
    }

    exibicao = ConsultaOficialService.icms_para_exibicao(consulta, tributacao)

    assert exibicao["origem"] == "CADASTRO LOCAL — CST PENDENTE"
    assert exibicao["cst_definido"] is False
    assert exibicao["aliquota"] == pytest.approx(12.0)
    assert "CST/CSOSN ainda não foi definido" in exibicao["observacao"]


def test_sem_cst_e_sem_aliquota_permanece_em_revisao():
    exibicao = ConsultaOficialService.icms_para_exibicao(
        {"icms_mg": {}, "icms_st_mg": {}},
        {"CST/CSOSN ICMS": "Não informado", "ICMS": 0.0},
    )

    assert exibicao["origem"] == "REVISAR"
    assert exibicao["cst_definido"] is False
    assert exibicao["aliquota"] is None
