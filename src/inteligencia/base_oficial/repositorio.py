from __future__ import annotations

import json
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.banco.conexao import Banco


class BaseOficialRepository:
    """Persistência de fontes, evidências e fila de revisão tributária."""

    @staticmethod
    def preparar_banco() -> None:
        conn = Banco.conectar()
        conn.cursor().executescript(
            """
            CREATE TABLE IF NOT EXISTS fontes_oficiais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT NOT NULL UNIQUE,
                nome TEXT NOT NULL,
                url TEXT NOT NULL,
                orgao TEXT NOT NULL,
                tipo TEXT NOT NULL,
                ativo INTEGER NOT NULL DEFAULT 1,
                atualizado_em TEXT,
                ultimo_status TEXT,
                ultima_mensagem TEXT
            );

            CREATE TABLE IF NOT EXISTS evidencias_tributarias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ncm TEXT,
                tema TEXT NOT NULL,
                valor_json TEXT NOT NULL,
                fonte_codigo TEXT NOT NULL,
                url TEXT NOT NULL,
                data_publicacao TEXT,
                coletado_em TEXT NOT NULL,
                confiabilidade REAL NOT NULL DEFAULT 1.0,
                status TEXT NOT NULL DEFAULT 'PENDENTE_REVISAO',
                observacao TEXT,
                UNIQUE(ncm, tema, valor_json, fonte_codigo, url)
            );

            CREATE TABLE IF NOT EXISTS atualizacoes_fontes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fonte_codigo TEXT NOT NULL,
                iniciado_em TEXT NOT NULL,
                finalizado_em TEXT,
                status TEXT NOT NULL,
                registros_lidos INTEGER NOT NULL DEFAULT 0,
                inseridos INTEGER NOT NULL DEFAULT 0,
                atualizados INTEGER NOT NULL DEFAULT 0,
                mensagem TEXT
            );

            CREATE TABLE IF NOT EXISTS fila_pesquisa_ia (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ncm TEXT NOT NULL,
                uf_origem TEXT,
                uf_destino TEXT,
                regime TEXT,
                operacao TEXT,
                criado_em TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDENTE',
                motivo TEXT,
                UNIQUE(ncm, uf_origem, uf_destino, regime, operacao, status)
            );

            CREATE TABLE IF NOT EXISTS ncm_oficial (
                ncm TEXT PRIMARY KEY,
                descricao TEXT NOT NULL,
                descricao_completa TEXT NOT NULL DEFAULT '',
                descricao_busca TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'ATIVO',
                fonte_codigo TEXT NOT NULL DEFAULT 'RFB_NCM',
                atualizado_em TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_ncm_oficial_descricao
                ON ncm_oficial(descricao);
            CREATE TABLE IF NOT EXISTS base_nacional_versoes (
                codigo TEXT PRIMARY KEY,
                versao TEXT NOT NULL,
                referencia TEXT NOT NULL DEFAULT '',
                data_publicacao TEXT,
                total_ncm INTEGER NOT NULL DEFAULT 0,
                total_tipi INTEGER NOT NULL DEFAULT 0,
                fonte_url TEXT NOT NULL DEFAULT '',
                instalado_em TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tipi_oficial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ncm TEXT NOT NULL,
                ex_tipi TEXT NOT NULL DEFAULT '',
                descricao TEXT NOT NULL DEFAULT '',
                aliquota REAL,
                aliquota_texto TEXT NOT NULL DEFAULT '',
                fonte_codigo TEXT NOT NULL DEFAULT 'RFB_TIPI',
                vigencia_referencia TEXT,
                atualizado_em TEXT NOT NULL,
                UNIQUE(ncm, ex_tipi)
            );

            CREATE INDEX IF NOT EXISTS idx_tipi_oficial_ncm
                ON tipi_oficial(ncm);

            CREATE TABLE IF NOT EXISTS st_mg_oficial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                segmento TEXT NOT NULL DEFAULT 'AUTOPEÇAS',
                item TEXT NOT NULL,
                cest TEXT NOT NULL,
                ncm_formatado TEXT NOT NULL,
                ncm_digitos TEXT NOT NULL,
                descricao TEXT NOT NULL,
                ambito TEXT NOT NULL DEFAULT '',
                mva REAL,
                mva_texto TEXT NOT NULL DEFAULT '',
                fonte_codigo TEXT NOT NULL DEFAULT 'SEF_MG_ST_AUTOPECAS',
                vigencia_referencia TEXT,
                atualizado_em TEXT NOT NULL,
                UNIQUE(segmento, item, cest, ncm_digitos)
            );

            CREATE INDEX IF NOT EXISTS idx_st_mg_ncm
                ON st_mg_oficial(ncm_digitos);
            CREATE INDEX IF NOT EXISTS idx_st_mg_cest
                ON st_mg_oficial(cest);

            CREATE TABLE IF NOT EXISTS st_mg_base_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                base_completa INTEGER NOT NULL DEFAULT 0,
                versao_schema INTEGER NOT NULL DEFAULT 1,
                paginas INTEGER NOT NULL DEFAULT 0,
                segmentos INTEGER NOT NULL DEFAULT 0,
                registros INTEGER NOT NULL DEFAULT 0,
                referencia TEXT NOT NULL DEFAULT '',
                fonte_url TEXT NOT NULL DEFAULT '',
                sincronizado_em TEXT
            );
            """
        )
        # Migração segura para bancos criados pela Sprint 9.2.
        colunas = {r[1] for r in conn.execute("PRAGMA table_info(fontes_oficiais)")}
        for nome in ("ultimo_status", "ultima_mensagem"):
            if nome not in colunas:
                conn.execute(f"ALTER TABLE fontes_oficiais ADD COLUMN {nome} TEXT")

        colunas_ncm = {r[1] for r in conn.execute("PRAGMA table_info(ncm_oficial)")}
        for nome in ("descricao_completa", "descricao_busca"):
            if nome not in colunas_ncm:
                conn.execute(
                    f"ALTER TABLE ncm_oficial ADD COLUMN {nome} TEXT NOT NULL DEFAULT ''"
                )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ncm_oficial_busca "
            "ON ncm_oficial(descricao_busca)"
        )

        colunas_st = {r[1] for r in conn.execute("PRAGMA table_info(st_mg_oficial)")}
        if "mva_texto" not in colunas_st:
            conn.execute(
                "ALTER TABLE st_mg_oficial ADD COLUMN mva_texto TEXT NOT NULL DEFAULT ''"
            )

        conn.execute(
            """INSERT OR IGNORE INTO st_mg_base_status(
                   id, base_completa, versao_schema, paginas, segmentos, registros,
                   referencia, fonte_url, sincronizado_em
               ) VALUES (1, 0, 1, 0, 0, 0, '', '', NULL)"""
        )
        conn.commit()
        conn.close()

    @staticmethod
    def registrar_fonte(codigo: str, nome: str, url: str, orgao: str, tipo: str) -> None:
        BaseOficialRepository.preparar_banco()
        conn = Banco.conectar()
        conn.execute(
            """
            INSERT INTO fontes_oficiais(codigo, nome, url, orgao, tipo, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(codigo) DO UPDATE SET
                nome=excluded.nome, url=excluded.url, orgao=excluded.orgao,
                tipo=excluded.tipo
            """,
            (codigo, nome, url, orgao, tipo, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit(); conn.close()

    @staticmethod
    def atualizar_status_fonte(codigo: str, status: str, mensagem: str = "") -> None:
        BaseOficialRepository.preparar_banco()
        conn = Banco.conectar()
        conn.execute(
            "UPDATE fontes_oficiais SET atualizado_em=?, ultimo_status=?, ultima_mensagem=? WHERE codigo=?",
            (datetime.now().isoformat(timespec="seconds"), status, mensagem, codigo),
        )
        conn.commit(); conn.close()

    @staticmethod
    def iniciar_atualizacao(fonte_codigo: str) -> int:
        BaseOficialRepository.preparar_banco()
        conn = Banco.conectar()
        cur = conn.execute(
            "INSERT INTO atualizacoes_fontes(fonte_codigo, iniciado_em, status) VALUES (?, ?, 'EXECUTANDO')",
            (fonte_codigo, datetime.now().isoformat(timespec="seconds")),
        )
        ident = int(cur.lastrowid)
        conn.commit(); conn.close()
        return ident

    @staticmethod
    def finalizar_atualizacao(identificador: int, status: str, registros_lidos: int,
                              inseridos: int, atualizados: int, mensagem: str = "") -> None:
        conn = Banco.conectar()
        conn.execute(
            """UPDATE atualizacoes_fontes SET finalizado_em=?, status=?, registros_lidos=?,
               inseridos=?, atualizados=?, mensagem=? WHERE id=?""",
            (datetime.now().isoformat(timespec="seconds"), status, registros_lidos,
             inseridos, atualizados, mensagem, identificador),
        )
        conn.commit(); conn.close()

    @staticmethod
    def salvar_evidencia(ncm: Optional[str], tema: str, valor: Dict[str, Any],
                         fonte_codigo: str, url: str, data_publicacao: Optional[str] = None,
                         confiabilidade: float = 1.0, observacao: str = "",
                         status: str = "PENDENTE_REVISAO") -> None:
        BaseOficialRepository.preparar_banco()
        conn = Banco.conectar()
        conn.execute(
            """INSERT OR IGNORE INTO evidencias_tributarias
            (ncm, tema, valor_json, fonte_codigo, url, data_publicacao, coletado_em,
             confiabilidade, status, observacao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ncm, tema, json.dumps(valor, ensure_ascii=False, sort_keys=True), fonte_codigo,
             url, data_publicacao, datetime.now().isoformat(timespec="seconds"),
             confiabilidade, status, observacao),
        )
        conn.commit(); conn.close()

    @staticmethod
    def listar_evidencias(ncm: str) -> List[Dict[str, Any]]:
        BaseOficialRepository.preparar_banco()
        conn = Banco.conectar()
        rows = conn.execute(
            """SELECT e.*, f.nome AS fonte_nome, f.orgao
               FROM evidencias_tributarias e
               LEFT JOIN fontes_oficiais f ON f.codigo=e.fonte_codigo
               WHERE e.ncm=? OR e.ncm IS NULL
               ORDER BY e.confiabilidade DESC, e.coletado_em DESC""",
            (ncm,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def listar_fontes() -> List[Dict[str, Any]]:
        BaseOficialRepository.preparar_banco()
        conn = Banco.conectar()
        rows = conn.execute("SELECT * FROM fontes_oficiais WHERE ativo=1 ORDER BY orgao, nome").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def enfileirar_pesquisa(consulta, motivo: str) -> None:
        BaseOficialRepository.preparar_banco()
        conn = Banco.conectar()
        conn.execute(
            """INSERT OR IGNORE INTO fila_pesquisa_ia
            (ncm, uf_origem, uf_destino, regime, operacao, criado_em, status, motivo)
            VALUES (?, ?, ?, ?, ?, ?, 'PENDENTE', ?)""",
            (consulta.ncm, consulta.uf_origem, consulta.uf_destino, consulta.regime,
             consulta.operacao, datetime.now().isoformat(timespec="seconds"), motivo),
        )
        conn.commit(); conn.close()
    @staticmethod
    def _texto_busca(texto: Any) -> str:
        valor = str(texto or "").upper()
        valor = "".join(
            caractere for caractere in unicodedata.normalize("NFD", valor)
            if unicodedata.category(caractere) != "Mn"
        )
        return " ".join(valor.split())

    @staticmethod
    def substituir_ncm_oficial(registros: List[Dict[str, Any]]) -> int:
        """Substitui a NCM vigente preservando descrições hierárquicas já instaladas."""
        BaseOficialRepository.preparar_banco()
        agora = datetime.now().isoformat(timespec="seconds")
        conn = Banco.conectar()
        try:
            anteriores = {
                str(row["ncm"]): str(row["descricao_completa"] or "")
                for row in conn.execute(
                    "SELECT ncm, descricao_completa FROM ncm_oficial"
                ).fetchall()
            }
            linhas = []
            for item in registros:
                codigo = str(item.get("ncm") or "")
                descricao = str(item.get("descricao") or "")
                completa = str(
                    item.get("descricao_completa")
                    or anteriores.get(codigo)
                    or descricao
                )
                linhas.append((
                    codigo, descricao, completa,
                    BaseOficialRepository._texto_busca(
                        f"{codigo} {descricao} {completa}"
                    ),
                    item.get("status", "ATIVO"),
                    item.get("fonte_codigo", "RFB_NCM"),
                    agora,
                ))

            conn.execute("BEGIN")
            conn.execute("DELETE FROM ncm_oficial")
            conn.executemany(
                """
                INSERT INTO ncm_oficial(
                    ncm, descricao, descricao_completa, descricao_busca,
                    status, fonte_codigo, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                linhas,
            )
            conn.commit()
            return len(linhas)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def buscar_ncm_oficial(ncm: str) -> Optional[Dict[str, Any]]:
        BaseOficialRepository.preparar_banco()
        codigo = "".join(c for c in str(ncm or "") if c.isdigit())
        conn = Banco.conectar()
        row = conn.execute(
            "SELECT * FROM ncm_oficial WHERE ncm = ?",
            (codigo,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def substituir_tipi(registros: List[Dict[str, Any]], referencia: str = "") -> int:
        """Substitui a cópia local da TIPI em uma única transação."""
        BaseOficialRepository.preparar_banco()
        agora = datetime.now().isoformat(timespec="seconds")
        conn = Banco.conectar()
        try:
            conn.execute("BEGIN")
            conn.execute("DELETE FROM tipi_oficial")
            conn.executemany(
                """
                INSERT INTO tipi_oficial(
                    ncm, ex_tipi, descricao, aliquota, aliquota_texto,
                    fonte_codigo, vigencia_referencia, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, 'RFB_TIPI', ?, ?)
                """,
                [
                    (
                        item.get("ncm", ""),
                        item.get("ex_tipi", ""),
                        item.get("descricao", ""),
                        item.get("aliquota"),
                        item.get("aliquota_texto", ""),
                        referencia,
                        agora,
                    )
                    for item in registros
                ],
            )
            conn.commit()
            return len(registros)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def buscar_tipi(ncm: str) -> List[Dict[str, Any]]:
        BaseOficialRepository.preparar_banco()
        codigo = "".join(c for c in str(ncm or "") if c.isdigit())
        conn = Banco.conectar()
        rows = conn.execute(
            """
            SELECT * FROM tipi_oficial
             WHERE ncm = ?
             ORDER BY CASE WHEN TRIM(ex_tipi) = '' THEN 0 ELSE 1 END, ex_tipi
            """,
            (codigo,),
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]



    @staticmethod
    def instalar_base_nacional(
        metadata: Dict[str, Any],
        registros_ncm: List[Dict[str, Any]],
        registros_tipi: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Instala/enriquece a base nacional sem apagar dados oficiais mais recentes.

        A descrição hierárquica do pacote é incorporada aos NCMs já sincronizados
        pelo Classif. Códigos adicionais existentes no banco são preservados. A TIPI
        somente é substituída quando o banco local está vazio ou incompleto.
        """
        BaseOficialRepository.preparar_banco()
        agora = datetime.now().isoformat(timespec="seconds")
        versao = str(metadata.get("versao") or "").strip()
        if not versao:
            raise ValueError("A versão da base nacional não foi informada.")

        conn = Banco.conectar()
        try:
            existentes = {
                str(row["ncm"]): dict(row)
                for row in conn.execute("SELECT * FROM ncm_oficial").fetchall()
            }
            mesclados: Dict[str, Dict[str, Any]] = dict(existentes)
            for item in registros_ncm:
                codigo = str(item.get("ncm") or "")
                if not codigo:
                    continue
                anterior = existentes.get(codigo, {})
                mesclados[codigo] = {
                    "ncm": codigo,
                    "descricao": anterior.get("descricao") or item.get("descricao", ""),
                    "descricao_completa": (
                        item.get("descricao_completa")
                        or anterior.get("descricao_completa")
                        or anterior.get("descricao")
                        or item.get("descricao", "")
                    ),
                    "status": anterior.get("status") or item.get("status", "ATIVO"),
                    "fonte_codigo": (
                        anterior.get("fonte_codigo")
                        or item.get("fonte_codigo")
                        or metadata.get("fonte_codigo", "RFB_TIPI")
                    ),
                }

            linhas_ncm = []
            for codigo in sorted(mesclados):
                item = mesclados[codigo]
                descricao = str(item.get("descricao") or "")
                completa = str(item.get("descricao_completa") or descricao)
                linhas_ncm.append((
                    codigo, descricao, completa,
                    BaseOficialRepository._texto_busca(f"{codigo} {descricao} {completa}"),
                    item.get("status", "ATIVO"),
                    item.get("fonte_codigo", "RFB_NCM"),
                    agora,
                ))

            total_tipi_atual = int(
                conn.execute("SELECT COUNT(*) FROM tipi_oficial").fetchone()[0]
            )
            substituir_tipi = total_tipi_atual < max(1, int(len(registros_tipi) * 0.95))

            conn.execute("BEGIN")
            conn.execute("DELETE FROM ncm_oficial")
            conn.executemany(
                """
                INSERT INTO ncm_oficial(
                    ncm, descricao, descricao_completa, descricao_busca,
                    status, fonte_codigo, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                linhas_ncm,
            )

            if substituir_tipi:
                conn.execute("DELETE FROM tipi_oficial")
                conn.executemany(
                    """
                    INSERT INTO tipi_oficial(
                        ncm, ex_tipi, descricao, aliquota, aliquota_texto,
                        fonte_codigo, vigencia_referencia, atualizado_em
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            item.get("ncm", ""),
                            item.get("ex_tipi", ""),
                            item.get("descricao", ""),
                            item.get("aliquota"),
                            item.get("aliquota_texto", ""),
                            metadata.get("fonte_codigo", "RFB_TIPI"),
                            metadata.get("referencia", ""),
                            agora,
                        )
                        for item in registros_tipi
                    ],
                )

            total_ncm_final = len(linhas_ncm)
            total_tipi_final = (
                len(registros_tipi) if substituir_tipi else total_tipi_atual
            )
            conn.execute(
                """
                INSERT INTO base_nacional_versoes(
                    codigo, versao, referencia, data_publicacao, total_ncm,
                    total_tipi, fonte_url, instalado_em
                ) VALUES ('NCM_TIPI', ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(codigo) DO UPDATE SET
                    versao=excluded.versao,
                    referencia=excluded.referencia,
                    data_publicacao=excluded.data_publicacao,
                    total_ncm=excluded.total_ncm,
                    total_tipi=excluded.total_tipi,
                    fonte_url=excluded.fonte_url,
                    instalado_em=excluded.instalado_em
                """,
                (
                    versao,
                    metadata.get("referencia", ""),
                    metadata.get("data_publicacao"),
                    total_ncm_final,
                    total_tipi_final,
                    metadata.get("fonte_url", ""),
                    agora,
                ),
            )
            conn.commit()
            return {
                "versao": versao,
                "total_ncm": total_ncm_final,
                "total_tipi": total_tipi_final,
                "tipi_substituida": substituir_tipi,
                "instalado_em": agora,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def resumo_base_nacional() -> Dict[str, Any]:
        BaseOficialRepository.preparar_banco()
        conn = Banco.conectar()
        try:
            meta = conn.execute(
                "SELECT * FROM base_nacional_versoes WHERE codigo='NCM_TIPI'"
            ).fetchone()
            total_ncm = int(conn.execute("SELECT COUNT(*) FROM ncm_oficial").fetchone()[0])
            total_tipi = int(conn.execute("SELECT COUNT(*) FROM tipi_oficial").fetchone()[0])
            resultado = dict(meta) if meta else {}
            resultado.update({"total_ncm": total_ncm, "total_tipi": total_tipi})
            return resultado
        finally:
            conn.close()

    @staticmethod
    def buscar_ncm_catalogo(termo: str, limite: int = 300) -> List[Dict[str, Any]]:
        """Pesquisa por código ou por todas as palavras da descrição oficial."""
        BaseOficialRepository.preparar_banco()
        termo_limpo = BaseOficialRepository._texto_busca(termo)
        palavras = [parte for parte in termo_limpo.split() if parte]
        limite = max(1, min(int(limite or 300), 1000))
        conn = Banco.conectar()
        try:
            condicoes: List[str] = []
            parametros: List[Any] = []
            for palavra in palavras:
                condicoes.append("n.descricao_busca LIKE ?")
                parametros.append(f"%{palavra}%")
            where = " AND ".join(condicoes) if condicoes else "1=1"
            parametros.append(limite)
            rows = conn.execute(
                f"""
                SELECT
                    n.ncm, n.descricao, n.descricao_completa, n.status,
                    MAX(CASE WHEN TRIM(t.ex_tipi) = '' THEN t.aliquota END) AS aliquota,
                    MAX(CASE WHEN TRIM(t.ex_tipi) = '' THEN t.aliquota_texto END) AS aliquota_texto,
                    SUM(CASE WHEN TRIM(t.ex_tipi) <> '' THEN 1 ELSE 0 END) AS quantidade_ex
                FROM ncm_oficial n
                LEFT JOIN tipi_oficial t ON t.ncm = n.ncm
                WHERE {where}
                GROUP BY n.ncm, n.descricao, n.descricao_completa, n.status
                ORDER BY
                    CASE WHEN n.ncm = ? THEN 0
                         WHEN n.ncm LIKE ? THEN 1 ELSE 2 END,
                    n.ncm
                LIMIT ?
                """,
                [*parametros[:-1], "".join(c for c in str(termo or "") if c.isdigit()),
                 f"{''.join(c for c in str(termo or '') if c.isdigit())}%", parametros[-1]],
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def substituir_st_mg(registros: List[Dict[str, Any]], referencia: str = "") -> int:
        """Substitui a cópia oficial da tabela mineira de ICMS-ST."""
        BaseOficialRepository.preparar_banco()
        agora = datetime.now().isoformat(timespec="seconds")
        conn = Banco.conectar()
        try:
            conn.execute("BEGIN")
            conn.execute("DELETE FROM st_mg_oficial")
            conn.executemany(
                """
                INSERT INTO st_mg_oficial(
                    segmento, item, cest, ncm_formatado, ncm_digitos, descricao,
                    ambito, mva, mva_texto, fonte_codigo, vigencia_referencia, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.get("segmento", "AUTOPEÇAS"),
                        item.get("item", ""),
                        item.get("cest", ""),
                        item.get("ncm_formatado", ""),
                        item.get("ncm_digitos", ""),
                        item.get("descricao", ""),
                        item.get("ambito", ""),
                        item.get("mva"),
                        item.get("mva_texto", ""),
                        item.get("fonte_codigo", "SEF_MG_ST_AUTOPECAS"),
                        referencia,
                        agora,
                    )
                    for item in registros
                ],
            )
            conn.commit()
            return len(registros)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def substituir_st_mg_segmento(
        registros: List[Dict[str, Any]],
        segmento: str,
        fonte_codigo: str,
        referencia: str = "",
    ) -> int:
        """Atualiza somente um segmento da tabela oficial de ST/MG.

        Isso permite sincronizar autopeças, pneumáticos e outros segmentos sem
        apagar os dados oficiais já baixados para os demais grupos.
        """
        BaseOficialRepository.preparar_banco()
        segmento_normalizado = str(segmento or "").strip().upper()
        agora = datetime.now().isoformat(timespec="seconds")
        conn = Banco.conectar()
        try:
            conn.execute("BEGIN")
            conn.execute("DELETE FROM st_mg_oficial WHERE segmento = ?", (segmento_normalizado,))
            conn.executemany(
                """
                INSERT INTO st_mg_oficial(
                    segmento, item, cest, ncm_formatado, ncm_digitos, descricao,
                    ambito, mva, mva_texto, fonte_codigo, vigencia_referencia, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        segmento_normalizado,
                        item.get("item", ""),
                        item.get("cest", ""),
                        item.get("ncm_formatado", ""),
                        item.get("ncm_digitos", ""),
                        item.get("descricao", ""),
                        item.get("ambito", ""),
                        item.get("mva"),
                        item.get("mva_texto", ""),
                        item.get("fonte_codigo", fonte_codigo),
                        referencia,
                        agora,
                    )
                    for item in registros
                ],
            )
            conn.commit()
            return len(registros)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def buscar_st_mg_por_ncm(ncm: str, segmento: Optional[str] = None) -> List[Dict[str, Any]]:
        """Busca o NCM em um segmento específico ou em toda a tabela ST/MG."""
        BaseOficialRepository.preparar_banco()
        codigo = "".join(c for c in str(ncm or "") if c.isdigit())
        conn = Banco.conectar()
        if segmento:
            rows = conn.execute(
                """
                SELECT * FROM st_mg_oficial
                 WHERE segmento = ?
                   AND TRIM(ncm_digitos) <> ''
                   AND ? LIKE ncm_digitos || '%'
                 ORDER BY LENGTH(ncm_digitos) DESC, item, cest
                """,
                (str(segmento).strip().upper(), codigo),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM st_mg_oficial
                 WHERE TRIM(ncm_digitos) <> ''
                   AND ? LIKE ncm_digitos || '%'
                 ORDER BY LENGTH(ncm_digitos) DESC, segmento, item, cest
                """,
                (codigo,),
            ).fetchall()
        conn.close()
        return [dict(row) for row in rows]
    @staticmethod
    def resumo_st_mg() -> Dict[str, Any]:
        """Retorna a cobertura atualmente instalada da tabela ST/MG.

        A contagem é apenas um indicador de cobertura técnica. Ela não confirma
        ausência de substituição tributária para NCMs não encontrados.
        """
        BaseOficialRepository.preparar_banco()
        conn = Banco.conectar()
        try:
            registros = int(
                conn.execute("SELECT COUNT(*) FROM st_mg_oficial").fetchone()[0]
            )
            segmentos = int(
                conn.execute(
                    "SELECT COUNT(DISTINCT segmento) FROM st_mg_oficial"
                ).fetchone()[0]
            )
            atualizado_em = conn.execute(
                "SELECT MAX(atualizado_em) FROM st_mg_oficial"
            ).fetchone()[0]
            lista = [
                str(row[0])
                for row in conn.execute(
                    "SELECT DISTINCT segmento FROM st_mg_oficial ORDER BY segmento"
                ).fetchall()
            ]
            status = conn.execute(
                "SELECT * FROM st_mg_base_status WHERE id = 1"
            ).fetchone()
            status_dict = dict(status) if status else {}
            return {
                "registros": registros,
                "segmentos": segmentos,
                "segmentos_lista": lista,
                "atualizado_em": atualizado_em or "",
                "base_completa": bool(status_dict.get("base_completa")),
                "versao_schema": int(status_dict.get("versao_schema") or 0),
                "paginas": int(status_dict.get("paginas") or 0),
                "referencia": str(status_dict.get("referencia") or ""),
                "fonte_url": str(status_dict.get("fonte_url") or ""),
                "sincronizado_em": str(status_dict.get("sincronizado_em") or ""),
            }
        finally:
            conn.close()

    @staticmethod
    def registrar_status_st_mg(
        *,
        base_completa: bool,
        versao_schema: int,
        paginas: int,
        segmentos: int,
        registros: int,
        referencia: str,
        fonte_url: str,
    ) -> None:
        """Registra se a cópia local cobre integralmente a Parte 2 do Anexo VII.

        A negativa automática de ICMS-ST só pode usar ausência de NCM como
        evidência quando ``base_completa`` estiver marcada por uma sincronização
        integral concluída com sucesso.
        """
        BaseOficialRepository.preparar_banco()
        conn = Banco.conectar()
        conn.execute(
            """
            INSERT INTO st_mg_base_status(
                id, base_completa, versao_schema, paginas, segmentos, registros,
                referencia, fonte_url, sincronizado_em
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                base_completa=excluded.base_completa,
                versao_schema=excluded.versao_schema,
                paginas=excluded.paginas,
                segmentos=excluded.segmentos,
                registros=excluded.registros,
                referencia=excluded.referencia,
                fonte_url=excluded.fonte_url,
                sincronizado_em=excluded.sincronizado_em
            """,
            (
                1 if base_completa else 0,
                int(versao_schema or 1),
                int(paginas or 0),
                int(segmentos or 0),
                int(registros or 0),
                str(referencia or ""),
                str(fonte_url or ""),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def status_st_mg() -> Dict[str, Any]:
        BaseOficialRepository.preparar_banco()
        conn = Banco.conectar()
        try:
            row = conn.execute(
                "SELECT * FROM st_mg_base_status WHERE id = 1"
            ).fetchone()
            if not row:
                return {
                    "base_completa": False,
                    "versao_schema": 0,
                    "paginas": 0,
                    "segmentos": 0,
                    "registros": 0,
                    "referencia": "",
                    "fonte_url": "",
                    "sincronizado_em": "",
                }
            dados = dict(row)
            dados["base_completa"] = bool(dados.get("base_completa"))
            return dados
        finally:
            conn.close()

    @staticmethod
    def ultima_atualizacao(fonte_codigo: str) -> Optional[Dict[str, Any]]:
        BaseOficialRepository.preparar_banco()
        conn = Banco.conectar()
        row = conn.execute(
            """
            SELECT * FROM atualizacoes_fontes
             WHERE fonte_codigo = ?
             ORDER BY id DESC LIMIT 1
            """,
            (fonte_codigo,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

