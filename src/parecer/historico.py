"""Histórico dos Pareceres Tributários — Sprint 13.4."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.banco.conexao import Banco


class HistoricoParecerRepository:
    @staticmethod
    def preparar_banco() -> None:
        conn = Banco.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS historico_parecer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ncm TEXT NOT NULL,
                descricao TEXT,
                empresa TEXT,
                regime TEXT,
                operacao TEXT,
                contexto_json TEXT,
                parecer_json TEXT NOT NULL,
                confiabilidade REAL DEFAULT 0,
                nivel_confiabilidade TEXT DEFAULT '',
                data_operacao DATE,
                regra_atual_id INTEGER,
                regra_reforma_id INTEGER,
                versao_motor TEXT DEFAULT '',
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        existentes = {linha[1] for linha in cursor.execute("PRAGMA table_info(historico_parecer)").fetchall()}
        for coluna, definicao in (
            ("confiabilidade", "REAL DEFAULT 0"),
            ("nivel_confiabilidade", "TEXT DEFAULT ''"),
            ("data_operacao", "DATE"),
            ("regra_atual_id", "INTEGER"),
            ("regra_reforma_id", "INTEGER"),
            ("versao_motor", "TEXT DEFAULT ''"),
        ):
            if coluna not in existentes:
                cursor.execute(f"ALTER TABLE historico_parecer ADD COLUMN {coluna} {definicao}")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_historico_parecer_ncm ON historico_parecer(ncm, id DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_historico_parecer_contexto ON historico_parecer(ncm, empresa, regime, operacao)")
        conn.commit()
        conn.close()

    @staticmethod
    def _normalizar_ncm(ncm: Any) -> str:
        return "".join(c for c in str(ncm or "") if c.isdigit())

    @classmethod
    def salvar(cls, parecer) -> int:
        cls.preparar_banco()
        dados = parecer.para_dict()
        contexto = dados.get("contexto", {})
        rastreabilidade = dados.get("regras_aplicadas", {})

        def id_regra(texto: Any) -> Optional[int]:
            digitos = "".join(c for c in str(texto or "") if c.isdigit())
            return int(digitos) if digitos else None

        conn = Banco.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO historico_parecer
            (ncm, descricao, empresa, regime, operacao, contexto_json, parecer_json,
             confiabilidade, nivel_confiabilidade, data_operacao, regra_atual_id,
             regra_reforma_id, versao_motor)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parecer.ncm,
                parecer.descricao,
                contexto.get("Empresa", contexto.get("empresa", "")),
                contexto.get("Regime", contexto.get("regime", "")),
                contexto.get("Operação", contexto.get("operação", contexto.get("operacao", ""))),
                json.dumps(contexto, ensure_ascii=False),
                json.dumps(dados, ensure_ascii=False),
                float(parecer.confiabilidade or 0),
                parecer.nivel_confiabilidade,
                cls._data_iso_contexto(contexto.get("Data da operação", contexto.get("data_operacao"))),
                id_regra(rastreabilidade.get("Regra atual")),
                id_regra(rastreabilidade.get("Regra da reforma")),
                parecer.versao_motor,
            ),
        )
        conn.commit()
        registro_id = int(cursor.lastrowid)
        conn.close()
        return registro_id

    @staticmethod
    def _data_iso_contexto(valor: Any) -> Optional[str]:
        from datetime import datetime

        texto = str(valor or "").strip()
        if not texto:
            return None
        for formato in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(texto[:10], formato).date().isoformat()
            except ValueError:
                continue
        return None

    @classmethod
    def listar_por_ncm(cls, ncm: Any, limite: int = 50) -> List[Dict[str, Any]]:
        cls.preparar_banco()
        conn = Banco.conectar()
        linhas = conn.execute(
            """
            SELECT id, ncm, descricao, empresa, regime, operacao,
                   confiabilidade, nivel_confiabilidade, data_operacao,
                   regra_atual_id, regra_reforma_id, versao_motor, criado_em
            FROM historico_parecer
            WHERE ncm = ?
            ORDER BY id DESC LIMIT ?
            """,
            (cls._normalizar_ncm(ncm), int(limite)),
        ).fetchall()
        conn.close()
        return [dict(linha) for linha in linhas]

    @classmethod
    def buscar_por_id(cls, registro_id: int) -> Optional[Dict[str, Any]]:
        cls.preparar_banco()
        conn = Banco.conectar()
        linha = conn.execute("SELECT * FROM historico_parecer WHERE id = ?", (int(registro_id),)).fetchone()
        conn.close()
        if not linha:
            return None
        item = dict(linha)
        try:
            item["contexto"] = json.loads(item.get("contexto_json") or "{}")
        except json.JSONDecodeError:
            item["contexto"] = {}
        try:
            item["parecer"] = json.loads(item.get("parecer_json") or "{}")
        except json.JSONDecodeError:
            item["parecer"] = {}
        return item
