"""Persistência dos usuários do FiscalPro em um banco separado.

O banco de autenticação fica em ``dados/seguranca`` e não altera o banco fiscal
já utilizado pelo projeto.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.caminhos import PASTA_SEGURANCA

BASE_DIR = PASTA_SEGURANCA.parents[1]
DB_PADRAO = PASTA_SEGURANCA / "fiscalpro_auth.db"


class RepositorioUsuarios:
    def __init__(self, caminho_db: str | Path | None = None):
        self.caminho_db = Path(caminho_db) if caminho_db else DB_PADRAO

    def _conectar(self) -> sqlite3.Connection:
        self.caminho_db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.caminho_db, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def preparar(self) -> None:
        with closing(self._conectar()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    usuario TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    perfil TEXT NOT NULL DEFAULT 'ADMINISTRADOR',
                    senha_hash BLOB NOT NULL,
                    senha_salt BLOB NOT NULL,
                    iteracoes INTEGER NOT NULL,
                    recovery_hash BLOB NOT NULL,
                    recovery_salt BLOB NOT NULL,
                    ativo INTEGER NOT NULL DEFAULT 1,
                    tentativas INTEGER NOT NULL DEFAULT 0,
                    bloqueado_ate TEXT,
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL,
                    ultimo_acesso TEXT
                )
                """
            )
            conn.commit()

    def possui_usuario(self) -> bool:
        self.preparar()
        with closing(self._conectar()) as conn:
            linha = conn.execute("SELECT 1 FROM usuarios WHERE ativo = 1 LIMIT 1").fetchone()
            return linha is not None

    def criar_administrador(
        self,
        *,
        nome: str,
        usuario: str,
        senha_hash: bytes,
        senha_salt: bytes,
        iteracoes: int,
        recovery_hash: bytes,
        recovery_salt: bytes,
    ) -> int:
        agora = datetime.now().isoformat(timespec="seconds")
        with closing(self._conectar()) as conn:
            cursor = conn.execute(
                """
                INSERT INTO usuarios (
                    nome, usuario, perfil, senha_hash, senha_salt, iteracoes,
                    recovery_hash, recovery_salt, ativo, tentativas,
                    criado_em, atualizado_em
                ) VALUES (?, ?, 'ADMINISTRADOR', ?, ?, ?, ?, ?, 1, 0, ?, ?)
                """,
                (
                    nome,
                    usuario,
                    sqlite3.Binary(senha_hash),
                    sqlite3.Binary(senha_salt),
                    int(iteracoes),
                    sqlite3.Binary(recovery_hash),
                    sqlite3.Binary(recovery_salt),
                    agora,
                    agora,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def buscar_por_usuario(self, usuario: str) -> sqlite3.Row | None:
        with closing(self._conectar()) as conn:
            return conn.execute(
                "SELECT * FROM usuarios WHERE usuario = ? COLLATE NOCASE LIMIT 1",
                (usuario,),
            ).fetchone()

    def registrar_sucesso(self, usuario_id: int) -> None:
        agora = datetime.now().isoformat(timespec="seconds")
        with closing(self._conectar()) as conn:
            conn.execute(
                """
                UPDATE usuarios
                   SET tentativas = 0,
                       bloqueado_ate = NULL,
                       ultimo_acesso = ?,
                       atualizado_em = ?
                 WHERE id = ?
                """,
                (agora, agora, usuario_id),
            )
            conn.commit()

    def registrar_falha(self, usuario_id: int, tentativas: int, bloqueado_ate: str | None) -> None:
        agora = datetime.now().isoformat(timespec="seconds")
        with closing(self._conectar()) as conn:
            conn.execute(
                """
                UPDATE usuarios
                   SET tentativas = ?, bloqueado_ate = ?, atualizado_em = ?
                 WHERE id = ?
                """,
                (int(tentativas), bloqueado_ate, agora, usuario_id),
            )
            conn.commit()

    def atualizar_senha(
        self,
        usuario_id: int,
        *,
        senha_hash: bytes,
        senha_salt: bytes,
        iteracoes: int,
        recovery_hash: bytes | None = None,
        recovery_salt: bytes | None = None,
    ) -> None:
        agora = datetime.now().isoformat(timespec="seconds")
        with closing(self._conectar()) as conn:
            if recovery_hash is None or recovery_salt is None:
                conn.execute(
                    """
                    UPDATE usuarios
                       SET senha_hash = ?, senha_salt = ?, iteracoes = ?,
                           tentativas = 0, bloqueado_ate = NULL, atualizado_em = ?
                     WHERE id = ?
                    """,
                    (
                        sqlite3.Binary(senha_hash),
                        sqlite3.Binary(senha_salt),
                        int(iteracoes),
                        agora,
                        usuario_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE usuarios
                       SET senha_hash = ?, senha_salt = ?, iteracoes = ?,
                           recovery_hash = ?, recovery_salt = ?,
                           tentativas = 0, bloqueado_ate = NULL, atualizado_em = ?
                     WHERE id = ?
                    """,
                    (
                        sqlite3.Binary(senha_hash),
                        sqlite3.Binary(senha_salt),
                        int(iteracoes),
                        sqlite3.Binary(recovery_hash),
                        sqlite3.Binary(recovery_salt),
                        agora,
                        usuario_id,
                    ),
                )
            conn.commit()

    @staticmethod
    def como_dict(linha: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(linha) if linha is not None else None
