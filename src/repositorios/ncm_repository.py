from src.banco.conexao import Banco


class NCMRepository:

    # ==========================================================
    # CADASTRO NCM
    # ==========================================================

    @staticmethod
    def buscar_por_ncm(ncm):

        conn = Banco.conectar()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM ncm
            WHERE ncm = ?
        """, (ncm,))

        resultado = cursor.fetchone()

        conn.close()

        return resultado

    @staticmethod
    def listar():

        conn = Banco.conectar()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM ncm
            ORDER BY ncm
        """)

        registros = cursor.fetchall()

        conn.close()

        return registros

    @staticmethod
    def inserir(
        ncm,
        descricao,
        cest="",
        ex_tipi="",
        data_inicio=None,
        data_fim=None,
        ato_legal=None,
        numero_ato=None,
        ano_ato=None,
        status="ATIVO"
    ):

        conn = Banco.conectar()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO ncm
            (
                ncm,
                descricao,
                cest,
                ex_tipi,
                data_inicio,
                data_fim,
                ato_legal,
                numero_ato,
                ano_ato,
                status
            )
            VALUES
            (
                ?,?,?,?,?,?,?,?,?,?
            )
        """, (
            ncm,
            descricao,
            cest,
            ex_tipi,
            data_inicio,
            data_fim,
            ato_legal,
            numero_ato,
            ano_ato,
            status
        ))

        conn.commit()
        conn.close()

    @staticmethod
    def atualizar(
        ncm,
        descricao,
        cest="",
        ex_tipi="",
        data_inicio=None,
        data_fim=None,
        ato_legal=None,
        numero_ato=None,
        ano_ato=None,
        status="ATIVO"
    ):

        conn = Banco.conectar()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE ncm
               SET descricao=?,
                   cest=?,
                   ex_tipi=?,
                   data_inicio=?,
                   data_fim=?,
                   ato_legal=?,
                   numero_ato=?,
                   ano_ato=?,
                   status=?,
                   atualizado_em=CURRENT_TIMESTAMP
             WHERE ncm=?
        """, (
            descricao,
            cest,
            ex_tipi,
            data_inicio,
            data_fim,
            ato_legal,
            numero_ato,
            ano_ato,
            status,
            ncm
        ))

        conn.commit()
        conn.close()

    @staticmethod
    def salvar(
        ncm,
        descricao,
        cest="",
        ex_tipi="",
        data_inicio=None,
        data_fim=None,
        ato_legal=None,
        numero_ato=None,
        ano_ato=None,
        status="ATIVO"
    ):

        registro = NCMRepository.buscar_por_ncm(ncm)

        # ------------------------------------------------------
        # NCM inexistente
        # ------------------------------------------------------

        if registro is None:

            NCMRepository.inserir(
                ncm=ncm,
                descricao=descricao,
                cest=cest,
                ex_tipi=ex_tipi,
                data_inicio=data_inicio,
                data_fim=data_fim,
                ato_legal=ato_legal,
                numero_ato=numero_ato,
                ano_ato=ano_ato,
                status=status
            )

            return "INSERIDO"

        # ------------------------------------------------------
        # Verifica se houve alteração
        # ------------------------------------------------------

        alterou = False

        if (registro["descricao"] or "") != (descricao or ""):
            alterou = True

        elif (registro["cest"] or "") != (cest or ""):
            alterou = True

        elif (registro["ex_tipi"] or "") != (ex_tipi or ""):
            alterou = True

        elif registro["data_inicio"] != data_inicio:
            alterou = True

        elif registro["data_fim"] != data_fim:
            alterou = True

        elif (registro["ato_legal"] or "") != (ato_legal or ""):
            alterou = True

        elif (registro["numero_ato"] or "") != (numero_ato or ""):
            alterou = True

        elif str(registro["ano_ato"] or "") != str(ano_ato or ""):
            alterou = True

        elif (registro["status"] or "") != (status or ""):
            alterou = True

        # ------------------------------------------------------
        # Atualiza apenas se necessário
        # ------------------------------------------------------

        if alterou:

            NCMRepository.atualizar(
                ncm=ncm,
                descricao=descricao,
                cest=cest,
                ex_tipi=ex_tipi,
                data_inicio=data_inicio,
                data_fim=data_fim,
                ato_legal=ato_legal,
                numero_ato=numero_ato,
                ano_ato=ano_ato,
                status=status
            )

            return "ATUALIZADO"

        return "SEM_ALTERACAO"

    @staticmethod
    def remover(ncm):

        conn = Banco.conectar()
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM ncm
            WHERE ncm = ?
        """, (ncm,))

        conn.commit()
        conn.close()
    
    # ==========================================================
    # TRIBUTAÇÃO ATUAL
    # ==========================================================

    @staticmethod
    def buscar_tributacao(ncm):

        conn = Banco.conectar()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                n.ncm,
                n.descricao,
                n.cest,

                t.uf,
                t.regime,
                t.operacao,

                t.pis_cst,
                t.cofins_cst,

                t.aliquota_pis,
                t.aliquota_cofins,

                t.icms,
                t.icms_st,
                t.fcp,
                t.ipi,

                t.beneficio,
                t.vigencia_inicio,
                t.vigencia_fim

            FROM tributacao_atual t

            INNER JOIN ncm n
                ON n.ncm = t.ncm

            WHERE t.ncm = ?
        """, (ncm,))

        resultado = cursor.fetchone()

        conn.close()

        return resultado

    @staticmethod
    def inserir_tributacao_atual(
        ncm,
        uf,
        regime,
        operacao,
        pis_cst,
        cofins_cst,
        aliquota_pis,
        aliquota_cofins,
        icms,
        icms_st,
        fcp,
        ipi,
        beneficio=None,
        vigencia_inicio=None,
        vigencia_fim=None
    ):

        conn = Banco.conectar()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO tributacao_atual
            (
                ncm,
                uf,
                regime,
                operacao,
                pis_cst,
                cofins_cst,
                aliquota_pis,
                aliquota_cofins,
                icms,
                icms_st,
                fcp,
                ipi,
                beneficio,
                vigencia_inicio,
                vigencia_fim
            )
            VALUES
            (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
        """, (
            ncm,
            uf,
            regime,
            operacao,
            pis_cst,
            cofins_cst,
            aliquota_pis,
            aliquota_cofins,
            icms,
            icms_st,
            fcp,
            ipi,
            beneficio,
            vigencia_inicio,
            vigencia_fim
        ))

        conn.commit()
        conn.close()

    @staticmethod
    def atualizar_tributacao_atual(
        ncm,
        uf,
        regime,
        operacao,
        pis_cst,
        cofins_cst,
        aliquota_pis,
        aliquota_cofins,
        icms,
        icms_st,
        fcp,
        ipi,
        beneficio=None,
        vigencia_inicio=None,
        vigencia_fim=None
    ):

        conn = Banco.conectar()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE tributacao_atual
               SET uf=?,
                   regime=?,
                   operacao=?,
                   pis_cst=?,
                   cofins_cst=?,
                   aliquota_pis=?,
                   aliquota_cofins=?,
                   icms=?,
                   icms_st=?,
                   fcp=?,
                   ipi=?,
                   beneficio=?,
                   vigencia_inicio=?,
                   vigencia_fim=?
             WHERE ncm=?
        """, (
            uf,
            regime,
            operacao,
            pis_cst,
            cofins_cst,
            aliquota_pis,
            aliquota_cofins,
            icms,
            icms_st,
            fcp,
            ipi,
            beneficio,
            vigencia_inicio,
            vigencia_fim,
            ncm
        ))

        conn.commit()
        conn.close()

    # ==========================================================
    # REFORMA TRIBUTÁRIA
    # ==========================================================

    @staticmethod
    def buscar_reforma(ncm):

        conn = Banco.conectar()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM tributacao_reforma
            WHERE ncm = ?
        """, (ncm,))

        resultado = cursor.fetchone()

        conn.close()

        return resultado

    @staticmethod
    def inserir_reforma(
        ncm,
        cclasstrib,
        ccredpres,
        cst_ibs,
        cst_cbs,
        aliquota_ibs,
        aliquota_cbs,
        imposto_seletivo,
        vigencia_inicio=None,
        vigencia_fim=None
    ):

        conn = Banco.conectar()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO tributacao_reforma
            (
                ncm,
                cclasstrib,
                ccredpres,
                cst_ibs,
                cst_cbs,
                aliquota_ibs,
                aliquota_cbs,
                imposto_seletivo,
                vigencia_inicio,
                vigencia_fim
            )
            VALUES
            (
                ?,?,?,?,?,?,?,?,?,?
            )
        """, (
            ncm,
            cclasstrib,
            ccredpres,
            cst_ibs,
            cst_cbs,
            aliquota_ibs,
            aliquota_cbs,
            imposto_seletivo,
            vigencia_inicio,
            vigencia_fim
        ))

        conn.commit()
        conn.close()

    @staticmethod
    def atualizar_reforma(
        ncm,
        cclasstrib,
        ccredpres,
        cst_ibs,
        cst_cbs,
        aliquota_ibs,
        aliquota_cbs,
        imposto_seletivo,
        vigencia_inicio=None,
        vigencia_fim=None
    ):

        conn = Banco.conectar()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE tributacao_reforma
               SET cclasstrib=?,
                   ccredpres=?,
                   cst_ibs=?,
                   cst_cbs=?,
                   aliquota_ibs=?,
                   aliquota_cbs=?,
                   imposto_seletivo=?,
                   vigencia_inicio=?,
                   vigencia_fim=?
             WHERE ncm=?
        """, (
            cclasstrib,
            ccredpres,
            cst_ibs,
            cst_cbs,
            aliquota_ibs,
            aliquota_cbs,
            imposto_seletivo,
            vigencia_inicio,
            vigencia_fim,
            ncm
        ))

        conn.commit()
        conn.close()

    @staticmethod
    def sincronizar_lote(registros):
        """Atualiza NCM e descrição em lote, preservando CEST e demais campos locais."""
        registros = [
            (str(item.get("ncm") or ""), str(item.get("descricao") or "").strip())
            for item in registros
            if len("".join(c for c in str(item.get("ncm") or "") if c.isdigit())) == 8
            and str(item.get("descricao") or "").strip()
        ]
        if not registros:
            return {"inseridos": 0, "atualizados": 0, "sem_alteracao": 0}

        conn = Banco.conectar()
        try:
            existentes = {
                str(linha["ncm"]): (str(linha["descricao"] or ""), str(linha["status"] or ""))
                for linha in conn.execute("SELECT ncm, descricao, status FROM ncm").fetchall()
            }
            inseridos = atualizados = sem_alteracao = 0
            for ncm, descricao in registros:
                anterior = existentes.get(ncm)
                if anterior is None:
                    inseridos += 1
                elif anterior[0] != descricao or anterior[1].upper() != "ATIVO":
                    atualizados += 1
                else:
                    sem_alteracao += 1

            conn.executemany(
                """
                INSERT INTO ncm(ncm, descricao, status, atualizado_em)
                VALUES (?, ?, 'ATIVO', CURRENT_TIMESTAMP)
                ON CONFLICT(ncm) DO UPDATE SET
                    descricao = excluded.descricao,
                    status = 'ATIVO',
                    atualizado_em = CURRENT_TIMESTAMP
                """,
                registros,
            )
            conn.commit()
            return {
                "inseridos": inseridos,
                "atualizados": atualizados,
                "sem_alteracao": sem_alteracao,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

