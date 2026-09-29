from types import SimpleNamespace
from pathlib import Path

from src.core.app_info import VERSAO_APP
from src.services.consulta_oficial_service import ConsultaOficialService


def _resultado_base():
    return {
        "ncm_confirmado": True,
        "normas_oficiais": [{"tipo": "Lei", "numero": "teste"}],
        "ipi_confirmado": True,
        "ipi_principal": {"aliquota": 15.0, "aliquota_texto": "15"},
        "tipi": [{"aliquota": 15.0, "aliquota_texto": "15", "ex_tipi": ""}],
        "piscofins_nacional": {
            "confirmado": True,
            "status": "CONFIRMADO — MONOFÁSICO",
            "cst_pis": "04",
            "aliquota_pis": 0.0,
            "cst_cofins": "04",
            "aliquota_cofins": 0.0,
        },
        "icms_mg": {
            "aliquota_nominal": 18.0,
            "aliquota_confirmada": False,
            "aliquota_status": "PADRÃO RESIDUAL — REVISAR EXCEÇÕES",
        },
        "icms_st_mg": {"confirmado": True, "encontrado": True},
    }


def _contexto():
    return {
        "empresa": "Mega Motos Comércio",
        "regime": "LUCRO PRESUMIDO",
        "operacao": "SAÍDA",
        "finalidade": "REVENDA",
        "uf_origem": "MG",
        "uf_destino": "MG",
    }


def test_versao_17827():
    assert tuple(map(int, VERSAO_APP.split("."))) >= (17, 8, 27)


def test_ipi_separa_tipi_de_operacao():
    resultado = _resultado_base()
    tributacao = {"CST IPI": "", "IPI": 0.0, "Regra aplicada": "REGRA TESTE"}
    exibicao = ConsultaOficialService.ipi_para_exibicao(resultado, tributacao, _contexto())

    assert exibicao["tipi_referencia"] == "15%"
    assert exibicao["tratamento_operacao"] == "CST não informado • 0,00%"
    assert exibicao["revisar_operacao"] is True
    assert "Não significa, sozinha" in exibicao["observacao_tipi"]
    assert "Não confundir" in exibicao["observacao_operacao"]


def test_diferenca_ipi_nao_e_tratada_como_erro_automatico():
    mensagem = ConsultaOficialService.divergencia_ipi(_resultado_base(), 0.0)
    assert "TIPI de referência" in mensagem
    assert "não é, por si só, erro" in mensagem


def test_revisao_explica_icms_cfop_e_ipi_sem_mandar_revisar_pisco_confirmado():
    parecer = SimpleNamespace(pendencias=[], confiabilidade=84.0)
    tributacao = {"CST IPI": "", "IPI": 0.0, "Regra aplicada": "REGRA TESTE"}
    revisao = ConsultaOficialService.revisao_para_exibicao(
        _resultado_base(), parecer, tributacao, _contexto()
    )

    assert revisao["precisa_revisar"] is True
    assert "ICMS" in revisao["motivos"]
    assert "CFOP" in revisao["motivos"]
    assert "IPI OPERAÇÃO" in revisao["motivos"]
    assert "PIS/COFINS" not in revisao["motivos"]


def test_ipi_operacao_com_cst_e_aliquota_deixa_de_ser_pendencia_propria():
    resultado = _resultado_base()
    tributacao = {"CST IPI": "53", "IPI": 0.0, "Regra aplicada": "REGRA TESTE"}
    exibicao = ConsultaOficialService.ipi_para_exibicao(resultado, tributacao, _contexto())
    assert exibicao["revisar_operacao"] is False
    assert exibicao["tratamento_operacao"] == "CST 53 • 0,00%"


def test_ficha_usa_rotulos_claros():
    arquivo = Path(__file__).resolve().parents[1] / "src" / "ui" / "janela_ficha_tributaria.py"
    texto = arquivo.read_text(encoding="utf-8")
    assert "TIPI — referência do NCM" in texto
    assert "IPI — tratamento da operação" in texto
    assert "ANÁLISE CONCLUÍDA — REVISAR:" in texto
    assert "Revisar antes de aplicar:" in texto
