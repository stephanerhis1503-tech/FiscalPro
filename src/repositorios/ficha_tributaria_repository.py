"""Persistência e leitura da Ficha Tributária Inteligente.

As migrações são idempotentes: acrescentam somente tabelas, colunas e índices
necessários às sprints novas, sem remover nem substituir os dados do usuário.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.banco.conexao import Banco


class FichaTributariaRepository:
    """Centraliza os dados exibidos no prontuário tributário do NCM."""

    @staticmethod
    def normalizar_ncm(ncm: Any) -> str:
        digitos = "".join(caractere for caractere in str(ncm or "") if caractere.isdigit())
        if len(digitos) != 8:
            raise ValueError("Informe um NCM com 8 dígitos.")
        return digitos

    @classmethod
    def preparar_banco(cls) -> None:
        conn = Banco.conectar()
        cursor = conn.cursor()

        def colunas_tabela(tabela: str) -> set[str]:
            cursor.execute(f"PRAGMA table_info({tabela})")
            return {str(linha[1]) for linha in cursor.fetchall()}

        def adicionar_coluna(tabela: str, coluna: str, definicao: str) -> None:
            if coluna not in colunas_tabela(tabela):
                cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")

        # Garante as tabelas centrais mesmo em uma instalação nova.
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tributacao_atual (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ncm TEXT, uf TEXT, regime TEXT, operacao TEXT,
                pis_cst TEXT, cofins_cst TEXT, aliquota_pis REAL, aliquota_cofins REAL,
                icms REAL, icms_st TEXT, fcp REAL, ipi REAL, beneficio TEXT,
                vigencia_inicio DATE, vigencia_fim DATE
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tributacao_reforma (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ncm TEXT, cclasstrib TEXT, ccredpres TEXT,
                cst_ibs TEXT, cst_cbs TEXT, aliquota_ibs REAL, aliquota_cbs REAL,
                imposto_seletivo TEXT, vigencia_inicio DATE, vigencia_fim DATE
            )
            """
        )

        # Sprint 13.2: contexto completo e versionamento das regras tributárias.
        # As colunas são acrescentadas de forma idempotente, sem substituir dados.
        for coluna, definicao in (
            ("empresa", "TEXT DEFAULT ''"),
            ("uf_origem", "TEXT DEFAULT ''"),
            ("uf_destino", "TEXT DEFAULT ''"),
            ("finalidade", "TEXT DEFAULT ''"),
            ("contribuinte", "TEXT DEFAULT 'TODOS'"),
            ("cfop", "TEXT DEFAULT ''"),
            ("cest", "TEXT DEFAULT ''"),
            ("mva_st", "REAL DEFAULT 0"),
            ("revisao_manual", "INTEGER DEFAULT 0"),
            ("cst_icms", "TEXT DEFAULT ''"),
            ("cst_ipi", "TEXT DEFAULT ''"),
            ("fonte", "TEXT DEFAULT ''"),
            ("confiabilidade", "INTEGER DEFAULT 50"),
            ("observacoes", "TEXT DEFAULT ''"),
            ("status", "TEXT DEFAULT 'VIGENTE'"),
            ("criado_em", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("atualizado_em", "TIMESTAMP"),
        ):
            adicionar_coluna("tributacao_atual", coluna, definicao)

        for coluna, definicao in (
            ("empresa", "TEXT DEFAULT ''"),
            ("uf_origem", "TEXT DEFAULT ''"),
            ("uf_destino", "TEXT DEFAULT ''"),
            ("regime", "TEXT DEFAULT ''"),
            ("operacao", "TEXT DEFAULT ''"),
            ("finalidade", "TEXT DEFAULT ''"),
            ("contribuinte", "TEXT DEFAULT 'TODOS'"),
            ("reducao_ibs", "REAL DEFAULT 0"),
            ("reducao_cbs", "REAL DEFAULT 0"),
            ("diferimento", "TEXT DEFAULT 'NÃO'"),
            ("fonte", "TEXT DEFAULT ''"),
            ("confiabilidade", "INTEGER DEFAULT 50"),
            ("observacoes", "TEXT DEFAULT ''"),
            ("status", "TEXT DEFAULT 'VIGENTE'"),
            ("criado_em", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("atualizado_em", "TIMESTAMP"),
        ):
            adicionar_coluna("tributacao_reforma", coluna, definicao)

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

        # Sprint 13.4: rastreabilidade do parecer salvo.
        for coluna, definicao in (
            ("confiabilidade", "REAL DEFAULT 0"),
            ("nivel_confiabilidade", "TEXT DEFAULT ''"),
            ("data_operacao", "DATE"),
            ("regra_atual_id", "INTEGER"),
            ("regra_reforma_id", "INTEGER"),
            ("versao_motor", "TEXT DEFAULT ''"),
        ):
            adicionar_coluna("historico_parecer", coluna, definicao)

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ficha_favoritos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ncm TEXT NOT NULL UNIQUE,
                favorito INTEGER NOT NULL DEFAULT 1,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ficha_consultas_recentes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ncm TEXT NOT NULL,
                descricao TEXT DEFAULT '',
                empresa TEXT NOT NULL DEFAULT '',
                regime TEXT DEFAULT '',
                operacao TEXT DEFAULT '',
                uf_origem TEXT DEFAULT '',
                uf_destino TEXT DEFAULT '',
                consultado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        adicionar_coluna("ficha_consultas_recentes", "contexto_chave", "TEXT DEFAULT ''")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ficha_base_legal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ncm TEXT NOT NULL,
                tipo_norma TEXT,
                numero_norma TEXT,
                orgao TEXT,
                artigo_item TEXT,
                descricao TEXT,
                trecho_relevante TEXT,
                url TEXT,
                data_publicacao DATE,
                vigencia_inicio DATE,
                vigencia_fim DATE,
                status TEXT DEFAULT 'VIGENTE',
                fonte TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Sprint 13.3: cadastro legal versionado, rastreabilidade da fonte e
        # comparação entre a norma atual e a anterior.
        for coluna, definicao in (
            ("assunto", "TEXT DEFAULT ''"),
            ("impacto_tributario", "TEXT DEFAULT ''"),
            ("origem_oficial", "INTEGER DEFAULT 1"),
            ("confiabilidade", "INTEGER DEFAULT 100"),
            ("norma_anterior_id", "INTEGER"),
            ("gera_alerta", "INTEGER DEFAULT 1"),
        ):
            adicionar_coluna("ficha_base_legal", coluna, definicao)

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ficha_historico_tributario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ncm TEXT NOT NULL,
                evento TEXT NOT NULL,
                campo TEXT,
                valor_anterior TEXT,
                valor_novo TEXT,
                origem TEXT,
                motivo TEXT,
                vigencia_inicio DATE,
                vigencia_fim DATE,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ficha_exemplos_nota (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ncm TEXT NOT NULL,
                tipo_documento TEXT,
                numero_documento TEXT,
                serie TEXT,
                chave TEXT,
                operacao TEXT,
                cfop TEXT,
                cst TEXT,
                descricao TEXT,
                observacoes TEXT,
                arquivo_origem TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ficha_alertas_legislativos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ncm TEXT NOT NULL,
                titulo TEXT NOT NULL,
                resumo TEXT,
                data_alteracao DATE,
                vigencia_inicio DATE,
                tipo_norma TEXT,
                numero_norma TEXT,
                url TEXT,
                status TEXT DEFAULT 'PENDENTE',
                lido INTEGER DEFAULT 0,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        for coluna, definicao in (
            ("base_legal_id", "INTEGER"),
            ("impacto_tributario", "TEXT DEFAULT ''"),
            ("comparacao_resumo", "TEXT DEFAULT ''"),
        ):
            adicionar_coluna("ficha_alertas_legislativos", coluna, definicao)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_historico_parecer_ncm ON historico_parecer(ncm, id DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_historico_parecer_contexto ON historico_parecer(ncm, empresa, regime, operacao)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ficha_legal_ncm ON ficha_base_legal(ncm)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ficha_legal_norma ON ficha_base_legal(ncm, tipo_norma, numero_norma)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ficha_legal_vigencia ON ficha_base_legal(ncm, vigencia_inicio, vigencia_fim, status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ficha_historico_ncm ON ficha_historico_tributario(ncm)")

        # 17.8.32: saneia duplicidades legadas do acesso rápido usando uma
        # chave de contexto calculada em Python. casefold() trata corretamente
        # acentos (ex.: SAÍDA/Saída), algo que o UPPER do SQLite não garante.
        linhas_recentes = cursor.execute(
            """
            SELECT id, ncm, empresa, regime, operacao, uf_origem, uf_destino
              FROM ficha_consultas_recentes
             ORDER BY consultado_em DESC, id DESC
            """
        ).fetchall()
        chaves_vistas = set()
        for linha in linhas_recentes:
            chave = cls._chave_contexto_consulta(
                linha["ncm"], linha["empresa"], linha["regime"], linha["operacao"],
                linha["uf_origem"], linha["uf_destino"]
            )
            if chave in chaves_vistas:
                cursor.execute("DELETE FROM ficha_consultas_recentes WHERE id = ?", (int(linha["id"]),))
                continue
            chaves_vistas.add(chave)
            cursor.execute(
                "UPDATE ficha_consultas_recentes SET contexto_chave = ? WHERE id = ?",
                (chave, int(linha["id"])),
            )

        cursor.execute("DROP INDEX IF EXISTS idx_ficha_consultas_recentes_contexto_unico")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ficha_consultas_recentes_data ON ficha_consultas_recentes(consultado_em DESC, id DESC)")
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_ficha_consultas_recentes_contexto_chave
                ON ficha_consultas_recentes(contexto_chave)
             WHERE TRIM(COALESCE(contexto_chave, '')) <> ''
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ficha_exemplos_ncm ON ficha_exemplos_nota(ncm)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ficha_alertas_ncm ON ficha_alertas_legislativos(ncm)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ficha_alertas_status ON ficha_alertas_legislativos(status, lido)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ficha_alertas_base_legal ON ficha_alertas_legislativos(base_legal_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tributacao_atual_ncm_contexto ON tributacao_atual(ncm, empresa, uf_origem, uf_destino, regime, operacao)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tributacao_atual_vigencia ON tributacao_atual(ncm, vigencia_inicio, vigencia_fim, status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reforma_ncm_contexto ON tributacao_reforma(ncm, empresa, uf_origem, uf_destino, regime, operacao)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reforma_vigencia ON tributacao_reforma(ncm, vigencia_inicio, vigencia_fim, status)")

        conn.commit()
        conn.close()

    @staticmethod
    def _linhas_para_dicts(linhas: Iterable[Any]) -> List[Dict[str, Any]]:
        return [dict(linha) for linha in linhas]

    @staticmethod
    def _texto(valor: Any) -> str:
        return str(valor or "").strip()

    @classmethod
    def _chave_contexto_consulta(
        cls, ncm: Any, empresa: Any, regime: Any, operacao: Any, uf_origem: Any, uf_destino: Any
    ) -> str:
        def normalizar(valor: Any) -> str:
            return " ".join(cls._texto(valor).split()).casefold()

        return "|".join(
            normalizar(valor)
            for valor in (ncm, empresa, regime, operacao, uf_origem, uf_destino)
        )

    @staticmethod
    def _numero(valor: Any, campo: str = "valor") -> float:
        if valor in (None, ""):
            return 0.0
        if isinstance(valor, (int, float)):
            return float(valor)
        texto = str(valor).strip().replace("%", "").replace(" ", "")
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        try:
            return float(texto)
        except (TypeError, ValueError) as erro:
            raise ValueError(f"Informe um número válido para {campo}.") from erro

    @staticmethod
    def _inteiro(valor: Any, campo: str, minimo: int = 0, maximo: int = 100) -> int:
        if valor in (None, ""):
            return minimo
        try:
            numero = int(float(str(valor).replace(",", ".")))
        except (TypeError, ValueError) as erro:
            raise ValueError(f"Informe um número inteiro válido para {campo}.") from erro
        if numero < minimo or numero > maximo:
            raise ValueError(f"{campo} deve ficar entre {minimo} e {maximo}.")
        return numero

    @staticmethod
    def _data_iso(valor: Any, campo: str = "data", obrigatoria: bool = False) -> Optional[str]:
        texto = str(valor or "").strip()
        if not texto:
            if obrigatoria:
                raise ValueError(f"Informe {campo}.")
            return None
        for formato in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(texto, formato).date().isoformat()
            except ValueError:
                continue
        raise ValueError(f"{campo.capitalize()} inválida. Use dd/mm/aaaa.")

    @staticmethod
    def _validar_periodo(inicio: Optional[str], fim: Optional[str]) -> None:
        if inicio and fim and date.fromisoformat(fim) < date.fromisoformat(inicio):
            raise ValueError("A vigência final não pode ser anterior à vigência inicial.")

    @staticmethod
    def _validar_uf(valor: Any, campo: str) -> str:
        texto = str(valor or "").strip().upper()
        ufs = {
            "", "TODAS", "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO",
            "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
            "RS", "RO", "RR", "SC", "SP", "SE", "TO",
        }
        if texto not in ufs:
            raise ValueError(f"{campo} inválida.")
        return texto

    @staticmethod
    def _validar_codigo(valor: Any, campo: str, tamanhos: Sequence[int]) -> str:
        texto = "".join(c for c in str(valor or "") if c.isdigit())
        if texto and len(texto) not in set(tamanhos):
            tamanhos_txt = " ou ".join(str(t) for t in tamanhos)
            raise ValueError(f"{campo} deve ter {tamanhos_txt} dígitos.")
        return texto

    @staticmethod
    def _periodos_sobrepostos(inicio_a: str, fim_a: Optional[str], inicio_b: str, fim_b: Optional[str]) -> bool:
        fim_maximo = "9999-12-31"
        return inicio_a <= (fim_b or fim_maximo) and inicio_b <= (fim_a or fim_maximo)

    @classmethod
    def _descricao_predominante(cls, ncm: str) -> str:
        conn = Banco.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT descricao_produto
            FROM tributacao_base
            WHERE ncm = ? AND ativo = 1 AND TRIM(COALESCE(descricao_produto, '')) <> ''
            """,
            (ncm,),
        )
        descricoes = [str(linha["descricao_produto"]).strip() for linha in cursor.fetchall()]
        conn.close()
        if not descricoes:
            return ""
        return Counter(descricoes).most_common(1)[0][0]

    @classmethod
    def buscar_dados_gerais(cls, ncm: Any) -> Dict[str, Any]:
        cls.preparar_banco()
        ncm = cls.normalizar_ncm(ncm)
        conn = Banco.conectar()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT ncm, descricao, cest, ex_tipi, data_inicio, data_fim,
                   ato_legal, numero_ato, ano_ato, status, criado_em, atualizado_em
            FROM ncm
            WHERE ncm = ?
            ORDER BY id DESC LIMIT 1
            """,
            (ncm,),
        )
        cadastro = cursor.fetchone()

        cursor.execute(
            """
            SELECT COUNT(*) AS total_produtos,
                   COUNT(DISTINCT empresa) AS total_empresas,
                   COUNT(DISTINCT COALESCE(NULLIF(cest, ''), '-')) AS total_cest,
                   MIN(ultima_validacao) AS primeira_validacao,
                   MAX(ultima_validacao) AS ultima_validacao,
                   MAX(atualizado_em) AS ultima_atualizacao
            FROM tributacao_base
            WHERE ncm = ? AND ativo = 1
            """,
            (ncm,),
        )
        base = cursor.fetchone()
        conn.close()

        descricao = (cadastro["descricao"] if cadastro else "") or cls._descricao_predominante(ncm)
        encontrado = bool(cadastro) or int(base["total_produtos"] or 0) > 0

        return {
            "encontrado": encontrado,
            "ncm": ncm,
            "descricao": descricao or "Descrição ainda não cadastrada",
            "cest": (cadastro["cest"] if cadastro else "") or "",
            "ex_tipi": (cadastro["ex_tipi"] if cadastro else "") or "",
            "status": (cadastro["status"] if cadastro else "CADASTRO OPERACIONAL") or "CADASTRO OPERACIONAL",
            "data_inicio": cadastro["data_inicio"] if cadastro else None,
            "data_fim": cadastro["data_fim"] if cadastro else None,
            "ato_legal": cadastro["ato_legal"] if cadastro else "",
            "numero_ato": cadastro["numero_ato"] if cadastro else "",
            "ano_ato": cadastro["ano_ato"] if cadastro else "",
            "criado_em": cadastro["criado_em"] if cadastro else None,
            "atualizado_em": cadastro["atualizado_em"] if cadastro else base["ultima_atualizacao"],
            "total_produtos": int(base["total_produtos"] or 0),
            "total_empresas": int(base["total_empresas"] or 0),
            "total_cest": int(base["total_cest"] or 0),
            "primeira_validacao": base["primeira_validacao"],
            "ultima_validacao": base["ultima_validacao"],
        }

    @classmethod
    def buscar_tributacao_atual(cls, ncm: Any, empresa: str = "") -> List[Dict[str, Any]]:
        cls.preparar_banco()
        ncm = cls.normalizar_ncm(ncm)
        empresa = str(empresa or "").strip()
        conn = Banco.conectar()
        cursor = conn.cursor()
        resultados: List[Dict[str, Any]] = []

        filtro_empresa = " AND (TRIM(COALESCE(empresa, '')) = '' OR empresa = ?)" if empresa else ""
        parametros: Tuple[Any, ...] = (ncm, empresa) if empresa else (ncm,)
        cursor.execute(
            f"""
            SELECT id, ncm, COALESCE(empresa, '') AS empresa,
                   COALESCE(NULLIF(uf_origem, ''), '') AS uf_origem,
                   COALESCE(NULLIF(uf_destino, ''), NULLIF(uf, ''), '') AS uf_destino,
                   COALESCE(regime, '') AS regime, COALESCE(operacao, '') AS operacao,
                   COALESCE(finalidade, '') AS finalidade,
                   COALESCE(contribuinte, 'TODOS') AS contribuinte,
                   COALESCE(cfop, '') AS cfop, COALESCE(cest, '') AS cest,
                   COALESCE(mva_st, 0) AS mva_st, COALESCE(revisao_manual, 0) AS revisao_manual,
                   COALESCE(cst_icms, '') AS cst_icms,
                   COALESCE(pis_cst, '') AS cst_pis, COALESCE(cofins_cst, '') AS cst_cofins,
                   aliquota_pis, aliquota_cofins, icms, COALESCE(icms_st, '') AS icms_st,
                   fcp, COALESCE(cst_ipi, '') AS cst_ipi, ipi, COALESCE(beneficio, '') AS beneficio,
                   vigencia_inicio, vigencia_fim, COALESCE(fonte, '') AS fonte,
                   COALESCE(confiabilidade, 50) AS confiabilidade,
                   COALESCE(observacoes, '') AS observacoes,
                   COALESCE(status, 'VIGENTE') AS status, criado_em, atualizado_em
            FROM tributacao_atual
            WHERE ncm = ? {filtro_empresa}
            ORDER BY CASE COALESCE(status, 'VIGENTE') WHEN 'VIGENTE' THEN 0 WHEN 'RASCUNHO' THEN 1 ELSE 2 END,
                     COALESCE(vigencia_inicio, '') DESC, id DESC
            """,
            parametros,
        )
        for linha in cursor.fetchall():
            item = dict(linha)
            item.update(
                {
                    "origem": "Regra por operação",
                    "tipo_origem": "tributacao_atual",
                    "empresa": item.get("empresa") or "Todas",
                    "codigo_produto": "",
                    "descricao_produto": "",
                    "ultima_validacao": item.get("atualizado_em") or item.get("vigencia_inicio"),
                }
            )
            resultados.append(item)

        filtro_produto = " AND empresa = ?" if empresa else ""
        parametros_produto = (ncm, empresa) if empresa else (ncm,)
        cursor.execute(
            f"""
            SELECT id, empresa, codigo_produto, descricao_produto, ncm, cest, cfop,
                   cst_icms, icms, icms_st, fcp, cst_pis, aliquota_pis,
                   cst_cofins, aliquota_cofins, cst_ipi, ipi, ibs, cbs,
                   classificacao, beneficio, fonte, confiabilidade,
                   ultima_validacao, observacoes, atualizado_em
            FROM tributacao_base
            WHERE ncm = ? AND ativo = 1 {filtro_produto}
            ORDER BY confiabilidade DESC, empresa, descricao_produto, id DESC
            """,
            parametros_produto,
        )
        for linha in cursor.fetchall():
            item = dict(linha)
            item.update(
                {
                    "origem": "Cadastro por produto",
                    "tipo_origem": "tributacao_base",
                    "uf_origem": "",
                    "uf_destino": "",
                    "regime": "",
                    "operacao": "",
                    "finalidade": "",
                    "contribuinte": "",
                    "vigencia_inicio": item.get("ultima_validacao"),
                    "vigencia_fim": None,
                    "status": "OPERACIONAL",
                }
            )
            resultados.append(item)

        conn.close()
        return resultados

    @classmethod
    def listar_empresas(cls, ncm: Any) -> List[str]:
        cls.preparar_banco()
        ncm = cls.normalizar_ncm(ncm)
        conn = Banco.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT empresa FROM tributacao_base
             WHERE ncm = ? AND ativo = 1 AND TRIM(COALESCE(empresa, '')) <> ''
            UNION
            SELECT empresa FROM tributacao_atual
             WHERE ncm = ? AND TRIM(COALESCE(empresa, '')) <> ''
            UNION
            SELECT empresa FROM tributacao_reforma
             WHERE ncm = ? AND TRIM(COALESCE(empresa, '')) <> ''
            ORDER BY empresa
            """,
            (ncm, ncm, ncm),
        )
        empresas = [str(linha["empresa"]) for linha in cursor.fetchall()]
        conn.close()
        return empresas

    @classmethod
    def buscar_reforma(cls, ncm: Any, empresa: str = "") -> List[Dict[str, Any]]:
        cls.preparar_banco()
        ncm = cls.normalizar_ncm(ncm)
        empresa = str(empresa or "").strip()
        conn = Banco.conectar()
        cursor = conn.cursor()
        filtro_empresa = " AND (TRIM(COALESCE(empresa, '')) = '' OR empresa = ?)" if empresa else ""
        parametros: Tuple[Any, ...] = (ncm, empresa) if empresa else (ncm,)
        cursor.execute(
            f"""
            SELECT id, ncm, COALESCE(empresa, '') AS empresa,
                   COALESCE(uf_origem, '') AS uf_origem, COALESCE(uf_destino, '') AS uf_destino,
                   COALESCE(regime, '') AS regime, COALESCE(operacao, '') AS operacao,
                   COALESCE(finalidade, '') AS finalidade, COALESCE(contribuinte, 'TODOS') AS contribuinte,
                   cclasstrib, ccredpres, cst_ibs, cst_cbs, aliquota_ibs, aliquota_cbs,
                   COALESCE(reducao_ibs, 0) AS reducao_ibs, COALESCE(reducao_cbs, 0) AS reducao_cbs,
                   COALESCE(diferimento, 'NÃO') AS diferimento, imposto_seletivo,
                   vigencia_inicio, vigencia_fim, COALESCE(fonte, '') AS fonte,
                   COALESCE(confiabilidade, 50) AS confiabilidade,
                   COALESCE(observacoes, '') AS observacoes, COALESCE(status, 'VIGENTE') AS status,
                   criado_em, atualizado_em
            FROM tributacao_reforma
            WHERE ncm = ? {filtro_empresa}
            ORDER BY CASE COALESCE(status, 'VIGENTE') WHEN 'VIGENTE' THEN 0 WHEN 'RASCUNHO' THEN 1 ELSE 2 END,
                     COALESCE(vigencia_inicio, '') DESC, id DESC
            """,
            parametros,
        )
        resultados = cls._linhas_para_dicts(cursor.fetchall())
        for item in resultados:
            item["tipo_origem"] = "tributacao_reforma"
            item["empresa"] = item.get("empresa") or "Todas"

        if not resultados:
            cursor.execute(
                """
                SELECT NULL AS id, classificacao AS cclasstrib, '' AS ccredpres,
                       '' AS cst_ibs, '' AS cst_cbs,
                       MAX(ibs) AS aliquota_ibs, MAX(cbs) AS aliquota_cbs,
                       0 AS reducao_ibs, 0 AS reducao_cbs, 'NÃO' AS diferimento,
                       '' AS imposto_seletivo, MAX(ultima_validacao) AS vigencia_inicio,
                       NULL AS vigencia_fim, fonte, 'Cadastro por produto' AS tipo_origem,
                       empresa, '' AS uf_origem, '' AS uf_destino, '' AS regime,
                       '' AS operacao, '' AS finalidade, '' AS contribuinte,
                       confiabilidade, observacoes, 'OPERACIONAL' AS status
                FROM tributacao_base
                WHERE ncm = ? AND ativo = 1
                GROUP BY classificacao, fonte, empresa, confiabilidade, observacoes
                HAVING COALESCE(classificacao, '') <> '' OR MAX(ibs) <> 0 OR MAX(cbs) <> 0
                ORDER BY fonte
                """,
                (ncm,),
            )
            resultados = cls._linhas_para_dicts(cursor.fetchall())
        conn.close()
        return resultados

    @classmethod
    def buscar_tributacao_atual_por_id(cls, registro_id: int) -> Optional[Dict[str, Any]]:
        cls.preparar_banco()
        conn = Banco.conectar()
        linha = conn.execute("SELECT * FROM tributacao_atual WHERE id = ?", (int(registro_id),)).fetchone()
        conn.close()
        return dict(linha) if linha else None

    @classmethod
    def _normalizar_tributacao_atual(cls, dados: Dict[str, Any]) -> Dict[str, Any]:
        ncm = cls.normalizar_ncm(dados.get("ncm"))
        empresa = cls._texto(dados.get("empresa"))
        if empresa.lower() in {"todas", "todas as empresas"}:
            empresa = ""
        inicio = cls._data_iso(dados.get("vigencia_inicio"), "a vigência inicial", obrigatoria=True)
        fim = cls._data_iso(dados.get("vigencia_fim"), "a vigência final")
        cls._validar_periodo(inicio, fim)
        status = cls._texto(dados.get("status") or "VIGENTE").upper()
        if status not in {"VIGENTE", "RASCUNHO", "ENCERRADA"}:
            raise ValueError("Status inválido para a regra tributária.")
        if fim and status == "VIGENTE" and fim < date.today().isoformat():
            status = "ENCERRADA"
        return {
            "ncm": ncm,
            "empresa": empresa,
            "uf_origem": cls._validar_uf(dados.get("uf_origem"), "UF de origem"),
            "uf_destino": cls._validar_uf(dados.get("uf_destino") or dados.get("uf"), "UF de destino"),
            "regime": cls._texto(dados.get("regime")).upper(),
            "operacao": cls._texto(dados.get("operacao")).upper(),
            "finalidade": cls._texto(dados.get("finalidade")).upper(),
            "contribuinte": cls._texto(dados.get("contribuinte") or "TODOS").upper(),
            "cfop": cls._validar_codigo(dados.get("cfop"), "CFOP", (4,)),
            "cest": cls._validar_codigo(dados.get("cest"), "CEST", (7,)),
            "mva_st": cls._numero(dados.get("mva_st"), "a MVA de ICMS-ST"),
            "revisao_manual": 1 if str(dados.get("revisao_manual") or "").strip().upper() in {"1", "SIM", "TRUE", "S", "YES"} or dados.get("revisao_manual") is True else 0,
            "cst_icms": cls._validar_codigo(dados.get("cst_icms"), "CST/CSOSN ICMS", (2, 3)),
            "pis_cst": cls._validar_codigo(dados.get("cst_pis") or dados.get("pis_cst"), "CST PIS", (2,)),
            "cofins_cst": cls._validar_codigo(dados.get("cst_cofins") or dados.get("cofins_cst"), "CST COFINS", (2,)),
            "cst_ipi": cls._validar_codigo(dados.get("cst_ipi"), "CST IPI", (2,)),
            "aliquota_pis": cls._numero(dados.get("aliquota_pis"), "a alíquota de PIS"),
            "aliquota_cofins": cls._numero(dados.get("aliquota_cofins"), "a alíquota de COFINS"),
            "icms": cls._numero(dados.get("icms"), "a alíquota de ICMS"),
            "icms_st": cls._texto(dados.get("icms_st")).upper(),
            "fcp": cls._numero(dados.get("fcp"), "a alíquota de FCP"),
            "ipi": cls._numero(dados.get("ipi"), "a alíquota de IPI"),
            "beneficio": cls._texto(dados.get("beneficio")),
            "vigencia_inicio": inicio,
            "vigencia_fim": fim,
            "fonte": cls._texto(dados.get("fonte")),
            "confiabilidade": cls._inteiro(dados.get("confiabilidade", 50), "Confiabilidade", 0, 100),
            "observacoes": cls._texto(dados.get("observacoes")),
            "status": status,
        }

    @staticmethod
    def _contexto_tributacao(item: Dict[str, Any]) -> Tuple[str, ...]:
        return tuple(str(item.get(campo) or "").strip().upper() for campo in (
            "ncm", "empresa", "uf_origem", "uf_destino", "regime", "operacao", "finalidade", "contribuinte"
        ))

    @classmethod
    def salvar_tributacao_atual(
        cls,
        dados: Dict[str, Any],
        registro_id: Optional[int] = None,
        encerrar_anterior: bool = True,
    ) -> int:
        cls.preparar_banco()
        novo = cls._normalizar_tributacao_atual(dados)
        antigo = cls.buscar_tributacao_atual_por_id(registro_id) if registro_id else None
        conn = Banco.conectar()
        cursor = conn.cursor()

        contexto = cls._contexto_tributacao(novo)
        cursor.execute(
            """
            SELECT * FROM tributacao_atual
             WHERE ncm = ? AND UPPER(TRIM(COALESCE(empresa, ''))) = ?
               AND UPPER(TRIM(COALESCE(uf_origem, ''))) = ?
               AND UPPER(TRIM(COALESCE(NULLIF(uf_destino, ''), uf, ''))) = ?
               AND UPPER(TRIM(COALESCE(regime, ''))) = ?
               AND UPPER(TRIM(COALESCE(operacao, ''))) = ?
               AND UPPER(TRIM(COALESCE(finalidade, ''))) = ?
               AND UPPER(TRIM(COALESCE(contribuinte, 'TODOS'))) = ?
               AND id <> ? AND COALESCE(status, 'VIGENTE') <> 'RASCUNHO'
            """,
            (*contexto, int(registro_id or 0)),
        )
        conflitos = [dict(linha) for linha in cursor.fetchall() if cls._periodos_sobrepostos(
            novo["vigencia_inicio"], novo["vigencia_fim"], str(linha["vigencia_inicio"] or "1900-01-01"), linha["vigencia_fim"]
        )]

        encerrados: List[Dict[str, Any]] = []
        for conflito in conflitos:
            inicio_existente = str(conflito.get("vigencia_inicio") or "1900-01-01")
            if registro_id or not encerrar_anterior or inicio_existente >= novo["vigencia_inicio"]:
                conn.close()
                raise ValueError(
                    "Já existe uma regra com o mesmo contexto e vigência sobreposta. "
                    "Edite a regra existente ou informe uma nova data de início."
                )
            nova_data_fim = (date.fromisoformat(novo["vigencia_inicio"]) - timedelta(days=1)).isoformat()
            cursor.execute(
                """UPDATE tributacao_atual
                      SET vigencia_fim = ?, status = 'ENCERRADA', atualizado_em = CURRENT_TIMESTAMP
                    WHERE id = ?""",
                (nova_data_fim, int(conflito["id"])),
            )
            conflito["nova_data_fim"] = nova_data_fim
            encerrados.append(conflito)

        colunas = (
            "ncm", "empresa", "uf_origem", "uf_destino", "regime", "operacao",
            "finalidade", "contribuinte", "cfop", "cest", "mva_st", "revisao_manual",
            "cst_icms", "pis_cst", "cofins_cst",
            "aliquota_pis", "aliquota_cofins", "icms", "icms_st", "fcp", "cst_ipi",
            "ipi", "beneficio", "vigencia_inicio", "vigencia_fim", "fonte",
            "confiabilidade", "observacoes", "status"
        )
        if registro_id:
            atribuicoes = ", ".join(f"{coluna} = ?" for coluna in colunas)
            cursor.execute(
                f"UPDATE tributacao_atual SET {atribuicoes}, uf = ?, atualizado_em = CURRENT_TIMESTAMP WHERE id = ?",
                tuple(novo[coluna] for coluna in colunas) + (novo["uf_destino"], int(registro_id)),
            )
            salvo_id = int(registro_id)
        else:
            nomes = ", ".join(colunas)
            marcadores = ", ".join("?" for _ in colunas)
            cursor.execute(
                f"INSERT INTO tributacao_atual ({nomes}, uf, atualizado_em) VALUES ({marcadores}, ?, CURRENT_TIMESTAMP)",
                tuple(novo[coluna] for coluna in colunas) + (novo["uf_destino"],),
            )
            salvo_id = int(cursor.lastrowid)
        conn.commit()
        conn.close()

        for item in encerrados:
            cls.registrar_historico(
                novo["ncm"], "VIGÊNCIA ENCERRADA", "Tributação Atual",
                valor_anterior=item.get("vigencia_fim") or "Sem fim", valor_novo=item["nova_data_fim"],
                origem="Ficha Tributária Inteligente",
                motivo=f"Regra {item['id']} substituída pela nova vigência {novo['vigencia_inicio']}",
            )
        cls.registrar_historico(
            novo["ncm"],
            "TRIBUTAÇÃO ATUAL EDITADA" if antigo else "TRIBUTAÇÃO ATUAL CADASTRADA",
            "Tributação Atual",
            valor_anterior=cls._resumo_regra(antigo) if antigo else "",
            valor_novo=cls._resumo_regra(novo),
            origem="Ficha Tributária Inteligente",
            motivo=f"Registro {salvo_id}",
            vigencia_inicio=novo["vigencia_inicio"],
            vigencia_fim=novo["vigencia_fim"],
        )
        return salvo_id

    @classmethod
    def encerrar_tributacao_atual(cls, registro_id: int, data_fim: Any) -> None:
        registro = cls.buscar_tributacao_atual_por_id(registro_id)
        if not registro:
            raise ValueError("Regra tributária não encontrada.")
        fim = cls._data_iso(data_fim, "a data de encerramento", obrigatoria=True)
        cls._validar_periodo(cls._data_iso(registro.get("vigencia_inicio"), "a vigência inicial", obrigatoria=True), fim)
        conn = Banco.conectar()
        conn.execute(
            "UPDATE tributacao_atual SET vigencia_fim = ?, status = 'ENCERRADA', atualizado_em = CURRENT_TIMESTAMP WHERE id = ?",
            (fim, int(registro_id)),
        )
        conn.commit()
        conn.close()
        cls.registrar_historico(
            registro["ncm"], "VIGÊNCIA ENCERRADA", "Tributação Atual",
            valor_anterior=registro.get("vigencia_fim") or "Sem fim", valor_novo=fim,
            origem="Ficha Tributária Inteligente", motivo=f"Registro {registro_id}",
        )

    @classmethod
    def buscar_reforma_por_id(cls, registro_id: int) -> Optional[Dict[str, Any]]:
        cls.preparar_banco()
        conn = Banco.conectar()
        linha = conn.execute("SELECT * FROM tributacao_reforma WHERE id = ?", (int(registro_id),)).fetchone()
        conn.close()
        return dict(linha) if linha else None

    @classmethod
    def _normalizar_reforma(cls, dados: Dict[str, Any]) -> Dict[str, Any]:
        ncm = cls.normalizar_ncm(dados.get("ncm"))
        empresa = cls._texto(dados.get("empresa"))
        if empresa.lower() in {"todas", "todas as empresas"}:
            empresa = ""
        inicio = cls._data_iso(dados.get("vigencia_inicio"), "a vigência inicial", obrigatoria=True)
        fim = cls._data_iso(dados.get("vigencia_fim"), "a vigência final")
        cls._validar_periodo(inicio, fim)
        status = cls._texto(dados.get("status") or "VIGENTE").upper()
        if status not in {"VIGENTE", "RASCUNHO", "ENCERRADA"}:
            raise ValueError("Status inválido para a regra da Reforma Tributária.")
        return {
            "ncm": ncm, "empresa": empresa,
            "uf_origem": cls._validar_uf(dados.get("uf_origem"), "UF de origem"),
            "uf_destino": cls._validar_uf(dados.get("uf_destino"), "UF de destino"),
            "regime": cls._texto(dados.get("regime")).upper(),
            "operacao": cls._texto(dados.get("operacao")).upper(),
            "finalidade": cls._texto(dados.get("finalidade")).upper(),
            "contribuinte": cls._texto(dados.get("contribuinte") or "TODOS").upper(),
            "cclasstrib": cls._texto(dados.get("cclasstrib")),
            "ccredpres": cls._texto(dados.get("ccredpres")),
            "cst_ibs": cls._validar_codigo(dados.get("cst_ibs"), "CST IBS", (3,)),
            "cst_cbs": cls._validar_codigo(dados.get("cst_cbs"), "CST CBS", (3,)),
            "aliquota_ibs": cls._numero(dados.get("aliquota_ibs"), "a alíquota de IBS"),
            "aliquota_cbs": cls._numero(dados.get("aliquota_cbs"), "a alíquota de CBS"),
            "reducao_ibs": cls._numero(dados.get("reducao_ibs"), "a redução de IBS"),
            "reducao_cbs": cls._numero(dados.get("reducao_cbs"), "a redução de CBS"),
            "diferimento": cls._texto(dados.get("diferimento") or "NÃO").upper(),
            "imposto_seletivo": cls._texto(dados.get("imposto_seletivo")).upper(),
            "vigencia_inicio": inicio, "vigencia_fim": fim,
            "fonte": cls._texto(dados.get("fonte")),
            "confiabilidade": cls._inteiro(dados.get("confiabilidade", 50), "Confiabilidade", 0, 100),
            "observacoes": cls._texto(dados.get("observacoes")),
            "status": status,
        }

    @staticmethod
    def _contexto_reforma(item: Dict[str, Any]) -> Tuple[str, ...]:
        return tuple(str(item.get(campo) or "").strip().upper() for campo in (
            "ncm", "empresa", "uf_origem", "uf_destino", "regime", "operacao", "finalidade", "contribuinte"
        ))

    @classmethod
    def salvar_reforma(
        cls, dados: Dict[str, Any], registro_id: Optional[int] = None, encerrar_anterior: bool = True
    ) -> int:
        cls.preparar_banco()
        novo = cls._normalizar_reforma(dados)
        antigo = cls.buscar_reforma_por_id(registro_id) if registro_id else None
        conn = Banco.conectar()
        cursor = conn.cursor()
        contexto = cls._contexto_reforma(novo)
        cursor.execute(
            """
            SELECT * FROM tributacao_reforma
             WHERE ncm = ? AND UPPER(TRIM(COALESCE(empresa, ''))) = ?
               AND UPPER(TRIM(COALESCE(uf_origem, ''))) = ?
               AND UPPER(TRIM(COALESCE(uf_destino, ''))) = ?
               AND UPPER(TRIM(COALESCE(regime, ''))) = ?
               AND UPPER(TRIM(COALESCE(operacao, ''))) = ?
               AND UPPER(TRIM(COALESCE(finalidade, ''))) = ?
               AND UPPER(TRIM(COALESCE(contribuinte, 'TODOS'))) = ?
               AND id <> ? AND COALESCE(status, 'VIGENTE') <> 'RASCUNHO'
            """,
            (*contexto, int(registro_id or 0)),
        )
        conflitos = [dict(linha) for linha in cursor.fetchall() if cls._periodos_sobrepostos(
            novo["vigencia_inicio"], novo["vigencia_fim"], str(linha["vigencia_inicio"] or "1900-01-01"), linha["vigencia_fim"]
        )]
        encerrados: List[Dict[str, Any]] = []
        for conflito in conflitos:
            inicio_existente = str(conflito.get("vigencia_inicio") or "1900-01-01")
            if registro_id or not encerrar_anterior or inicio_existente >= novo["vigencia_inicio"]:
                conn.close()
                raise ValueError(
                    "Já existe uma regra da Reforma com o mesmo contexto e vigência sobreposta. "
                    "Edite a regra existente ou informe outra data de início."
                )
            nova_data_fim = (date.fromisoformat(novo["vigencia_inicio"]) - timedelta(days=1)).isoformat()
            cursor.execute(
                "UPDATE tributacao_reforma SET vigencia_fim = ?, status = 'ENCERRADA', atualizado_em = CURRENT_TIMESTAMP WHERE id = ?",
                (nova_data_fim, int(conflito["id"])),
            )
            conflito["nova_data_fim"] = nova_data_fim
            encerrados.append(conflito)

        colunas = (
            "ncm", "empresa", "uf_origem", "uf_destino", "regime", "operacao", "finalidade",
            "contribuinte", "cclasstrib", "ccredpres", "cst_ibs", "cst_cbs", "aliquota_ibs",
            "aliquota_cbs", "reducao_ibs", "reducao_cbs", "diferimento", "imposto_seletivo",
            "vigencia_inicio", "vigencia_fim", "fonte", "confiabilidade", "observacoes", "status"
        )
        if registro_id:
            atribuicoes = ", ".join(f"{coluna} = ?" for coluna in colunas)
            cursor.execute(
                f"UPDATE tributacao_reforma SET {atribuicoes}, atualizado_em = CURRENT_TIMESTAMP WHERE id = ?",
                tuple(novo[coluna] for coluna in colunas) + (int(registro_id),),
            )
            salvo_id = int(registro_id)
        else:
            nomes = ", ".join(colunas)
            marcadores = ", ".join("?" for _ in colunas)
            cursor.execute(
                f"INSERT INTO tributacao_reforma ({nomes}, atualizado_em) VALUES ({marcadores}, CURRENT_TIMESTAMP)",
                tuple(novo[coluna] for coluna in colunas),
            )
            salvo_id = int(cursor.lastrowid)
        conn.commit()
        conn.close()

        for item in encerrados:
            cls.registrar_historico(
                novo["ncm"], "VIGÊNCIA ENCERRADA", "Reforma Tributária",
                valor_anterior=item.get("vigencia_fim") or "Sem fim", valor_novo=item["nova_data_fim"],
                origem="Ficha Tributária Inteligente",
                motivo=f"Regra {item['id']} substituída pela nova vigência {novo['vigencia_inicio']}",
            )
        cls.registrar_historico(
            novo["ncm"], "REFORMA EDITADA" if antigo else "REFORMA CADASTRADA", "Reforma Tributária",
            valor_anterior=cls._resumo_regra(antigo) if antigo else "",
            valor_novo=cls._resumo_regra(novo), origem="Ficha Tributária Inteligente",
            motivo=f"Registro {salvo_id}", vigencia_inicio=novo["vigencia_inicio"], vigencia_fim=novo["vigencia_fim"],
        )
        return salvo_id

    @classmethod
    def encerrar_reforma(cls, registro_id: int, data_fim: Any) -> None:
        registro = cls.buscar_reforma_por_id(registro_id)
        if not registro:
            raise ValueError("Regra da Reforma Tributária não encontrada.")
        fim = cls._data_iso(data_fim, "a data de encerramento", obrigatoria=True)
        cls._validar_periodo(cls._data_iso(registro.get("vigencia_inicio"), "a vigência inicial", obrigatoria=True), fim)
        conn = Banco.conectar()
        conn.execute(
            "UPDATE tributacao_reforma SET vigencia_fim = ?, status = 'ENCERRADA', atualizado_em = CURRENT_TIMESTAMP WHERE id = ?",
            (fim, int(registro_id)),
        )
        conn.commit()
        conn.close()
        cls.registrar_historico(
            registro["ncm"], "VIGÊNCIA ENCERRADA", "Reforma Tributária",
            valor_anterior=registro.get("vigencia_fim") or "Sem fim", valor_novo=fim,
            origem="Ficha Tributária Inteligente", motivo=f"Registro {registro_id}",
        )

    @staticmethod
    def _resumo_regra(item: Optional[Dict[str, Any]]) -> str:
        if not item:
            return ""
        contexto = " / ".join(str(item.get(campo) or "-") for campo in (
            "empresa", "uf_origem", "uf_destino", "regime", "operacao", "finalidade", "contribuinte"
        ))
        vigencia = f"{item.get('vigencia_inicio') or '-'} a {item.get('vigencia_fim') or 'sem fim'}"
        return f"{contexto} | Vigência: {vigencia} | Status: {item.get('status') or 'VIGENTE'}"

    # ------------------------------------------------------------------
    # Base Legal e alterações legislativas — Sprint 13.3
    # ------------------------------------------------------------------
    @staticmethod
    def _validar_url(valor: Any) -> str:
        url = str(valor or "").strip()
        if url and not url.lower().startswith(("http://", "https://")):
            raise ValueError("O link da fonte oficial deve começar com http:// ou https://.")
        return url

    @classmethod
    def _normalizar_base_legal(cls, dados: Dict[str, Any]) -> Dict[str, Any]:
        ncm = cls.normalizar_ncm(dados.get("ncm"))
        tipo_norma = cls._texto(dados.get("tipo_norma")).upper()
        numero_norma = cls._texto(dados.get("numero_norma"))
        descricao = cls._texto(dados.get("descricao"))
        if not tipo_norma:
            raise ValueError("Informe o tipo da norma.")
        if not numero_norma:
            raise ValueError("Informe o número ou identificação da norma.")
        if not descricao:
            raise ValueError("Informe a descrição ou ementa da norma.")

        publicacao = cls._data_iso(dados.get("data_publicacao"), "a data de publicação")
        inicio = cls._data_iso(dados.get("vigencia_inicio"), "a vigência inicial")
        fim = cls._data_iso(dados.get("vigencia_fim"), "a vigência final")
        cls._validar_periodo(inicio, fim)

        status = cls._texto(dados.get("status") or "VIGENTE").upper()
        if status not in {"VIGENTE", "RASCUNHO", "ENCERRADA", "REVOGADA"}:
            raise ValueError("Status inválido para a base legal.")

        norma_anterior = dados.get("norma_anterior_id")
        try:
            norma_anterior_id = int(norma_anterior) if str(norma_anterior or "").strip() else None
        except (TypeError, ValueError) as erro:
            raise ValueError("A norma anterior informada é inválida.") from erro

        return {
            "ncm": ncm,
            "tipo_norma": tipo_norma,
            "numero_norma": numero_norma,
            "orgao": cls._texto(dados.get("orgao")).upper(),
            "artigo_item": cls._texto(dados.get("artigo_item")),
            "assunto": cls._texto(dados.get("assunto")),
            "descricao": descricao,
            "trecho_relevante": cls._texto(dados.get("trecho_relevante")),
            "impacto_tributario": cls._texto(dados.get("impacto_tributario")),
            "url": cls._validar_url(dados.get("url")),
            "data_publicacao": publicacao,
            "vigencia_inicio": inicio,
            "vigencia_fim": fim,
            "status": status,
            "fonte": cls._texto(dados.get("fonte")),
            "origem_oficial": 1 if bool(dados.get("origem_oficial", True)) else 0,
            "confiabilidade": cls._inteiro(dados.get("confiabilidade", 100), "Confiabilidade", 0, 100),
            "norma_anterior_id": norma_anterior_id,
            "gera_alerta": 1 if bool(dados.get("gera_alerta", True)) else 0,
        }

    @classmethod
    def buscar_base_legal_por_id(cls, registro_id: int) -> Optional[Dict[str, Any]]:
        cls.preparar_banco()
        conn = Banco.conectar()
        linha = conn.execute(
            "SELECT * FROM ficha_base_legal WHERE id = ?",
            (int(registro_id),),
        ).fetchone()
        conn.close()
        return dict(linha) if linha else None

    @classmethod
    def _buscar_norma_anterior_automatica(
        cls,
        ncm: str,
        referencia_data: Optional[str],
        ignorar_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        conn = Banco.conectar()
        parametros: List[Any] = [ncm]
        filtro_id = ""
        if ignorar_id:
            filtro_id = " AND id <> ?"
            parametros.append(int(ignorar_id))
        filtro_data = ""
        if referencia_data:
            filtro_data = " AND COALESCE(vigencia_inicio, data_publicacao, '0001-01-01') <= ?"
            parametros.append(referencia_data)
        linha = conn.execute(
            f"""
            SELECT * FROM ficha_base_legal
             WHERE ncm = ? {filtro_id} {filtro_data}
             ORDER BY COALESCE(vigencia_inicio, data_publicacao, '0001-01-01') DESC, id DESC
             LIMIT 1
            """,
            tuple(parametros),
        ).fetchone()
        conn.close()
        return dict(linha) if linha else None

    @staticmethod
    def _resumo_base_legal(item: Optional[Dict[str, Any]]) -> str:
        if not item:
            return ""
        norma = " ".join(
            parte for parte in (str(item.get("tipo_norma") or ""), str(item.get("numero_norma") or "")) if parte
        )
        vigencia = f"{item.get('vigencia_inicio') or '-'} a {item.get('vigencia_fim') or 'sem fim'}"
        return (
            f"{norma} | {item.get('orgao') or 'Órgão não informado'} | "
            f"{item.get('artigo_item') or 'Artigo não informado'} | Vigência: {vigencia} | "
            f"Status: {item.get('status') or 'VIGENTE'}"
        )

    @classmethod
    def comparar_base_legal(
        cls,
        registro_atual_id: int,
        registro_anterior_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        atual = cls.buscar_base_legal_por_id(registro_atual_id)
        if not atual:
            raise ValueError("Registro da base legal não encontrado.")

        anterior: Optional[Dict[str, Any]] = None
        id_anterior = registro_anterior_id or atual.get("norma_anterior_id")
        if id_anterior:
            anterior = cls.buscar_base_legal_por_id(int(id_anterior))
        if not anterior:
            referencia = atual.get("vigencia_inicio") or atual.get("data_publicacao")
            anterior = cls._buscar_norma_anterior_automatica(
                atual["ncm"],
                referencia,
                ignorar_id=int(atual["id"]),
            )

        campos = (
            ("tipo_norma", "Tipo da norma"),
            ("numero_norma", "Número da norma"),
            ("orgao", "Órgão"),
            ("artigo_item", "Artigo/Item"),
            ("assunto", "Assunto"),
            ("descricao", "Descrição/Ementa"),
            ("trecho_relevante", "Trecho relevante"),
            ("impacto_tributario", "Impacto tributário"),
            ("data_publicacao", "Data de publicação"),
            ("vigencia_inicio", "Início da vigência"),
            ("vigencia_fim", "Fim da vigência"),
            ("status", "Status"),
            ("fonte", "Fonte"),
            ("url", "Link oficial"),
        )
        alteracoes: List[Dict[str, Any]] = []
        for campo, rotulo in campos:
            valor_anterior = str((anterior or {}).get(campo) or "")
            valor_atual = str(atual.get(campo) or "")
            alteracoes.append(
                {
                    "campo": campo,
                    "rotulo": rotulo,
                    "anterior": valor_anterior,
                    "atual": valor_atual,
                    "alterado": valor_anterior.strip() != valor_atual.strip(),
                }
            )
        return {
            "anterior": anterior,
            "atual": atual,
            "alteracoes": alteracoes,
            "total_alteracoes": sum(1 for item in alteracoes if item["alterado"]),
        }

    @classmethod
    def _salvar_alerta_da_norma(
        cls,
        norma: Dict[str, Any],
        comparacao: Optional[Dict[str, Any]] = None,
    ) -> int:
        alteradas = [item["rotulo"] for item in (comparacao or {}).get("alteracoes", []) if item["alterado"]]
        comparacao_resumo = ", ".join(alteradas[:8])
        if len(alteradas) > 8:
            comparacao_resumo += f" e mais {len(alteradas) - 8} campo(s)"

        anterior = (comparacao or {}).get("anterior")
        norma_txt = " ".join(
            parte for parte in (norma.get("tipo_norma"), norma.get("numero_norma")) if parte
        )
        titulo = f"Alteração legislativa — {norma_txt}" if anterior else f"Nova base legal — {norma_txt}"
        resumo = norma.get("impacto_tributario") or norma.get("descricao") or "Base legal atualizada."
        data_alteracao = norma.get("data_publicacao") or date.today().isoformat()

        conn = Banco.conectar()
        existente = conn.execute(
            "SELECT id FROM ficha_alertas_legislativos WHERE base_legal_id = ? ORDER BY id DESC LIMIT 1",
            (int(norma["id"]),),
        ).fetchone()
        valores = (
            norma["ncm"], titulo, resumo, data_alteracao, norma.get("vigencia_inicio"),
            norma.get("tipo_norma"), norma.get("numero_norma"), norma.get("url"),
            "PENDENTE", 0, int(norma["id"]), norma.get("impacto_tributario") or "",
            comparacao_resumo,
        )
        if existente:
            conn.execute(
                """
                UPDATE ficha_alertas_legislativos
                   SET ncm = ?, titulo = ?, resumo = ?, data_alteracao = ?, vigencia_inicio = ?,
                       tipo_norma = ?, numero_norma = ?, url = ?, status = ?, lido = ?,
                       base_legal_id = ?, impacto_tributario = ?, comparacao_resumo = ?,
                       atualizado_em = CURRENT_TIMESTAMP
                 WHERE id = ?
                """,
                valores + (int(existente["id"]),),
            )
            alerta_id = int(existente["id"])
        else:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO ficha_alertas_legislativos
                (ncm, titulo, resumo, data_alteracao, vigencia_inicio, tipo_norma,
                 numero_norma, url, status, lido, base_legal_id, impacto_tributario,
                 comparacao_resumo, atualizado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                valores,
            )
            alerta_id = int(cursor.lastrowid)
        conn.commit()
        conn.close()
        return alerta_id

    @classmethod
    def salvar_base_legal(
        cls,
        dados: Dict[str, Any],
        registro_id: Optional[int] = None,
    ) -> int:
        cls.preparar_banco()
        novo = cls._normalizar_base_legal(dados)
        antigo = cls.buscar_base_legal_por_id(registro_id) if registro_id else None

        if novo["norma_anterior_id"] is None and not registro_id:
            referencia = novo.get("vigencia_inicio") or novo.get("data_publicacao")
            anterior_auto = cls._buscar_norma_anterior_automatica(novo["ncm"], referencia)
            if anterior_auto:
                novo["norma_anterior_id"] = int(anterior_auto["id"])

        colunas = (
            "ncm", "tipo_norma", "numero_norma", "orgao", "artigo_item", "assunto",
            "descricao", "trecho_relevante", "impacto_tributario", "url",
            "data_publicacao", "vigencia_inicio", "vigencia_fim", "status", "fonte",
            "origem_oficial", "confiabilidade", "norma_anterior_id", "gera_alerta",
        )
        conn = Banco.conectar()
        cursor = conn.cursor()
        if registro_id:
            atribuicoes = ", ".join(f"{coluna} = ?" for coluna in colunas)
            cursor.execute(
                f"UPDATE ficha_base_legal SET {atribuicoes}, atualizado_em = CURRENT_TIMESTAMP WHERE id = ?",
                tuple(novo[coluna] for coluna in colunas) + (int(registro_id),),
            )
            salvo_id = int(registro_id)
        else:
            nomes = ", ".join(colunas)
            marcadores = ", ".join("?" for _ in colunas)
            cursor.execute(
                f"INSERT INTO ficha_base_legal ({nomes}, atualizado_em) VALUES ({marcadores}, CURRENT_TIMESTAMP)",
                tuple(novo[coluna] for coluna in colunas),
            )
            salvo_id = int(cursor.lastrowid)
        conn.commit()
        conn.close()

        salvo = cls.buscar_base_legal_por_id(salvo_id)
        cls.registrar_historico(
            novo["ncm"],
            "BASE LEGAL EDITADA" if antigo else "BASE LEGAL CADASTRADA",
            "Base Legal",
            valor_anterior=cls._resumo_base_legal(antigo) if antigo else "",
            valor_novo=cls._resumo_base_legal(salvo),
            origem="Ficha Tributária Inteligente",
            motivo=f"Registro {salvo_id}",
            vigencia_inicio=novo.get("vigencia_inicio"),
            vigencia_fim=novo.get("vigencia_fim"),
        )

        if salvo and int(novo.get("gera_alerta") or 0) and novo["status"] != "RASCUNHO":
            comparacao = cls.comparar_base_legal(salvo_id)
            cls._salvar_alerta_da_norma(salvo, comparacao)
        return salvo_id

    @classmethod
    def encerrar_base_legal(
        cls,
        registro_id: int,
        data_fim: Any,
        status: str = "ENCERRADA",
    ) -> None:
        registro = cls.buscar_base_legal_por_id(registro_id)
        if not registro:
            raise ValueError("Registro da base legal não encontrado.")
        fim = cls._data_iso(data_fim, "a data de encerramento", obrigatoria=True)
        inicio = cls._data_iso(registro.get("vigencia_inicio"), "a vigência inicial")
        cls._validar_periodo(inicio, fim)
        status_normalizado = cls._texto(status or "ENCERRADA").upper()
        if status_normalizado not in {"ENCERRADA", "REVOGADA"}:
            raise ValueError("O encerramento deve usar o status ENCERRADA ou REVOGADA.")
        conn = Banco.conectar()
        conn.execute(
            """
            UPDATE ficha_base_legal
               SET vigencia_fim = ?, status = ?, atualizado_em = CURRENT_TIMESTAMP
             WHERE id = ?
            """,
            (fim, status_normalizado, int(registro_id)),
        )
        conn.commit()
        conn.close()
        cls.registrar_historico(
            registro["ncm"],
            "BASE LEGAL ENCERRADA" if status_normalizado == "ENCERRADA" else "BASE LEGAL REVOGADA",
            "Base Legal",
            valor_anterior=registro.get("vigencia_fim") or "Sem fim",
            valor_novo=fim,
            origem="Ficha Tributária Inteligente",
            motivo=f"Registro {registro_id} — {status_normalizado}",
            vigencia_inicio=registro.get("vigencia_inicio"),
            vigencia_fim=fim,
        )

    @classmethod
    def buscar_base_legal(cls, ncm: Any) -> List[Dict[str, Any]]:
        cls.preparar_banco()
        ncm = cls.normalizar_ncm(ncm)
        conn = Banco.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, ncm, tipo_norma, numero_norma, orgao, artigo_item,
                   assunto, descricao, trecho_relevante, impacto_tributario,
                   url, data_publicacao, vigencia_inicio, vigencia_fim,
                   status, fonte, origem_oficial, confiabilidade,
                   norma_anterior_id, gera_alerta, criado_em, atualizado_em
            FROM ficha_base_legal
            WHERE ncm = ?
            ORDER BY CASE status WHEN 'VIGENTE' THEN 0 ELSE 1 END,
                     COALESCE(vigencia_inicio, data_publicacao, '') DESC, id DESC
            """,
            (ncm,),
        )
        itens = cls._linhas_para_dicts(cursor.fetchall())
        for item in itens:
            item["tipo_origem"] = "ficha_base_legal"

        # Compatibilidade com a tabela antiga de legislação, quando houver conteúdo.
        cursor.execute(
            """
            SELECT id, tipo AS tipo_norma, numero AS numero_norma,
                   '' AS orgao, '' AS artigo_item, descricao,
                   '' AS trecho_relevante, url, NULL AS data_publicacao,
                   vigencia AS vigencia_inicio, NULL AS vigencia_fim,
                   'VIGENTE' AS status, 'Legislação geral' AS fonte,
                   '' AS assunto, '' AS impacto_tributario,
                   0 AS origem_oficial, 50 AS confiabilidade,
                   NULL AS norma_anterior_id, 0 AS gera_alerta
            FROM legislacao
            WHERE descricao LIKE ? OR numero LIKE ?
            ORDER BY vigencia DESC, id DESC
            """,
            (f"%{ncm}%", f"%{ncm}%"),
        )
        antigos = cls._linhas_para_dicts(cursor.fetchall())
        for item in antigos:
            item["tipo_origem"] = "legislacao"
        itens.extend(antigos)
        conn.close()
        return itens

    @classmethod
    def buscar_historico(cls, ncm: Any, limite: int = 200) -> List[Dict[str, Any]]:
        cls.preparar_banco()
        ncm = cls.normalizar_ncm(ncm)
        conn = Banco.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, ncm, evento, campo, valor_anterior, valor_novo,
                   origem, motivo, vigencia_inicio, vigencia_fim, criado_em
            FROM ficha_historico_tributario
            WHERE ncm = ?
            ORDER BY id DESC LIMIT ?
            """,
            (ncm, int(limite)),
        )
        itens = cls._linhas_para_dicts(cursor.fetchall())

        cursor.execute(
            """
            SELECT id, ncm, 'PARECER SALVO' AS evento, 'Parecer tributário' AS campo,
                   '' AS valor_anterior, descricao AS valor_novo,
                   'FiscalPro' AS origem,
                   COALESCE(empresa, '') || CASE WHEN regime <> '' THEN ' | ' || regime ELSE '' END AS motivo,
                   NULL AS vigencia_inicio, NULL AS vigencia_fim, criado_em
            FROM historico_parecer
            WHERE ncm = ?
            ORDER BY id DESC LIMIT ?
            """,
            (ncm, int(limite)),
        )
        itens.extend(cls._linhas_para_dicts(cursor.fetchall()))
        itens.sort(key=lambda item: str(item.get("criado_em") or ""), reverse=True)
        conn.close()
        return itens[:limite]

    @classmethod
    def buscar_exemplos(cls, ncm: Any) -> List[Dict[str, Any]]:
        cls.preparar_banco()
        ncm = cls.normalizar_ncm(ncm)
        conn = Banco.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, ncm, tipo_documento, numero_documento, serie, chave,
                   operacao, cfop, cst, descricao, observacoes, arquivo_origem, criado_em
            FROM ficha_exemplos_nota
            WHERE ncm = ?
            ORDER BY id DESC
            """,
            (ncm,),
        )
        itens = cls._linhas_para_dicts(cursor.fetchall())
        conn.close()
        return itens

    @classmethod
    def buscar_alertas(cls, ncm: Any) -> List[Dict[str, Any]]:
        cls.preparar_banco()
        ncm = cls.normalizar_ncm(ncm)
        conn = Banco.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, ncm, titulo, resumo, data_alteracao, vigencia_inicio,
                   tipo_norma, numero_norma, url, status, lido,
                   base_legal_id, impacto_tributario, comparacao_resumo,
                   criado_em, atualizado_em
            FROM ficha_alertas_legislativos
            WHERE ncm = ?
            ORDER BY lido ASC, COALESCE(vigencia_inicio, data_alteracao, '') DESC, id DESC
            """,
            (ncm,),
        )
        itens = cls._linhas_para_dicts(cursor.fetchall())
        conn.close()
        return itens

    @classmethod
    def eh_favorito(cls, ncm: Any) -> bool:
        cls.preparar_banco()
        ncm = cls.normalizar_ncm(ncm)
        conn = Banco.conectar()
        linha = conn.execute(
            "SELECT favorito FROM ficha_favoritos WHERE ncm = ?",
            (ncm,),
        ).fetchone()
        conn.close()
        return bool(linha and int(linha["favorito"] or 0) == 1)

    @classmethod
    def definir_favorito(cls, ncm: Any, favorito: bool) -> bool:
        cls.preparar_banco()
        ncm = cls.normalizar_ncm(ncm)
        conn = Banco.conectar()
        conn.execute(
            """
            INSERT INTO ficha_favoritos (ncm, favorito, atualizado_em)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(ncm) DO UPDATE SET
                favorito = excluded.favorito,
                atualizado_em = CURRENT_TIMESTAMP
            """,
            (ncm, 1 if favorito else 0),
        )
        conn.commit()
        conn.close()
        return favorito

    @classmethod
    def listar_favoritos(cls) -> List[Dict[str, Any]]:
        cls.preparar_banco()
        conn = Banco.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT f.ncm,
                   COALESCE(NULLIF(n.descricao, ''),
                       (SELECT tb.descricao_produto
                          FROM tributacao_base tb
                         WHERE tb.ncm = f.ncm AND tb.ativo = 1
                           AND TRIM(COALESCE(tb.descricao_produto, '')) <> ''
                         ORDER BY tb.confiabilidade DESC, tb.id DESC LIMIT 1),
                       'Descrição ainda não cadastrada') AS descricao,
                   f.atualizado_em
            FROM ficha_favoritos f
            LEFT JOIN ncm n ON n.ncm = f.ncm
            WHERE f.favorito = 1
            ORDER BY f.atualizado_em DESC, f.ncm
            """
        )
        itens = cls._linhas_para_dicts(cursor.fetchall())
        conn.close()
        return itens

    @classmethod
    def registrar_consulta_recente(
        cls,
        ncm: Any,
        descricao: str = "",
        empresa: str = "",
        regime: str = "",
        operacao: str = "",
        uf_origem: str = "",
        uf_destino: str = "",
    ) -> int:
        """Registra a consulta concluída sem duplicar o mesmo contexto no topo."""
        cls.preparar_banco()
        ncm = cls.normalizar_ncm(ncm)
        valores = (
            ncm, cls._texto(descricao), cls._texto(empresa), cls._texto(regime).upper(),
            cls._texto(operacao).upper(), cls._texto(uf_origem).upper(), cls._texto(uf_destino).upper(),
        )
        contexto_chave = cls._chave_contexto_consulta(
            valores[0], valores[2], valores[3], valores[4], valores[5], valores[6]
        )
        conn = Banco.conectar()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM ficha_consultas_recentes WHERE contexto_chave = ?",
            (contexto_chave,),
        )
        cursor.execute(
            """
            INSERT INTO ficha_consultas_recentes
                (ncm, descricao, empresa, regime, operacao, uf_origem, uf_destino, contexto_chave, consultado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (*valores, contexto_chave),
        )
        registro_id = int(cursor.lastrowid)
        # Mantém somente um histórico curto para não crescer indefinidamente.
        cursor.execute(
            """
            DELETE FROM ficha_consultas_recentes
             WHERE id NOT IN (
                SELECT id FROM ficha_consultas_recentes
                 ORDER BY consultado_em DESC, id DESC LIMIT 50
             )
            """
        )
        conn.commit()
        conn.close()
        return registro_id

    @classmethod
    def listar_consultas_recentes(cls, limite: int = 6) -> List[Dict[str, Any]]:
        cls.preparar_banco()
        conn = Banco.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT r.id, r.ncm,
                   COALESCE(NULLIF(r.descricao, ''), NULLIF(n.descricao, ''), 'Descrição não informada') AS descricao,
                   COALESCE(r.empresa, '') AS empresa, COALESCE(r.regime, '') AS regime,
                   COALESCE(r.operacao, '') AS operacao, COALESCE(r.uf_origem, '') AS uf_origem,
                   COALESCE(r.uf_destino, '') AS uf_destino, r.consultado_em
              FROM ficha_consultas_recentes r
              LEFT JOIN ncm n ON n.ncm = r.ncm
             ORDER BY r.consultado_em DESC, r.id DESC
             LIMIT ?
            """,
            (max(1, int(limite)),),
        )
        itens = cls._linhas_para_dicts(cursor.fetchall())
        conn.close()
        return itens

    @classmethod
    def registrar_historico(
        cls,
        ncm: Any,
        evento: str,
        campo: str = "",
        valor_anterior: Any = "",
        valor_novo: Any = "",
        origem: str = "FiscalPro",
        motivo: str = "",
        vigencia_inicio: Optional[str] = None,
        vigencia_fim: Optional[str] = None,
    ) -> int:
        cls.preparar_banco()
        ncm = cls.normalizar_ncm(ncm)
        conn = Banco.conectar()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ficha_historico_tributario
            (ncm, evento, campo, valor_anterior, valor_novo, origem, motivo,
             vigencia_inicio, vigencia_fim)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ncm,
                str(evento or "ATUALIZAÇÃO"),
                str(campo or ""),
                str(valor_anterior or ""),
                str(valor_novo or ""),
                str(origem or "FiscalPro"),
                str(motivo or ""),
                vigencia_inicio,
                vigencia_fim,
            ),
        )
        conn.commit()
        registro_id = int(cursor.lastrowid)
        conn.close()
        return registro_id

    @classmethod
    def marcar_alerta_lido(cls, alerta_id: int, lido: bool = True) -> None:
        cls.preparar_banco()
        conn = Banco.conectar()
        conn.execute(
            "UPDATE ficha_alertas_legislativos SET lido = ?, atualizado_em = CURRENT_TIMESTAMP WHERE id = ?",
            (1 if lido else 0, int(alerta_id)),
        )
        conn.commit()
        conn.close()

    @classmethod
    def buscar_alerta_por_id(cls, alerta_id: int) -> Optional[Dict[str, Any]]:
        cls.preparar_banco()
        conn = Banco.conectar()
        linha = conn.execute(
            "SELECT * FROM ficha_alertas_legislativos WHERE id = ?",
            (int(alerta_id),),
        ).fetchone()
        conn.close()
        return dict(linha) if linha else None

    @classmethod
    def carregar_ficha(cls, ncm: Any, empresa: str = "") -> Dict[str, Any]:
        ncm = cls.normalizar_ncm(ncm)
        dados = cls.buscar_dados_gerais(ncm)
        tributacoes = cls.buscar_tributacao_atual(ncm, empresa=empresa)
        reforma = cls.buscar_reforma(ncm, empresa=empresa)
        base_legal = cls.buscar_base_legal(ncm)
        historico = cls.buscar_historico(ncm)
        exemplos = cls.buscar_exemplos(ncm)
        alertas = cls.buscar_alertas(ncm)
        favorito = cls.eh_favorito(ncm)

        dados["consultado_em"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        return {
            "dados_gerais": dados,
            "tributacoes": tributacoes,
            "reforma": reforma,
            "base_legal": base_legal,
            "historico": historico,
            "exemplos": exemplos,
            "alertas": alertas,
            "favorito": favorito,
            "empresas": cls.listar_empresas(ncm),
        }
