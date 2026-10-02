"""Persistência isolada da Distribuição DF-e e Manifestação do Destinatário."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from src.core.caminhos import PASTA_DADOS_INTERNOS


PASTA_NFE = PASTA_DADOS_INTERNOS / "nfe"
BANCO_NFE = PASTA_NFE / "manifestacao_nfe.db"


class RepositorioManifestacaoNFe:
    def __init__(self, caminho: str | Path = BANCO_NFE):
        self.caminho = Path(caminho)
        self.preparar()

    def conectar(self):
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.caminho)
        conn.row_factory = sqlite3.Row
        return conn

    def preparar(self):
        with self.conectar() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS configuracao_nfe (
                    cnpj TEXT NOT NULL,
                    ambiente TEXT NOT NULL,
                    uf_autor TEXT NOT NULL DEFAULT '',
                    ultimo_nsu INTEGER NOT NULL DEFAULT 0,
                    max_nsu INTEGER NOT NULL DEFAULT 0,
                    bloqueado_ate TEXT NOT NULL DEFAULT '',
                    ultima_consulta_em TEXT NOT NULL DEFAULT '',
                    ultimo_cstat TEXT NOT NULL DEFAULT '',
                    ultimo_motivo TEXT NOT NULL DEFAULT '',
                    atualizado_em TEXT NOT NULL,
                    PRIMARY KEY(cnpj, ambiente)
                );

                CREATE TABLE IF NOT EXISTS consultas_dfe_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cnpj TEXT NOT NULL,
                    ambiente TEXT NOT NULL,
                    uf_autor TEXT NOT NULL DEFAULT '',
                    consultado_em TEXT NOT NULL,
                    nsu_enviado INTEGER NOT NULL DEFAULT 0,
                    cstat TEXT NOT NULL DEFAULT '',
                    motivo TEXT NOT NULL DEFAULT '',
                    ultimo_nsu_retornado INTEGER,
                    max_nsu_retornado INTEGER,
                    quantidade_documentos INTEGER NOT NULL DEFAULT 0,
                    detalhes_documentos TEXT NOT NULL DEFAULT '',
                    observacao TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_consultas_dfe_cnpj
                    ON consultas_dfe_log(cnpj, ambiente, id DESC);

                CREATE TABLE IF NOT EXISTS consultas_chave_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cnpj TEXT NOT NULL,
                    ambiente TEXT NOT NULL,
                    chave TEXT NOT NULL,
                    consultado_em TEXT NOT NULL,
                    cstat TEXT NOT NULL DEFAULT '',
                    motivo TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_consultas_chave_cnpj
                    ON consultas_chave_log(cnpj, ambiente, consultado_em DESC);

                CREATE TABLE IF NOT EXISTS documentos_nfe (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cnpj_empresa TEXT NOT NULL,
                    ambiente TEXT NOT NULL,
                    nsu INTEGER NOT NULL,
                    schema_doc TEXT NOT NULL DEFAULT '',
                    chave TEXT NOT NULL DEFAULT '',
                    tipo_doc TEXT NOT NULL DEFAULT '',
                    emitente_doc TEXT NOT NULL DEFAULT '',
                    emitente_nome TEXT NOT NULL DEFAULT '',
                    emitente_ie TEXT NOT NULL DEFAULT '',
                    data_emissao TEXT NOT NULL DEFAULT '',
                    data_autorizacao TEXT NOT NULL DEFAULT '',
                    valor_nf REAL NOT NULL DEFAULT 0,
                    situacao_nfe TEXT NOT NULL DEFAULT '',
                    tp_nf TEXT NOT NULL DEFAULT '',
                    prazo_final TEXT NOT NULL DEFAULT '',
                    xml TEXT NOT NULL DEFAULT '',
                    tem_xml_completo INTEGER NOT NULL DEFAULT 0,
                    recebido_em TEXT NOT NULL,
                    UNIQUE(cnpj_empresa, ambiente, nsu)
                );
                CREATE INDEX IF NOT EXISTS idx_nfe_chave ON documentos_nfe(cnpj_empresa, ambiente, chave);
                CREATE INDEX IF NOT EXISTS idx_nfe_emissao ON documentos_nfe(cnpj_empresa, ambiente, data_emissao);

                CREATE TABLE IF NOT EXISTS manifestacoes_nfe (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cnpj_empresa TEXT NOT NULL,
                    ambiente TEXT NOT NULL,
                    chave TEXT NOT NULL,
                    tp_evento TEXT NOT NULL,
                    descricao TEXT NOT NULL DEFAULT '',
                    justificativa TEXT NOT NULL DEFAULT '',
                    cstat TEXT NOT NULL DEFAULT '',
                    motivo TEXT NOT NULL DEFAULT '',
                    protocolo TEXT NOT NULL DEFAULT '',
                    data_evento TEXT NOT NULL DEFAULT '',
                    xml_envio TEXT NOT NULL DEFAULT '',
                    xml_retorno TEXT NOT NULL DEFAULT '',
                    registrado INTEGER NOT NULL DEFAULT 0,
                    criado_em TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_manifestacao_chave ON manifestacoes_nfe(cnpj_empresa, ambiente, chave, id);
                """
            )
            # Migração segura para bancos criados antes da proteção contra cStat 656.
            colunas = {str(r["name"]) for r in conn.execute("PRAGMA table_info(configuracao_nfe)").fetchall()}
            extras = {
                "bloqueado_ate": "TEXT NOT NULL DEFAULT ''",
                "ultima_consulta_em": "TEXT NOT NULL DEFAULT ''",
                "ultimo_cstat": "TEXT NOT NULL DEFAULT ''",
                "ultimo_motivo": "TEXT NOT NULL DEFAULT ''",
            }
            for nome, definicao in extras.items():
                if nome not in colunas:
                    conn.execute(f"ALTER TABLE configuracao_nfe ADD COLUMN {nome} {definicao}")

            # Migração segura para o rastro detalhado de documentos da Distribuição DF-e.
            colunas_log = {str(r["name"]) for r in conn.execute("PRAGMA table_info(consultas_dfe_log)").fetchall()}
            if "detalhes_documentos" not in colunas_log:
                conn.execute(
                    "ALTER TABLE consultas_dfe_log ADD COLUMN detalhes_documentos TEXT NOT NULL DEFAULT ''"
                )

    def obter_config(self, cnpj: str, ambiente: str) -> dict:
        cnpj = "".join(ch for ch in str(cnpj or "") if ch.isdigit())
        ambiente = str(ambiente or "PRODUCAO").upper()
        with self.conectar() as conn:
            r = conn.execute(
                "SELECT * FROM configuracao_nfe WHERE cnpj=? AND ambiente=?", (cnpj, ambiente)
            ).fetchone()
            return dict(r) if r else {
                "cnpj": cnpj, "ambiente": ambiente, "uf_autor": "", "ultimo_nsu": 0, "max_nsu": 0,
                "bloqueado_ate": "", "ultima_consulta_em": "", "ultimo_cstat": "", "ultimo_motivo": "",
            }

    def salvar_config(self, cnpj: str, ambiente: str, *, uf_autor: str | None = None,
                      ultimo_nsu: int | None = None, max_nsu: int | None = None,
                      bloqueado_ate: str | None = None, ultima_consulta_em: str | None = None,
                      ultimo_cstat: str | None = None, ultimo_motivo: str | None = None):
        atual = self.obter_config(cnpj, ambiente)
        uf = (uf_autor if uf_autor is not None else atual.get("uf_autor") or "").upper()
        ult = int(ultimo_nsu if ultimo_nsu is not None else atual.get("ultimo_nsu") or 0)
        maximo = int(max_nsu if max_nsu is not None else atual.get("max_nsu") or 0)
        bloqueio = str(bloqueado_ate if bloqueado_ate is not None else atual.get("bloqueado_ate") or "")
        ultima = str(ultima_consulta_em if ultima_consulta_em is not None else atual.get("ultima_consulta_em") or "")
        cstat = str(ultimo_cstat if ultimo_cstat is not None else atual.get("ultimo_cstat") or "")
        motivo = str(ultimo_motivo if ultimo_motivo is not None else atual.get("ultimo_motivo") or "")
        agora = datetime.now().isoformat(timespec="seconds")
        with self.conectar() as conn:
            conn.execute(
                """
                INSERT INTO configuracao_nfe(
                    cnpj,ambiente,uf_autor,ultimo_nsu,max_nsu,bloqueado_ate,ultima_consulta_em,ultimo_cstat,ultimo_motivo,atualizado_em
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(cnpj,ambiente) DO UPDATE SET
                    uf_autor=excluded.uf_autor,
                    ultimo_nsu=excluded.ultimo_nsu,
                    max_nsu=excluded.max_nsu,
                    bloqueado_ate=excluded.bloqueado_ate,
                    ultima_consulta_em=excluded.ultima_consulta_em,
                    ultimo_cstat=excluded.ultimo_cstat,
                    ultimo_motivo=excluded.ultimo_motivo,
                    atualizado_em=excluded.atualizado_em
                """,
                (
                    "".join(ch for ch in str(cnpj or "") if ch.isdigit()),
                    str(ambiente or "PRODUCAO").upper(), uf, ult, maximo, bloqueio, ultima, cstat, motivo, agora,
                ),
            )

    def registrar_consulta_dfe(
        self,
        cnpj: str,
        ambiente: str,
        uf_autor: str,
        *,
        nsu_enviado: int,
        cstat: str,
        motivo: str = "",
        ultimo_nsu_retornado: int | None = None,
        max_nsu_retornado: int | None = None,
        quantidade_documentos: int = 0,
        detalhes_documentos: str = "",
        observacao: str = "",
        consultado_em: str | None = None,
    ) -> None:
        """Guarda um rastro local de cada chamada feita pelo FiscalPro à Distribuição DF-e."""
        cnpj = "".join(ch for ch in str(cnpj or "") if ch.isdigit())
        ambiente = str(ambiente or "PRODUCAO").upper()
        quando = str(consultado_em or datetime.now().isoformat(timespec="seconds"))
        with self.conectar() as conn:
            conn.execute(
                """
                INSERT INTO consultas_dfe_log(
                    cnpj,ambiente,uf_autor,consultado_em,nsu_enviado,cstat,motivo,
                    ultimo_nsu_retornado,max_nsu_retornado,quantidade_documentos,detalhes_documentos,observacao
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    cnpj, ambiente, str(uf_autor or "").upper(), quando, int(nsu_enviado or 0),
                    str(cstat or ""), str(motivo or ""),
                    None if ultimo_nsu_retornado is None else int(ultimo_nsu_retornado),
                    None if max_nsu_retornado is None else int(max_nsu_retornado),
                    int(quantidade_documentos or 0), str(detalhes_documentos or ""), str(observacao or ""),
                ),
            )

    def registrar_consulta_chave(
        self, cnpj: str, ambiente: str, chave: str, cstat: str, motivo: str = "",
        consultado_em: str | None = None,
    ) -> None:
        cnpj = "".join(ch for ch in str(cnpj or "") if ch.isdigit())
        ambiente = str(ambiente or "PRODUCAO").upper()
        chave = "".join(ch for ch in str(chave or "") if ch.isdigit())
        quando = str(consultado_em or datetime.now().isoformat(timespec="seconds"))
        with self.conectar() as conn:
            conn.execute(
                """
                INSERT INTO consultas_chave_log(cnpj,ambiente,chave,consultado_em,cstat,motivo)
                VALUES(?,?,?,?,?,?)
                """,
                (cnpj, ambiente, chave, quando, str(cstat or ""), str(motivo or "")),
            )

    def contar_consultas_chave_ultima_hora(self, cnpj: str, ambiente: str) -> int:
        cnpj = "".join(ch for ch in str(cnpj or "") if ch.isdigit())
        ambiente = str(ambiente or "PRODUCAO").upper()
        corte = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
        with self.conectar() as conn:
            linha = conn.execute(
                """
                SELECT COUNT(*) AS qtd
                FROM consultas_chave_log
                WHERE cnpj=? AND ambiente=? AND consultado_em>=?
                """,
                (cnpj, ambiente, corte),
            ).fetchone()
        return int(linha["qtd"] or 0) if linha else 0

    def listar_consultas_dfe(self, cnpj: str, ambiente: str, limite: int = 8) -> list[dict]:
        cnpj = "".join(ch for ch in str(cnpj or "") if ch.isdigit())
        ambiente = str(ambiente or "PRODUCAO").upper()
        limite = max(1, min(int(limite or 8), 50))
        with self.conectar() as conn:
            linhas = conn.execute(
                """
                SELECT * FROM consultas_dfe_log
                WHERE cnpj=? AND ambiente=?
                ORDER BY id DESC LIMIT ?
                """,
                (cnpj, ambiente, limite),
            ).fetchall()
        return [dict(linha) for linha in linhas]

    def obter_ultima_consulta_dfe(self, cnpj: str, ambiente: str) -> dict:
        historico = self.listar_consultas_dfe(cnpj, ambiente, 1)
        return historico[0] if historico else {}

    def listar_documentos_intervalo_nsu(
        self, cnpj: str, ambiente: str, nsu_inicio_exclusivo: int, nsu_fim_inclusivo: int
    ) -> list[dict]:
        """Retorna documentos já armazenados entre dois NSUs, sem consultar a SEFAZ."""
        cnpj = "".join(ch for ch in str(cnpj or "") if ch.isdigit())
        ambiente = str(ambiente or "PRODUCAO").upper()
        inicio = int(nsu_inicio_exclusivo or 0)
        fim = int(nsu_fim_inclusivo or 0)
        if fim <= inicio:
            return []
        with self.conectar() as conn:
            linhas = conn.execute(
                """
                SELECT nsu,schema_doc,tipo_doc,chave,emitente_nome,emitente_doc,tem_xml_completo
                FROM documentos_nfe
                WHERE cnpj_empresa=? AND ambiente=? AND nsu>? AND nsu<=?
                ORDER BY nsu
                """,
                (cnpj, ambiente, inicio, fim),
            ).fetchall()
        return [dict(linha) for linha in linhas]

    def salvar_documento(self, cnpj: str, ambiente: str, nsu: int, schema: str, xml: str, dados: dict) -> bool:
        agora = datetime.now().isoformat(timespec="seconds")
        vals = (
            cnpj, ambiente, int(nsu), schema or "", dados.get("chave", ""), dados.get("tipo", ""),
            dados.get("emitente_doc", ""), dados.get("emitente_nome", ""), dados.get("emitente_ie", ""),
            dados.get("data_emissao", ""), dados.get("data_autorizacao", ""), float(dados.get("valor_nf", 0) or 0),
            dados.get("situacao_nfe", ""), dados.get("tp_nf", ""), dados.get("prazo_final", ""), xml or "",
            1 if dados.get("tem_xml_completo") else 0, agora,
        )
        with self.conectar() as conn:
            antes = conn.total_changes
            conn.execute(
                """
                INSERT INTO documentos_nfe(
                    cnpj_empresa,ambiente,nsu,schema_doc,chave,tipo_doc,emitente_doc,emitente_nome,emitente_ie,
                    data_emissao,data_autorizacao,valor_nf,situacao_nfe,tp_nf,prazo_final,xml,tem_xml_completo,recebido_em
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(cnpj_empresa,ambiente,nsu) DO UPDATE SET
                    schema_doc=excluded.schema_doc,
                    chave=CASE WHEN excluded.chave<>'' THEN excluded.chave ELSE documentos_nfe.chave END,
                    tipo_doc=excluded.tipo_doc,
                    emitente_doc=CASE WHEN excluded.emitente_doc<>'' THEN excluded.emitente_doc ELSE documentos_nfe.emitente_doc END,
                    emitente_nome=CASE WHEN excluded.emitente_nome<>'' THEN excluded.emitente_nome ELSE documentos_nfe.emitente_nome END,
                    emitente_ie=CASE WHEN excluded.emitente_ie<>'' THEN excluded.emitente_ie ELSE documentos_nfe.emitente_ie END,
                    data_emissao=CASE WHEN excluded.data_emissao<>'' THEN excluded.data_emissao ELSE documentos_nfe.data_emissao END,
                    data_autorizacao=CASE WHEN excluded.data_autorizacao<>'' THEN excluded.data_autorizacao ELSE documentos_nfe.data_autorizacao END,
                    valor_nf=CASE WHEN excluded.valor_nf<>0 THEN excluded.valor_nf ELSE documentos_nfe.valor_nf END,
                    situacao_nfe=CASE WHEN excluded.situacao_nfe<>'' THEN excluded.situacao_nfe ELSE documentos_nfe.situacao_nfe END,
                    tp_nf=CASE WHEN excluded.tp_nf<>'' THEN excluded.tp_nf ELSE documentos_nfe.tp_nf END,
                    prazo_final=CASE WHEN excluded.prazo_final<>'' THEN excluded.prazo_final ELSE documentos_nfe.prazo_final END,
                    xml=CASE WHEN excluded.xml<>'' THEN excluded.xml ELSE documentos_nfe.xml END,
                    tem_xml_completo=MAX(documentos_nfe.tem_xml_completo, excluded.tem_xml_completo),
                    recebido_em=excluded.recebido_em
                """,
                vals,
            )
            return conn.total_changes > antes

    def salvar_manifestacao(self, cnpj: str, ambiente: str, chave: str, tp_evento: str,
                            descricao: str, justificativa: str, retorno: dict,
                            xml_envio: str, xml_retorno: str):
        agora = datetime.now().isoformat(timespec="seconds")
        cstat = str(retorno.get("cstat") or "")
        registrado = 1 if cstat in {"135", "136"} else 0
        with self.conectar() as conn:
            conn.execute(
                """
                INSERT INTO manifestacoes_nfe(
                    cnpj_empresa,ambiente,chave,tp_evento,descricao,justificativa,cstat,motivo,protocolo,
                    data_evento,xml_envio,xml_retorno,registrado,criado_em
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (cnpj, ambiente, chave, tp_evento, descricao, justificativa, cstat,
                 str(retorno.get("motivo") or ""), str(retorno.get("protocolo") or ""),
                 str(retorno.get("data_evento") or ""), xml_envio or "", xml_retorno or "", registrado, agora),
            )

    def registrar_evento_distribuido(self, cnpj: str, ambiente: str, dados: dict, xml: str):
        tp = str(dados.get("manifestacao_codigo") or "")
        chave = str(dados.get("chave") or "")
        if not tp or not chave:
            return
        # Evita duplicar o mesmo protocolo que já foi salvo no envio local.
        protocolo = str(dados.get("protocolo") or "")
        with self.conectar() as conn:
            if protocolo:
                existe = conn.execute(
                    "SELECT 1 FROM manifestacoes_nfe WHERE cnpj_empresa=? AND ambiente=? AND protocolo=? LIMIT 1",
                    (cnpj, ambiente, protocolo),
                ).fetchone()
                if existe:
                    return
            conn.execute(
                """
                INSERT INTO manifestacoes_nfe(
                    cnpj_empresa,ambiente,chave,tp_evento,descricao,justificativa,cstat,motivo,protocolo,
                    data_evento,xml_envio,xml_retorno,registrado,criado_em
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (cnpj, ambiente, chave, tp, dados.get("manifestacao", ""), "",
                 dados.get("cstat_manifestacao", ""), dados.get("motivo_manifestacao", ""), protocolo,
                 dados.get("data_manifestacao", ""), "", xml or "", 1, datetime.now().isoformat(timespec="seconds")),
            )

    def listar_notas(self, cnpj: str, ambiente: str, busca: str = "", manifestacao: str = "TODAS") -> list[dict]:
        busca_like = f"%{str(busca or '').strip()}%"
        with self.conectar() as conn:
            # Consolida por chave e prioriza o registro que contém XML completo.
            linhas = conn.execute(
                """
                WITH base AS (
                    SELECT d.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY d.chave
                               ORDER BY d.tem_xml_completo DESC, d.nsu DESC, d.id DESC
                           ) AS rn
                    FROM documentos_nfe d
                    WHERE d.cnpj_empresa=? AND d.ambiente=? AND d.tipo_doc='NFE' AND d.chave<>''
                ), ult_man AS (
                    SELECT m.*,
                           ROW_NUMBER() OVER (PARTITION BY m.chave ORDER BY m.id DESC) AS rn
                    FROM manifestacoes_nfe m
                    WHERE m.cnpj_empresa=? AND m.ambiente=? AND m.registrado=1
                )
                SELECT b.*,
                       COALESCE(u.tp_evento,'') AS manifestacao_codigo,
                       COALESCE(NULLIF(u.descricao,''),'SEM MANIFESTAÇÃO') AS manifestacao,
                       COALESCE(u.protocolo,'') AS protocolo_manifestacao,
                       COALESCE(u.data_evento,'') AS data_manifestacao
                FROM base b
                LEFT JOIN ult_man u ON u.chave=b.chave AND u.rn=1
                WHERE b.rn=1 AND (
                    ?='' OR b.chave LIKE ? OR b.emitente_nome LIKE ? OR b.emitente_doc LIKE ?
                )
                ORDER BY COALESCE(NULLIF(b.data_emissao,''), b.recebido_em) DESC, b.nsu DESC
                """,
                (cnpj, ambiente, cnpj, ambiente, str(busca or "").strip(), busca_like, busca_like, busca_like),
            ).fetchall()
        regs = [dict(r) for r in linhas]
        filtro = str(manifestacao or "TODAS").upper()
        if filtro != "TODAS":
            regs = [r for r in regs if str(r.get("manifestacao") or "SEM MANIFESTAÇÃO").upper() == filtro]
        return regs

    def obter_xml_completo(self, cnpj: str, ambiente: str, chave: str) -> str:
        with self.conectar() as conn:
            r = conn.execute(
                """
                SELECT xml FROM documentos_nfe
                WHERE cnpj_empresa=? AND ambiente=? AND chave=? AND tem_xml_completo=1 AND xml<>''
                ORDER BY nsu DESC, id DESC LIMIT 1
                """,
                (cnpj, ambiente, chave),
            ).fetchone()
            return str(r["xml"]) if r else ""
