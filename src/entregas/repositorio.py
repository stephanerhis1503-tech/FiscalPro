"""Persistência do Controle de Entregas do FiscalPro.

Hotfix 17.8.15 — grade mensal enxuta, preservando históricos das colunas removidas.
O módulo usa um banco próprio para não misturar o controle operacional com
SPED, tributação ou contas a pagar.
"""

from __future__ import annotations

import calendar
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from src.core.caminhos import BANCO_ENTREGAS


class EntregasRepositorio:
    def __init__(self, banco: Path = BANCO_ENTREGAS):
        self.banco = Path(banco)
        self.preparar_banco()

    @contextmanager
    def _conectar(self) -> Iterator[sqlite3.Connection]:
        self.banco.parent.mkdir(parents=True, exist_ok=True)
        conexao = sqlite3.connect(self.banco, timeout=30)
        conexao.row_factory = sqlite3.Row
        conexao.execute("PRAGMA foreign_keys = ON")
        try:
            yield conexao
            conexao.commit()
        except Exception:
            conexao.rollback()
            raise
        finally:
            conexao.close()

    def preparar_banco(self) -> None:
        with self._conectar() as conexao:
            conexao.executescript(
                """
                CREATE TABLE IF NOT EXISTS empresas_entregas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    cnpj TEXT NOT NULL DEFAULT '',
                    tipo_pessoa TEXT NOT NULL DEFAULT 'PJ',
                    ativa INTEGER NOT NULL DEFAULT 1,
                    manual INTEGER NOT NULL DEFAULT 0,
                    criado_em TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS modelos_entrega (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empresa_id INTEGER NOT NULL,
                    tipo_arquivo TEXT NOT NULL COLLATE NOCASE,
                    dia_prazo INTEGER NOT NULL DEFAULT 10,
                    meses_apos_competencia INTEGER NOT NULL DEFAULT 1,
                    destinatario TEXT NOT NULL DEFAULT '',
                    observacoes TEXT NOT NULL DEFAULT '',
                    ativo INTEGER NOT NULL DEFAULT 1,
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL,
                    FOREIGN KEY(empresa_id) REFERENCES empresas_entregas(id) ON DELETE CASCADE,
                    UNIQUE(empresa_id, tipo_arquivo)
                );

                CREATE TABLE IF NOT EXISTS entregas_arquivos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empresa_id INTEGER NOT NULL,
                    competencia TEXT NOT NULL,
                    tipo_arquivo TEXT NOT NULL COLLATE NOCASE,
                    prazo TEXT NOT NULL DEFAULT '',
                    data_entrega TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'PENDENTE',
                    destinatario TEXT NOT NULL DEFAULT '',
                    caminho_arquivo TEXT NOT NULL DEFAULT '',
                    observacoes TEXT NOT NULL DEFAULT '',
                    modelo_id INTEGER,
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL,
                    FOREIGN KEY(empresa_id) REFERENCES empresas_entregas(id) ON DELETE RESTRICT,
                    FOREIGN KEY(modelo_id) REFERENCES modelos_entrega(id) ON DELETE SET NULL,
                    UNIQUE(empresa_id, competencia, tipo_arquivo)
                );

                CREATE INDEX IF NOT EXISTS idx_entregas_competencia
                    ON entregas_arquivos(competencia);
                CREATE INDEX IF NOT EXISTS idx_entregas_status
                    ON entregas_arquivos(status);
                CREATE INDEX IF NOT EXISTS idx_entregas_empresa_comp
                    ON entregas_arquivos(empresa_id, competencia);

                CREATE TABLE IF NOT EXISTS historico_entregas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entrega_id INTEGER,
                    acao TEXT NOT NULL,
                    detalhe TEXT NOT NULL DEFAULT '',
                    realizado_em TEXT NOT NULL,
                    FOREIGN KEY(entrega_id) REFERENCES entregas_arquivos(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS observacoes_competencia (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empresa_id INTEGER NOT NULL,
                    competencia TEXT NOT NULL,
                    observacoes TEXT NOT NULL DEFAULT '',
                    atualizado_em TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(empresa_id) REFERENCES empresas_entregas(id) ON DELETE CASCADE,
                    UNIQUE(empresa_id, competencia)
                );
                """
            )

            # Migração 17.6.1: modelos antigos passam a vencer no mês seguinte
            # à competência, preservando todos os cadastros já feitos pela usuária.
            colunas_modelos = {
                str(linha["name"])
                for linha in conexao.execute("PRAGMA table_info(modelos_entrega)").fetchall()
            }
            if "meses_apos_competencia" not in colunas_modelos:
                conexao.execute(
                    "ALTER TABLE modelos_entrega "
                    "ADD COLUMN meses_apos_competencia INTEGER NOT NULL DEFAULT 1"
                )

            # Migração 17.8.13: regime por empresa e detalhes de cada célula da grade.
            colunas_empresas = {
                str(linha["name"])
                for linha in conexao.execute("PRAGMA table_info(empresas_entregas)").fetchall()
            }
            if "regime" not in colunas_empresas:
                conexao.execute(
                    "ALTER TABLE empresas_entregas ADD COLUMN regime TEXT NOT NULL DEFAULT ''"
                )
            if "manual" not in colunas_empresas:
                conexao.execute(
                    "ALTER TABLE empresas_entregas ADD COLUMN manual INTEGER NOT NULL DEFAULT 0"
                )
            if "tipo_pessoa" not in colunas_empresas:
                conexao.execute(
                    "ALTER TABLE empresas_entregas ADD COLUMN tipo_pessoa TEXT NOT NULL DEFAULT 'PJ'"
                )
                # Compatibilidade: se alguma instalação já tiver documento com
                # 11 dígitos, ele passa a ser reconhecido como pessoa física.
                conexao.execute(
                    "UPDATE empresas_entregas SET tipo_pessoa = 'PF' "
                    "WHERE LENGTH(TRIM(COALESCE(cnpj, ''))) = 11"
                )

            colunas_entregas = {
                str(linha["name"])
                for linha in conexao.execute("PRAGMA table_info(entregas_arquivos)").fetchall()
            }
            if "valor" not in colunas_entregas:
                conexao.execute(
                    "ALTER TABLE entregas_arquivos ADD COLUMN valor REAL NOT NULL DEFAULT 0"
                )
            if "protocolo" not in colunas_entregas:
                conexao.execute(
                    "ALTER TABLE entregas_arquivos ADD COLUMN protocolo TEXT NOT NULL DEFAULT ''"
                )

    @staticmethod
    def _agora() -> str:
        return datetime.now().isoformat(timespec="seconds")

    # ------------------------------------------------------------------
    # Empresas
    # ------------------------------------------------------------------
    def salvar_empresa(
        self,
        nome: str,
        cnpj: str = "",
        regime: str = "",
        tipo_pessoa: str = "PJ",
        *,
        manual: bool = False,
    ) -> int:
        nome = " ".join((nome or "").strip().split())
        if not nome:
            raise ValueError("Informe o nome da empresa/pessoa.")
        cnpj = "".join(ch for ch in (cnpj or "") if ch.isdigit())
        regime = " ".join((regime or "").strip().upper().split())
        tipo_pessoa = str(tipo_pessoa or "PJ").strip().upper()
        if tipo_pessoa not in {"PJ", "PF"}:
            tipo_pessoa = "PJ"
        agora = self._agora()
        with self._conectar() as conexao:
            existente = conexao.execute(
                "SELECT id FROM empresas_entregas WHERE nome = ? COLLATE NOCASE",
                (nome,),
            ).fetchone()
            if existente:
                conexao.execute(
                    """
                    UPDATE empresas_entregas
                       SET ativa = 1,
                           cnpj = CASE WHEN ? <> '' THEN ? ELSE cnpj END,
                           regime = CASE WHEN ? <> '' THEN ? ELSE regime END,
                           tipo_pessoa = ?,
                           manual = CASE WHEN ? = 1 THEN 1 ELSE manual END
                     WHERE id = ?
                    """,
                    (
                        cnpj, cnpj, regime, regime, tipo_pessoa,
                        int(bool(manual)), int(existente["id"]),
                    ),
                )
                return int(existente["id"])
            cursor = conexao.execute(
                "INSERT INTO empresas_entregas(nome, cnpj, regime, tipo_pessoa, ativa, manual, criado_em) "
                "VALUES (?, ?, ?, ?, 1, ?, ?)",
                (nome, cnpj, regime, tipo_pessoa, int(bool(manual)), agora),
            )
            return int(cursor.lastrowid)

    def listar_empresas(
        self,
        incluir_inativas: bool = False,
        incluir_pessoas_fisicas: bool = False,
    ) -> list[sqlite3.Row]:
        filtros: list[str] = []
        if not incluir_inativas:
            filtros.append("ativa = 1")
        if not incluir_pessoas_fisicas:
            filtros.append("COALESCE(tipo_pessoa, 'PJ') <> 'PF'")
        where = f"WHERE {' AND '.join(filtros)}" if filtros else ""
        with self._conectar() as conexao:
            return list(
                conexao.execute(
                    f"SELECT id, nome, cnpj, regime, tipo_pessoa, ativa, manual "
                    f"FROM empresas_entregas {where} ORDER BY nome"
                ).fetchall()
            )

    def obter_empresa_por_nome(self, nome: str) -> sqlite3.Row | None:
        with self._conectar() as conexao:
            return conexao.execute(
                "SELECT id, nome, cnpj, regime, tipo_pessoa, ativa, manual "
                "FROM empresas_entregas WHERE nome = ? COLLATE NOCASE",
                ((nome or "").strip(),),
            ).fetchone()

    def obter_empresa_por_id(self, empresa_id: int) -> sqlite3.Row | None:
        with self._conectar() as conexao:
            return conexao.execute(
                "SELECT id, nome, cnpj, regime, tipo_pessoa, ativa, manual "
                "FROM empresas_entregas WHERE id = ?",
                (int(empresa_id),),
            ).fetchone()

    def obter_empresa_por_documento(
        self, documento: str, *, excluir_id: int | None = None
    ) -> sqlite3.Row | None:
        documento = "".join(ch for ch in str(documento or "") if ch.isdigit())
        if not documento:
            return None
        parametros: list[object] = [documento]
        filtro = "cnpj = ?"
        if excluir_id is not None:
            filtro += " AND id <> ?"
            parametros.append(int(excluir_id))
        with self._conectar() as conexao:
            return conexao.execute(
                "SELECT id, nome, cnpj, regime, tipo_pessoa, ativa, manual "
                f"FROM empresas_entregas WHERE {filtro} LIMIT 1",
                parametros,
            ).fetchone()

    def atualizar_empresa(
        self,
        empresa_id: int,
        *,
        nome: str,
        cnpj: str = "",
        regime: str = "",
        tipo_pessoa: str = "PJ",
    ) -> None:
        nome = " ".join((nome or "").strip().split())
        if not nome:
            raise ValueError("Informe o nome da empresa/pessoa.")
        cnpj = "".join(ch for ch in (cnpj or "") if ch.isdigit())
        regime = " ".join((regime or "").strip().upper().split()) or "A DEFINIR"
        tipo_pessoa = str(tipo_pessoa or "PJ").strip().upper()
        if tipo_pessoa not in {"PJ", "PF"}:
            tipo_pessoa = "PJ"
        with self._conectar() as conexao:
            conflito = conexao.execute(
                "SELECT id FROM empresas_entregas "
                "WHERE nome = ? COLLATE NOCASE AND id <> ?",
                (nome, int(empresa_id)),
            ).fetchone()
            if conflito:
                raise ValueError("Já existe outro cadastro com esse nome.")
            conexao.execute(
                """
                UPDATE empresas_entregas
                   SET nome = ?, cnpj = ?, regime = ?, tipo_pessoa = ?, ativa = 1
                 WHERE id = ?
                """,
                (nome, cnpj, regime, tipo_pessoa, int(empresa_id)),
            )

    def excluir_empresa(self, empresa_id: int) -> None:
        """Exclui o cadastro central quando não há entregas históricas vinculadas."""
        with self._conectar() as conexao:
            empresa = conexao.execute(
                "SELECT id FROM empresas_entregas WHERE id = ?", (int(empresa_id),)
            ).fetchone()
            if empresa is None:
                raise ValueError("Cadastro não localizado.")
            vinculadas = conexao.execute(
                "SELECT COUNT(*) AS total FROM entregas_arquivos WHERE empresa_id = ?",
                (int(empresa_id),),
            ).fetchone()
            if int(vinculadas["total"] or 0):
                raise ValueError(
                    "Este cadastro possui entregas históricas vinculadas e não pode ser excluído. "
                    "Use Ativar / Desativar para preservar o histórico."
                )
            conexao.execute("DELETE FROM empresas_entregas WHERE id = ?", (int(empresa_id),))

    def atualizar_regime_empresa(self, empresa_id: int, regime: str) -> None:
        regime = " ".join((regime or "").strip().upper().split()) or "A DEFINIR"
        with self._conectar() as conexao:
            conexao.execute(
                "UPDATE empresas_entregas SET regime = ? WHERE id = ?",
                (regime, int(empresa_id)),
            )

    def desativar_empresa(self, empresa_id: int) -> None:
        with self._conectar() as conexao:
            conexao.execute(
                "UPDATE empresas_entregas SET ativa = 0 WHERE id = ?", (int(empresa_id),)
            )

    def desativar_empresas_exceto(self, nomes: list[str] | tuple[str, ...]) -> None:
        nomes_limpos = [str(nome).strip() for nome in nomes if str(nome).strip()]
        with self._conectar() as conexao:
            if not nomes_limpos:
                conexao.execute("UPDATE empresas_entregas SET ativa = 0 WHERE manual = 0")
                return
            marcadores = ",".join("?" for _ in nomes_limpos)
            conexao.execute(
                f"UPDATE empresas_entregas SET ativa = 0 "
                f"WHERE manual = 0 AND nome COLLATE NOCASE NOT IN ({marcadores})",
                nomes_limpos,
            )

    # ------------------------------------------------------------------
    # Modelos mensais
    # ------------------------------------------------------------------
    def salvar_modelo(
        self,
        *,
        empresa_id: int,
        tipo_arquivo: str,
        dia_prazo: int,
        meses_apos_competencia: int = 1,
        destinatario: str = "",
        observacoes: str = "",
        modelo_id: int | None = None,
    ) -> int:
        tipo_arquivo = " ".join((tipo_arquivo or "").strip().split())
        if not tipo_arquivo:
            raise ValueError("Informe o arquivo/obrigação do modelo.")
        dia_prazo = int(dia_prazo)
        if not 0 <= dia_prazo <= 31:
            raise ValueError("O dia do prazo deve ficar entre 0 e 31. Use 0 quando não houver prazo fixo.")
        meses_apos_competencia = int(meses_apos_competencia)
        if not 0 <= meses_apos_competencia <= 12:
            raise ValueError("O prazo após a competência deve ficar entre 0 e 12 meses.")
        agora = self._agora()
        with self._conectar() as conexao:
            if modelo_id is None:
                cursor = conexao.execute(
                    """
                    INSERT INTO modelos_entrega(
                        empresa_id, tipo_arquivo, dia_prazo, meses_apos_competencia, destinatario,
                        observacoes, ativo, criado_em, atualizado_em
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(empresa_id, tipo_arquivo) DO UPDATE SET
                        dia_prazo = excluded.dia_prazo,
                        meses_apos_competencia = excluded.meses_apos_competencia,
                        destinatario = excluded.destinatario,
                        observacoes = excluded.observacoes,
                        ativo = 1,
                        atualizado_em = excluded.atualizado_em
                    """,
                    (
                        int(empresa_id), tipo_arquivo, dia_prazo, meses_apos_competencia,
                        (destinatario or "").strip(), (observacoes or "").strip(),
                        agora, agora,
                    ),
                )
                if cursor.lastrowid:
                    return int(cursor.lastrowid)
                linha = conexao.execute(
                    "SELECT id FROM modelos_entrega WHERE empresa_id = ? AND tipo_arquivo = ? COLLATE NOCASE",
                    (int(empresa_id), tipo_arquivo),
                ).fetchone()
                return int(linha["id"])
            conexao.execute(
                """
                UPDATE modelos_entrega
                   SET empresa_id = ?, tipo_arquivo = ?, dia_prazo = ?,
                       meses_apos_competencia = ?, destinatario = ?, observacoes = ?,
                       ativo = 1, atualizado_em = ?
                 WHERE id = ?
                """,
                (
                    int(empresa_id), tipo_arquivo, dia_prazo, meses_apos_competencia,
                    (destinatario or "").strip(), (observacoes or "").strip(),
                    agora, int(modelo_id),
                ),
            )
            return int(modelo_id)

    def listar_modelos(self, empresa_id: int | None = None) -> list[sqlite3.Row]:
        parametros: list[object] = []
        filtro = "WHERE m.ativo = 1"
        if empresa_id:
            filtro += " AND m.empresa_id = ?"
            parametros.append(int(empresa_id))
        with self._conectar() as conexao:
            return list(
                conexao.execute(
                    f"""
                    SELECT m.*, e.nome AS empresa
                      FROM modelos_entrega m
                      JOIN empresas_entregas e ON e.id = m.empresa_id
                      {filtro}
                     ORDER BY e.nome, m.tipo_arquivo
                    """,
                    parametros,
                ).fetchall()
            )

    def obter_modelo(self, modelo_id: int) -> sqlite3.Row | None:
        with self._conectar() as conexao:
            return conexao.execute(
                """
                SELECT m.*, e.nome AS empresa
                  FROM modelos_entrega m
                  JOIN empresas_entregas e ON e.id = m.empresa_id
                 WHERE m.id = ?
                """,
                (int(modelo_id),),
            ).fetchone()

    def obter_modelo_por_empresa_tipo(
        self, empresa_id: int, tipo_arquivo: str, *, incluir_inativo: bool = True
    ) -> sqlite3.Row | None:
        filtro_ativo = "" if incluir_inativo else "AND m.ativo = 1"
        with self._conectar() as conexao:
            return conexao.execute(
                f"""
                SELECT m.*, e.nome AS empresa, e.regime AS regime
                  FROM modelos_entrega m
                  JOIN empresas_entregas e ON e.id = m.empresa_id
                 WHERE m.empresa_id = ? AND m.tipo_arquivo = ? COLLATE NOCASE {filtro_ativo}
                """,
                (int(empresa_id), str(tipo_arquivo)),
            ).fetchone()

    def excluir_modelo(self, modelo_id: int) -> None:
        with self._conectar() as conexao:
            conexao.execute("UPDATE modelos_entrega SET ativo = 0 WHERE id = ?", (int(modelo_id),))

    # ------------------------------------------------------------------
    # Entregas
    # ------------------------------------------------------------------
    @staticmethod
    def prazo_modelo(
        competencia: str, dia_prazo: int, meses_apos_competencia: int = 1
    ) -> str:
        if int(dia_prazo) <= 0:
            return ""
        ano, mes = [int(parte) for parte in competencia.split("-", 1)]
        deslocamento = int(meses_apos_competencia)
        indice_mes = (ano * 12 + (mes - 1)) + deslocamento
        ano_prazo, mes_zero = divmod(indice_mes, 12)
        mes_prazo = mes_zero + 1
        ultimo = calendar.monthrange(ano_prazo, mes_prazo)[1]
        return date(ano_prazo, mes_prazo, min(int(dia_prazo), ultimo)).isoformat()

    def gerar_competencia(self, competencia: str, empresa_id: int | None = None) -> int:
        modelos = self.listar_modelos(empresa_id)
        agora = self._agora()
        inseridos = 0
        with self._conectar() as conexao:
            for modelo in modelos:
                prazo = self.prazo_modelo(
                    competencia,
                    int(modelo["dia_prazo"]),
                    int(modelo["meses_apos_competencia"]),
                )
                cursor = conexao.execute(
                    """
                    INSERT OR IGNORE INTO entregas_arquivos(
                        empresa_id, competencia, tipo_arquivo, prazo, data_entrega,
                        status, destinatario, caminho_arquivo, observacoes, modelo_id,
                        criado_em, atualizado_em
                    ) VALUES (?, ?, ?, ?, '', 'PENDENTE', ?, '', ?, ?, ?, ?)
                    """,
                    (
                        int(modelo["empresa_id"]), competencia, str(modelo["tipo_arquivo"]),
                        prazo, str(modelo["destinatario"] or ""),
                        str(modelo["observacoes"] or ""), int(modelo["id"]), agora, agora,
                    ),
                )
                if cursor.rowcount:
                    inseridos += 1
                else:
                    # Se a competência já havia sido gerada antes do Hotfix 17.6.1,
                    # recalcula somente itens ainda abertos e vinculados ao modelo.
                    # Entregues e “Não se aplica” são preservados integralmente.
                    conexao.execute(
                        """
                        UPDATE entregas_arquivos
                           SET prazo = ?, atualizado_em = ?
                         WHERE empresa_id = ? AND competencia = ?
                           AND tipo_arquivo = ? COLLATE NOCASE
                           AND modelo_id = ?
                           AND status IN ('PENDENTE', 'EM ANDAMENTO', 'ATRASADO')
                        """,
                        (
                            prazo, agora, int(modelo["empresa_id"]), competencia,
                            str(modelo["tipo_arquivo"]), int(modelo["id"]),
                        ),
                    )
        return inseridos

    def inserir_entrega(self, dados: dict[str, object]) -> int:
        agora = self._agora()
        with self._conectar() as conexao:
            cursor = conexao.execute(
                """
                INSERT INTO entregas_arquivos(
                    empresa_id, competencia, tipo_arquivo, prazo, data_entrega,
                    status, destinatario, caminho_arquivo, observacoes, modelo_id,
                    valor, protocolo, criado_em, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(dados["empresa_id"]), str(dados["competencia"]),
                    str(dados["tipo_arquivo"]), str(dados.get("prazo") or ""),
                    str(dados.get("data_entrega") or ""), str(dados.get("status") or "PENDENTE"),
                    str(dados.get("destinatario") or ""), str(dados.get("caminho_arquivo") or ""),
                    str(dados.get("observacoes") or ""), dados.get("modelo_id"),
                    float(dados.get("valor") or 0), str(dados.get("protocolo") or ""), agora, agora,
                ),
            )
            entrega_id = int(cursor.lastrowid)
            self._registrar_historico(conexao, entrega_id, "CRIADA", "Entrega cadastrada")
            return entrega_id

    def atualizar_entrega(self, entrega_id: int, dados: dict[str, object]) -> None:
        agora = self._agora()
        with self._conectar() as conexao:
            conexao.execute(
                """
                UPDATE entregas_arquivos
                   SET empresa_id = ?, competencia = ?, tipo_arquivo = ?, prazo = ?,
                       data_entrega = ?, status = ?, destinatario = ?, caminho_arquivo = ?,
                       observacoes = ?, valor = ?, protocolo = ?, atualizado_em = ?
                 WHERE id = ?
                """,
                (
                    int(dados["empresa_id"]), str(dados["competencia"]), str(dados["tipo_arquivo"]),
                    str(dados.get("prazo") or ""), str(dados.get("data_entrega") or ""),
                    str(dados.get("status") or "PENDENTE"), str(dados.get("destinatario") or ""),
                    str(dados.get("caminho_arquivo") or ""), str(dados.get("observacoes") or ""),
                    float(dados.get("valor") or 0), str(dados.get("protocolo") or ""),
                    agora, int(entrega_id),
                ),
            )
            self._registrar_historico(conexao, int(entrega_id), "EDITADA", "Dados atualizados")

    def obter_entrega(self, entrega_id: int) -> sqlite3.Row | None:
        with self._conectar() as conexao:
            return conexao.execute(
                """
                SELECT a.*, e.nome AS empresa, e.cnpj AS cnpj, e.regime AS regime
                  FROM entregas_arquivos a
                  JOIN empresas_entregas e ON e.id = a.empresa_id
                 WHERE a.id = ?
                """,
                (int(entrega_id),),
            ).fetchone()

    def listar_entregas(
        self,
        *,
        empresa_id: int | None = None,
        competencia: str = "",
        status: str = "",
        busca: str = "",
        prazo_inicio: str = "",
        prazo_fim: str = "",
    ) -> list[sqlite3.Row]:
        filtros = ["1 = 1"]
        parametros: list[object] = []
        if empresa_id:
            filtros.append("a.empresa_id = ?")
            parametros.append(int(empresa_id))
        if competencia:
            filtros.append("a.competencia = ?")
            parametros.append(competencia)
        if status:
            filtros.append("a.status = ?")
            parametros.append(status)
        if prazo_inicio:
            filtros.append("TRIM(a.prazo) <> '' AND a.prazo >= ?")
            parametros.append(prazo_inicio)
        if prazo_fim:
            filtros.append("TRIM(a.prazo) <> '' AND a.prazo <= ?")
            parametros.append(prazo_fim)
        if busca.strip():
            termo = f"%{busca.strip()}%"
            filtros.append(
                "(a.tipo_arquivo LIKE ? OR a.destinatario LIKE ? OR a.observacoes LIKE ? OR e.nome LIKE ?)"
            )
            parametros.extend((termo, termo, termo, termo))
        where = " AND ".join(filtros)
        with self._conectar() as conexao:
            return list(
                conexao.execute(
                    f"""
                    SELECT a.*, e.nome AS empresa, e.cnpj AS cnpj, e.regime AS regime
                      FROM entregas_arquivos a
                      JOIN empresas_entregas e ON e.id = a.empresa_id
                     WHERE {where}
                     ORDER BY CASE a.status WHEN 'ATRASADO' THEN 0 WHEN 'PENDENTE' THEN 1 ELSE 2 END,
                              CASE WHEN TRIM(a.prazo) = '' THEN 1 ELSE 0 END,
                              a.prazo, e.nome, a.competencia DESC, a.tipo_arquivo
                    """,
                    parametros,
                ).fetchall()
            )

    def atualizar_status_em_lote(self, hoje: str | None = None) -> None:
        hoje = hoje or date.today().isoformat()
        with self._conectar() as conexao:
            conexao.execute(
                """
                UPDATE entregas_arquivos
                   SET status = CASE
                       WHEN status = 'NÃO SE APLICA' THEN 'NÃO SE APLICA'
                       WHEN TRIM(data_entrega) <> '' THEN 'ENTREGUE'
                       WHEN TRIM(prazo) <> '' AND prazo < ? THEN 'ATRASADO'
                       WHEN status = 'EM ANDAMENTO' THEN 'EM ANDAMENTO'
                       ELSE 'PENDENTE'
                   END,
                       atualizado_em = ?
                """,
                (hoje, self._agora()),
            )

    def marcar_entregue(self, entrega_id: int, data_entrega: str) -> None:
        with self._conectar() as conexao:
            conexao.execute(
                "UPDATE entregas_arquivos SET data_entrega = ?, status = 'ENTREGUE', atualizado_em = ? WHERE id = ?",
                (data_entrega, self._agora(), int(entrega_id)),
            )
            self._registrar_historico(conexao, int(entrega_id), "ENTREGUE", data_entrega)

    def reabrir(self, entrega_id: int) -> None:
        with self._conectar() as conexao:
            conexao.execute(
                "UPDATE entregas_arquivos SET data_entrega = '', status = 'PENDENTE', atualizado_em = ? WHERE id = ?",
                (self._agora(), int(entrega_id)),
            )
            self._registrar_historico(conexao, int(entrega_id), "REABERTA", "Entrega reaberta")

    def marcar_nao_aplica(self, entrega_id: int) -> None:
        with self._conectar() as conexao:
            conexao.execute(
                "UPDATE entregas_arquivos SET data_entrega = '', status = 'NÃO SE APLICA', atualizado_em = ? WHERE id = ?",
                (self._agora(), int(entrega_id)),
            )
            self._registrar_historico(conexao, int(entrega_id), "NÃO SE APLICA", "Marcada como não aplicável")

    def excluir_entrega(self, entrega_id: int) -> None:
        with self._conectar() as conexao:
            self._registrar_historico(conexao, int(entrega_id), "EXCLUÍDA", "Entrega excluída")
            conexao.execute("DELETE FROM entregas_arquivos WHERE id = ?", (int(entrega_id),))

    def obter_entrega_por_chave(
        self, empresa_id: int, competencia: str, tipo_arquivo: str
    ) -> sqlite3.Row | None:
        with self._conectar() as conexao:
            return conexao.execute(
                """
                SELECT a.*, e.nome AS empresa, e.cnpj AS cnpj, e.regime AS regime
                  FROM entregas_arquivos a
                  JOIN empresas_entregas e ON e.id = a.empresa_id
                 WHERE a.empresa_id = ? AND a.competencia = ?
                   AND a.tipo_arquivo = ? COLLATE NOCASE
                """,
                (int(empresa_id), str(competencia), str(tipo_arquivo)),
            ).fetchone()

    def salvar_observacao_competencia(
        self, empresa_id: int, competencia: str, observacoes: str
    ) -> None:
        with self._conectar() as conexao:
            conexao.execute(
                """
                INSERT INTO observacoes_competencia(empresa_id, competencia, observacoes, atualizado_em)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(empresa_id, competencia) DO UPDATE SET
                    observacoes = excluded.observacoes, atualizado_em = excluded.atualizado_em
                """,
                (int(empresa_id), str(competencia), str(observacoes or '').strip(), self._agora()),
            )

    def obter_observacao_competencia(self, empresa_id: int, competencia: str) -> str:
        with self._conectar() as conexao:
            linha = conexao.execute(
                "SELECT observacoes FROM observacoes_competencia WHERE empresa_id = ? AND competencia = ?",
                (int(empresa_id), str(competencia)),
            ).fetchone()
        return str(linha["observacoes"] or "") if linha else ""

    def resumo(
        self, *, empresa_id: int | None = None, competencia: str = "",
        prazo_inicio: str = "", prazo_fim: str = ""
    ) -> dict[str, int]:
        filtros = ["1 = 1"]
        parametros: list[object] = []
        if empresa_id:
            filtros.append("empresa_id = ?")
            parametros.append(int(empresa_id))
        if competencia:
            filtros.append("competencia = ?")
            parametros.append(competencia)
        if prazo_inicio:
            filtros.append("TRIM(prazo) <> '' AND prazo >= ?")
            parametros.append(prazo_inicio)
        if prazo_fim:
            filtros.append("TRIM(prazo) <> '' AND prazo <= ?")
            parametros.append(prazo_fim)
        where = " AND ".join(filtros)
        with self._conectar() as conexao:
            linha = conexao.execute(
                f"""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status = 'ENTREGUE' THEN 1 ELSE 0 END) AS entregues,
                       SUM(CASE WHEN status IN ('PENDENTE', 'EM ANDAMENTO') THEN 1 ELSE 0 END) AS pendentes,
                       SUM(CASE WHEN status = 'ATRASADO' THEN 1 ELSE 0 END) AS atrasados,
                       SUM(CASE WHEN status = 'NÃO SE APLICA' THEN 1 ELSE 0 END) AS nao_aplica
                  FROM entregas_arquivos
                 WHERE {where}
                """,
                parametros,
            ).fetchone()
        return {
            "total": int(linha["total"] or 0),
            "entregues": int(linha["entregues"] or 0),
            "pendentes": int(linha["pendentes"] or 0),
            "atrasados": int(linha["atrasados"] or 0),
            "nao_aplica": int(linha["nao_aplica"] or 0),
        }

    @staticmethod
    def _registrar_historico(
        conexao: sqlite3.Connection, entrega_id: int | None, acao: str, detalhe: str = ""
    ) -> None:
        conexao.execute(
            "INSERT INTO historico_entregas(entrega_id, acao, detalhe, realizado_em) VALUES (?, ?, ?, ?)",
            (entrega_id, acao, detalhe, datetime.now().isoformat(timespec="seconds")),
        )
