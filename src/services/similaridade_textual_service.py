"""Reaproveitamento limitado de comparacoes de texto, sem cache fiscal.

A chave contem os dois textos completos e ordenados. NCM, CEST, MVA,
operacao e decisoes de enquadramento nao sao armazenados aqui. Uma mudanca
no texto oficial ou comercial produz uma nova chave automaticamente.
"""

from difflib import SequenceMatcher
from functools import lru_cache


# Limita tanto o numero de entradas quanto o tamanho dos textos retidos.
# Entradas maiores continuam aceitas, mas nao permanecem no cache.
_MAX_ENTRADAS = 8192
_MAX_CARACTERES = 4096


@lru_cache(maxsize=_MAX_ENTRADAS)
def _similaridade_em_cache(texto_produto: str, texto_oficial: str) -> float:
    # Preservar a ordem e os defaults do algoritmo usado anteriormente.
    return SequenceMatcher(None, texto_produto, texto_oficial).ratio()


def similaridade_textual(texto_produto: str, texto_oficial: str) -> float:
    """Retorna exatamente a mesma proporcao do SequenceMatcher anterior."""
    if len(texto_produto) + len(texto_oficial) > _MAX_CARACTERES:
        return SequenceMatcher(None, texto_produto, texto_oficial).ratio()
    return _similaridade_em_cache(texto_produto, texto_oficial)
