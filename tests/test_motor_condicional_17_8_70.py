from types import SimpleNamespace

from src.services.icms_st_mg_service import ICMSSTMGService


CTX_MG = {"uf_origem": "MG", "uf_destino": "MG"}


def test_ausencia_nominal_nunca_vira_nao_st():
    r = ICMSSTMGService.analisar("12345678", CTX_MG, "PRODUTO SEM REGRA NOMINAL")
    assert r["confirmado"] is False
    assert r["decisao_st"] == "CONDICIONAL"
    assert r["status"].startswith("CONDICIONAL")
    assert r["cest_sugerido"] == "01.999.00"
    assert r["mva_sugerida"] == 71.78


def test_finalidade_confirmada_aplica_residual():
    contexto = {
        **CTX_MG,
        "finalidade_automotiva": "PEÇA/COMPONENTE/ACESSÓRIO DE MOTO",
    }
    r = ICMSSTMGService.analisar("12345678", contexto, "COMPONENTE ESPECÍFICO")
    assert r["confirmado"] is True
    assert r["decisao_st"] == "SIM"
    assert r["cest"] == "01.999.00"
    assert r["mva_original"] == 71.78


def test_finalidade_negada_nao_produz_negativa_geral_sem_base_legal():
    contexto = {**CTX_MG, "finalidade_automotiva": "NÃO É PEÇA AUTOMOTIVA"}
    r = ICMSSTMGService.analisar("12345678", contexto, "PRODUTO GENÉRICO")
    assert r["confirmado"] is False
    assert r["exige_revisao"] is True
    assert r["decisao_st"] == "CONDICIONAL"
    assert "OUTROS SEGMENTOS" in r["status"]


def test_cabo_motor_partida_validado_no_residual():
    r = ICMSSTMGService.analisar("85444200", CTX_MG, "CABO DO MOTOR DE PARTIDA")
    assert r["confirmado"] is True
    assert r["cest"] == "01.999.00"
    assert r["mva_original"] == 71.78


def test_ncm_sem_descricao_continua_condicional():
    r = ICMSSTMGService.analisar("85444200", CTX_MG, "")
    assert r["confirmado"] is False
    assert r["decisao_st"] == "CONDICIONAL"


def test_parecer_local_nao_e_substituido_por_condicional():
    r = ICMSSTMGService.analisar("12345678", CTX_MG, "PRODUTO SEM REGRA")
    parecer = SimpleNamespace(
        tributacao_atual={"ICMS-ST": "NÃO"},
        dados_gerais={},
        alertas=[],
        conclusoes=[],
        regras_aplicadas={},
    )
    ICMSSTMGService.aplicar_ao_parecer(parecer, r)
    assert parecer.tributacao_atual["ICMS-ST"].startswith("CONDICIONAL")
    assert parecer.alertas


def test_enquadramento_especifico_continua_prevalecendo():
    r = ICMSSTMGService.analisar("85365090", CTX_MG, "INTERRUPTOR DE MOTO")
    assert r["confirmado"] is True
    assert r["cest"] == "01.065.00"
    assert r["mva_original"] == 71.78
