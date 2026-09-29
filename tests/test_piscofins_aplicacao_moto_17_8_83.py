from src.services.piscofins_monofasico_service import PISCOFINSMonofasicoService
from src.services.piscofins_nacional_service import PISCOFINSNacionalService


BASE = {
    "operacao": "SAÍDA",
    "regime": "LUCRO PRESUMIDO",
    "finalidade": "REVENDA",
    "data_operacao": "2026-08-31",
}


def test_84811000_moto_explicita_exclui_monofasico():
    contexto = {
        **BASE,
        "finalidade_automotiva": "PEÇA/COMPONENTE/ACESSÓRIO DE MOTO",
    }
    resultado = PISCOFINSMonofasicoService.analisar(
        "84811000",
        contexto=contexto,
        descricao="REGULADOR PRESSAO XRE300",
    )

    assert resultado["status"] == "NÃO ENQUADRADO"
    assert resultado["enquadramento"] == "ANEXO II — FORA DA DESCRIÇÃO LEGAL"
    assert resultado["exclusao_confirmada"] is True
    assert resultado["destinacao_identificada"] == "MOTOCICLETA (87.11)"
    assert resultado["exige_revisao"] is False
    assert resultado["cst_pis"] == ""
    assert resultado["cst_cofins"] == ""


def test_84811000_moto_cai_no_padrao_cumulativo_sem_confirmar_automaticamente():
    contexto = {
        **BASE,
        "finalidade_automotiva": "PEÇA/COMPONENTE/ACESSÓRIO DE MOTO",
    }
    resultado = PISCOFINSNacionalService.analisar(
        "84811000",
        contexto=contexto,
        descricao="REGULADOR PRESSAO XRE 300",
    )

    assert resultado["status"] == "SUGESTÃO CONDICIONAL — REGIME CUMULATIVO"
    assert resultado["confirmado"] is False
    assert resultado["exige_revisao"] is True
    assert resultado["sugestao_cst_pis"] == "01"
    assert resultado["sugestao_aliquota_pis"] == 0.65
    assert resultado["sugestao_cst_cofins"] == "01"
    assert resultado["sugestao_aliquota_cofins"] == 3.0


def test_84811000_xre300_na_descricao_identifica_moto_mesmo_sem_finalidade():
    resultado = PISCOFINSMonofasicoService.analisar(
        "84811000",
        contexto={**BASE, "finalidade_automotiva": "NÃO INFORMADA — MANTER CONDICIONAL"},
        descricao="REGULADOR PRESSAO XRE300",
    )

    assert resultado["status"] == "NÃO ENQUADRADO"
    assert resultado["exclusao_confirmada"] is True
    assert resultado["destinacao_identificada"] == "MOTOCICLETA (87.11)"


def test_84811000_sem_aplicacao_permanece_em_revisao():
    resultado = PISCOFINSMonofasicoService.analisar(
        "84811000",
        contexto={**BASE, "finalidade_automotiva": "NÃO INFORMADA — MANTER CONDICIONAL"},
        descricao="VALVULA REDUTORA DE PRESSAO",
    )

    assert resultado["status"] == "REVISÃO NECESSÁRIA"
    assert resultado["enquadramento"] == "ANEXO II"
    assert resultado["exclusao_confirmada"] is False
    assert resultado["exige_revisao"] is True


def test_84811000_nao_automotiva_nao_e_forcada_como_moto():
    resultado = PISCOFINSMonofasicoService.analisar(
        "84811000",
        contexto={**BASE, "finalidade_automotiva": "NÃO É PEÇA AUTOMOTIVA"},
        descricao="REGULADOR DE PRESSAO",
    )

    assert resultado["status"] == "REVISÃO NECESSÁRIA"
    assert resultado["exclusao_confirmada"] is False


def test_84811000_moto_lucro_real_sugere_padrao_nao_cumulativo():
    contexto = {
        **BASE,
        "regime": "LUCRO REAL",
        "finalidade_automotiva": "PEÇA/COMPONENTE/ACESSÓRIO DE MOTO",
    }
    resultado = PISCOFINSNacionalService.analisar(
        "84811000",
        contexto=contexto,
        descricao="REGULADOR PRESSAO XRE300",
    )

    assert resultado["status"] == "SUGESTÃO CONDICIONAL — REGIME NÃO CUMULATIVO"
    assert resultado["sugestao_cst_pis"] == "01"
    assert resultado["sugestao_aliquota_pis"] == 1.65
    assert resultado["sugestao_cst_cofins"] == "01"
    assert resultado["sugestao_aliquota_cofins"] == 7.6


def test_exibicao_mantem_exclusao_mono_e_mostra_sugestao_do_regime():
    from src.services.consulta_oficial_service import ConsultaOficialService

    contexto = {
        **BASE,
        "finalidade_automotiva": "PEÇA/COMPONENTE/ACESSÓRIO DE MOTO",
    }
    mono = PISCOFINSMonofasicoService.analisar(
        "84811000", contexto=contexto, descricao="REGULADOR PRESSAO XRE300"
    )
    nacional = PISCOFINSNacionalService.analisar(
        "84811000", contexto=contexto, descricao="REGULADOR PRESSAO XRE300"
    )
    exibicao = ConsultaOficialService.piscofins_para_exibicao(
        {
            "ncm_confirmado": True,
            "piscofins_monofasico": mono,
            "piscofins_nacional": nacional,
        }
    )

    assert exibicao["monofasico_excluido"] is True
    assert exibicao["destinacao_identificada"] == "MOTOCICLETA (87.11)"
    assert exibicao["sugerido"] is True
    assert exibicao["confirmado"] is False
    assert exibicao["cst_pis"] == "01"
    assert exibicao["aliquota_pis"] == 0.65
    assert exibicao["cst_cofins"] == "01"
    assert exibicao["aliquota_cofins"] == 3.0
    assert "monofásico" in exibicao["observacao"].lower()
    assert "excluído" in exibicao["observacao"].lower()
