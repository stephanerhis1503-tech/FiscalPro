from src.banco.conexao import Banco


class TributacaoBaseRepository:

    @staticmethod
    def _texto(valor):
        return "" if valor is None else str(valor).strip()

    @staticmethod
    def _numero(valor):
        if valor is None or valor == "":
            return 0.0
        if isinstance(valor, (int, float)):
            return float(valor)
        texto = str(valor).strip().replace("%", "").replace("R$", "").replace(" ", "")
        if "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", ".")
        try:
            return float(texto)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _digitos(valor):
        return "".join(c for c in TributacaoBaseRepository._texto(valor) if c.isdigit())

    @staticmethod
    def buscar_por_codigo(codigo_produto, empresa=""):
        conn = Banco.conectar()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM tributacao_base
            WHERE empresa = ? AND codigo_produto = ? AND ativo = 1
            ORDER BY id DESC LIMIT 1
        """, (TributacaoBaseRepository._texto(empresa),
              TributacaoBaseRepository._texto(codigo_produto)))
        resultado = cursor.fetchone()
        conn.close()
        return resultado

    @staticmethod
    def buscar_por_ncm(ncm, empresa=""):
        conn = Banco.conectar()
        cursor = conn.cursor()
        ncm = TributacaoBaseRepository._digitos(ncm)
        if empresa:
            cursor.execute("""
                SELECT * FROM tributacao_base
                WHERE ncm = ? AND empresa = ? AND ativo = 1
                ORDER BY confiabilidade DESC, id DESC
            """, (ncm, TributacaoBaseRepository._texto(empresa)))
        else:
            cursor.execute("""
                SELECT * FROM tributacao_base
                WHERE ncm = ? AND ativo = 1
                ORDER BY confiabilidade DESC, id DESC
            """, (ncm,))
        resultados = cursor.fetchall()
        conn.close()
        return resultados


    @staticmethod
    def buscar_perfil_predominante(ncm, empresa=""):
        """Retorna o perfil tributário mais frequente para o NCM.

        A base Digisat é por produto; um mesmo NCM pode possuir cadastros
        diferentes. Por isso a consulta por NCM escolhe o perfil predominante
        e informa quantos produtos e variações existem, sem ocultar a ambiguidade.
        """
        conn = Banco.conectar()
        cursor = conn.cursor()
        ncm = TributacaoBaseRepository._digitos(ncm)

        filtro_empresa = " AND empresa = ?" if empresa else ""
        parametros = (ncm, TributacaoBaseRepository._texto(empresa)) if empresa else (ncm,)

        cursor.execute(f"""
            SELECT
                ncm, cest, cfop, cst_icms, icms, icms_st, fcp,
                cst_pis, aliquota_pis, cst_cofins, aliquota_cofins,
                cst_ipi, ipi, ibs, cbs, classificacao, beneficio,
                fonte, MAX(confiabilidade) AS confiabilidade,
                COUNT(*) AS quantidade_produtos
            FROM tributacao_base
            WHERE ncm = ? AND ativo = 1 {filtro_empresa}
            GROUP BY
                ncm, cest, cfop, cst_icms, icms, icms_st, fcp,
                cst_pis, aliquota_pis, cst_cofins, aliquota_cofins,
                cst_ipi, ipi, ibs, cbs, classificacao, beneficio, fonte
            ORDER BY quantidade_produtos DESC, confiabilidade DESC, id DESC
            LIMIT 1
        """, parametros)
        perfil = cursor.fetchone()

        cursor.execute(f"""
            SELECT COUNT(*) AS total
            FROM tributacao_base
            WHERE ncm = ? AND ativo = 1 {filtro_empresa}
        """, parametros)
        total = cursor.fetchone()["total"]

        cursor.execute(f"""
            SELECT COUNT(*) AS total FROM (
                SELECT 1
                FROM tributacao_base
                WHERE ncm = ? AND ativo = 1 {filtro_empresa}
                GROUP BY cest, cfop, cst_icms, icms, icms_st, fcp,
                         cst_pis, aliquota_pis, cst_cofins, aliquota_cofins,
                         cst_ipi, ipi, ibs, cbs
            )
        """, parametros)
        variacoes = cursor.fetchone()["total"]
        conn.close()

        return perfil, int(total or 0), int(variacoes or 0)

    @staticmethod
    def salvar(**dados):
        empresa = TributacaoBaseRepository._texto(dados.get("empresa"))
        codigo = TributacaoBaseRepository._texto(dados.get("codigo_produto"))
        ncm = TributacaoBaseRepository._digitos(dados.get("ncm"))
        if not ncm:
            raise ValueError("NCM obrigatório.")

        conn = Banco.conectar()
        cursor = conn.cursor()
        existente = None
        if codigo:
            cursor.execute("""
                SELECT id FROM tributacao_base
                WHERE empresa = ? AND codigo_produto = ?
                ORDER BY id DESC LIMIT 1
            """, (empresa, codigo))
            existente = cursor.fetchone()

        valores = (
            empresa,
            codigo,
            TributacaoBaseRepository._texto(dados.get("descricao_produto")),
            ncm,
            TributacaoBaseRepository._digitos(dados.get("cest")),
            TributacaoBaseRepository._digitos(dados.get("cfop")),
            TributacaoBaseRepository._texto(dados.get("cst_icms")),
            TributacaoBaseRepository._numero(dados.get("icms")),
            TributacaoBaseRepository._texto(dados.get("icms_st")),
            TributacaoBaseRepository._numero(dados.get("fcp")),
            TributacaoBaseRepository._texto(dados.get("cst_pis")),
            TributacaoBaseRepository._numero(dados.get("aliquota_pis")),
            TributacaoBaseRepository._texto(dados.get("cst_cofins")),
            TributacaoBaseRepository._numero(dados.get("aliquota_cofins")),
            TributacaoBaseRepository._texto(dados.get("cst_ipi")),
            TributacaoBaseRepository._numero(dados.get("ipi")),
            TributacaoBaseRepository._numero(dados.get("ibs")),
            TributacaoBaseRepository._numero(dados.get("cbs")),
            TributacaoBaseRepository._texto(dados.get("classificacao")),
            TributacaoBaseRepository._texto(dados.get("beneficio")),
            TributacaoBaseRepository._texto(dados.get("fonte", "DIGISAT")),
            int(dados.get("confiabilidade", 90) or 90),
            dados.get("ultima_validacao"),
            TributacaoBaseRepository._texto(dados.get("observacoes")),
            int(dados.get("ativo", 1) or 1),
        )

        if existente:
            cursor.execute("""
                UPDATE tributacao_base SET
                    empresa=?, codigo_produto=?, descricao_produto=?, ncm=?, cest=?, cfop=?,
                    cst_icms=?, icms=?, icms_st=?, fcp=?, cst_pis=?, aliquota_pis=?,
                    cst_cofins=?, aliquota_cofins=?, cst_ipi=?, ipi=?, ibs=?, cbs=?,
                    classificacao=?, beneficio=?, fonte=?, confiabilidade=?, ultima_validacao=?,
                    observacoes=?, ativo=?, atualizado_em=CURRENT_TIMESTAMP
                WHERE id=?
            """, valores + (existente["id"],))
            status = "ATUALIZADO"
            registro_id = existente["id"]
        else:
            cursor.execute("""
                INSERT INTO tributacao_base (
                    empresa, codigo_produto, descricao_produto, ncm, cest, cfop,
                    cst_icms, icms, icms_st, fcp, cst_pis, aliquota_pis,
                    cst_cofins, aliquota_cofins, cst_ipi, ipi, ibs, cbs,
                    classificacao, beneficio, fonte, confiabilidade, ultima_validacao,
                    observacoes, ativo, atualizado_em
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            """, valores)
            status = "INSERIDO"
            registro_id = cursor.lastrowid

        conn.commit()
        conn.close()
        return {"status": status, "id": registro_id}
