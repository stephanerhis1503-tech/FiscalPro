"""Simulador Tributário do FiscalPro."""

from .motor_simulador import (
    EntradaSimulacao,
    LinhaCalculo,
    MotorSimuladorTributario,
    ResultadoSimulacao,
)
from .historico import HistoricoSimuladorRepository
from .exportadores import ExportadorSimulacao
from .tabela_difal import aliquotas_automaticas, aliquota_interna_destino, aliquota_interestadual

__all__ = [
    "EntradaSimulacao",
    "LinhaCalculo",
    "MotorSimuladorTributario",
    "ResultadoSimulacao",
    "HistoricoSimuladorRepository",
    "ExportadorSimulacao",
    "aliquotas_automaticas",
    "aliquota_interna_destino",
    "aliquota_interestadual",
]
