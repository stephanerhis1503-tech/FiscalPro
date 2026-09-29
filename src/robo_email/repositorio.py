"""Registro local de mensagens, anexos, links e controle de duplicidades."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

from .config import BANCO_PATH


class RoboEmailRepositorio:
    def __init__(self, banco: Path = BANCO_PATH):
        self.banco = banco
        self.preparar_banco()

    @contextmanager
    def _conectar(self) -> Iterator[sqlite3.Connection]:
        """Abre uma transação curta e sempre libera o arquivo do SQLite.

        O gerenciador nativo de ``sqlite3.Connection`` confirma ou desfaz a
        transação, mas não fecha a conexão. No Windows isso pode manter o
        arquivo ``.db`` bloqueado após testes, cópias ou limpezas temporárias.
        """
        self.banco.parent.mkdir(parents=True, exist_ok=True)
        conexao = sqlite3.connect(self.banco, timeout=30)
        conexao.row_factory = sqlite3.Row
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
                CREATE TABLE IF NOT EXISTS mensagens_email (
                    mensagem_id TEXT PRIMARY KEY,
                    thread_id TEXT,
                    empresa TEXT,
                    remetente TEXT,
                    assunto TEXT,
                    data_email TEXT,
                    processado_em TEXT NOT NULL,
                    status TEXT NOT NULL,
                    detalhe TEXT
                );

                CREATE TABLE IF NOT EXISTS anexos_email (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mensagem_id TEXT NOT NULL,
                    empresa TEXT NOT NULL,
                    nome_original TEXT NOT NULL,
                    hash_sha256 TEXT NOT NULL,
                    caminho_salvo TEXT NOT NULL,
                    salvo_em TEXT NOT NULL,
                    UNIQUE(empresa, hash_sha256),
                    FOREIGN KEY(mensagem_id) REFERENCES mensagens_email(mensagem_id)
                );

                CREATE TABLE IF NOT EXISTS links_email (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mensagem_id TEXT NOT NULL,
                    empresa TEXT,
                    remetente TEXT,
                    assunto TEXT,
                    data_email TEXT,
                    url TEXT NOT NULL,
                    dominio TEXT NOT NULL,
                    texto_link TEXT,
                    status TEXT NOT NULL,
                    detalhe TEXT,
                    url_final TEXT,
                    caminho_salvo TEXT,
                    registrado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL,
                    UNIQUE(mensagem_id, url),
                    FOREIGN KEY(mensagem_id) REFERENCES mensagens_email(mensagem_id)
                );

                CREATE INDEX IF NOT EXISTS idx_anexos_empresa_hash
                    ON anexos_email(empresa, hash_sha256);
                CREATE INDEX IF NOT EXISTS idx_links_status
                    ON links_email(status);
                CREATE INDEX IF NOT EXISTS idx_links_dominio
                    ON links_email(dominio);

                CREATE TABLE IF NOT EXISTS eventos_robo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT NOT NULL,
                    empresa TEXT,
                    mensagem_id TEXT,
                    data_referencia TEXT NOT NULL,
                    detalhe TEXT,
                    criado_em TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_eventos_periodo
                    ON eventos_robo(data_referencia, empresa, tipo);
                """
            )
            self._garantir_coluna(
                conexao,
                tabela="mensagens_email",
                coluna="links_verificados",
                definicao="INTEGER NOT NULL DEFAULT 0",
            )
            self._garantir_coluna(
                conexao,
                tabela="anexos_email",
                coluna="categoria",
                definicao="TEXT NOT NULL DEFAULT 'Outros'",
            )
            self._garantir_coluna(
                conexao,
                tabela="anexos_email",
                coluna="competencia",
                definicao="TEXT NOT NULL DEFAULT ''",
            )
            self._garantir_coluna(
                conexao,
                tabela="anexos_email",
                coluna="nome_padronizado",
                definicao="TEXT NOT NULL DEFAULT ''",
            )
            self._garantir_coluna(
                conexao,
                tabela="anexos_email",
                coluna="origem_documento",
                definicao="TEXT NOT NULL DEFAULT 'GMAIL'",
            )
            self._garantir_coluna(
                conexao,
                tabela="anexos_email",
                coluna="status_organizacao",
                definicao="TEXT NOT NULL DEFAULT 'ORGANIZADO'",
            )
            self._garantir_coluna(
                conexao,
                tabela="anexos_email",
                coluna="detalhe_organizacao",
                definicao="TEXT NOT NULL DEFAULT ''",
            )
            for coluna, definicao in (
                ("documento_tipo", "TEXT NOT NULL DEFAULT ''"),
                ("documento_numero", "TEXT NOT NULL DEFAULT ''"),
                ("cnpj_documento", "TEXT NOT NULL DEFAULT ''"),
                ("competencia_documento", "TEXT NOT NULL DEFAULT ''"),
                ("valor_documento", "REAL"),
                ("vencimento_documento", "TEXT NOT NULL DEFAULT ''"),
                ("tributo_documento", "TEXT NOT NULL DEFAULT ''"),
                ("status_conferencia", "TEXT NOT NULL DEFAULT 'NÃO ANALISADO'"),
                ("alertas_conferencia", "TEXT NOT NULL DEFAULT ''"),
                ("fonte_leitura", "TEXT NOT NULL DEFAULT ''"),
                ("resumo_leitura", "TEXT NOT NULL DEFAULT ''"),
            ):
                self._garantir_coluna(
                    conexao,
                    tabela="anexos_email",
                    coluna=coluna,
                    definicao=definicao,
                )
            conexao.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_anexos_hash_global
                    ON anexos_email(hash_sha256)
                """
            )
            conexao.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_anexos_competencia_empresa
                    ON anexos_email(competencia, empresa)
                """
            )
            conexao.execute(
                """
                UPDATE links_email
                   SET status = 'IGNORADO_RASTREADOR',
                       detalhe = 'Rastreador de abertura ignorado pelo FiscalPro.',
                       atualizado_em = ?
                 WHERE lower(dominio) IN (
                    'mailtrack.email', 'mailtrack.io', 'mailtrack.com',
                    'www.mailtrack.email', 'www.mailtrack.io', 'www.mailtrack.com'
                 )
                   AND status NOT IN ('BAIXADO', 'DUPLICADO')
                """,
                (datetime.now().isoformat(timespec="seconds"),),
            )

    @staticmethod
    def _garantir_coluna(
        conexao: sqlite3.Connection,
        *,
        tabela: str,
        coluna: str,
        definicao: str,
    ) -> None:
        colunas = {
            linha["name"]
            for linha in conexao.execute(f"PRAGMA table_info({tabela})").fetchall()
        }
        if coluna not in colunas:
            conexao.execute(
                f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}"
            )

    def mensagem_concluida(self, mensagem_id: str) -> bool:
        with self._conectar() as conexao:
            linha = conexao.execute(
                """
                SELECT status, links_verificados
                  FROM mensagens_email
                 WHERE mensagem_id = ?
                """,
                (mensagem_id,),
            ).fetchone()
        return bool(
            linha
            and linha["status"] == "CONCLUIDO"
            and int(linha["links_verificados"] or 0) == 1
        )

    def anexo_duplicado(self, empresa: str, hash_sha256: str) -> str | None:
        with self._conectar() as conexao:
            linha = conexao.execute(
                """
                SELECT caminho_salvo
                  FROM anexos_email
                 WHERE empresa = ? AND hash_sha256 = ?
                """,
                (empresa, hash_sha256),
            ).fetchone()
        return str(linha["caminho_salvo"]) if linha else None

    def localizar_anexo_duplicado(self, hash_sha256: str) -> sqlite3.Row | None:
        """Procura o mesmo conteúdo em qualquer empresa antes de gravar no disco."""

        with self._conectar() as conexao:
            return conexao.execute(
                """
                SELECT id, empresa, nome_original, nome_padronizado,
                       caminho_salvo, competencia, categoria
                  FROM anexos_email
                 WHERE hash_sha256 = ?
                 ORDER BY id
                 LIMIT 1
                """,
                (hash_sha256,),
            ).fetchone()

    def registrar_mensagem(
        self,
        *,
        mensagem_id: str,
        thread_id: str,
        empresa: str | None,
        remetente: str,
        assunto: str,
        data_email: datetime,
        status: str,
        detalhe: str = "",
        links_verificados: bool = False,
    ) -> None:
        with self._conectar() as conexao:
            conexao.execute(
                """
                INSERT INTO mensagens_email (
                    mensagem_id, thread_id, empresa, remetente, assunto,
                    data_email, processado_em, status, detalhe, links_verificados
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mensagem_id) DO UPDATE SET
                    empresa = excluded.empresa,
                    remetente = excluded.remetente,
                    assunto = excluded.assunto,
                    data_email = excluded.data_email,
                    processado_em = excluded.processado_em,
                    status = excluded.status,
                    detalhe = excluded.detalhe,
                    links_verificados = excluded.links_verificados
                """,
                (
                    mensagem_id,
                    thread_id,
                    empresa,
                    remetente,
                    assunto,
                    data_email.isoformat(),
                    datetime.now().isoformat(timespec="seconds"),
                    status,
                    detalhe,
                    1 if links_verificados else 0,
                ),
            )

    def registrar_anexo(
        self,
        *,
        mensagem_id: str,
        empresa: str,
        nome_original: str,
        hash_sha256: str,
        caminho_salvo: str,
        categoria: str = "Outros",
        competencia: str = "",
        nome_padronizado: str = "",
        origem_documento: str = "GMAIL",
        status_organizacao: str = "ORGANIZADO",
        detalhe_organizacao: str = "",
    ) -> None:
        with self._conectar() as conexao:
            conexao.execute(
                """
                INSERT OR IGNORE INTO anexos_email (
                    mensagem_id, empresa, nome_original, hash_sha256,
                    caminho_salvo, salvo_em, categoria, competencia,
                    nome_padronizado, origem_documento, status_organizacao,
                    detalhe_organizacao
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mensagem_id,
                    empresa,
                    nome_original,
                    hash_sha256,
                    caminho_salvo,
                    datetime.now().isoformat(timespec="seconds"),
                    categoria,
                    competencia,
                    nome_padronizado,
                    origem_documento,
                    status_organizacao,
                    detalhe_organizacao,
                ),
            )

    def atualizar_conferencia_por_hash(
        self,
        *,
        hash_sha256: str,
        documento_tipo: str = "",
        documento_numero: str = "",
        cnpj_documento: str = "",
        competencia_documento: str = "",
        valor_documento: float | None = None,
        vencimento_documento: str = "",
        tributo_documento: str = "",
        status_conferencia: str = "REVISAR",
        alertas_conferencia: str = "",
        fonte_leitura: str = "",
        resumo_leitura: str = "",
        status_organizacao: str | None = None,
        detalhe_organizacao: str | None = None,
    ) -> None:
        campos = [
            "documento_tipo = ?",
            "documento_numero = ?",
            "cnpj_documento = ?",
            "competencia_documento = ?",
            "valor_documento = ?",
            "vencimento_documento = ?",
            "tributo_documento = ?",
            "status_conferencia = ?",
            "alertas_conferencia = ?",
            "fonte_leitura = ?",
            "resumo_leitura = ?",
        ]
        parametros: list[object] = [
            documento_tipo,
            documento_numero,
            cnpj_documento,
            competencia_documento,
            valor_documento,
            vencimento_documento,
            tributo_documento,
            status_conferencia,
            alertas_conferencia,
            fonte_leitura,
            resumo_leitura,
        ]
        if status_organizacao is not None:
            campos.append("status_organizacao = ?")
            parametros.append(status_organizacao)
        if detalhe_organizacao is not None:
            campos.append("detalhe_organizacao = ?")
            parametros.append(detalhe_organizacao)
        parametros.append(hash_sha256)
        with self._conectar() as conexao:
            conexao.execute(
                f"UPDATE anexos_email SET {', '.join(campos)} WHERE hash_sha256 = ?",
                parametros,
            )

    def atualizar_conferencia_por_id(
        self,
        documento_id: int,
        **dados: object,
    ) -> None:
        permitidos = {
            "documento_tipo", "documento_numero", "cnpj_documento",
            "competencia_documento", "valor_documento", "vencimento_documento",
            "tributo_documento", "status_conferencia", "alertas_conferencia",
            "fonte_leitura", "resumo_leitura", "status_organizacao",
            "detalhe_organizacao",
        }
        itens = [(chave, valor) for chave, valor in dados.items() if chave in permitidos]
        if not itens:
            return
        with self._conectar() as conexao:
            conexao.execute(
                f"UPDATE anexos_email SET {', '.join(f'{chave} = ?' for chave, _ in itens)} WHERE id = ?",
                [valor for _, valor in itens] + [int(documento_id)],
            )

    def obter_documento(self, documento_id: int) -> sqlite3.Row | None:
        with self._conectar() as conexao:
            return conexao.execute(
                """
                SELECT a.*, m.assunto, m.data_email
                  FROM anexos_email a
                  LEFT JOIN mensagens_email m ON m.mensagem_id = a.mensagem_id
                 WHERE a.id = ?
                """,
                (int(documento_id),),
            ).fetchone()

    def listar_documentos(
        self,
        *,
        empresa: str | None = None,
        competencia: str | None = None,
        limite: int = 2000,
    ) -> list[sqlite3.Row]:
        """Lista o histórico de documentos e seus caminhos de arquivamento."""

        filtros: list[str] = []
        parametros: list[object] = []
        if empresa is not None:
            filtros.append("empresa = ?")
            parametros.append(empresa)
        if competencia:
            filtros.append("competencia = ?")
            parametros.append(competencia)
        where = "WHERE " + " AND ".join(filtros) if filtros else ""
        parametros.append(int(limite))

        with self._conectar() as conexao:
            return conexao.execute(
                f"""
                SELECT a.*, m.remetente, m.assunto, m.data_email
                  FROM anexos_email a
                  LEFT JOIN mensagens_email m ON m.mensagem_id = a.mensagem_id
                  {where.replace("empresa", "a.empresa").replace("competencia", "a.competencia")}
                 ORDER BY a.salvo_em DESC, a.id DESC
                 LIMIT ?
                """,
                parametros,
            ).fetchall()

    def registrar_link(
        self,
        *,
        mensagem_id: str,
        empresa: str | None,
        remetente: str,
        assunto: str,
        data_email: datetime,
        url: str,
        dominio: str,
        texto_link: str,
        status: str,
        detalhe: str = "",
        url_final: str = "",
        caminho_salvo: str = "",
    ) -> int:
        agora = datetime.now().isoformat(timespec="seconds")
        with self._conectar() as conexao:
            conexao.execute(
                """
                INSERT INTO links_email (
                    mensagem_id, empresa, remetente, assunto, data_email,
                    url, dominio, texto_link, status, detalhe, url_final,
                    caminho_salvo, registrado_em, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mensagem_id, url) DO UPDATE SET
                    empresa = excluded.empresa,
                    remetente = excluded.remetente,
                    assunto = excluded.assunto,
                    data_email = excluded.data_email,
                    dominio = excluded.dominio,
                    texto_link = excluded.texto_link,
                    status = CASE
                        WHEN links_email.status IN ('BAIXADO', 'DUPLICADO')
                            THEN links_email.status
                        ELSE excluded.status
                    END,
                    detalhe = CASE
                        WHEN links_email.status IN ('BAIXADO', 'DUPLICADO')
                            THEN links_email.detalhe
                        ELSE excluded.detalhe
                    END,
                    url_final = CASE
                        WHEN links_email.status IN ('BAIXADO', 'DUPLICADO')
                            THEN links_email.url_final
                        ELSE excluded.url_final
                    END,
                    caminho_salvo = CASE
                        WHEN links_email.status IN ('BAIXADO', 'DUPLICADO')
                            THEN links_email.caminho_salvo
                        ELSE excluded.caminho_salvo
                    END,
                    atualizado_em = excluded.atualizado_em
                """,
                (
                    mensagem_id,
                    empresa,
                    remetente,
                    assunto,
                    data_email.isoformat(),
                    url,
                    dominio,
                    texto_link,
                    status,
                    detalhe,
                    url_final,
                    caminho_salvo,
                    agora,
                    agora,
                ),
            )
            linha = conexao.execute(
                "SELECT id FROM links_email WHERE mensagem_id = ? AND url = ?",
                (mensagem_id, url),
            ).fetchone()
        return int(linha["id"])

    def atualizar_link(
        self,
        link_id: int,
        *,
        status: str,
        detalhe: str = "",
        url_final: str = "",
        caminho_salvo: str = "",
    ) -> None:
        with self._conectar() as conexao:
            conexao.execute(
                """
                UPDATE links_email
                   SET status = ?, detalhe = ?, url_final = ?, caminho_salvo = ?,
                       atualizado_em = ?
                 WHERE id = ?
                """,
                (
                    status,
                    detalhe,
                    url_final,
                    caminho_salvo,
                    datetime.now().isoformat(timespec="seconds"),
                    link_id,
                ),
            )

    def obter_link(self, link_id: int) -> sqlite3.Row | None:
        with self._conectar() as conexao:
            return conexao.execute(
                "SELECT * FROM links_email WHERE id = ?",
                (link_id,),
            ).fetchone()

    def listar_links(
        self,
        *,
        statuses: Iterable[str] | None = None,
        limite: int = 500,
    ) -> list[sqlite3.Row]:
        parametros: list[object] = []
        where = ""
        if statuses:
            lista = list(statuses)
            marcadores = ",".join("?" for _ in lista)
            where = f"WHERE status IN ({marcadores})"
            parametros.extend(lista)
        parametros.append(int(limite))

        with self._conectar() as conexao:
            return conexao.execute(
                f"""
                SELECT *
                  FROM links_email
                  {where}
                 ORDER BY data_email DESC, id DESC
                 LIMIT ?
                """,
                parametros,
            ).fetchall()

    def registrar_evento(
        self,
        *,
        tipo: str,
        empresa: str | None,
        data_referencia: datetime,
        mensagem_id: str = "",
        detalhe: str = "",
    ) -> None:
        """Registra ocorrências que não viram arquivo, como duplicidade e erro."""
        with self._conectar() as conexao:
            conexao.execute(
                """
                INSERT INTO eventos_robo (
                    tipo, empresa, mensagem_id, data_referencia, detalhe, criado_em
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (tipo or "EVENTO").strip().upper(),
                    empresa,
                    mensagem_id,
                    data_referencia.isoformat(),
                    detalhe,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def resumo_mensal(self, ano: int, mes: int) -> dict[str, dict[str, object]]:
        """Agrupa mensagens, links e eventos por empresa no mês de referência."""
        periodo = f"{int(ano):04d}-{int(mes):02d}"
        resumo: dict[str, dict[str, object]] = {}

        def item(empresa: str | None) -> dict[str, object]:
            chave = empresa or "Não Identificada"
            return resumo.setdefault(
                chave,
                {
                    "emails": 0,
                    "links_pendentes": 0,
                    "duplicados": 0,
                    "erros": 0,
                    "conferidos": 0,
                    "revisar_documentos": 0,
                    "vencimentos_passados": 0,
                    "ultimo_processamento": "",
                },
            )

        with self._conectar() as conexao:
            for linha in conexao.execute(
                """
                SELECT empresa,
                       COUNT(*) AS emails,
                       SUM(CASE WHEN status = 'ERRO' THEN 1 ELSE 0 END) AS erros,
                       MAX(processado_em) AS ultimo_processamento
                  FROM mensagens_email
                 WHERE substr(data_email, 1, 7) = ?
                 GROUP BY empresa
                """,
                (periodo,),
            ).fetchall():
                dados = item(linha["empresa"])
                dados["emails"] = int(linha["emails"] or 0)
                dados["erros"] = int(linha["erros"] or 0)
                dados["ultimo_processamento"] = linha["ultimo_processamento"] or ""

            for linha in conexao.execute(
                """
                SELECT empresa,
                       SUM(CASE WHEN status IN (
                                    'PENDENTE_DOMINIO', 'AUTORIZADO_AGUARDANDO',
                                    'PENDENTE_ACESSO'
                                ) THEN 1 ELSE 0 END) AS pendentes,
                       SUM(CASE WHEN status = 'DUPLICADO' THEN 1 ELSE 0 END) AS duplicados,
                       SUM(CASE WHEN status IN ('ERRO', 'BLOQUEADO') THEN 1 ELSE 0 END) AS erros
                  FROM links_email
                 WHERE substr(data_email, 1, 7) = ?
                 GROUP BY empresa
                """,
                (periodo,),
            ).fetchall():
                dados = item(linha["empresa"])
                dados["links_pendentes"] = int(linha["pendentes"] or 0)
                dados["duplicados"] = int(dados["duplicados"]) + int(
                    linha["duplicados"] or 0
                )
                dados["erros"] = int(dados["erros"]) + int(linha["erros"] or 0)

            for linha in conexao.execute(
                """
                SELECT empresa, tipo, COUNT(*) AS total
                  FROM eventos_robo
                 WHERE substr(data_referencia, 1, 7) = ?
                 GROUP BY empresa, tipo
                """,
                (periodo,),
            ).fetchall():
                dados = item(linha["empresa"])
                tipo = str(linha["tipo"] or "").upper()
                total = int(linha["total"] or 0)
                if tipo == "DUPLICADO":
                    dados["duplicados"] = int(dados["duplicados"]) + total
                elif tipo == "ERRO":
                    dados["erros"] = int(dados["erros"]) + total

            for linha in conexao.execute(
                """
                SELECT empresa,
                       SUM(CASE WHEN status_conferencia = 'CONFERIDO' THEN 1 ELSE 0 END) AS conferidos,
                       SUM(CASE WHEN status_conferencia = 'REVISAR' THEN 1 ELSE 0 END) AS revisar,
                       SUM(CASE WHEN status_conferencia = 'VENCIMENTO PASSADO' THEN 1 ELSE 0 END) AS vencidos
                  FROM anexos_email
                 WHERE COALESCE(NULLIF(competencia_documento, ''), competencia) = ?
                 GROUP BY empresa
                """,
                (periodo,),
            ).fetchall():
                dados = item(linha["empresa"])
                dados["conferidos"] = int(linha["conferidos"] or 0)
                dados["revisar_documentos"] = int(linha["revisar"] or 0)
                dados["vencimentos_passados"] = int(linha["vencidos"] or 0)

        return resumo

    def resumo(self) -> dict[str, int]:
        with self._conectar() as conexao:
            mensagens = conexao.execute(
                "SELECT COUNT(*) AS total FROM mensagens_email WHERE status = 'CONCLUIDO'"
            ).fetchone()["total"]
            anexos = conexao.execute(
                "SELECT COUNT(*) AS total FROM anexos_email"
            ).fetchone()["total"]
            links_pendentes = conexao.execute(
                """
                SELECT COUNT(*) AS total
                  FROM links_email
                 WHERE status NOT IN ('BAIXADO', 'DUPLICADO')
                """
            ).fetchone()["total"]
            links_baixados = conexao.execute(
                "SELECT COUNT(*) AS total FROM links_email WHERE status = 'BAIXADO'"
            ).fetchone()["total"]
        return {
            "mensagens": int(mensagens),
            "anexos": int(anexos),
            "links_pendentes": int(links_pendentes),
            "links_baixados": int(links_baixados),
        }
