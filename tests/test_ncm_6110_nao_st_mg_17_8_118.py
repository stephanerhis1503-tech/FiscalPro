from src.services.icms_st_mg_service import ICMSSTMGService


CTX_MG = {
    "uf_origem": "MG",
    "uf_destino": "MG",
    "finalidade_automotiva": "NÃO É PEÇA AUTOMOTIVA",
}


def test_colete_61103000_retorna_nao_st_mg_sem_cest_mva():
    r = ICMSSTMGService.analisar("61103000", CTX_MG, "COLETE")

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
    assert "6110" in r["status"]


def test_posicao_6110_inteira_usa_negativa_conferida():
    r = ICMSSTMGService.analisar("61109000", CTX_MG, "COLETE DE MALHA")
    assert r["decisao_st"] == "NAO"
    assert r["exige_revisao"] is False
    assert r["ncm_legal"] == "6110"


def test_outro_ncm_sem_cobertura_continua_condicional():
    r = ICMSSTMGService.analisar("12345678", CTX_MG, "PRODUTO GENERICO")
    assert r["decisao_st"] == "CONDICIONAL"
    assert r["exige_revisao"] is True
