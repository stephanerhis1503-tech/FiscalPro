from pathlib import Path

import pytest

import src.banco.conexao as conexao
from src.inteligencia.base_oficial.repositorio import BaseOficialRepository
from src.services.atualizador_fontes_oficiais import (
    AtualizadorFontesOficiais,
    RESIDUAIS_ST_MG_SEM_NCM_SUPORTADOS,
    ST_MG_SCHEMA_VERSAO,
)


def _preparar_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    banco = tmp_path / "fiscalpro_17_8_120.db"
    monkeypatch.setattr(conexao, "DB", banco)
    BaseOficialRepository.preparar_banco()


def test_parser_residual_nao_confunde_0813_0909_com_regra_sem_ncm():
    html = """
    <table>
      <tr><td>116.0</td><td>17.116.00</td><td>08.13<br>09.09</td>
          <td>Sementes e frutas secas para infusões</td><td>17.1</td><td>40</td></tr>
      <tr><td>999.0</td><td>28.999.00</td><td></td>
          <td>Outros produtos comercializados por marketing direto porta a porta</td><td>28.1</td><td>30</td></tr>
    </table>
    """

    residuais = AtualizadorFontesOficiais._ler_st_mg_residuais_sem_ncm_html(html)
    assert {item["cest"] for item in residuais} == {"28.999.00"}

    registros = AtualizadorFontesOficiais._ler_st_mg_segmento_html(
        html,
        prefixo_cest="17",
        segmento="PRODUTOS ALIMENTÍCIOS",
        fonte_codigo="SEF_MG_ST_COMPLETA",
    )
    assert {item["ncm_digitos"] for item in registros} == {"0813", "0909"}
    assert all(item["cest"] == "17.116.00" for item in registros)


def test_parser_capitulos_amplos_entram_no_indice_e_nao_viram_residual():
    html = """
    <table>
      <tr><td>58.0</td><td>28.058.00</td>
          <td>Capítulos 39, 42, 48, 52, 61, 71, 83, 90 e 91</td>
          <td>Acessórios diversos</td><td>28.1</td><td>31,80</td></tr>
      <tr><td>62.0</td><td>28.062.00</td>
          <td>Capítulos 13 e 15 a 23</td>
          <td>Produtos das indústrias alimentares e bebidas</td><td>28.1</td><td>42</td></tr>
      <tr><td>999.0</td><td>28.999.00</td><td></td>
          <td>Outros produtos comercializados pelo sistema de marketing direto porta a porta</td><td>28.1</td><td>30</td></tr>
    </table>
    """

    residuais = AtualizadorFontesOficiais._ler_st_mg_residuais_sem_ncm_html(html)
    assert {item["cest"] for item in residuais} == {"28.999.00"}

    registros = AtualizadorFontesOficiais._ler_st_mg_segmento_html(
        html,
        prefixo_cest="28",
        segmento="VENDA DE MERCADORIAS PELO SISTEMA PORTA A PORTA",
        fonte_codigo="SEF_MG_ST_COMPLETA",
    )
    por_cest = {}
    for item in registros:
        por_cest.setdefault(item["cest"], set()).add(item["ncm_digitos"])

    assert por_cest["28.058.00"] == {"39", "42", "48", "52", "61", "71", "83", "90", "91"}
    assert por_cest["28.062.00"] == {"13", "15", "16", "17", "18", "19", "20", "21", "22", "23"}
    assert "28.999.00" not in por_cest


def test_busca_por_ncm_encontra_regra_publicada_no_nivel_do_capitulo(tmp_path, monkeypatch):
    _preparar_db(tmp_path, monkeypatch)
    BaseOficialRepository.substituir_st_mg([
        {
            "segmento": "VENDA DE MERCADORIAS PELO SISTEMA PORTA A PORTA",
            "item": "59.0",
            "cest": "28.059.00",
            "ncm_formatado": "Capítulo 61",
            "ncm_digitos": "61",
            "descricao": "Vestuário e seus acessórios",
            "ambito": "28.1",
            "mva": 35.60,
            "mva_texto": "35,60",
            "fonte_codigo": "SEF_MG_ST_COMPLETA",
        }
    ])

    achados = BaseOficialRepository.buscar_st_mg_por_ncm("61103000")
    assert len(achados) == 1
    assert achados[0]["cest"] == "28.059.00"
    assert achados[0]["ncm_digitos"] == "61"


def test_schema_da_base_completa_foi_elevado_para_invalidar_base_119():
    assert ST_MG_SCHEMA_VERSAO == 3


def test_residuais_suportados_continuam_somente_os_reais_sem_nbm_sh():
    assert RESIDUAIS_ST_MG_SEM_NCM_SUPORTADOS == {"01.999.00", "28.999.00"}


def test_segmento_28_nominal_so_aplica_em_operacao_porta_a_porta(tmp_path, monkeypatch):
    from src.services.icms_st_mg_service import ICMSSTMGService

    _preparar_db(tmp_path, monkeypatch)
    BaseOficialRepository.substituir_st_mg([
        {
            "segmento": "VENDA DE MERCADORIAS PELO SISTEMA PORTA A PORTA",
            "item": "59.0",
            "cest": "28.059.00",
            "ncm_formatado": "Capítulo 61",
            "ncm_digitos": "61",
            "descricao": "Vestuário e seus acessórios",
            "ambito": "28.1",
            "mva": 35.60,
            "mva_texto": "35,60",
            "fonte_codigo": "SEF_MG_ST_COMPLETA",
        }
    ])
    BaseOficialRepository.registrar_status_st_mg(
        base_completa=True,
        versao_schema=3,
        paginas=3,
        segmentos=28,
        registros=1,
        referencia="RICMS/MG/2023 — Anexo VII, Parte 2 vigente",
        fonte_url="https://www.fazenda.mg.gov.br/",
    )

    comum = ICMSSTMGService.analisar(
        "61103000",
        contexto={
            "uf_origem": "MG",
            "uf_destino": "MG",
            "finalidade_automotiva": "NÃO É PEÇA AUTOMOTIVA",
            "operacao": "SAÍDA",
        },
        descricao="COLETE",
    )
    assert comum["decisao_st"] == "NAO"
    assert comum["cest"] == ""

    porta_a_porta = ICMSSTMGService.analisar(
        "61103000",
        contexto={
            "uf_origem": "MG",
            "uf_destino": "MG",
            "finalidade_automotiva": "NÃO É PEÇA AUTOMOTIVA",
            "operacao": "VENDA PORTA A PORTA",
        },
        descricao="COLETE DE VESTUÁRIO",
    )
    assert porta_a_porta["decisao_st"] == "SIM"
    assert porta_a_porta["cest"] == "28.059.00"
