"""Verificacao de contadores tributarios SEM criar/alterar arquivos oficiais."""
import sqlite3

from src.services.diagnostico_regras_operacionais_service import (
    diagnosticar_regras_operacionais, texto_diagnostico_regras,
)


def test_conta_regras_no_banco_temporario_sem_gravar(tmp_path):
    banco = tmp_path / "isolado.db"
    with sqlite3.connect(banco) as conn:
        conn.execute("CREATE TABLE tributacao_atual (id INTEGER, status TEXT)")
        conn.execute("CREATE TABLE tributacao_base (id INTEGER, ativo INTEGER)")
        conn.execute("INSERT INTO tributacao_atual VALUES (1, 'VIGENTE')")
        conn.execute("INSERT INTO tributacao_atual VALUES (2, 'RASCUNHO')")
        conn.execute("INSERT INTO tributacao_base VALUES (1, 1)")
        conn.execute("INSERT INTO tributacao_base VALUES (2, 0)")
    antes = banco.read_bytes()
    resultado = diagnosticar_regras_operacionais(banco)
    assert resultado["regras_por_operacao"] == 2
    assert resultado["regras_vigentes"] == 1
    assert resultado["cadastros_produto_total"] == 2
    assert resultado["cadastros_produto_ativos"] == 1
    assert banco.read_bytes() == antes
    assert "NCM, empresa, regime" in texto_diagnostico_regras(resultado)


def test_nao_cria_banco_ausente(tmp_path):
    banco = tmp_path / "inexistente.db"
    resultado = diagnosticar_regras_operacionais(banco)
    assert resultado["existe"] is False
    assert not banco.exists()


def test_sem_tabelas_eh_indisponivel_nao_zero(tmp_path):
    banco = tmp_path / "vazio.db"
    with sqlite3.connect(banco) as conn:
        conn.execute("CREATE TABLE outra_tabela (id INTEGER)")
    resultado = diagnosticar_regras_operacionais(banco)
    assert resultado["regras_por_operacao"] is None
    assert resultado["cadastros_produto_ativos"] is None
    assert "indisponível" in texto_diagnostico_regras(resultado, isolado=True)


def test_texto_discrimina_projeto_local_sem_inferir_banco_oficial(tmp_path):
    banco = tmp_path / "dev.db"
    with sqlite3.connect(banco) as conn:
        conn.execute("CREATE TABLE tributacao_atual (id INTEGER, status TEXT)")
        conn.execute("CREATE TABLE tributacao_base (id INTEGER, ativo INTEGER)")
    dados = diagnosticar_regras_operacionais(banco)
    texto = texto_diagnostico_regras(dados, ambiente="PROJETO LOCAL (CÓDIGO-FONTE)")
    assert "PROJETO LOCAL" in texto
    assert "Não conclua que o FiscalPro instalado" in texto
    assert "0" in texto


def test_nova_ui_disponibiliza_conferencia_opcional_por_arquivo():
    from pathlib import Path

    fonte = (
        Path(__file__).resolve().parents[1] / "src" / "ui" / "janela_principal.py"
    ).read_text(encoding="utf-8")
    assert "def conferir_outro_banco_tributario" in fonte
    assert "Conferir outro banco (leitura)" in fonte
    assert "diagnosticar_regras_operacionais(banco)" in fonte
    assert "PROJETO LOCAL (CÓDIGO-FONTE)" in fonte


def test_lista_sete_regras_apenas_leitura(tmp_path):
    from src.services.diagnostico_regras_operacionais_service import (
        listar_regras_operacionais, texto_lista_regras,
    )
    banco = tmp_path / "regras.db"
    with sqlite3.connect(banco) as conn:
        conn.execute(
            "CREATE TABLE tributacao_atual ("
            "id INTEGER, ncm TEXT, empresa TEXT, status TEXT,"
            "operacao TEXT, finalidade TEXT, vigencia_inicio TEXT, vigencia_fim TEXT)"
        )
        for i in range(7):
            conn.execute(
                "INSERT INTO tributacao_atual VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (i + 1, "87141000", "EMPRESA TESTE", "VIGENTE", "ENTRADA", "REVENDA", "01/10/2026", ""),
            )
    anterior = banco.read_bytes()
    regras = listar_regras_operacionais(banco)
    texto = texto_lista_regras(regras)
    assert len(regras) == 7
    assert "NCM 87141000" in texto
    assert "Empresa: EMPRESA TESTE" in texto
    assert banco.read_bytes() == anterior


def test_lista_compatibilidade_sem_tabela(tmp_path):
    from src.services.diagnostico_regras_operacionais_service import (
        listar_regras_operacionais,
    )
    banco = tmp_path / "sem_regras.db"
    with sqlite3.connect(banco) as conn:
        conn.execute("CREATE TABLE outra (id INTEGER)")
    assert listar_regras_operacionais(banco) == []
