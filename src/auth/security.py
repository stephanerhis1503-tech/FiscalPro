"""Funções criptográficas sem dependências externas.

As senhas nunca são gravadas em texto puro. O FiscalPro usa PBKDF2-HMAC-SHA256
com sal aleatório por usuário.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string

ITERACOES_PADRAO = 310_000
TAMANHO_SAL = 16


def gerar_sal() -> bytes:
    return secrets.token_bytes(TAMANHO_SAL)


def derivar_hash(segredo: str, sal: bytes, iteracoes: int = ITERACOES_PADRAO) -> bytes:
    if not isinstance(segredo, str):
        raise TypeError("O segredo deve ser texto.")
    return hashlib.pbkdf2_hmac(
        "sha256",
        segredo.encode("utf-8"),
        sal,
        int(iteracoes),
    )


def comparar_hash(segredo: str, sal: bytes, hash_esperado: bytes, iteracoes: int) -> bool:
    calculado = derivar_hash(segredo, sal, iteracoes)
    return hmac.compare_digest(calculado, hash_esperado)


def gerar_codigo_recuperacao() -> str:
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    blocos = ["".join(secrets.choice(alfabeto) for _ in range(4)) for _ in range(3)]
    return "-".join(blocos)


def normalizar_codigo_recuperacao(codigo: str) -> str:
    permitido = set(string.ascii_letters + string.digits)
    limpo = "".join(ch for ch in (codigo or "") if ch in permitido)
    return limpo.upper()
