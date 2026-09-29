"""Integração do Motor ICMS/MG ao Motor Tributário — Sprint 16.6."""

from src.services.icms_mg_nacional_service import ICMSMGNacionalService


class RegraICMS:

    @staticmethod
    def aplicar(ficha, consulta):
        if ficha is None:
            return ficha

        contexto = {
            "uf_origem": getattr(consulta, "uf_origem", ""),
            "uf_destino": getattr(consulta, "uf_destino", ""),
            "regime": getattr(consulta, "regime", ""),
            "operacao": getattr(consulta, "operacao", ""),
            "finalidade": getattr(consulta, "finalidade", ""),
            "consumidor_final": getattr(consulta, "consumidor_final", False),
            "data_operacao": getattr(consulta, "data_operacao", ""),
            "perfil_remetente": getattr(consulta, "perfil_remetente", ""),
            "mercadoria_importada": getattr(consulta, "mercadoria_importada", False),
            "excecao_aliquota_importacao": getattr(
                consulta, "excecao_aliquota_importacao", False
            ),
        }
        descricao_operacao = str(getattr(consulta, "descricao_produto", "") or "").strip()
        resultado = ICMSMGNacionalService.analisar(
            getattr(ficha, "ncm", getattr(consulta, "ncm", "")),
            contexto=contexto,
            descricao=descricao_operacao or getattr(ficha, "descricao", ""),
        )
        return ICMSMGNacionalService.aplicar_ao_ficha(ficha, resultado)
