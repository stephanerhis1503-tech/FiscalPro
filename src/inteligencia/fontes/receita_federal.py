from .fonte_base import FonteBase
from src.inteligencia.base_oficial.repositorio import BaseOficialRepository
from src.inteligencia.ficha_tributaria import FichaTributaria
from src.services.base_ncm_nacional_service import BaseNCMNacionalService


class ReceitaFederal(FonteBase):
    """Consulta a NCM e a TIPI oficiais já sincronizadas no banco local."""

    def pesquisar(self, consulta):
        BaseNCMNacionalService.garantir_instalada()

        ncm = "".join(c for c in str(consulta.ncm or "") if c.isdigit())
        cadastro = BaseOficialRepository.buscar_ncm_oficial(ncm)
        if not cadastro:
            return None

        registros_tipi = BaseOficialRepository.buscar_tipi(ncm)
        principal = next(
            (
                item
                for item in registros_tipi
                if not str(item.get("ex_tipi") or "").strip()
            ),
            None,
        )
        if principal is None and len(registros_tipi) == 1:
            principal = registros_tipi[0]

        descricao = (
            cadastro.get("descricao_completa")
            or cadastro.get("descricao")
            or ""
        )
        ficha = FichaTributaria(
            ncm=ncm,
            descricao=str(descricao),
            status="NCM_OFICIAL_TIPI",
            fontes=[
                "Receita Federal / Siscomex — NCM",
                "Receita Federal — TIPI",
            ],
            base_legal=[
                "Tabela NCM oficial vigente",
                "TIPI oficial vigente",
            ],
            confiabilidade=1.0,
            observacoes=(
                "NCM e IPI localizados em base oficial. ICMS, ICMS-ST, PIS/Cofins, "
                "benefícios e CSTs dependem do produto, da operação, da UF, do regime "
                "e da vigência e continuam sujeitos à validação específica."
            ),
        )

        if principal and principal.get("aliquota") is not None:
            ficha.ipi = float(principal["aliquota"])
        if len(registros_tipi) > 1:
            ficha.observacoes += (
                f" Este NCM possui {len(registros_tipi) - 1} EX TIPI; confirme a "
                "descrição exata do produto antes de aplicar a alíquota."
            )
        return ficha
