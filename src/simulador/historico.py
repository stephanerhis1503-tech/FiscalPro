"""Histórico persistente do Simulador Tributário — Sprint 13.7."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.banco.conexao import Banco
from src.simulador.motor_simulador import ResultadoSimulacao


class HistoricoSimuladorRepository:
    @classmethod
    def preparar_banco(cls) -> None:
        conn = Banco.conectar()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historico_simulacao_tributaria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ncm TEXT NOT NULL,
                descricao_cenario TEXT,
                empresa TEXT,
                regime TEXT,
                operacao TEXT,
                finalidade TEXT,
                uf_origem TEXT,
                uf_destino TEXT,
                data_operacao DATE,
                valor_operacao REAL DEFAULT 0,
                total_tributos_atual REAL DEFAULT 0,
                total_reforma REAL DEFAULT 0,
                diferenca REAL DEFAULT 0,
                confiabilidade REAL DEFAULT 0,
                entrada_json TEXT NOT NULL,
                resultado_json TEXT NOT NULL,
                versao_motor TEXT DEFAULT '13.7',
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_simulacao_ncm_data ON historico_simulacao_tributaria(ncm, id DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_simulacao_contexto ON historico_simulacao_tributaria(empresa, regime, operacao, uf_destino)"
        )
        conn.commit()
        conn.close()

    @classmethod
    def salvar(cls, resultado: ResultadoSimulacao) -> int:
        cls.preparar_banco()
        entrada = resultado.entrada
        conn = Banco.conectar()
        cursor = conn.execute(
            """
            INSERT INTO historico_simulacao_tributaria (
                ncm, descricao_cenario, empresa, regime, operacao, finalidade,
                uf_origem, uf_destino, data_operacao, valor_operacao,
                total_tributos_atual, total_reforma, diferenca, confiabilidade,
                entrada_json, resultado_json, versao_motor
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entrada.ncm,
                entrada.descricao_cenario,
                entrada.empresa,
                entrada.regime,
                entrada.operacao,
                entrada.finalidade,
                entrada.uf_origem,
                entrada.uf_destino,
                entrada.data_operacao,
                float(resultado.valor_operacao),
                float(resultado.total_tributos_atual),
                float(resultado.total_reforma),
                float(resultado.diferenca_reforma_atual),
                float(resultado.confiabilidade),
                json.dumps(entrada.para_dict(), ensure_ascii=False),
                json.dumps(resultado.para_dict(), ensure_ascii=False),
                resultado.versao_motor,
            ),
        )
        registro_id = int(cursor.lastrowid)
        conn.commit()
        conn.close()
        return registro_id

    @classmethod
    def listar(cls, ncm: str = "", limite: int = 200) -> List[Dict[str, Any]]:
        cls.preparar_banco()
        conn = Banco.conectar()
        parametros: list[Any] = []
        filtro = ""
        digitos = "".join(c for c in str(ncm or "") if c.isdigit())
        if digitos:
            filtro = "WHERE ncm = ?"
            parametros.append(digitos)
        parametros.append(max(1, min(int(limite), 1000)))
        linhas = conn.execute(
            f"""
            SELECT id, ncm, descricao_cenario, empresa, regime, operacao, finalidade,
                   uf_origem, uf_destino, data_operacao, valor_operacao,
                   total_tributos_atual, total_reforma, diferenca, confiabilidade,
                   versao_motor, criado_em
              FROM historico_simulacao_tributaria
              {filtro}
             ORDER BY id DESC
             LIMIT ?
            """,
            tuple(parametros),
        ).fetchall()
        conn.close()
        return [dict(linha) for linha in linhas]

    @classmethod
    def buscar(cls, registro_id: int) -> Optional[ResultadoSimulacao]:
        cls.preparar_banco()
        conn = Banco.conectar()
        linha = conn.execute(
            "SELECT resultado_json FROM historico_simulacao_tributaria WHERE id = ?",
            (int(registro_id),),
        ).fetchone()
        conn.close()
        if not linha:
            return None
        return ResultadoSimulacao.de_dict(json.loads(linha["resultado_json"]))

    @classmethod
    def excluir(cls, registro_id: int) -> None:
        cls.preparar_banco()
        conn = Banco.conectar()
        conn.execute("DELETE FROM historico_simulacao_tributaria WHERE id = ?", (int(registro_id),))
        conn.commit()
        conn.close()


__all__ = ["HistoricoSimuladorRepository"]
