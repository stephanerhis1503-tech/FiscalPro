from src.inteligencia.base_oficial.repositorio import BaseOficialRepository
from src.inteligencia.fontes.catalogo_fontes import CatalogoFontes


class Pesquisador:
    """Orquestra fontes oficiais e registra pendências para a camada de IA."""

    def buscar(self, consulta):
        for fonte in CatalogoFontes.listar():
            try:
                resultado = fonte.pesquisar(consulta)
            except Exception:
                resultado = None
            if resultado:
                return resultado

        BaseOficialRepository.enfileirar_pesquisa(
            consulta,
            "NCM/tributação não encontrados em base validada. Exige coleta oficial e revisão humana.",
        )
        return None
