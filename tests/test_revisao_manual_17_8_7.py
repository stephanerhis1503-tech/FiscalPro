from types import SimpleNamespace

import pytest

from src.repositorios.ficha_tributaria_repository import FichaTributariaRepository
from src.services.icms_st_mg_service import ICMSSTMGService
from src.services.piscofins_monofasico_service import PISCOFINSMonofasicoService
from src.services.piscofins_nacional_service import PISCOFINSNacionalService
from src.services.consulta_oficial_service import ConsultaOficialService


def _parecer_manual():
    return SimpleNamespace(
        ncm="84879000",
        contexto={
            "regime": "LUCRO REAL",
            "operacao": "SAÍDA",
            "finalidade": "REVENDA",
            "uf_origem": "MG",
            "uf_destino": "MG",
            "contribuinte": "TODOS",
            "data_operacao": "2026-08-12",
        },
        dados_gerais={"CEST": "9999999"},
        tributacao_atual={
            "Revisão manual": True,
            "CEST": "1234567",
            "MVA ST": 44.5,
            "ICMS-ST": "SIM",
            "CST PIS": "01",
            "PIS": 1.65,
            "CST COFINS": "01",
            "COFINS": 7.6,
            "CFOP": "5405",
        },
        regras_aplicadas={},
        base_legal=[],
        fontes=[],
        conclusoes=[],
        fundamentos=[],
        alertas=[],
        pendencias=[],
        confiabilidade=70.0,
        nivel_confiabilidade="MÉDIA",
        resumo_executivo="",
        versao_motor="17.8.6",
    )


def test_normalizacao_regra_manual_guarda_cest_mva_e_marca_manual():
    dados = FichaTributariaRepository._normalizar_tributacao_atual(
        {
            "ncm": "84879000",
            "empresa": "",
            "uf_origem": "MG",
            "uf_destino": "MG",
            "regime": "LUCRO REAL",
            "operacao": "SAÍDA",
            "finalidade": "REVENDA",
            "contribuinte": "TODOS",
            "cfop": "5405",
            "cest": "01.076.00",
            "mva_st": "71,78",
            "revisao_manual": 1,
            "cst_icms": "60",
            "icms": "18",
            "icms_st": "SIM",
            "cst_pis": "01",
            "aliquota_pis": "1,65",
            "cst_cofins": "01",
            "aliquota_cofins": "7,60",
            "cst_ipi": "50",
            "ipi": "9",
            "vigencia_inicio": "12/08/2026",
            "status": "VIGENTE",
            "fonte": "ALTERAÇÃO MANUAL — USUÁRIO",
            "confiabilidade": "95",
        }
    )

    assert dados["cest"] == "0107600"
    assert dados["mva_st"] == pytest.approx(71.78)
    assert dados["revisao_manual"] == 1
    assert dados["cfop"] == "5405"


def test_icms_st_oficial_nao_sobrescreve_regra_manual():
    parecer = _parecer_manual()
    resultado = {
        "encontrado": True,
        "confirmado": True,
        "cest": "01.076.00",
        "mva_original": 71.78,
        "segmento": "autopeças",
        "ambito": "MG",
        "fundamento": "RICMS/MG",
        "artigo_item": "Anexo VII",
        "fonte_url": "https://example.invalid/oficial",
    }

    ICMSSTMGService.aplicar_ao_parecer(parecer, resultado)

    assert parecer.tributacao_atual["ICMS-ST"] == "SIM"
    assert parecer.tributacao_atual["MVA ST"] == pytest.approx(44.5)
    assert parecer.dados_gerais["CEST"] == "9999999"
    assert parecer.tributacao_atual["CEST oficial MG"] == "01.076.00"
    assert parecer.tributacao_atual["ICMS-ST oficial MG — comparação"] == "SIM"
    assert any("não sobrescreveu" in alerta for alerta in parecer.alertas)


def test_piscofins_monofasico_oficial_nao_sobrescreve_regra_manual():
    parecer = _parecer_manual()
    resultado = {
        "confirmado": True,
        "cst_pis": "04",
        "aliquota_pis": 0.0,
        "cst_cofins": "04",
        "aliquota_cofins": 0.0,
        "fundamento": "Lei 10.485/2002",
        "artigo": "art. 3º",
        "fonte_url": "https://example.invalid/lei",
        "ncm": "84879000",
        "enquadramento": "Anexo",
        "codigo_legal": "84879000",
    }

    PISCOFINSMonofasicoService.aplicar_ao_parecer(parecer, resultado)

    assert parecer.tributacao_atual["CST PIS"] == "01"
    assert parecer.tributacao_atual["PIS"] == pytest.approx(1.65)
    assert parecer.tributacao_atual["CST COFINS"] == "01"
    assert parecer.tributacao_atual["COFINS"] == pytest.approx(7.6)
    assert "PIS/COFINS oficial — comparação" in parecer.tributacao_atual


def test_piscofins_nacional_confirmado_nao_sobrescreve_regra_manual():
    parecer = _parecer_manual()
    resultado = {
        "confirmado": True,
        "cst_pis": "08",
        "aliquota_pis": 0.0,
        "cst_cofins": "08",
        "aliquota_cofins": 0.0,
        "status": "EXPORTAÇÃO",
        "fundamento": "Lei",
        "artigo": "artigo",
        "fonte_url": "https://example.invalid/fonte",
        "observacao": "Comparação oficial",
    }

    PISCOFINSNacionalService.aplicar_ao_parecer(parecer, resultado)

    assert parecer.tributacao_atual["CST PIS"] == "01"
    assert parecer.tributacao_atual["PIS"] == pytest.approx(1.65)
    assert parecer.tributacao_atual["CST COFINS"] == "01"
    assert parecer.tributacao_atual["COFINS"] == pytest.approx(7.6)
    assert "PIS/COFINS nacional — comparação" in parecer.tributacao_atual


def test_resumo_oficial_identifica_regra_manual_preservada():
    parecer = _parecer_manual()
    consulta = {
        "ncm_confirmado": True,
        "ipi_confirmado": True,
        "icms_mg": {
            "aliquota_nominal": 18.0,
            "aliquota_confirmada": False,
            "confiabilidade_aliquota": 70.0,
        },
        "icms_st_mg": {"encontrado": False, "confirmado": False},
        "piscofins_nacional": {"confirmado": False, "confiabilidade": 65.0},
    }

    ConsultaOficialService.aplicar_confianca_oficial_ao_parecer(parecer, consulta)

    assert "existe uma regra manual salva e preservada" in parecer.resumo_executivo
