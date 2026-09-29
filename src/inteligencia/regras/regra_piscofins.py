"""Integração do motor nacional de PIS/Cofins com a Ficha Tributária."""

from __future__ import annotations

from typing import Any, Dict

from src.services.piscofins_nacional_service import PISCOFINSNacionalService


class RegraPISCOFINS:

    @staticmethod
    def _contexto(consulta: Any) -> Dict[str, Any]:
        return {
            "empresa": getattr(consulta, "empresa", ""),
            "regime": getattr(consulta, "regime", ""),
            "operacao": getattr(consulta, "operacao", ""),
            "finalidade": getattr(consulta, "finalidade", "Revenda"),
            "data_operacao": getattr(consulta, "data_operacao", ""),
        }

    @staticmethod
    def _possui_tributacao_especifica(ficha: Any) -> bool:
        return bool(
            str(getattr(ficha, "pis_cst", "") or "").strip()
            or str(getattr(ficha, "cofins_cst", "") or "").strip()
            or float(getattr(ficha, "aliquota_pis", 0.0) or 0.0) != 0.0
            or float(getattr(ficha, "aliquota_cofins", 0.0) or 0.0) != 0.0
        )

    @classmethod
    def aplicar(cls, ficha: Any, consulta: Any):
        """Aplica conclusão confirmada ou registra sugestão sem sobrescrever base local."""
        if ficha is None:
            return ficha

        if not str(getattr(ficha, "regime", "") or "").strip():
            ficha.regime = str(getattr(consulta, "regime", "") or "")
        if not str(getattr(ficha, "operacao", "") or "").strip():
            ficha.operacao = str(getattr(consulta, "operacao", "") or "")

        descricao_operacao = str(getattr(consulta, "descricao_produto", "") or "").strip()
        resultado = PISCOFINSNacionalService.analisar(
            ficha.ncm,
            contexto=cls._contexto(consulta),
            descricao=descricao_operacao or getattr(ficha, "descricao", ""),
            ex_tipi=getattr(consulta, "ex_tipi", ""),
        )

        ficha.piscofins_status = resultado.get("status") or ""
        ficha.piscofins_enquadramento = resultado.get("enquadramento") or ""
        ficha.piscofins_confirmado = bool(resultado.get("confirmado"))
        ficha.piscofins_exige_revisao = bool(resultado.get("exige_revisao", True))
        ficha.piscofins_fundamento = " — ".join(
            parte
            for parte in (
                resultado.get("fundamento"),
                resultado.get("artigo"),
            )
            if parte
        )
        ficha.piscofins_fonte = resultado.get("fonte_url") or ""
        ficha.piscofins_tabela_efd = resultado.get("tabela_efd") or ""
        ficha.piscofins_observacoes = resultado.get("observacao") or ""
        ficha.piscofins_confiabilidade = float(resultado.get("confiabilidade") or 0.0)
        ficha.piscofins_sugestao_cst_pis = resultado.get("sugestao_cst_pis") or ""
        ficha.piscofins_sugestao_aliquota_pis = float(
            resultado.get("sugestao_aliquota_pis") or 0.0
        )
        ficha.piscofins_sugestao_cst_cofins = (
            resultado.get("sugestao_cst_cofins") or ""
        )
        ficha.piscofins_sugestao_aliquota_cofins = float(
            resultado.get("sugestao_aliquota_cofins") or 0.0
        )

        if not resultado.get("confirmado"):
            return ficha

        cst_pis = str(resultado.get("cst_pis") or "")
        cst_cofins = str(resultado.get("cst_cofins") or "")
        aliquota_pis = float(resultado.get("aliquota_pis") or 0.0)
        aliquota_cofins = float(resultado.get("aliquota_cofins") or 0.0)

        if cls._possui_tributacao_especifica(ficha):
            diverge = (
                str(getattr(ficha, "pis_cst", "") or "") != cst_pis
                or str(getattr(ficha, "cofins_cst", "") or "") != cst_cofins
                or abs(float(getattr(ficha, "aliquota_pis", 0.0) or 0.0) - aliquota_pis)
                > 0.0001
                or abs(
                    float(getattr(ficha, "aliquota_cofins", 0.0) or 0.0)
                    - aliquota_cofins
                )
                > 0.0001
            )
            if diverge:
                ficha.piscofins_divergencia = True
                ficha.piscofins_observacoes = (
                    "DIVERGÊNCIA: a regra oficial confirmada não coincide com a base "
                    "tributária já cadastrada. O FiscalPro preservou o cadastro existente "
                    "para revisão humana. "
                    + ficha.piscofins_observacoes
                )
            return ficha

        ficha.pis_cst = cst_pis
        ficha.cofins_cst = cst_cofins
        ficha.aliquota_pis = aliquota_pis
        ficha.aliquota_cofins = aliquota_cofins
        ficha.piscofins_aplicado_automaticamente = True
        if ficha.piscofins_fundamento:
            fonte = f"PIS/COFINS: {ficha.piscofins_fundamento}"
            if fonte not in ficha.fontes:
                ficha.fontes.append(fonte)
        return ficha
