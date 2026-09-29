from types import SimpleNamespace

from src.services.icms_st_mg_service import ICMSSTMGService


CTX_MG = {
    "uf_origem": "MG",
    "uf_destino": "MG",
    "finalidade_automotiva": "NÃO É PEÇA AUTOMOTIVA",
}


def test_cola_35061090_retorna_nao_st_sem_cest_mva():
    r = ICMSSTMGService.analisar(
        "35061090", CTX_MG, "COLA INST. 401 20G BICO PRECISAO"
    )

    assert r["encontrado"] is False
    assert r["confirmado"] is False
    assert r["exige_revisao"] is False
    assert r["decisao_st"] == "NAO"
    assert r["nao_aplicavel"] is True
    assert r["aplicabilidade_segmento"] == "NCM_FORA_ANEXO_VII_PARTE_2"
    assert r["cest"] == ""
    assert r["cest_sugerido"] == ""
    assert r["mva_original"] is None
    assert r["mva_sugerida"] is None
    assert r["potencial"] is False


def test_toda_posicao_3506_usa_mesma_negativa_legal_mg():
    r = ICMSSTMGService.analisar(
        "35069990", {"uf_origem": "MG", "uf_destino": "MG"}, "ADESIVO PREPARADO"
    )
    assert r["decisao_st"] == "NAO"
    assert r["exige_revisao"] is False
    assert "3506" in r["status"]


def test_negativa_3506_limpa_cest_mva_antigos_do_parecer():
    r = ICMSSTMGService.analisar(
        "35061090", CTX_MG, "COLA INST. 401 20G BICO PRECISAO"
    )
    parecer = SimpleNamespace(
        tributacao_atual={
            "ICMS-ST": "CONDICIONAL",
            "CEST sugerido MG": "01.999.00",
            "MVA sugerida MG": 71.78,
            "MVA ST oficial MG": 71.78,
        },
        dados_gerais={"CEST": "0199900"},
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
    assert "NÃO" in parecer.tributacao_atual["ICMS-ST"]
    assert "CEST sugerido MG" not in parecer.tributacao_atual
    assert "MVA sugerida MG" not in parecer.tributacao_atual
    assert "MVA ST oficial MG" not in parecer.tributacao_atual
    assert any("ICMS-ST = NÃO" in c for c in parecer.conclusoes)


def test_ncm_qualquer_sem_cobertura_continua_condicional():
    r = ICMSSTMGService.analisar(
        "12345678", {"uf_origem": "MG", "uf_destino": "MG"}, "PRODUTO GENERICO"
    )
    assert r["decisao_st"] == "CONDICIONAL"
    assert r["exige_revisao"] is True
