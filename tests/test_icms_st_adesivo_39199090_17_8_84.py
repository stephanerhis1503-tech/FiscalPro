from types import SimpleNamespace

from src.services.consulta_oficial_service import ConsultaOficialService
from src.services.icms_st_mg_service import ICMSSTMGService
from src.services.indicador_seguranca_tributaria import IndicadorSegurancaTributaria


CTX_MG = {"uf_origem": "MG", "uf_destino": "MG"}


def test_adesivo_kit_prata_biz125_nao_aplica_cest_0109000():
    r = ICMSSTMGService.analisar(
        "39199090", CTX_MG, "ADESIVO KIT PRATA BIZ125"
    )

    assert r["nao_aplicavel"] is True
    assert r["decisao_st"] == "NAO"
    assert r["confirmado"] is False
    assert r["exige_revisao"] is False
    assert r["cest"] == ""
    assert r["mva_original"] is None
    assert "REFLETIVO" in r["status"]
    assert "01.999.00" in r["observacao"]
    assert "não deve ser aplicado automaticamente" in r["observacao"]


def test_adesivo_refletivo_de_seguranca_mantem_st():
    r = ICMSSTMGService.analisar(
        "39199090", CTX_MG, "ADESIVO REFLETIVO SEGURANCA MOTO"
    )

    assert r["nao_aplicavel"] is False
    assert r["decisao_st"] == "SIM"
    assert r["confirmado"] is True
    assert r["cest"] == "01.090.00"
    assert r["mva_original"] == 71.78


def test_39199090_sem_descricao_suficiente_nao_confirma_por_ncm_sozinho():
    r = ICMSSTMGService.analisar(
        "39199090", CTX_MG, "ADESIVO 39199090"
    )

    assert r["confirmado"] is False
    assert r["nao_aplicavel"] is False
    assert r["decisao_st"] == "CONDICIONAL"
    assert r["exige_revisao"] is True
    assert r["cest"] == ""
    assert r["cest_sugerido"] == "01.090.00"
    assert r["mva_sugerida"] == 71.78
    assert "NCM isolado" in r["observacao"]


def test_finalidade_automotiva_nao_forca_residual_0199900_no_39199090():
    r = ICMSSTMGService.analisar(
        "39199090",
        {**CTX_MG, "finalidade_automotiva": "PEÇA/COMPONENTE/ACESSÓRIO DE MOTO"},
        "ADESIVO KIT PRATA BIZ125",
    )

    assert r["decisao_st"] == "NAO"
    assert r["cest"] == ""
    assert r["mva_original"] is None
    assert r["cest_sugerido"] == ""


def test_parecer_remove_cest_antigo_quando_descricao_rejeita_enquadramento():
    r = ICMSSTMGService.analisar(
        "39199090", CTX_MG, "ADESIVO KIT PRATA BIZ125"
    )
    parecer = SimpleNamespace(
        tributacao_atual={"ICMS-ST": "SIM"},
        dados_gerais={"CEST": "0109000"},
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
    assert "NÃO APLICÁVEL" in parecer.tributacao_atual["ICMS-ST"]
    assert any("3919.90" in x for x in parecer.conclusoes)


def test_indicador_mostra_decisao_nao_aplicavel_com_100_porcento():
    r = ICMSSTMGService.analisar(
        "39199090", CTX_MG, "ADESIVO KIT PRATA BIZ125"
    )
    indicador = IndicadorSegurancaTributaria.icms_st_uf(r, "MG")

    assert indicador.resultado == "100% — NÃO APLICÁVEL"


def test_cfop_interno_sem_st_confirmada_deixa_de_sugerir_5405_5403():
    r = ICMSSTMGService.analisar(
        "39199090", CTX_MG, "ADESIVO KIT PRATA BIZ125"
    )
    resultado = {"icms_st_mg": r}
    cfop = ConsultaOficialService.cfop_para_exibicao(
        resultado,
        contexto={"operacao": "VENDA", "finalidade": "REVENDA", **CTX_MG},
        tributacao_atual={},
    )

    assert cfop["valor"] == "5102"
    assert cfop["status"] == "SUGESTÃO FORTE"
