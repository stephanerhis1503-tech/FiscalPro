"""Preferências não sensíveis da tela de login."""

from __future__ import annotations

import json
from pathlib import Path

from src.core.caminhos import PASTA_SEGURANCA

ARQUIVO_PADRAO = PASTA_SEGURANCA / "preferencias_login.json"


class PreferenciasLogin:
    def __init__(self, caminho: str | Path | None = None):
        self.caminho = Path(caminho) if caminho else ARQUIVO_PADRAO

    def carregar_usuario(self) -> str:
        try:
            dados = json.loads(self.caminho.read_text(encoding="utf-8"))
            return str(dados.get("ultimo_usuario", "")).strip()
        except (OSError, ValueError, TypeError):
            return ""

    def salvar_usuario(self, usuario: str, lembrar: bool) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        dados = {"ultimo_usuario": usuario.strip() if lembrar else ""}
        self.caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
