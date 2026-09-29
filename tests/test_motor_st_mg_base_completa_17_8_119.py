from pathlib import Path

import pytest

import src.banco.conexao as conexao
from src.inteligencia.base_oficial.repositorio import BaseOficialRepository
from src.services.atualizador_fontes_oficiais import (
    AtualizadorFontesOficiais,
    RESIDUAIS_ST_MG_SEM_NCM_SUPORTADOS,
    URL_SEFAZ_MG_ST_PAGINAS,
)
from src.services.icms_st_mg_service import ICMSSTMGService


def _preparar_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    banco = tmp_path / "fiscalpro_17_8_119.db"
    monkeypatch.setattr(conexao, "DB", banco)
    BaseOficialRepository.preparar_banco()


def _linha_pastilha() -> dict:
    return {
        "segmento": "AUTOPEÇAS",
        "item": "14.0",
        "cest": "01.014.00",
        "ncm_formatado": "6813.81.10",
        "ncm_digitos": "68138110",
        "descricao": "Pastilhas de freio",
        "ambito": "1.1",
        "mva": 71.78,
        "mva_texto": "71,78%",
        "fonte_codigo": "SEF_MG_ST_COMPLETA",
    }


def _marcar_base_completa() -> None:
    BaseOficialRepository.registrar_status_st_mg(
        base_completa=True,
        versao_schema=3,
        paginas=3,
        segmentos=28,
        registros=1,
        referencia="RICMS/MG/2023 — Anexo VII, Parte 2 vigente",
        fonte_url=URL_SEFAZ_MG_ST_PAGINAS[0],
    )


def test_ncm_ausente_vira_nao_st_so_com_base_completa_e_finalidade_nao_automotiva(tmp_path, monkeypatch):
    _preparar_db(tmp_path, monkeypatch)
    BaseOficialRepository.substituir_st_mg([_linha_pastilha()])
    _marcar_base_completa()

    resultado = ICMSSTMGService.analisar(
        "99999999",
        contexto={
            "uf_origem": "MG",
            "uf_destino": "MG",
            "finalidade_automotiva": "NÃO É PEÇA AUTOMOTIVA",
        },
        descricao="PRODUTO GENÉRICO NÃO AUTOMOTIVO",
    )

    assert resultado["decisao_st"] == "NAO"
    assert resultado["nao_aplicavel"] is True
    assert resultado["exige_revisao"] is False
    assert resultado["cest"] == ""
    assert resultado["mva_original"] is None
    assert resultado["aplicabilidade_segmento"] == "NCM_AUSENTE_BASE_OFICIAL_COMPLETA"
    assert resultado["base_st_completa"] is True


def test_ncm_ausente_continua_condicional_se_base_nao_estiver_completa(tmp_path, monkeypatch):
    _preparar_db(tmp_path, monkeypatch)
    BaseOficialRepository.substituir_st_mg([_linha_pastilha()])

    resultado = ICMSSTMGService.analisar(
        "99999999",
        contexto={
            "uf_origem": "MG",
            "uf_destino": "MG",
            "finalidade_automotiva": "NÃO É PEÇA AUTOMOTIVA",
        },
        descricao="PRODUTO GENÉRICO NÃO AUTOMOTIVO",
    )

    assert resultado["decisao_st"] == "CONDICIONAL"
    assert resultado["exige_revisao"] is True
    assert resultado["base_st_completa"] is False


def test_finalidade_nao_informada_permanece_condicional_por_causa_do_residual_sem_ncm(tmp_path, monkeypatch):
    _preparar_db(tmp_path, monkeypatch)
    BaseOficialRepository.substituir_st_mg([_linha_pastilha()])
    _marcar_base_completa()

    resultado = ICMSSTMGService.analisar(
        "99999999",
        contexto={"uf_origem": "MG", "uf_destino": "MG"},
        descricao="COMPONENTE ESPECÍFICO",
    )

    assert resultado["decisao_st"] == "CONDICIONAL"
    assert resultado["exige_revisao"] is True
    assert resultado["cest_sugerido"] == "01.999.00"


def test_residual_autopecas_0199900_continua_valendo_mesmo_com_base_nominal_completa(tmp_path, monkeypatch):
    _preparar_db(tmp_path, monkeypatch)
    BaseOficialRepository.substituir_st_mg([_linha_pastilha()])
    _marcar_base_completa()

    resultado = ICMSSTMGService.analisar(
        "99999999",
        contexto={
            "uf_origem": "MG",
            "uf_destino": "MG",
            "finalidade_automotiva": "SIM",
        },
        descricao="PEÇA SUPORTE DE MOTO",
    )

    assert resultado["decisao_st"] == "SIM"
    assert resultado["confirmado"] is True
    assert resultado["cest"] == "01.999.00"
    assert resultado["mva_original"] == pytest.approx(71.78)


def test_ncm_nominal_da_tabela_completa_continua_enquadrando_st(tmp_path, monkeypatch):
    _preparar_db(tmp_path, monkeypatch)
    BaseOficialRepository.substituir_st_mg([_linha_pastilha()])
    _marcar_base_completa()

    resultado = ICMSSTMGService.analisar(
        "68138110",
        contexto={"uf_origem": "MG", "uf_destino": "MG"},
        descricao="PASTILHA DE FREIO BIZ",
    )

    assert resultado["decisao_st"] == "SIM"
    assert resultado["confirmado"] is True
    assert resultado["cest"] == "01.014.00"
    assert resultado["mva_original"] == pytest.approx(71.78)


def test_parser_importa_linha_com_mva_textual_para_nao_perder_enquadramento():
    html = """
    <table>
      <tr>
        <td>1.0</td><td>06.001.00</td><td>2207.10</td>
        <td>Álcool etílico e outros espíritos</td><td>6.1</td>
        <td>Vide Capítulo XII do Título II da Parte 1</td>
      </tr>
    </table>
    """

    registros = AtualizadorFontesOficiais._ler_st_mg_segmento_html(
        html,
        prefixo_cest="06",
        segmento="COMBUSTÍVEIS E LUBRIFICANTES",
        fonte_codigo="SEF_MG_ST_COMPLETA",
    )

    assert len(registros) == 1
    assert registros[0]["cest"] == "06.001.00"
    assert registros[0]["ncm_digitos"] == "220710"
    assert registros[0]["mva"] is None
    assert "Vide Capítulo" in registros[0]["mva_texto"]


def test_sincronizador_integral_usa_somente_paginas_da_parte_2():
    assert len(URL_SEFAZ_MG_ST_PAGINAS) == 3
    assert URL_SEFAZ_MG_ST_PAGINAS[0].endswith("anexovii2023_4.html")
    assert URL_SEFAZ_MG_ST_PAGINAS[1].endswith("anexovii2023_5.html")
    assert URL_SEFAZ_MG_ST_PAGINAS[2].endswith("anexovii2023_6.html")


def test_residual_porta_a_porta_sem_ncm_e_avaliado_antes_da_negativa(tmp_path, monkeypatch):
    _preparar_db(tmp_path, monkeypatch)
    BaseOficialRepository.substituir_st_mg([_linha_pastilha()])
    _marcar_base_completa()

    resultado = ICMSSTMGService.analisar(
        "99999999",
        contexto={
            "uf_origem": "MG",
            "uf_destino": "MG",
            "finalidade_automotiva": "NÃO É PEÇA AUTOMOTIVA",
            "operacao": "VENDA PORTA A PORTA",
        },
        descricao="PRODUTO DE VENDA DIRETA",
    )

    assert resultado["decisao_st"] == "SIM"
    assert resultado["confirmado"] is True
    assert resultado["cest"] == "28.999.00"
    assert resultado["mva_original"] == pytest.approx(30.0)


def test_parser_reconhece_residuais_sem_ncm_publicados_na_parte_2():
    html = """
    <table>
      <tr><td>999.0</td><td>01.999.00</td><td></td>
          <td>Outras peças, partes e acessórios para veículos automotores</td><td>1.2</td><td>71,78</td></tr>
      <tr><td>999.0</td><td>28.999.00</td><td></td>
          <td>Outros produtos comercializados pelo sistema de marketing direto porta a porta</td><td>28.1</td><td>30</td></tr>
    </table>
    """

    residuais = AtualizadorFontesOficiais._ler_st_mg_residuais_sem_ncm_html(html)
    cests = {item["cest"] for item in residuais}

    assert cests == RESIDUAIS_ST_MG_SEM_NCM_SUPORTADOS
    por_cest = {item["cest"]: item for item in residuais}
    assert por_cest["01.999.00"]["mva"] == pytest.approx(71.78)
    assert por_cest["28.999.00"]["mva"] == pytest.approx(30.0)


def test_sincronizacao_integral_so_promove_base_apos_validar_volume_segmentos_e_residuais(tmp_path, monkeypatch):
    _preparar_db(tmp_path, monkeypatch)

    linhas = []
    sequencia = 0
    for segmento in range(1, 21):
        prefixo = f"{segmento:02d}"
        for item in range(1, 16):
            sequencia += 1
            ncm = f"{10000000 + sequencia:08d}"
            linhas.append(
                f"<tr><td>{item}.0</td><td>{prefixo}.{item:03d}.00</td>"
                f"<td>{ncm[:4]}.{ncm[4:6]}.{ncm[6:]}</td>"
                f"<td>Produto oficial {segmento}-{item}</td><td>1.1</td><td>40,00</td></tr>"
            )
    linhas.extend(
        [
            "<tr><td>999.0</td><td>01.999.00</td><td></td>"
            "<td>Outras peças, partes e acessórios para veículos automotores</td><td>1.2</td><td>71,78</td></tr>",
            "<tr><td>999.0</td><td>28.999.00</td><td></td>"
            "<td>Outros produtos comercializados pelo sistema de marketing direto porta a porta</td><td>28.1</td><td>30</td></tr>",
        ]
    )
    html = ("<html><table>" + "".join(linhas) + "</table></html>").encode("utf-8")

    class _Headers:
        @staticmethod
        def get_content_charset():
            return "utf-8"

    class _Resposta:
        headers = _Headers()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return html

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: _Resposta())

    resultado = AtualizadorFontesOficiais(timeout=1).atualizar_st_mg_completa()
    cobertura = BaseOficialRepository.resumo_st_mg()

    assert resultado.status == "SUCESSO"
    assert resultado.inseridos == 300
    assert cobertura["base_completa"] is True
    assert cobertura["versao_schema"] == 3
    assert cobertura["registros"] == 300
    assert cobertura["segmentos"] == 20
