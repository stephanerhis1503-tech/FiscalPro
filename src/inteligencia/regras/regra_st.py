"""Regra de ICMS-ST integrada ao Motor ICMS/MG — Sprint 16.6."""

from src.services.icms_st_mg_service import ICMSSTMGService


class RegraST:

    @staticmethod
    def aplicar(ficha, consulta):
        if ficha is None or getattr(ficha, "icms_mg_st_status", ""):
            return ficha

        contexto = {
            "uf_origem": getattr(consulta, "uf_origem", ""),
            "uf_destino": getattr(consulta, "uf_destino", ""),
        }
        descricao_operacao = str(getattr(consulta, "descricao_produto", "") or "").strip()
        resultado = ICMSSTMGService.analisar(
            getattr(ficha, "ncm", getattr(consulta, "ncm", "")),
            contexto=contexto,
            descricao=descricao_operacao or getattr(ficha, "descricao", ""),
        )
        ficha.icms_mg_st_status = str(resultado.get("status") or "")
        ficha.icms_mg_st_confirmado = bool(resultado.get("confirmado"))
        ficha.icms_mg_cest = str(resultado.get("cest") or "")
        ficha.icms_mg_mva = float(resultado.get("mva_original") or 0.0)
        if resultado.get("confirmado"):
            ficha.icms_st = "SIM"
            if resultado.get("cest"):
                ficha.cest = "".join(c for c in str(resultado["cest"]) if c.isdigit())
        return ficha
