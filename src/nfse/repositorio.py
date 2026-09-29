"""Persistência local do módulo NFS-e Nacional."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from src.core.caminhos import PASTA_DADOS_INTERNOS
from src.services.empresas_regimes_service import EmpresasRegimesService

from .parser import somente_digitos


PASTA_NFSE = PASTA_DADOS_INTERNOS / "nfse"
BANCO_NFSE = PASTA_NFSE / "nfse_nacional.db"


class RepositorioNFSe:
    def __init__(self, caminho: str | Path = BANCO_NFSE):
        self.caminho = Path(caminho)
        self.preparar()

    def conectar(self):
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.caminho)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def preparar(self):
        with self.conectar() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS empresas_nfse (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    cnpj TEXT NOT NULL UNIQUE,
                    certificado_path TEXT NOT NULL DEFAULT '',
                    ambiente TEXT NOT NULL DEFAULT 'PRODUCAO',
                    ultimo_nsu INTEGER NOT NULL DEFAULT 0,
                    ativa INTEGER NOT NULL DEFAULT 1,
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS documentos_nfse (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empresa_id INTEGER NOT NULL,
                    nsu INTEGER NOT NULL,
                    chave_acesso TEXT NOT NULL DEFAULT '',
                    tipo_documento TEXT NOT NULL DEFAULT '',
                    tipo_evento TEXT NOT NULL DEFAULT '',
                    data_hora_geracao TEXT NOT NULL DEFAULT '',
                    xml TEXT NOT NULL DEFAULT '',
                    direcao TEXT NOT NULL DEFAULT '',
                    numero_nfse TEXT NOT NULL DEFAULT '',
                    competencia TEXT NOT NULL DEFAULT '',
                    data_emissao TEXT NOT NULL DEFAULT '',
                    prestador_doc TEXT NOT NULL DEFAULT '',
                    prestador_nome TEXT NOT NULL DEFAULT '',
                    tomador_doc TEXT NOT NULL DEFAULT '',
                    tomador_nome TEXT NOT NULL DEFAULT '',
                    intermediario_doc TEXT NOT NULL DEFAULT '',
                    intermediario_nome TEXT NOT NULL DEFAULT '',
                    valor_servico REAL NOT NULL DEFAULT 0,
                    valor_liquido REAL NOT NULL DEFAULT 0,
                    iss REAL NOT NULL DEFAULT 0,
                    pis REAL NOT NULL DEFAULT 0,
                    cofins REAL NOT NULL DEFAULT 0,
                    csll REAL NOT NULL DEFAULT 0,
                    ir REAL NOT NULL DEFAULT 0,
                    inss REAL NOT NULL DEFAULT 0,
                    situacao TEXT NOT NULL DEFAULT 'ATIVA',
                    importado_em TEXT NOT NULL,
                    UNIQUE(empresa_id, nsu),
                    FOREIGN KEY(empresa_id) REFERENCES empresas_nfse(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_nfse_empresa_data ON documentos_nfse(empresa_id, data_emissao);
                CREATE INDEX IF NOT EXISTS idx_nfse_chave ON documentos_nfse(chave_acesso);
                CREATE INDEX IF NOT EXISTS idx_nfse_direcao ON documentos_nfse(direcao);
                """
            )
            colunas = {str(r[1]) for r in conn.execute("PRAGMA table_info(empresas_nfse)").fetchall()}
            if "ativa" not in colunas:
                conn.execute("ALTER TABLE empresas_nfse ADD COLUMN ativa INTEGER NOT NULL DEFAULT 1")
            self._sincronizar_empresas_centralizadas_conexao(conn)

    @staticmethod
    def _somente_digitos(valor: object) -> str:
        return "".join(ch for ch in str(valor or "") if ch.isdigit())

    def _sincronizar_empresas_centralizadas_conexao(self, conn: sqlite3.Connection) -> None:
        cadastros = EmpresasRegimesService.listar_cadastros()
        if not cadastros:
            return

        identidades: list[tuple[str, str]] = []
        for empresa in cadastros:
            nome = " ".join(str(empresa.get("nome") or "").split())
            cnpj = self._somente_digitos(empresa.get("cnpj"))
            if not nome:
                continue
            identidades.append((nome, cnpj))
            if len(cnpj) != 14:
                # A empresa continua centralizada, mas NF-e/NFS-e só pode usar
                # a identidade quando o CNPJ estiver preenchido no cadastro.
                continue

            existente = conn.execute(
                "SELECT id, nome, cnpj FROM empresas_nfse WHERE cnpj = ? LIMIT 1",
                (cnpj,),
            ).fetchone()
            if existente is None:
                existente = conn.execute(
                    "SELECT id, nome, cnpj FROM empresas_nfse WHERE nome = ? COLLATE NOCASE LIMIT 1",
                    (nome,),
                ).fetchone()

            agora = datetime.now().isoformat(timespec="seconds")
            if existente is None:
                conn.execute(
                    """
                    INSERT INTO empresas_nfse(
                        nome, cnpj, certificado_path, ambiente, ultimo_nsu, ativa, criado_em, atualizado_em
                    ) VALUES (?, ?, '', 'PRODUCAO', 0, 1, ?, ?)
                    """,
                    (nome, cnpj, agora, agora),
                )
            else:
                conn.execute(
                    "UPDATE empresas_nfse SET nome=?, cnpj=?, ativa=1, atualizado_em=? WHERE id=?",
                    (nome, cnpj, agora, int(existente["id"])),
                )

        # Empresas antigas com certificado/documentos nunca são apagadas. Se
        # ainda não foram consolidadas no cadastro central, permanecem visíveis
        # para evitar perda operacional; a migração central as absorve na abertura.

    def sincronizar_empresas_centralizadas(self) -> None:
        with self.conectar() as conn:
            self._sincronizar_empresas_centralizadas_conexao(conn)

    def listar_empresas(self):
        with self.conectar() as conn:
            self._sincronizar_empresas_centralizadas_conexao(conn)
            return [dict(r) for r in conn.execute("SELECT * FROM empresas_nfse WHERE ativa = 1 ORDER BY nome")]

    def obter_empresa(self, empresa_id: int):
        with self.conectar() as conn:
            r = conn.execute("SELECT * FROM empresas_nfse WHERE id=?", (int(empresa_id),)).fetchone()
            return dict(r) if r else None

    def salvar_empresa(self, nome: str, cnpj: str, certificado_path: str, ambiente: str = "PRODUCAO", empresa_id=None):
        cnpj = somente_digitos(cnpj)
        if len(cnpj) != 14:
            raise ValueError("Informe o CNPJ com 14 dígitos.")
        nome = " ".join(str(nome or "").split())
        if not nome:
            raise ValueError("Informe o nome da empresa.")
        agora = datetime.now().isoformat(timespec="seconds")
        with self.conectar() as conn:
            if empresa_id:
                conn.execute(
                    "UPDATE empresas_nfse SET nome=?, cnpj=?, certificado_path=?, ambiente=?, ativa=1, atualizado_em=? WHERE id=?",
                    (nome, cnpj, certificado_path or "", ambiente, agora, int(empresa_id)),
                )
                return int(empresa_id)
            cur = conn.execute(
                "INSERT INTO empresas_nfse(nome,cnpj,certificado_path,ambiente,ativa,criado_em,atualizado_em) VALUES(?,?,?,?,1,?,?)",
                (nome, cnpj, certificado_path or "", ambiente, agora, agora),
            )
            return int(cur.lastrowid)

    def excluir_empresa(self, empresa_id: int):
        with self.conectar() as conn:
            conn.execute("DELETE FROM empresas_nfse WHERE id=?", (int(empresa_id),))

    def atualizar_ultimo_nsu(self, empresa_id: int, nsu: int):
        with self.conectar() as conn:
            conn.execute(
                "UPDATE empresas_nfse SET ultimo_nsu=?, atualizado_em=? WHERE id=?",
                (int(nsu), datetime.now().isoformat(timespec="seconds"), int(empresa_id)),
            )

    def salvar_documento(self, empresa_id: int, item: dict, dados: dict, xml: str) -> bool:
        nsu = int(item.get("NSU") or item.get("nsu") or 0)
        chave = str(item.get("ChaveAcesso") or item.get("chaveAcesso") or "")
        tipo_documento = str(item.get("TipoDocumento") or item.get("tipoDocumento") or "")
        tipo_evento = str(item.get("TipoEvento") or item.get("tipoEvento") or "")
        data_geracao = str(item.get("DataHoraGeracao") or item.get("dataHoraGeracao") or "")
        agora = datetime.now().isoformat(timespec="seconds")

        valores = (
            int(empresa_id), nsu, chave, tipo_documento, tipo_evento, data_geracao, xml or "",
            dados.get("direcao", ""), dados.get("numero_nfse", ""), dados.get("competencia", ""),
            dados.get("data_emissao", ""), dados.get("prestador_doc", ""), dados.get("prestador_nome", ""),
            dados.get("tomador_doc", ""), dados.get("tomador_nome", ""), dados.get("intermediario_doc", ""),
            dados.get("intermediario_nome", ""), float(dados.get("valor_servico", 0) or 0),
            float(dados.get("valor_liquido", 0) or 0), float(dados.get("iss", 0) or 0),
            float(dados.get("pis", 0) or 0), float(dados.get("cofins", 0) or 0),
            float(dados.get("csll", 0) or 0), float(dados.get("ir", 0) or 0),
            float(dados.get("inss", 0) or 0), "ATIVA", agora,
        )
        with self.conectar() as conn:
            antes = conn.total_changes
            conn.execute(
                """
                INSERT INTO documentos_nfse(
                    empresa_id,nsu,chave_acesso,tipo_documento,tipo_evento,data_hora_geracao,xml,
                    direcao,numero_nfse,competencia,data_emissao,prestador_doc,prestador_nome,tomador_doc,tomador_nome,
                    intermediario_doc,intermediario_nome,valor_servico,valor_liquido,iss,pis,cofins,csll,ir,inss,situacao,importado_em
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(empresa_id,nsu) DO UPDATE SET
                    chave_acesso=excluded.chave_acesso,
                    tipo_documento=excluded.tipo_documento,
                    tipo_evento=excluded.tipo_evento,
                    data_hora_geracao=excluded.data_hora_geracao,
                    xml=CASE WHEN excluded.xml<>'' THEN excluded.xml ELSE documentos_nfse.xml END,
                    direcao=CASE WHEN excluded.direcao<>'' THEN excluded.direcao ELSE documentos_nfse.direcao END,
                    numero_nfse=CASE WHEN excluded.numero_nfse<>'' THEN excluded.numero_nfse ELSE documentos_nfse.numero_nfse END,
                    competencia=CASE WHEN excluded.competencia<>'' THEN excluded.competencia ELSE documentos_nfse.competencia END,
                    data_emissao=CASE WHEN excluded.data_emissao<>'' THEN excluded.data_emissao ELSE documentos_nfse.data_emissao END,
                    prestador_doc=CASE WHEN excluded.prestador_doc<>'' THEN excluded.prestador_doc ELSE documentos_nfse.prestador_doc END,
                    prestador_nome=CASE WHEN excluded.prestador_nome<>'' THEN excluded.prestador_nome ELSE documentos_nfse.prestador_nome END,
                    tomador_doc=CASE WHEN excluded.tomador_doc<>'' THEN excluded.tomador_doc ELSE documentos_nfse.tomador_doc END,
                    tomador_nome=CASE WHEN excluded.tomador_nome<>'' THEN excluded.tomador_nome ELSE documentos_nfse.tomador_nome END,
                    valor_servico=CASE WHEN excluded.valor_servico<>0 THEN excluded.valor_servico ELSE documentos_nfse.valor_servico END,
                    valor_liquido=CASE WHEN excluded.valor_liquido<>0 THEN excluded.valor_liquido ELSE documentos_nfse.valor_liquido END,
                    importado_em=excluded.importado_em
                """,
                valores,
            )
            evento_norm = tipo_evento.strip().upper()
            codigos_cancelam = {"101101", "105102", "105104"}
            evento_cancela = evento_norm in codigos_cancelam or (
                "CANCEL" in evento_norm and "INDEFER" not in evento_norm and "SOLICITA" not in evento_norm
            )
            if evento_cancela and chave:
                conn.execute(
                    "UPDATE documentos_nfse SET situacao='CANCELADA' WHERE empresa_id=? AND chave_acesso=? AND tipo_evento=''",
                    (int(empresa_id), chave),
                )
            return conn.total_changes > antes

    def listar_documentos(
        self,
        empresa_ids: list[int] | None = None,
        inicio: str = "",
        fim: str = "",
        direcao: str = "TODAS",
        busca: str = "",
        limite: int = 5000,
    ):
        filtros = ["1=1"]
        params: list = []
        if empresa_ids:
            marcadores = ",".join("?" for _ in empresa_ids)
            filtros.append(f"d.empresa_id IN ({marcadores})")
            params.extend(int(x) for x in empresa_ids)
        if inicio:
            filtros.append("COALESCE(NULLIF(d.data_emissao,''), NULLIF(d.competencia,''), substr(d.data_hora_geracao,1,10)) >= ?")
            params.append(inicio)
        if fim:
            filtros.append("COALESCE(NULLIF(d.data_emissao,''), NULLIF(d.competencia,''), substr(d.data_hora_geracao,1,10)) <= ?")
            params.append(fim)
        if direcao and direcao != "TODAS":
            filtros.append("d.direcao=?")
            params.append(direcao)
        busca = str(busca or "").strip()
        if busca:
            like = f"%{busca}%"
            filtros.append("(d.numero_nfse LIKE ? OR d.chave_acesso LIKE ? OR d.prestador_doc LIKE ? OR d.prestador_nome LIKE ? OR d.tomador_doc LIKE ? OR d.tomador_nome LIKE ?)")
            params.extend([like] * 6)
        sql = f"""
            SELECT d.*, e.nome AS empresa_nome, e.cnpj AS empresa_cnpj
            FROM documentos_nfse d
            JOIN empresas_nfse e ON e.id=d.empresa_id
            WHERE {' AND '.join(filtros)}
            ORDER BY COALESCE(NULLIF(d.data_emissao,''), NULLIF(d.competencia,''), substr(d.data_hora_geracao,1,10)) DESC, d.nsu DESC
            LIMIT ?
        """
        params.append(int(limite))
        with self.conectar() as conn:
            return [dict(r) for r in conn.execute(sql, params)]
