from src.repositorios.tributacao_repository import TributacaoRepository


class MotorDecisao:

    """
    Motor responsável por decidir toda a tributação do produto.

    Toda a inteligência do FiscalPro passará por aqui.
    """

    def decidir(
        self,
        ncm,
        uf="",
        regime="",
        operacao="",
        cfop="",
        finalidade=""
    ):

        ficha = TributacaoRepository.buscar_ficha(ncm)

        if ficha is None:

            return {

                "sucesso": False,

                "mensagem": "NCM não cadastrado.",

                "ficha": None,

                "erros": [
                    "NCM inexistente na base."
                ]

            }

        inconsistencias = []

        # ---------------------------------------------------
        # Verificações básicas
        # ---------------------------------------------------

        if ficha.status == "SEM_TRIBUTACAO":

            inconsistencias.append(
                "NCM cadastrado, porém sem tributação."
            )

        if uf:

            ficha.uf = uf

        if regime:

            ficha.regime = regime

        if operacao:

            ficha.operacao = operacao

        resultado = {

            "sucesso": True,

            "ficha": ficha,

            "pis_cst": ficha.pis_cst,

            "cofins_cst": ficha.cofins_cst,

            "aliquota_pis": ficha.aliquota_pis,

            "aliquota_cofins": ficha.aliquota_cofins,

            "icms": ficha.icms,

            "icms_st": ficha.icms_st,

            "ipi": ficha.ipi,

            "fcp": ficha.fcp,

            "inconsistencias": inconsistencias

        }

        return resultado