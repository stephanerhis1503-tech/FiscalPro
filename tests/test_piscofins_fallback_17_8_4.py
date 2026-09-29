from types import SimpleNamespace

import pytest

from src.services.consulta_oficial_service import ConsultaOficialService
from src.services.piscofins_monofasico_service import PISCOFINSMonofasicoService
from src.services.piscofins_nacional_service import PISCOFINSNacionalService


CONTEXTO_REAL = {
    "regime": "LUCRO REAL",
    "operacao": "SAÍDA",
    "finalidade": "REVENDA",
    "data_operacao": "2026-08-12",
}


def test_73261900_nao_e_tratado_como_ncm_inexistente():
    mono = PISCOFINSMonofasicoService.analisar(
        "73261900", contexto=CONTEXTO_REAL, descricao="Outras obras de ferro ou aço"
    )

    assert mono["status"] == "NÃO ENQUADRADO"
    assert mono["confirmado"] is False
    assert "não significa que o NCM seja inválido" in mono["observacao"]


def test_73261900_continua_para_padrao_nao_cumulativo():
    resultado = PISCOFINSNacionalService.analisar(
        "73261900", contexto=CONTEXTO_REAL, descricao="Outras obras de ferro ou aço"
    )

    assert resultado["status"] == "SUGESTÃO CONDICIONAL — REGIME NÃO CUMULATIVO"
    assert resultado["confirmado"] is False
    assert resultado["sugestao_cst_pis"] == "01"
    assert resultado["sugestao_aliquota_pis"] == pytest.approx(1.65)
    assert resultado["sugestao_cst_cofins"] == "01"
    assert resultado["sugestao_aliquota_cofins"] == pytest.approx(7.60)


def test_exibicao_usa_sugestao_quando_cadastro_local_esta_vazio():
    nacional = PISCOFINSNacionalService.analisar(
        "73261900", contexto=CONTEXTO_REAL, descricao="Outras obras de ferro ou aço"
    )
    consulta = {
        "ncm_confirmado": True,
        "piscofins_nacional": nacional,
        "piscofins_monofasico": PISCOFINSMonofasicoService.analisar(
            "73261900", contexto=CONTEXTO_REAL
        ),
    }
    tributacao = {
        "CST PIS": "Não informado",
        "PIS": 0.0,
        "CST COFINS": "Não informado",
        "COFINS": 0.0,
    }

    exibicao = ConsultaOficialService.piscofins_para_exibicao(consulta, tributacao)

    assert exibicao["sugerido"] is True
    assert exibicao["cst_pis"] == "01"
    assert exibicao["aliquota_pis"] == pytest.approx(1.65)
    assert exibicao["cst_cofins"] == "01"
    assert exibicao["aliquota_cofins"] == pytest.approx(7.60)
    assert "NCM válido e localizado" in exibicao["observacao"]
    assert "Não houve enquadramento automático" in exibicao["observacao"]


def test_exibicao_preserva_tributacao_local_especifica():
    nacional = PISCOFINSNacionalService.analisar(
        "73261900", contexto=CONTEXTO_REAL
    )
    consulta = {"ncm_confirmado": True, "piscofins_nacional": nacional}
    tributacao = {
        "CST PIS": "06",
        "PIS": 0.0,
        "CST COFINS": "06",
        "COFINS": 0.0,
    }

    exibicao = ConsultaOficialService.piscofins_para_exibicao(consulta, tributacao)

    assert exibicao["origem"] == "CADASTRO LOCAL"
    assert exibicao["sugerido"] is False
    assert exibicao["cst_pis"] == "06"
    assert exibicao["cst_cofins"] == "06"


def test_sugestao_e_anexada_ao_parecer_sem_virar_regra_confirmada():
    resultado = PISCOFINSNacionalService.analisar(
        "73261900", contexto=CONTEXTO_REAL
    )
    parecer = SimpleNamespace(
        tributacao_atual={
            "CST PIS": "Não informado",
            "PIS": 0.0,
            "CST COFINS": "Não informado",
            "COFINS": 0.0,
        },
        regras_aplicadas={},
        base_legal=[],
        fontes=[],
        conclusoes=[],
        pendencias=[],
        versao_motor="13.4",
    )

    PISCOFINSNacionalService.aplicar_ao_parecer(parecer, resultado)

    # A sugestão fica rastreável, mas não é promovida silenciosamente a regra confirmada.
    assert parecer.tributacao_atual["CST PIS"] == "Não informado"
    assert parecer.tributacao_atual["CST PIS sugerido"] == "01"
    assert parecer.tributacao_atual["PIS sugerido"] == pytest.approx(1.65)
    assert parecer.tributacao_atual["CST COFINS sugerido"] == "01"
    assert parecer.tributacao_atual["COFINS sugerido"] == pytest.approx(7.60)
    assert parecer.regras_aplicadas["piscofins_nacional"]["status"].startswith("SUGESTÃO")
    assert parecer.pendencias
    assert parecer.versao_motor == "17.8.4"


def test_monofasico_confirmado_continua_com_cst_04():
    resultado = PISCOFINSNacionalService.analisar(
        "40114000",
        contexto=CONTEXTO_REAL,
        descricao="Pneu novo de borracha para motocicleta",
    )

    assert resultado["confirmado"] is True
    assert resultado["cst_pis"] == "04"
    assert resultado["aliquota_pis"] == 0.0
    assert resultado["cst_cofins"] == "04"
    assert resultado["aliquota_cofins"] == 0.0


def test_exportacao_continua_confirmada_com_cst_08():
    contexto = dict(CONTEXTO_REAL)
    contexto["operacao"] = "EXPORTAÇÃO"
    resultado = PISCOFINSNacionalService.analisar("73261900", contexto=contexto)

    assert resultado["confirmado"] is True
    assert resultado["cst_pis"] == "08"
    assert resultado["cst_cofins"] == "08"
