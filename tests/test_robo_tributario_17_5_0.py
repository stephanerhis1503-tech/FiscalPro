from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.inteligencia.consulta_tributaria import ConsultaTributaria
from src.inteligencia.ficha_tributaria import FichaTributaria
from src.inteligencia.regras.regra_icms import RegraICMS
from src.inteligencia.regras.regra_piscofins import RegraPISCOFINS
from src.inteligencia.regras.regra_st import RegraST
from src.services.robo_tributario_service import RoboTributarioService


def consulta(**kwargs):
    dados = dict(
        ncm="85122011",
        descricao_produto="Farol de motocicleta",
        uf_origem="MG",
        uf_destino="MG",
        regime="Lucro Real",
        operacao="Venda",
        consumidor_final=False,
        finalidade="Revenda",
        perfil_remetente="Comerciante",
        situacao_icms_st="Responsável por reter ICMS-ST nesta saída",
    )
    dados.update(kwargs)
    return ConsultaTributaria(**dados)


def ficha_confirmada():
    ficha = FichaTributaria(ncm="85122011", descricao="APARELHOS DE ILUMINAÇÃO")
    ficha.pis_cst = "01"
    ficha.cofins_cst = "01"
    ficha.aliquota_pis = 1.65
    ficha.aliquota_cofins = 7.60
    ficha.piscofins_status = "CONFIRMADO — TRIBUTAÇÃO PADRÃO"
    ficha.piscofins_confirmado = True
    ficha.piscofins_exige_revisao = False
    ficha.piscofins_confiabilidade = 95.0
    ficha.piscofins_fundamento = "Base legal PIS/COFINS"
    ficha.icms_mg_aliquota_status = "CONFIRMADA — ALÍQUOTA INTERNA"
    ficha.icms_mg_confirmado = True
    ficha.icms_mg_confiabilidade = 100.0
    ficha.icms_mg_aliquota_nominal = 18.0
    ficha.icms_mg_fundamento = "RICMS/MG"
    ficha.icms_mg_st_status = "CONFIRMADO — ICMS-ST MG"
    ficha.icms_mg_st_confirmado = True
    ficha.icms_mg_cest = "0100100"
    ficha.icms_mg_mva = 40.0
    ficha.reforma_status = "CADASTRO ESPECÍFICO"
    ficha.cst_ibs = "000"
    ficha.cst_cbs = "000"
    ficha.aliquota_ibs = 0.10
    ficha.aliquota_cbs = 0.90
    ficha.fontes = ["Base oficial de teste"]
    return ficha


def test_rejeita_ncm_invalido():
    with pytest.raises(ValueError, match="8 dígitos"):
        RoboTributarioService.avaliar_ficha(consulta(ncm="123"), None)


def test_ncm_sem_ficha_fica_pendente():
    resultado = RoboTributarioService.avaliar_ficha(consulta(), None)
    assert resultado.status == "PENDENTE"
    assert resultado.confiabilidade == 0
    assert "não encontrados" in resultado.relatorio


def test_ficha_confirmada_resulta_consistente():
    resultado = RoboTributarioService.avaliar_ficha(consulta(), ficha_confirmada())
    assert resultado.status == "CONSISTENTE"
    assert resultado.confiabilidade == 90.0
    assert {d.status for d in resultado.diagnosticos if d.tributo != "IPI"} == {"CONFIRMADO"}
    assert "não aplica correções automaticamente" in resultado.relatorio


def test_divergencia_piscofins_forca_revisao():
    ficha = ficha_confirmada()
    ficha.piscofins_divergencia = True
    resultado = RoboTributarioService.avaliar_ficha(consulta(), ficha)
    assert resultado.status == "REVISAR"
    assert any("Divergência" in alerta for alerta in resultado.alertas)
    pis = next(d for d in resultado.diagnosticos if d.tributo == "PIS/COFINS")
    assert pis.status == "REVISAR"


def test_st_nao_localizada_nao_e_tratada_como_ausencia_de_st():
    ficha = ficha_confirmada()
    ficha.icms_mg_st_status = "NÃO LOCALIZADO NA TABELA ST/MG SINCRONIZADA"
    ficha.icms_mg_st_confirmado = False
    resultado = RoboTributarioService.avaliar_ficha(consulta(), ficha)
    assert resultado.status == "PENDENTE"
    st = next(d for d in resultado.diagnosticos if d.tributo == "ICMS-ST")
    assert st.status == "PENDENTE"
    assert "não trata ausência de informação" in resultado.relatorio


def test_cenario_padrao_reforma_exige_revisao():
    ficha = ficha_confirmada()
    ficha.reforma_status = "CENÁRIO PADRÃO 2026"
    resultado = RoboTributarioService.avaliar_ficha(consulta(), ficha)
    reforma = next(d for d in resultado.diagnosticos if d.tributo == "Reforma 2026")
    assert reforma.status == "REVISAR"
    assert resultado.status == "REVISAR"


def test_regra_icms_prioriza_descricao_real_da_operacao():
    ficha = FichaTributaria(ncm="85122011", descricao="Descrição oficial genérica")
    with patch("src.inteligencia.regras.regra_icms.ICMSMGNacionalService.analisar") as analisar, patch(
        "src.inteligencia.regras.regra_icms.ICMSMGNacionalService.aplicar_ao_ficha",
        side_effect=lambda f, r: f,
    ):
        analisar.return_value = {}
        RegraICMS.aplicar(ficha, consulta(descricao_produto="FAROL LED MOTO"))
        assert analisar.call_args.kwargs["descricao"] == "FAROL LED MOTO"


def test_regra_st_prioriza_descricao_real_da_operacao():
    ficha = FichaTributaria(ncm="85122011", descricao="Descrição oficial genérica")
    with patch("src.inteligencia.regras.regra_st.ICMSSTMGService.analisar") as analisar:
        analisar.return_value = {
            "status": "NÃO LOCALIZADO",
            "confirmado": False,
            "cest": "",
            "mva_original": 0,
        }
        RegraST.aplicar(ficha, consulta(descricao_produto="FAROL LED MOTO"))
        assert analisar.call_args.kwargs["descricao"] == "FAROL LED MOTO"


def test_regra_piscofins_prioriza_descricao_real_da_operacao():
    ficha = FichaTributaria(ncm="85122011", descricao="Descrição oficial genérica")
    with patch("src.inteligencia.regras.regra_piscofins.PISCOFINSNacionalService.analisar") as analisar:
        analisar.return_value = {"status": "REVISAR", "confirmado": False, "exige_revisao": True}
        RegraPISCOFINS.aplicar(ficha, consulta(descricao_produto="FAROL LED MOTO"))
        assert analisar.call_args.kwargs["descricao"] == "FAROL LED MOTO"
