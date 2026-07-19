from src.banco.conexao import Banco


class NCMRepository:

    @staticmethod
    def buscar_por_ncm(ncm):

        conn = Banco.conectar()

        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM ncm
            WHERE ncm=?
        """, (ncm,))

        resultado = cursor.fetchone()

        conn.close()

        return resultado


    @staticmethod
    def inserir(ncm, descricao, cest=""):

        conn = Banco.conectar()

        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO ncm
            (
                ncm,
                descricao,
                cest
            )
            VALUES
            (
                ?,?,?
            )
        """, (
            ncm,
            descricao,
            cest
        ))

        conn.commit()

        conn.close()
        
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
                t.ipi

            FROM tributacao_atual t

            INNER JOIN ncm n
                ON n.ncm = t.ncm

         WHERE t.ncm = ?
    """, (ncm,))

        resultado = cursor.fetchone()

        conn.close()

        return resultado

        @staticmethod
        def buscar_reforma(ncm):

            conn = Banco.conectar()
            cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM tributacao_reforma
            WHERE ncm=?
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
        ipi
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
                ipi
            )
            VALUES
            (
                ?,?,?,?,?,?,?,?,?,?,?,?
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
            ipi
        ))

        conn.commit()
        conn.close()

    @staticmethod
    def inserir_reforma(
        ncm,
        cclasstrib,
        ccredpres,
        cst_ibs,
        cst_cbs,
        aliquota_ibs,
        aliquota_cbs,
        imposto_seletivo
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
                imposto_seletivo
            )
            VALUES
            (
                ?,?,?,?,?,?,?,?
            )
        """, (
            ncm,
            cclasstrib,
            ccredpres,
            cst_ibs,
            cst_cbs,
            aliquota_ibs,
            aliquota_cbs,
            imposto_seletivo
        ))

        conn.commit()
        conn.close()