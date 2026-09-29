from datetime import date
from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.atualizador_fontes_oficiais import AtualizadorFontesOficiais
from src.services.consulta_oficial_service import ConsultaOficialService
from src.services.icms_uf_service import ICMSUFService


def _ctx():
    return {
        "uf_origem": "MG",
        "uf_destino": "RN",
        "data_operacao": date(2026, 8, 24).isoformat(),
    }


def test_versao_17_8_60():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 60)


def test_rn_autopeca_expoe_fonte_e_regra_contextuais():
    resultado = ICMSUFService.analisar("87141000", contexto=_ctx())
    consulta = {"icms_uf": resultado}
    st = ConsultaOficialService.st_contextual(consulta)
    assert st["fonte_codigo"] == "SEFAZ_RN_ANEXO_005"
    assert st["fonte_nome"] == "SEFAZ/RN — RICMS/RN, Anexo 005"
    assert st["regra_aplicada"] == "ANTECIPAÇÃO ICMS/RN — ANEXO 005"
    assert "Anexo 005" in st["fundamento_legal"]
    assert "diariooficial.rn.gov.br" in st["fonte_url"]


def test_rn_pneu_expoe_anexo_007_como_fonte_contextual():
    resultado = ICMSUFService.analisar("40114000", contexto=_ctx())
    st = ConsultaOficialService.st_contextual({"icms_uf": resultado})
    assert st["fonte_codigo"] == "SEFAZ_RN_ANEXO_007"
    assert st["fonte_nome"] == "SEFAZ/RN — RICMS/RN, Anexo 007"
    assert "PNEUMÁTICOS" in st["regra_aplicada"]


def test_revisao_nao_diz_regra_local_ausente_quando_st_estadual_esta_estruturada():
    resultado_uf = ICMSUFService.analisar("87141000", contexto=_ctx())
    resultado = {
        "ncm_confirmado": True,
        "ipi_confirmado": True,
        "piscofins_nacional": {"confirmado": True},
        "icms_uf": resultado_uf,
        "normas_oficiais": [],
    }
    class Parecer:
        pendencias = []
        confiabilidade = 90
    rev = ConsultaOficialService.revisao_para_exibicao(
        resultado, Parecer(), {"Regra aplicada": "Não localizada", "CST IPI": "00", "IPI": 0}, _ctx()
    )
    assert "REGRA LOCAL" not in rev["motivos"]


def test_base_legal_nao_possui_fallback_mg_para_st_estadual():
    fonte = Path("src/ui/janela_ficha_tributaria.py").read_text(encoding="utf-8")
    assert 'codigo_st = "SEF_MG_ST" if uf_st == "MG" else f"SEFA_{uf_st}"' in fonte
    assert 'str(st_mg.get("fonte_codigo") or "SEF_MG_ST")' not in fonte


def test_catalogo_registra_fontes_rn():
    fonte = Path("src/services/atualizador_fontes_oficiais.py").read_text(encoding="utf-8")
    assert '"SEFA_RN"' in fonte
    assert '"SEFAZ_RN_ANEXO_005"' in fonte
    assert '"SEFAZ_RN_ANEXO_007"' in fonte


def test_base_legal_rotula_antecipacao_rn_sem_chamar_de_st():
    fonte = Path("src/ui/janela_ficha_tributaria.py").read_text(encoding="utf-8")
    assert 'rotulo_st_base_legal = f"Antecipação ICMS {uf_st} — CEST e regra"' in fonte
