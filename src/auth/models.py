"""Modelos simples da autenticação local."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SessaoUsuario:
    id: int
    nome: str
    usuario: str
    perfil: str = "ADMINISTRADOR"


@dataclass(frozen=True, slots=True)
class ResultadoAutenticacao:
    sucesso: bool
    mensagem: str
    sessao: SessaoUsuario | None = None
    segundos_bloqueio: int = 0
