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
