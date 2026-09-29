from types import SimpleNamespace

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


def _resultado_87141000():
    return {
        "ncm_confirmado": True,
        "ipi_confirmado": True,
        "icms_mg": {
            "aliquota_nominal": 18.0,
            "aliquota_confirmada": False,
            "confiabilidade_aliquota": 70.0,
            "aliquota_status": "PADRÃO RESIDUAL — REVISAR EXCEÇÕES DO ANEXO I",
        },
        "icms_st_mg": {
            "encontrado": True,
            "confirmado": True,
            "cest": "01.076.00",
            "mva_original": 71.78,
        },
        "piscofins_nacional": {
            "confirmado": False,
            "confiabilidade": 65.0,
            "status": "SUGESTÃO CONDICIONAL — REGIME NÃO CUMULATIVO",
        },
    }


def test_87141000_cfop_interno_st_mostra_alternativas_condicionais():
    exibicao = ConsultaOficialService.cfop_para_exibicao(
        _resultado_87141000(), CONTEXTO_MG, {"CFOP": "Não informado"}
    )

    assert exibicao["valor"] == "5405 / 5403 — condicional"
    assert exibicao["status"] == "CONDICIONAL"
    assert exibicao["confiabilidade"] == pytest.approx(65.0)
    assert "5405 quando o ICMS-ST já foi retido" in exibicao["observacao"]
    assert "5403 quando o estabelecimento for responsável" in exibicao["observacao"]


def test_cfop_local_real_continua_prevalecendo():
    exibicao = ConsultaOficialService.cfop_para_exibicao(
        _resultado_87141000(), CONTEXTO_MG, {"CFOP": "5405"}
    )

    assert exibicao["valor"] == "5405"
    assert exibicao["status"] == "CADASTRO LOCAL"


def test_revenda_interna_sem_st_sugere_5102_sem_forcar_cst():
    resultado = _resultado_87141000()
    resultado["icms_st_mg"] = {"encontrado": False, "confirmado": False}

    exibicao = ConsultaOficialService.cfop_para_exibicao(
        resultado, CONTEXTO_MG, {"CFOP": "Não informado"}
    )

    assert exibicao["valor"] == "5102"
    assert exibicao["status"] == "SUGESTÃO FORTE"


def test_seguranca_oficial_nao_fica_em_6_porcento_quando_fontes_estao_preenchidas():
    seguranca = ConsultaOficialService.confianca_oficial_para_exibicao(
        _resultado_87141000(), CONTEXTO_MG, {"CFOP": "Não informado"}
    )

    assert seguranca["nivel"] == "MÉDIA"
    assert seguranca["confiabilidade"] == pytest.approx(83.5)
    assert seguranca["confiabilidade"] < 85.0  # pontos condicionais impedem ALTA
    assert "ICMS-ST/CEST/MVA confirmados" in seguranca["detalhes"]


def test_aplicacao_oficial_atualiza_resumo_sem_promover_condicionais_a_confirmados():
    parecer = SimpleNamespace(
        ncm="87141000",
        contexto=dict(CONTEXTO_MG),
        tributacao_atual={"CFOP": "Não informado"},
        regras_aplicadas={},
        confiabilidade=6.0,
        nivel_confiabilidade="BAIXA",
        resumo_executivo="Resumo antigo com confiança baixa.",
        versao_motor="13.4",
    )

    ConsultaOficialService.aplicar_confianca_oficial_ao_parecer(
        parecer, _resultado_87141000()
    )

    assert parecer.confiabilidade == pytest.approx(83.5)
    assert parecer.nivel_confiabilidade == "MÉDIA"
    assert "Segurança geral da análise: média (84%)" in parecer.resumo_executivo
    assert "CFOP depende do contexto operacional" in parecer.resumo_executivo
    assert parecer.regras_aplicadas["seguranca_oficial_17_8_6"]["cfop"]["status"] == "CONDICIONAL"
    assert parecer.versao_motor == "17.8.6"
