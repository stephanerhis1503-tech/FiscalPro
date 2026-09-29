from .fonte_base import FonteBase


class Confaz(FonteBase):
    """Conector reservado para evidências de convênios e protocolos ICMS."""

    def pesquisar(self, consulta):
        # Conteúdo jurídico não deve ser convertido automaticamente em alíquota sem
        # identificar vigência, UF, operação, produto e adesão estadual.
        return None
