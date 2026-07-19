from src.repositorios.ncm_repository import NCMRepository
from src.inteligencia.ficha_tributaria import FichaTributaria


class TributacaoRepository:

    @staticmethod
    def buscar_ficha(ncm):

        cadastro = NCMRepository.buscar_por_ncm(ncm)

        if cadastro is None:
            return None

        tributacao = NCMRepository.buscar_tributacao(ncm)

        ficha = FichaTributaria(
            ncm=cadastro["ncm"],
            descricao=cadastro["descricao"] or "",
            cest=cadastro["cest"] or "",
            status="CADASTRO"
        )

        if tributacao:

            ficha.uf = tributacao["uf"] or ""
            ficha.regime = tributacao["regime"] or ""
            ficha.operacao = tributacao["operacao"] or ""

            ficha.pis_cst = tributacao["pis_cst"] or ""
            ficha.cofins_cst = tributacao["cofins_cst"] or ""

            ficha.aliquota_pis = float(tributacao["aliquota_pis"] or 0)
            ficha.aliquota_cofins = float(tributacao["aliquota_cofins"] or 0)

            ficha.icms = float(tributacao["icms"] or 0)
            ficha.icms_st = tributacao["icms_st"] or ""

            ficha.fcp = float(tributacao["fcp"] or 0)
            ficha.ipi = float(tributacao["ipi"] or 0)

            ficha.status = "COMPLETO"

        else:

            ficha.status = "SEM_TRIBUTACAO"

        return ficha