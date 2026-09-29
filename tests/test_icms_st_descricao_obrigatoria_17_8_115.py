from types import SimpleNamespace

from src.services.icms_st_mg_service import ICMSSTMGService


CTX_MG = {"uf_origem": "MG", "uf_destino": "MG"}


def test_ncm_nominal_sem_aderencia_da_descricao_nao_confirma_st():
    r = ICMSSTMGService.analisar(
        "68138110", CTX_MG, "PRODUTO DECORATIVO PARA MOTOCICLETA"
    )

    assert r["confirmado"] is False
    assert r["exige_revisao"] is True
    assert r["decisao_st"] == "CONDICIONAL"
    assert r["cest"] == "01.014.00"
    assert "NCM isolado" in r["observacao"]


def test_plural_singular_nao_bloqueia_pastilha_de_freio_real():
    r = ICMSSTMGService.analisar(
        "68138110", CTX_MG, "PASTILHA DE FREIO BIZ 125"
    )

    assert r["confirmado"] is True
    assert r["exige_revisao"] is False
    assert r["decisao_st"] == "SIM"
    assert r["cest"] == "01.014.00"


def test_cola_nao_vira_residual_0199900_so_por_finalidade_automotiva():
    contexto = {
        **CTX_MG,
        "finalidade_automotiva": "PEÇA/COMPONENTE/ACESSÓRIO DE MOTO",
    }
    r = ICMSSTMGService.analisar(
        "35061090", contexto, "COLA INST 401 20G BICO PRECISAO"
    )

    assert r["confirmado"] is False
    assert r["decisao_st"] == "NAO"
    assert r["nao_aplicavel"] is True
    assert r["cest"] == ""
    assert r["cest_sugerido"] == ""
    assert r["mva_sugerida"] is None
    assert "Parte 2" in r["observacao"]


def test_componente_explicitamente_identificado_ainda_pode_usar_residual():
    contexto = {
        **CTX_MG,
        "finalidade_automotiva": "PEÇA/COMPONENTE/ACESSÓRIO DE MOTO",
    }
    r = ICMSSTMGService.analisar(
        "12345678", contexto, "COMPONENTE ESPECIFICO"
    )

    assert r["confirmado"] is True
    assert r["decisao_st"] == "SIM"
    assert r["cest"] == "01.999.00"


def test_cest_condicional_fica_como_sugestao_e_nao_e_gravado_como_confirmado():
    r = ICMSSTMGService.analisar(
        "68138110", CTX_MG, "PRODUTO DECORATIVO PARA MOTOCICLETA"
    )
    parecer = SimpleNamespace(
        tributacao_atual={"ICMS-ST": "NÃO"},
        dados_gerais={"CEST": ""},
        alertas=[],
        conclusoes=[],
        base_legal=[],
        fontes=[],
        pendencias=[],
        regras_aplicadas={},
        versao_motor="",
    )

    ICMSSTMGService.aplicar_ao_parecer(parecer, r)

    assert parecer.dados_gerais["CEST"] == ""
    assert parecer.tributacao_atual["ICMS-ST"] == "REVISAR"
    assert parecer.tributacao_atual["CEST sugerido MG"] == "01.014.00"
    assert "CEST oficial MG" not in parecer.tributacao_atual


def test_cola_sem_finalidade_tambem_nao_recebe_sugestao_residual():
    r = ICMSSTMGService.analisar(
        "35061090", CTX_MG, "COLA INST 401 20G BICO PRECISAO"
    )

    assert r["confirmado"] is False
    assert r["decisao_st"] == "NAO"
    assert r["nao_aplicavel"] is True
    assert r["cest_sugerido"] == ""
    assert r["mva_sugerida"] is None
    assert "3506" in r["status"]


def test_cabo_motor_partida_abreviado_continua_confirmado_no_residual():
    r = ICMSSTMGService.analisar(
        "85444200", CTX_MG, "CAB.MOT.PART. BIZ 125"
    )

    assert r["confirmado"] is True
    assert r["decisao_st"] == "SIM"
    assert r["cest"] == "01.999.00"
