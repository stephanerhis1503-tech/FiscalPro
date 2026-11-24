"""Consulta estritamente de leitura às regras operacionais do FiscalPro.

Não cria bancos, tabelas, migrações, regras ou arquivos. Não confunde tabelas
oficiais de NCM/ST com regras cadastradas e não calcula cobertura de SPED.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def diagnosticar_regras_operacionais(caminho: str | Path) -> dict[str, Any]:
    """Retorna quantidades no banco indicado, inclusive tabelas ausentes.

    Conexão SQLite mode=ro evita criar arquivos e evita escrita acidental.
    Contagens existentes não comprovam vigência nem aderência a cada operação.
    """
    banco = Path(caminho).expanduser().resolve()
    resultado: dict[str, Any] = {
        "caminho": str(banco),
        "existe": banco.is_file(),
        "tabelas_presentes": [],
        "regras_por_operacao": None,
        "regras_vigentes": None,
        "cadastros_produto_total": None,
        "cadastros_produto_ativos": None,
    }
    if not resultado["existe"]:
        return resultado

    with sqlite3.connect(banco.as_uri() + "?mode=ro", uri=True, timeout=10) as conn:
        tabelas = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND "
                "name IN ('tributacao_atual', 'tributacao_base')"
            )
        }
        resultado["tabelas_presentes"] = sorted(tabelas)
        if "tributacao_atual" in tabelas:
            resultado["regras_por_operacao"] = int(
                conn.execute("SELECT COUNT(*) FROM tributacao_atual").fetchone()[0]
            )
            colunas = {
                str(row[1]) for row in conn.execute(
                    'PRAGMA table_info("tributacao_atual")'
                )
            }
            if "status" in colunas:
                resultado["regras_vigentes"] = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM tributacao_atual "
                        "WHERE UPPER(TRIM(COALESCE(status, ''))) = 'VIGENTE'"
                    ).fetchone()[0]
                )
        if "tributacao_base" in tabelas:
            resultado["cadastros_produto_total"] = int(
                conn.execute("SELECT COUNT(*) FROM tributacao_base").fetchone()[0]
            )
            colunas = {
                str(row[1]) for row in conn.execute(
                    'PRAGMA table_info("tributacao_base")'
                )
            }
            if "ativo" in colunas:
                resultado["cadastros_produto_ativos"] = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM tributacao_base WHERE ativo = 1"
                    ).fetchone()[0]
                )
    return resultado


def texto_diagnostico_regras(dados: dict[str, Any], *, isolado: bool = False) -> str:
    """Não tira conclusões de conformidade fiscal de contagens cadastrais."""
    def numero(valor: Any) -> str:
        return f"{valor:,}".replace(",", ".") if isinstance(valor, int) else "indisponível"

    linhas = ["DIAGNÓSTICO DE REGRAS — SOMENTE LEITURA", ""]
    linhas.append("Ambiente: " + ("TESTE ISOLADO PR27" if isolado else "BANCO DESTA INSTALAÇÃO"))
    linhas.append("Banco: " + str(dados.get("caminho") or "(não informado)"))
    if not dados.get("existe"):
        linhas += ["", "Banco não encontrado nesse caminho. Nenhum arquivo foi criado."]
        return "\n".join(linhas)
    linhas += [
        "",
        "Regras por operação (tributacao_atual): "
        + numero(dados.get("regras_por_operacao")),
        "Dessas, com status VIGENTE: " + numero(dados.get("regras_vigentes")),
        "Cadastros por produto (tributacao_base): "
        + numero(dados.get("cadastros_produto_total")),
        "Desses, marcados como ativos: "
        + numero(dados.get("cadastros_produto_ativos")),
        "",
        "Esses totais são cadastros operacionais, não o catálogo oficial de NCM/ST.",
        "Mesmo que existam regras, só contam na auditoria as aplicáveis ao",
        "NCM, empresa, regime, UF, operação, finalidade e vigência.",
        "Nenhum cadastro, XML ou SPED foi alterado por esta consulta.",
    ]
    return "\n".join(linhas)
