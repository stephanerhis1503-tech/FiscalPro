from src.banco.conexao import Banco


class ConsultaNCM:

    @staticmethod
    def buscar(ncm):

        conn = Banco.conectar()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                n.ncm,
                n.descricao,
                n.cest,

                ta.uf,
                ta.regime,
                ta.operacao,
                ta.pis_cst,
                ta.cofins_cst,
                ta.aliquota_pis,
                ta.aliquota_cofins,
                ta.icms,
                ta.icms_st,
                ta.fcp,
                ta.ipi,

                tr.cclasstrib,
                tr.ccredpres,
                tr.cst_ibs,
                tr.cst_cbs,
                tr.aliquota_ibs,
                tr.aliquota_cbs,
                tr.imposto_seletivo

            FROM ncm n

            LEFT JOIN tributacao_atual ta
                ON ta.ncm = n.ncm

            LEFT JOIN tributacao_reforma tr
                ON tr.ncm = n.ncm

            WHERE n.ncm = ?
        """, (ncm,))

        resultado = cursor.fetchone()

        conn.close()

        return resultado