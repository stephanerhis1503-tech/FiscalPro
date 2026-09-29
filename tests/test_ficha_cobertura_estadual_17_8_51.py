from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.consulta_oficial_service import ConsultaOficialService
from src.services.icms_st_uf_service import ICMSSTUFService


def _resultado_contextual_mt(mva_base, mva_aplicada, cest, segmento):
    return {
        "icms_uf": {
            "uf_destino": "MT",
            "aliquota_operacao": 7.0,
            "aliquota_operacao_status": "CONFIRMADA — REGRA INTERESTADUAL 7%",
            "aliquota_operacao_confirmada": True,
            "aliquota_interna_destino": 17.0,
            "aliquota_interna_status": "MODAL MT 17%",
            "st_potencial": True,
            "st_confirmado": True,
            "st_decisao_confirmada": True,
            "st_status": "ICMS-ST/MT CONFIRMADO — MVA CONDICIONAL",
            "cest": cest,
            "segmento_st": segmento,
            "mva_original": mva_base,
            "mva_ajustada": None,
            "mva_aplicada": mva_aplicada,
            "mva_tipo": "MVA ART. 2º-B/MT — DESTINATÁRIO SEM BENEFÍCIO INFORMADO",
            "st_responsabilidade": "REVISAR RESPONSABILIDADE",
            "st_acordo_status": "CONFERIR SITUAÇÃO DO DESTINATÁRIO",
            "fundamento_st": "RICMS/MT; Portaria 195/2019",
            "fonte_st": "SEFAZ/MT",
            "observacao": "Confirme a situação cadastral/benefício do destinatário antes de aplicar.",
            "fcp": 0.0,
            "fcp_status": "FCP 0% NO ESCOPO AUTOMOTIVO ESTRUTURADO",
        },
        "icms_mg": {"aliquota_nominal": 18.0, "uf": "MG"},
        "icms_st_mg": {"status": "FORA DO ESCOPO DE MINAS GERAIS", "uf": "MG"},
    }


def test_versao_17851():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 51)


def test_contexto_icms_prioriza_uf_destino_mt():
    resultado = _resultado_contextual_mt(62.27, 78.79, "16.003.00", "PNEUMÁTICOS")
    icms = ConsultaOficialService.icms_contextual(resultado)
    assert icms["uf"] == "MT"
    assert icms["aliquota_nominal"] == 7.0
    assert icms["aliquota_interna_destino"] == 17.0


def test_contexto_st_prioriza_mt_em_vez_do_fallback_mg():
    resultado = _resultado_contextual_mt(62.27, 78.79, "16.003.00", "PNEUMÁTICOS")
    st = ConsultaOficialService.st_contextual(resultado)
    assert st["uf"] == "MT"
    assert st["cest"] == "16.003.00"
    assert st["mva_original"] == 62.27
    assert st["mva_aplicada"] == 78.79
    assert "DESTINATÁRIO SEM BENEFÍCIO" in st["mva_tipo"]
    assert "MINAS GERAIS" not in st["status"].upper()


def test_motor_mt_preserva_as_duas_mvas_e_condicao_do_destinatario():
    pneu = ICMSSTUFService._mt(
        {"segmento": "PNEUMÁTICOS", "cest": "16.003.00"},
        origem="MG", aliquota_inter=7.0, contrato_fidelidade=False
    )
    assert pneu["mva_original"] == 62.27
    assert pneu["mva_aplicada"] == 78.79
    assert "DESTINATÁRIO SEM BENEFÍCIO" in pneu["mva_tipo"]

    autopeca = ICMSSTUFService._mt(
        {"segmento": "AUTOPEÇAS", "cest": "01.076.00"},
        origem="MG", aliquota_inter=7.0, contrato_fidelidade=False
    )
    assert autopeca["mva_original"] == 50.39
    assert autopeca["mva_aplicada"] == 65.29


def test_ficha_exibe_campos_estaduais_sem_rotulo_fixo_mg():
    fonte = Path("src/ui/janela_ficha_tributaria.py").read_text(encoding="utf-8")
    assert "ICMS interestadual" in fonte
    assert "ICMS interno {uf_icms}" in fonte
    assert "ICMS-ST {uf_icms}" in fonte
    assert "MVA-base {uf_icms}" in fonte
    assert "MVA aplicada {uf_icms}" in fonte
    assert "FCP {uf_icms}" in fonte


def test_parecer_de_outra_uf_remove_conclusao_automatica_de_mg():
    class ParecerFake:
        def __init__(self):
            self.tributacao_atual = {
                "ICMS-ST": "SIM",
                "MVA ST oficial MG": 60.0,
                "Segmento ST MG": "PNEUMÁTICOS",
            }
            self.dados_gerais = {}
            self.base_legal = []
            self.fontes = []
            self.conclusoes = [
                "NCM enquadrado no segmento de pneumáticos do ICMS-ST de Minas Gerais, CEST 16.003.00, MVA original 60.00%.",
                "PIS/COFINS: CONFIRMADO — MONOFÁSICO.",
            ]
            self.alertas = []
            self.pendencias = []
            self.regras_aplicadas = {}

    parecer = ParecerFake()
    resultado = _resultado_contextual_mt(62.27, 78.79, "16.003.00", "PNEUMÁTICOS")
    parecer = ConsultaOficialService.aplicar_icms_st_mg_ao_parecer(parecer, resultado)
    texto = "\n".join(parecer.conclusoes).upper()
    assert "ICMS-ST DE MINAS GERAIS" not in texto
    assert "ICMS-ST/MT" in texto
    assert "MVA ST oficial MG" not in parecer.tributacao_atual
    assert parecer.tributacao_atual["MVA ST oficial MT"] == 78.79
