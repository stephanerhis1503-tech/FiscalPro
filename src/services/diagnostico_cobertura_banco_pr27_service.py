"""Mensagem de diagnostico de cobertura no ambiente PORTATIL/ISOLADO PR27.

Nao abre bancos e nao consulta producao; apenas interpreta os contadores
ja calculados pelo auditor no banco que esta em uso.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


PASTA_PR27 = "fiscalpro_teste_ficha_pr27"


def aviso_banco_isolado_pr27(resultado: Any, diretorio_dados: str | None) -> str:
    """Explica 0% no clone, sem inferir ausencia de regras na instalacao oficial."""
    pasta = str(diretorio_dados or "").strip().strip('"').rstrip("/\\")
    if not pasta or Path(pasta).name.casefold() != PASTA_PR27:
        return ""
    if not bool(getattr(resultado, "auditoria_tributaria_inconclusiva", False)):
        return ""

    contadores = getattr(resultado, "regras_operacionais_banco", {}) or {}
    atual = contadores.get("tributacao_atual")
    produto = contadores.get("tributacao_base_ativa")
    if atual == 0 and produto == 0:
        descricao = (
            "O banco isolado do teste esta com 0 regras por operacao e "
            "0 cadastros tributarios ativos por produto."
        )
    elif isinstance(atual, int) and isinstance(produto, int):
        descricao = (
            f"O banco isolado do teste tem {atual} regras por operacao e "
            f"{produto} cadastros ativos por produto, mas nenhuma regra "
            "foi aplicada aos itens desta auditoria."
        )
    else:
        descricao = "A quantidade de regras no banco isolado nao pode ser confirmada."

    return (
        "AMBIENTE DE TESTE PR27 - COPIA ISOLADA\n"
        + descricao
        + "\nO arquivo TESTAR_FICHA_PR27.bat copia o banco apenas na primeira "
        "execucao; nas proximas usa a copia ja existente. Isso NAO comprova "
        "que o banco oficial esteja sem regras.\n"
        "Nao copie, substitua ou exclua bancos nem aprove regras em lote "
        "para elevar o percentual. Confira o cadastro no banco correto "
        "e homologue cada regra fiscal individualmente."
    )
