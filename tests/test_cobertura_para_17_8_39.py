import pytest

from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.consulta_oficial_service import ConsultaOficialService
from src.services.icms_st_uf_service import ICMSSTUFService
from src.services.icms_uf_service import ICMSUFService


def test_pa_modal_19_e_fcp_permanece_revisao():
    r = ICMSUFService.analisar(
        "87141000",
        contexto={"uf_origem": "PA", "uf_destino": "PA"},
        descricao="Partes e acessórios de motocicletas",
    )
    assert r["aliquota_operacao"] == pytest.approx(19.0)
    assert r["aliquota_interna_destino"] == pytest.approx(19.0)
    assert "MODAL OFICIAL" in r["aliquota_interna_status"]
    assert r["fcp_confirmado"] is False
    assert "REVISAR FCP" in r["fcp_status"]


def test_autopeca_mg_para_pa_confirma_st_e_mva_ajustada():
    r = ICMSUFService.analisar(
        "87141000",
        contexto={"uf_origem": "MG", "uf_destino": "PA"},
        descricao="Partes e acessórios de motocicletas",
    )
    assert r["aliquota_operacao"] == pytest.approx(7.0)
    assert r["aliquota_interna_destino"] == pytest.approx(19.0)
    assert r["st_confirmado"] is True
    assert r["cest"] == "01.076.00"
    assert r["mva_original"] == pytest.approx(71.78)
    assert r["mva_ajustada"] == pytest.approx(97.23)
    assert r["mva_aplicada"] == pytest.approx(97.23)
    assert "PROTOCOLO 41/08" in r["mva_tipo"]
    assert "Protocolo ICMS 41/08" in r["fundamento_st"]


def test_autopeca_com_fidelidade_usa_mva_original_3656_no_interestadual():
    r = ICMSUFService.analisar(
        "87141000",
        contexto={
            "uf_origem": "MG",
            "uf_destino": "PA",
            "contrato_fidelidade": True,
        },
        descricao="Partes e acessórios de motocicletas",
    )
    assert r["st_confirmado"] is True
    assert r["mva_original"] == pytest.approx(36.56)
    assert r["mva_ajustada"] == pytest.approx(56.79)


def test_autopeca_interna_pa_usa_mva_anexo_xiii():
    r = ICMSUFService.analisar(
        "87141000",
        contexto={"uf_origem": "PA", "uf_destino": "PA"},
        descricao="Partes e acessórios de motocicletas",
    )
    assert r["st_confirmado"] is True
    assert r["mva_original"] == pytest.approx(71.78)
    assert r["mva_ajustada"] is None
    assert r["mva_aplicada"] == pytest.approx(71.78)
    assert "ANEXO XIII/PA" in r["mva_tipo"]


def test_pneu_moto_pa_confirma_cest_e_mva_60():
    r = ICMSUFService.analisar(
        "40114000",
        contexto={"uf_origem": "MG", "uf_destino": "PA"},
        descricao="Pneu novo para motocicleta",
    )
    assert r["st_confirmado"] is True
    assert r["cest"] == "16.003.00"
    assert r["segmento_st"] == "PNEUMÁTICOS"
    assert r["mva_original"] == pytest.approx(60.0)
    assert r["mva_aplicada"] == pytest.approx(60.0)
    assert "Convênio ICMS 102/17" in r["fundamento_st"]


def test_item_fora_do_ambito_pa_nao_vira_falso_nao_st():
    r = ICMSSTUFService.analisar(
        ncm="73110000",
        descricao="Recipientes para gases comprimidos",
        uf_origem="MG",
        uf_destino="PA",
        data_operacao=__import__("datetime").date(2026, 8, 21),
        aliquota_interestadual=7.0,
        aliquota_interna=19.0,
    )
    assert r["aplica_st"] is False
    assert r["decisao_confirmada"] is False
    assert "FORA DA COBERTURA" in r["status"]


def test_consulta_oficial_expoe_st_contextual_do_pa_e_cfop_condicional():
    r = ConsultaOficialService.consultar(
        "87141000",
        contexto={
            "empresa": "Mega Motos Comércio",
            "operacao": "SAÍDA",
            "finalidade": "REVENDA",
            "uf_origem": "MG",
            "uf_destino": "PA",
        },
        descricao="Partes e acessórios de motocicletas",
    )
    st = ConsultaOficialService.st_contextual(r)
    icms = ConsultaOficialService.icms_contextual(r)
    cfop = ConsultaOficialService.cfop_para_exibicao(r, {
        "operacao": "SAÍDA", "finalidade": "REVENDA", "uf_origem": "MG", "uf_destino": "PA"
    }, {})
    assert st["confirmado"] is True
    assert st["uf"] == "PA"
    assert st["mva_aplicada"] == pytest.approx(97.23)
    assert icms["uf"] == "PA"
    assert icms["aliquota_nominal"] == pytest.approx(7.0)
    assert "6403" in cfop["valor"]


def test_mapa_pa_vira_parcial_e_sai_da_prioridade_regra_geral():
    d = CoberturaTributariaService.diagnostico()
    pa = next(x for x in d["ufs"] if x["uf"] == "PA")
    assert pa["nivel"] == 2
    assert "19%" in pa["icms"]
    assert "Autopeças + pneumáticos" in pa["st"]
    assert "revisar" in pa["fcp"].lower()
    assert "PA" not in d["prioridades"]
    assert d["totais"] == {"ampliada": 1, "parcial": 25, "geral": 1}
