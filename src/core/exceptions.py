"""
=========================================
Exceções do FiscalPro
=========================================
"""


class FiscalProError(Exception):
    """Exceção base do sistema."""


class SPEDInvalidoError(FiscalProError):
    """Arquivo SPED inválido."""


class XMLInvalidoError(FiscalProError):
    """XML inválido."""


class ArquivoNaoEncontradoError(FiscalProError):
    """Arquivo não encontrado."""