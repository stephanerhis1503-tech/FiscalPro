"""Robô FiscalPro: anexos do Gmail e links fiscais com validação de segurança."""

from .config import ConfiguracaoRoboEmail
from .servico import ResultadoProcessamento, RoboEmailService

__all__ = ["ConfiguracaoRoboEmail", "RoboEmailService", "ResultadoProcessamento"]
