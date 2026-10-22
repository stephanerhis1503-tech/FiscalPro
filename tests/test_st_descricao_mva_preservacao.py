"""Regressoes isoladas: descricoes comerciais, MVA e valores condicionais.

Fixtures sinteticas, sem XMLs, empresas, identificadores ou valores reais.
Referencia para as linhas publicas:
https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/ricms_2023_seco/anexovii2023_4.html
Nao representa homologacao tributaria nem certificacao de vigencia historica.
"""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from src.services.calculadora_icms_st_mg_service import CalculadoraICMSSTMGService as Calc
from src.services.icms_st_mg_service import ICMSSTMGService as ST
from src.inteligencia.base_oficial.repositorio import BaseOficialRepository as Repo
from src.services.xml_icms_st_service import XMLICMSSTService as XML
from src.services.exportador_xml_icms_st_xlsx import ExportadorXMLICMSSTXLSX as Exportador
from tests.test_motor_st_contextual_17_8_128 import _item


def regra(ncm, cest, descricao, segmento="AUTOPEÇAS", mva=71.78):
    return dict(ncm_digitos=ncm, ncm_formatado=ncm, cest=cest, descricao=descricao,
                segmento=segmento, mva=mva, ambito="1.1", item="TESTE", fonte_codigo="TESTE")


REGRAS = (
    regra("853650", "01.065.00", "Interruptores e seccionadores e comutadores"),
    regra("853650", "09.004.00", "Starter", "LAMPADAS, REATORES E STARTERS", 102.31),
    regra("85364", "01.068.00", "Relés"),
    regra("85443000", "01.073.00", "Jogos de fios para velas de ignição e outros jogos de fios"),
    regra("8511", "01.054.00", "Aparelhos e dispositivos eletricos de ignicao ou arranque para motores"),
    regra("9029", "01.080.00", "Contadores, indicadores de velocidade e tacometros, suas partes e acessorios"),
    regra("8483", "01.050.00", "Arvores de transmissao, arvores de cames, virabrequins, engrenagens e embreagens"),
    regra("84099", "01.030.00", "Partes reconheciveis como exclusiva ou principalmente destinadas aos motores das posicoes 8407 ou 8408"),
    regra("8482", "01.049.00", "Rolamentos"),
    regra("87141", "01.076.00", "Partes e acessorios de motocicletas"),
    regra("40169300", "01.007.00", "Juntas, gaxetas e outros elementos com funcao semelhante de vedacao"),
)


@pytest.fixture
def base_controlada(monkeypatch):
    monkeypatch.setattr(Repo, "resumo_st_mg", staticmethod(lambda: {}))
    monkeypatch.setattr(Repo, "buscar_st_mg_por_ncm", staticmethod(
        lambda ncm: [deepcopy(r) for r in REGRAS if ncm.startswith(r["ncm_digitos"])]
    ))


def calcular(item, **kwargs):
    return XML.calcular_item(item, uf_origem="SC", uf_destino="MG",
                            aliquota_interna=18, aliquota_interestadual=4, **kwargs)


@pytest.mark.parametrize("descricao", [
    "CHAVE.IGN. BROS TESTE", "INT.FR.TRAS. FAZER TESTE", "INT.PARTIDA XLR TESTE",
    "INTER.TRAS. FACTOR TESTE", "CHAVE DE IGNICAO MOTO TESTE",
])
def test_interruptor_abreviado_nao_vira_starter(descricao, base_controlada):
    original = _item("85365090", descricao)
    copia = original.para_dict()
    r = calcular(original)
    assert r["calculado"] is True
    assert r["cest"] == "01.065.00"
    assert r["mva_original"] == 71.78
    assert r["mva_utilizada"] == 101.11
    assert not r["calculo_condicional"]
    assert original.para_dict() == copia


@pytest.mark.parametrize("descricao", [
    "SUPORTE CHAVE IGN MOTO", "CAPA INT PARTIDA MOTO", "MIOLO CHAVE IGN MOTO",
    "CHAVE IGN AVULSA", "CARCACA INTERRUPTOR MOTO", "PRODUTO GENERICO", "INT",
])
def test_partes_e_termos_genericos_nao_ganham_alias(descricao):
    assert not ST._descricao_indica_interruptor(descricao)


def test_starter_verdadeiro_mantem_regra_especifica(base_controlada):
    r = calcular(_item("85365090", "STARTER PARA LAMPADA TESTE"))
    assert r["cest"] == "09.004.00"
    assert r["calculado"] is True
    assert r["mva_original"] == 102.31
    assert not r["calculo_condicional"]


def test_ambiguidade_nao_confirma_regra_por_ordem_numerica(base_controlada):
    r = calcular(_item("85365090", "PRODUTO GENERICO"))
    assert r["st_oficial"]["confirmado"] is False
    assert r["st_oficial"]["decisao_st"] == "CONDICIONAL"
    assert r["calculado"] is False
    assert r["cest"] == ""
    assert r["mva_original"] is None
    assert r["conferencia_status"] == "REVISAR NCM / CEST / MVA"


def test_mva_manual_nao_transforma_ambiguidade_em_imposto_devido(base_controlada):
    r = calcular(_item("85365090", "PRODUTO GENERICO"), mva_manual=71.78)
    assert r["calculado"] is True
    assert r["calculo_condicional"] is True
    assert r["status"].startswith("SIMULADO")
    assert r["conferencia_status"] == "REVISAR NCM / CEST / MVA"


def test_duplicatas_nao_tentam_ordenar_dicionarios():
    r = REGRAS[0]
    candidato, ambiguo = ST._selecionar_candidato(
        [dict(r, id=2), dict(r, id=1)], "INTERRUPTOR MOTO"
    )
    assert candidato["cest"] == r["cest"]
    assert ambiguo is True


def test_finalidade_negada_nao_desempata_em_favor_de_autopecas():
    auto = REGRAS[0]
    outro = dict(auto, segmento="MATERIAIS ELETRICOS", cest="12.004.00")
    escolhido, ambiguo = ST._selecionar_candidato(
        [auto, outro], "INT.PARTIDA XLR TESTE", "NAO_AUTOMOTIVA"
    )
    assert ambiguo is True
    assert escolhido["cest"] == "12.004.00"


@pytest.mark.parametrize("descricao,finalidade", [
    ("CHAVE IGN TESTE", ""), ("INT.PARTIDA TESTE", ""),
    ("INT.PARTIDA XLR TESTE", "NAO_AUTOMOTIVA"),
    ("CHAVE.IGN. BROS TESTE", "NAO_AUTOMOTIVA"),
])
def test_abreviatura_sem_aplicacao_ou_com_negacao_nao_confirma_st(
    descricao, finalidade, base_controlada
):
    r = calcular(_item("85365090", descricao), finalidade_automotiva=finalidade)
    assert not r["st_oficial"]["confirmado"]
    assert r["calculo_condicional"]
    assert r["conferencia_status"] == "REVISAR NCM / CEST / MVA"


@pytest.mark.parametrize("descricao,ncm", [
    ("SENS.INCL. TESTE", "85364100"),
    ("REGUL.RETIF. TESTE", "85118020"),
    ("PAINEL TESTE", "90292010"),
])
def test_valor_assistido_preservado_sem_falso_st_nao_destacado(descricao, ncm, base_controlada):
    r = calcular(_item(ncm, descricao))
    esperado = Calc.calcular(valor_mercadoria=100, mva_original=71.78,
                            aliquota_interestadual=4, aliquota_interna=18, icms_proprio_deduzir=4)
    assert r["calculado"] is True
    assert r["icms_st"] == esperado["icms_st"]
    assert r["calculo_condicional"] is True
    assert r["conferencia_status"] == "REVISAR NCM / CEST / MVA"
    assert not r["conferencia_ok"]


@pytest.mark.parametrize("ncm,descricao,cest", [
    ("85443000", "FIACAO.PRIN. FACTOR TESTE", "01.073.00"),
    ("85364100", "RELE.PARTIDA MOTO TESTE", "01.068.00"),
    ("85114000", "MOTOR DE ARRANQUE MOTO TESTE", "01.054.00"),
])
def test_componentes_ja_reconhecidos_mantem_calculo(ncm, descricao, cest, base_controlada):
    r = calcular(_item(ncm, descricao))
    assert r["cest"] == cest
    assert r["calculado"] is True
    assert r["mva_original"] == 71.78
    assert r["mva_utilizada"] == 101.11
    assert not r["calculo_condicional"]



@pytest.mark.parametrize("ncm,descricao,cest", [
    ("84831020", "ARVORE DO COMANDO BIZ-125 TESTE", "01.050.00"),
    ("84099190", "BALANCIM CG-150 TESTE", "01.030.00"),
    ("84099190", "BRACO OSCILANTE CG-125 TESTE", "01.030.00"),
    ("84821010", "CAIXA DE DIRECAO YES-125 TESTE", "01.049.00"),
    ("87141000", "EIXO SECUNDARIO NXR-150 TESTE", "01.076.00"),
    ("84099112", "KIT CILINDRO COMPLETO NMAX-160 TESTE", "01.030.00"),
    ("87141000", "KIT EMBREAGEM BIZ-125 TESTE", "01.076.00"),
    ("84099120", "KIT PISTAO COM ANEL CG-150 TESTE", "01.030.00"),
    ("87141000", "PLACA DA PARTIDA CBX-200 TESTE", "01.076.00"),
    ("40169300", "RETENTOR BENGALA CB-300 TESTE", "01.007.00"),
    ("84099190", "TENSIONADOR DE CORRENTE YES-125 TESTE", "01.030.00"),
    ("84099114", "VALVULA DE ADMISSAO CBX-250 TESTE", "01.030.00"),
    ("84099114", "VALVULA DE ESCAPE YBR-125 TESTE", "01.030.00"),
    ("87141000", "SEPARADOR DA EMBREAGEM CG-150 TESTE", "01.076.00"),
])
def test_peca_mecanica_com_modelo_de_moto_confirma_segmento_autopecas(
    ncm, descricao, cest, base_controlada
):
    r = calcular(_item(ncm, descricao))
    assert ST.inferir_finalidade_automotiva(descricao) == "AUTOPECA_CONFIRMADA"
    assert r["cest"] == cest
    assert r["calculado"] is True
    assert r["st_oficial"]["confirmado"] is True
    assert r["calculo_condicional"] is False
    assert r["conferencia_status"] == "ST NÃO DESTACADO"


@pytest.mark.parametrize("ncm,descricao", [
    ("84099190", "BALANCIM INDUSTRIAL TESTE"),
    ("84099120", "KIT PISTAO UNIVERSAL TESTE"),
    ("84099112", "CILINDRO HIDRAULICO TESTE"),
    ("87141000", "EMBREAGEM INDUSTRIAL TESTE"),
    ("84099114", "VALVULA DE ADMISSAO INDUSTRIAL TESTE"),
    ("84821010", "CAIXA DE DIRECAO GENERICA TESTE"),
])
def test_peca_mecanica_sem_modelo_de_moto_continua_condicional(
    ncm, descricao, base_controlada
):
    assert ST.inferir_finalidade_automotiva(descricao) == "NAO_INFORMADA"
    r = calcular(_item(ncm, descricao))
    assert r["st_oficial"]["confirmado"] is False
    assert r["calculo_condicional"] is True
    assert r["conferencia_status"] == "REVISAR NCM / CEST / MVA"


def test_negacao_explicita_prevalece_sobre_modelo_de_moto(base_controlada):
    r = calcular(
        _item("84099120", "KIT PISTAO CG-150 TESTE"),
        finalidade_automotiva="NAO_AUTOMOTIVA",
    )
    assert r["st_oficial"]["confirmado"] is False
    assert r["calculo_condicional"] is True
    assert r["conferencia_status"] == "REVISAR NCM / CEST / MVA"



@pytest.mark.parametrize("mva", [0, 71.78, 100, 102.31, 250, "102,31"])
def test_mva_nao_tem_limite_de_aliquota(mva):
    r = Calc.calcular(valor_mercadoria=100, mva_original=mva,
                     aliquota_interestadual=4, aliquota_interna=18)
    assert r["base_calculo_st"] >= 100
    assert r["mva_original"] == float(str(mva).replace(",", "."))


@pytest.mark.parametrize("mva", [-1, "NaN", "Infinity", "-Infinity", Decimal("sNaN")])
def test_mva_negativa_ou_nao_finita_continua_bloqueada(mva):
    with pytest.raises(ValueError):
        Calc.calcular(valor_mercadoria=100, mva_original=mva,
                      aliquota_interestadual=4, aliquota_interna=18)


@pytest.mark.parametrize("campo", ["aliquota_interestadual", "aliquota_interna", "aliquota_fcp_st"])
def test_limite_de_aliquota_continua_ativo(campo):
    args = dict(valor_mercadoria=100, mva_original=102.31,
                aliquota_interestadual=4, aliquota_interna=18, aliquota_fcp_st=0)
    args[campo] = 100
    with pytest.raises(ValueError, match="100%"):
        Calc.calcular(**args)



def test_aliquota_do_xml_tem_prioridade_sobre_inferencia_generica(base_controlada):
    item = _item("87141000", "PASTILHA DIANT BROS160 TESTE")
    item = replace(
        item,
        origem_mercadoria="0",
        aliquota_icms_xml=Decimal("4.00"),
        icms_proprio=Decimal("4.00"),
        base_icms_proprio=Decimal("100.00"),
    )
    r = XML.calcular_item(
        item,
        uf_origem="RO",
        uf_destino="MG",
        aliquota_interna=18,
        aplicar_mva_ajustada=True,
    )
    assert r["aliquota_interestadual"] == 4.0
    assert r["icms_proprio_deduzir"] == 4.0
    assert r["mva_utilizada"] == 101.11


def test_sem_picms_xml_mantem_fallback_por_origem(base_controlada):
    item = _item("87141000", "PASTILHA DIANT BROS160 TESTE")
    item = replace(
        item,
        origem_mercadoria="0",
        aliquota_icms_xml=Decimal("0"),
        icms_proprio=Decimal("0"),
    )
    r = XML.calcular_item(
        item,
        uf_origem="RO",
        uf_destino="MG",
        aliquota_interna=18,
        aplicar_mva_ajustada=True,
    )
    assert r["aliquota_interestadual"] == 12.0


def test_resumo_separa_simulacoes_e_exporta_aviso(tmp_path, base_controlada):
    nota = SimpleNamespace(
        uf_origem="SC", uf_destino="MG", total_icms_st_xml=Decimal("0"),
        itens=[_item("85365090", "INT.PARTIDA XLR TESTE"),
               replace(_item("85364100", "SENS.INCL. TESTE"), numero_item=2)],
        para_dict=lambda: dict(numero="TESTE", serie="1"),
    )
    resultado = XML.calcular_nota(nota)
    r = resultado["resumo"]
    assert r["itens_calculo_condicional"] == 1
    assert r["itens_revisar"] == 1
    assert r["total_icms_st"] == pytest.approx(
        r["total_icms_st_sem_simulacoes"] + r["total_icms_st_condicional"]
    )
    assert r["apuracao_pendente"]
    assert "Nao e apuracao final" in r["aviso_apuracao"]
    path = Exportador.exportar(resultado, str(tmp_path / "teste.xlsx"))
    book = load_workbook(path, data_only=True)
    try:
        sheet = book.active
        assert sheet["A8"].value == r["aviso_apuracao"]
        assert sheet["AD11"].value.startswith("SIMULADO")
        assert sheet["AA11"].value == "REVISAR NCM / CEST / MVA"
        assert sheet["X12"].value == r["total_icms_st"]
    finally:
        book.close()
