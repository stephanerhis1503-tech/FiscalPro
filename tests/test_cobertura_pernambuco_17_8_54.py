from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.cobertura_tributaria_service import CoberturaTributariaService
from src.services.consulta_oficial_service import ConsultaOficialService
from src.services.icms_uf_service import ICMSUFService


def _ctx(ncm, origem="MG", destino="PE", descricao="", **extra):
    contexto = {
        "uf_origem": origem,
        "uf_destino": destino,
        "data_operacao": "2026-08-21",
        "operacao": "SAÍDA",
        "finalidade": "REVENDA",
    }
    contexto.update(extra)
    return ICMSUFService.analisar(ncm, contexto=contexto, descricao=descricao)


def test_versao_17854():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 54)


def test_pe_modal_205_e_interestadual_mg_pe_7():
    r = _ctx("87141000")
    assert r["aliquota_operacao"] == 7.0
    assert r["aliquota_operacao_confirmada"] is True
    assert r["aliquota_interna_destino"] == 20.5
    assert "20,5%" in r["aliquota_interna_status"]


def test_autopeca_mg_pe_mva_10095_sem_reter_st_automaticamente():
    r = _ctx("87141000")
    assert r["cest"] == "01.076.00"
    assert r["st_potencial"] is True
    assert r["st_confirmado"] is False
    assert r["st_decisao_confirmada"] is False
    assert r["mva_original"] == 71.78
    assert r["mva_ajustada"] == 100.95
    assert r["mva_aplicada"] == 100.95
    assert "RETENÇÃO PELO REMETENTE NÃO AUTOMÁTICA" in r["st_status"]
    assert "DESTINATÁRIO PE" in r["st_responsabilidade"]
    assert "ORIGEM MG" in r["st_acordo_status"]
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True


def test_autopeca_mg_pe_fidelidade_usa_mva_5975_mas_continua_em_revisao():
    r = _ctx("87141000", contrato_fidelidade=True)
    assert r["mva_original"] == 36.56
    assert r["mva_ajustada"] == 59.75
    assert r["mva_aplicada"] == 59.75
    assert r["st_confirmado"] is False
    assert "FIDELIDADE" in r["observacao"].upper()


def test_autopeca_ba_pe_signatario_inter_12_mva_9015_e_st_confirmada():
    r = _ctx("87141000", origem="BA")
    assert r["aliquota_operacao"] == 12.0
    assert r["mva_original"] == 71.78
    assert r["mva_ajustada"] == 90.15
    assert r["mva_aplicada"] == 90.15
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert "REMETENTE" in r["st_responsabilidade"]


def test_pneu_moto_mg_pe_mva_60_ajustada_8717_e_st_confirmada():
    r = _ctx("40114000")
    assert r["cest"] == "16.003.00"
    assert r["st_confirmado"] is True
    assert r["st_decisao_confirmada"] is True
    assert r["mva_original"] == 60.0
    assert r["mva_ajustada"] == 87.17
    assert r["mva_aplicada"] == 87.17
    assert "CONVÊNIO ICMS 102/17" in r["st_acordo_status"]
    assert r["fcp"] == 0.0
    assert r["fcp_confirmado"] is True


def test_st_contextual_propaga_mva_pe_mesmo_quando_responsabilidade_autopeca_requer_revisao():
    consulta = {"icms_uf": _ctx("87141000")}
    st = ConsultaOficialService.st_contextual(consulta)
    assert st["uf"] == "PE"
    assert st["encontrado"] is True
    assert st["confirmado"] is False
    assert st["mva_original"] == 71.78
    assert st["mva_aplicada"] == 100.95


def test_cfop_autopeca_mg_pe_nao_vira_6403_quando_remetente_nao_e_signatario():
    consulta = {"icms_uf": _ctx("87141000")}
    cfop = ConsultaOficialService.cfop_para_exibicao(
        consulta,
        {"uf_origem": "MG", "uf_destino": "PE", "operacao": "SAÍDA", "finalidade": "REVENDA"},
        {},
    )
    assert cfop["valor"] == "6102 / 6108 — condicional"


def test_cfop_pneu_mg_pe_pode_indicar_faixa_st_condicional():
    consulta = {"icms_uf": _ctx("40114000")}
    cfop = ConsultaOficialService.cfop_para_exibicao(
        consulta,
        {"uf_origem": "MG", "uf_destino": "PE", "operacao": "SAÍDA", "finalidade": "REVENDA"},
        {},
    )
    assert cfop["valor"] == "6403 / 6404 — revisar posição na ST"


def test_mapa_pe_parcial_e_totais_atualizados():
    linha = next(x for x in CoberturaTributariaService.mapa_ufs() if x["uf"] == "PE")
    assert linha["nivel"] == 2
    assert "20,5%" in linha["icms"]
    assert "Autopeças + pneumáticos" in linha["st"]
    assert "17.8.54" in linha["observacao"]
    d = CoberturaTributariaService.diagnostico()
    assert d["totais"] == {"ampliada": 1, "parcial": 25, "geral": 1}


def test_olist_continua_usando_motor_unico_sem_tabela_pe_paralela():
    fonte = Path("src/services/configurador_olist_service.py").read_text(encoding="utf-8")
    assert "ICMSUFService.analisar" in fonte
    assert '"PE": {' not in fonte


def test_ficha_tem_estado_revisar_mva_para_regra_pe_sem_retencao_confirmada():
    fonte = Path("src/ui/janela_ficha_tributaria.py").read_text(encoding="utf-8")
    assert "elif st_encontrado and mva_st is not None:" in fonte
    assert 'valor_st = f"REVISAR • MVA {mva_st_texto}"' in fonte
