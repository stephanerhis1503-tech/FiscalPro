from src.repositorios.ncm_repository import NCMRepository
from src.repositorios.tributacao_base_repository import TributacaoBaseRepository
from src.inteligencia.ficha_tributaria import FichaTributaria
from src.inteligencia.base_oficial.repositorio import BaseOficialRepository
from src.services.base_ncm_nacional_service import BaseNCMNacionalService


class TributacaoRepository:

    @staticmethod
    def _ncm_limpo(ncm):
        return "".join(c for c in str(ncm or "") if c.isdigit())

    @staticmethod
    def _aplicar_reforma(ficha, ncm):
        """Preenche IBS/CBS usando cadastro específico ou cenário-padrão de 2026."""
        reforma = NCMRepository.buscar_reforma(ncm)

        if reforma:
            ficha.cclasstrib = reforma["cclasstrib"] or ""
            ficha.ccredpres = reforma["ccredpres"] or ""
            ficha.cst_ibs = reforma["cst_ibs"] or ""
            ficha.cst_cbs = reforma["cst_cbs"] or ""
            ficha.aliquota_ibs = float(reforma["aliquota_ibs"] or 0)
            ficha.aliquota_cbs = float(reforma["aliquota_cbs"] or 0)
            ficha.imposto_seletivo = reforma["imposto_seletivo"] or "NÃO"
            ficha.reforma_status = "CADASTRO ESPECÍFICO"
            ficha.reforma_observacoes = (
                "Enquadramento da Reforma Tributária localizado na base do FiscalPro. "
                "Validar a operação, o destinatário e a vigência antes da emissão."
            )
            return ficha

        # Cenário geral de testes de 2026 para operação regular integralmente tributada.
        # Não substitui o enquadramento específico por produto/operação.
        ficha.cclasstrib = ficha.cclasstrib or "000001"
        ficha.ccredpres = ficha.ccredpres or "NÃO"
        ficha.cst_ibs = ficha.cst_ibs or "000"
        ficha.cst_cbs = ficha.cst_cbs or "000"
        ficha.aliquota_ibs = ficha.aliquota_ibs or 0.10
        ficha.aliquota_cbs = ficha.aliquota_cbs or 0.90
        ficha.imposto_seletivo = ficha.imposto_seletivo or "NÃO IDENTIFICADO"
        ficha.reforma_status = "CENÁRIO PADRÃO 2026"
        ficha.reforma_observacoes = (
            "Alíquota-teste de 2026: IBS 0,10% e CBS 0,90%. "
            "CST 000 e cClassTrib 000001 representam tributação integral padrão. "
            "Produtos com redução, alíquota zero, imunidade, regime específico ou "
            "Imposto Seletivo precisam de cadastro próprio."
        )
        return ficha

    @staticmethod
    def buscar_ficha(ncm):
        ncm = TributacaoRepository._ncm_limpo(ncm)
        BaseNCMNacionalService.garantir_instalada()

        cadastro = NCMRepository.buscar_por_ncm(ncm)
        cadastro_oficial = BaseOficialRepository.buscar_ncm_oficial(ncm)

        if cadastro is None and cadastro_oficial is None:
            return None

        descricao_oficial = ""
        if cadastro_oficial:
            descricao_oficial = (
                cadastro_oficial.get("descricao_completa")
                or cadastro_oficial.get("descricao")
                or ""
            )

        ficha = FichaTributaria(
            ncm=ncm,
            descricao=(
                descricao_oficial
                or (cadastro["descricao"] if cadastro is not None else "")
                or ""
            ),
            cest=(cadastro["cest"] if cadastro is not None else "") or "",
            status="CADASTRO" if cadastro is not None else "NCM_OFICIAL"
        )

        # 1) Base tributária específica/manual, quando existir.
        tributacao = NCMRepository.buscar_tributacao(ncm)
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
            ficha.fontes = ["Base tributária FiscalPro"]
            return TributacaoRepository._aplicar_reforma(ficha, ncm)

        # 2) Base de produtos importada do Digisat.
        perfil, total, variacoes = TributacaoBaseRepository.buscar_perfil_predominante(ncm)
        if perfil:
            ficha.cest = perfil["cest"] or ficha.cest
            ficha.cfop = perfil["cfop"] or ""
            ficha.cst_icms = perfil["cst_icms"] or ""
            ficha.icms = float(perfil["icms"] or 0)
            ficha.icms_st = perfil["icms_st"] or ""
            ficha.fcp = float(perfil["fcp"] or 0)
            ficha.pis_cst = perfil["cst_pis"] or ""
            ficha.aliquota_pis = float(perfil["aliquota_pis"] or 0)
            ficha.cofins_cst = perfil["cst_cofins"] or ""
            ficha.aliquota_cofins = float(perfil["aliquota_cofins"] or 0)
            ficha.cst_ipi = perfil["cst_ipi"] or ""
            ficha.ipi = float(perfil["ipi"] or 0)
            ficha.aliquota_ibs = float(perfil["ibs"] or 0)
            ficha.aliquota_cbs = float(perfil["cbs"] or 0)
            ficha.cclasstrib = perfil["classificacao"] or ""
            ficha.fontes = [perfil["fonte"] or "Base de produtos Digisat"]
            ficha.confiabilidade = float(perfil["confiabilidade"] or 0)
            ficha.quantidade_produtos = total
            ficha.quantidade_variacoes = variacoes
            ficha.status = "BASE_DIGISAT"
            ficha.observacoes = (
                f"Perfil predominante entre {total} produto(s) deste NCM. "
                f"Foram encontradas {variacoes} variação(ões) tributária(s). "
                "Confirme a tributação conforme descrição, operação e legislação vigente."
            )
            return TributacaoRepository._aplicar_reforma(ficha, ncm)

        registros_tipi = BaseOficialRepository.buscar_tipi(ncm)
        ipi_principal = next(
            (
                item for item in registros_tipi
                if not str(item.get("ex_tipi") or "").strip()
            ),
            None,
        )
        if ipi_principal is None and len(registros_tipi) == 1:
            ipi_principal = registros_tipi[0]
        if ipi_principal and ipi_principal.get("aliquota") is not None:
            ficha.ipi = float(ipi_principal["aliquota"])

        ficha.status = "NCM_OFICIAL_SEM_TRIBUTACAO"
        ficha.fontes = [
            "Receita Federal / Siscomex — NCM",
            "Receita Federal — TIPI",
        ]
        ficha.confiabilidade = 1.0
        ficha.observacoes = (
            "NCM e IPI confirmados em base oficial. A tributação completa ainda "
            "depende da descrição do produto, regime, operação, UF e vigência. "
            "O FiscalPro não preenche ICMS, PIS/Cofins ou CSTs por aproximação."
        )
        if len(registros_tipi) > 1:
            ficha.observacoes += (
                f" Existem {len(registros_tipi) - 1} EX TIPI para este NCM; "
                "confirme o enquadramento do produto."
            )
        return TributacaoRepository._aplicar_reforma(ficha, ncm)
