"""Indicadores independentes de segurança tributária da Ficha Inteligente.

Sprint 16.7.0

Cada tributo possui um nível próprio de confirmação. O enquadramento de
ICMS-ST pode estar confirmado mesmo quando a alíquota do ICMS próprio ainda é
condicional, e nenhum desses resultados deve ser confundido com a pontuação
geral do parecer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class IndicadorSeguranca:
    campo: str
    resultado: str
    observacao: str


class IndicadorSegurancaTributaria:
    """Monta indicadores específicos sem misturar tributos diferentes."""

    @staticmethod
    def _percentual(valor: Any, padrao: float = 0.0) -> float:
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            numero = padrao
        return max(0.0, min(100.0, numero))

    @staticmethod
    def _nivel(percentual: float) -> str:
        if percentual >= 90:
            return "ALTA"
        if percentual >= 70:
            return "BOA"
        if percentual >= 50:
            return "MÉDIA"
        return "BAIXA"

    @staticmethod
    def _texto_percentual(valor: float) -> str:
        return f"{valor:.0f}%"

    @classmethod
    def piscofins(cls, resultado_oficial: Mapping[str, Any] | None) -> IndicadorSeguranca:
        resultado = dict(resultado_oficial or {})
        confirmado = bool(resultado.get("confirmado"))

        if confirmado:
            return IndicadorSeguranca(
                campo="Segurança PIS/COFINS",
                resultado="100% — CONFIRMADA",
                observacao=(
                    "Confirmação específica do enquadramento de PIS/COFINS pela fonte oficial. "
                    "Não depende da pontuação geral dos demais tributos."
                ),
            )

        confiabilidade = cls._percentual(
            resultado.get("confiabilidade", resultado.get("seguranca", 0.0))
        )
        status = str(resultado.get("status") or "").strip().upper()
        exige_revisao = bool(resultado.get("exige_revisao", True))

        if confiabilidade > 0:
            sufixo = "REVISAR" if exige_revisao else cls._nivel(confiabilidade)
            texto = f"{confiabilidade:.0f}% — {sufixo}"
        elif status:
            texto = "REVISÃO NECESSÁRIA"
        else:
            texto = "NÃO ANALISADA"

        observacao = str(resultado.get("observacao") or "").strip()
        if not observacao:
            observacao = (
                "O enquadramento de PIS/COFINS ainda não possui confirmação automática "
                "para este produto e contexto."
            )

        return IndicadorSeguranca(
            campo="Segurança PIS/COFINS",
            resultado=texto,
            observacao=observacao,
        )

    @classmethod
    def icms_proprio_uf(
        cls, resultado_oficial: Mapping[str, Any] | None, uf: str = "MG"
    ) -> IndicadorSeguranca:
        """Indicador genérico da alíquota de ICMS da operação para a UF consultada."""
        resultado = dict(resultado_oficial or {})
        uf = str(uf or "MG").strip().upper() or "MG"
        aliquota = resultado.get("aliquota_operacao", resultado.get("aliquota_nominal"))
        confirmado = bool(resultado.get("aliquota_operacao_confirmada", resultado.get("aliquota_confirmada")))
        confiabilidade = cls._percentual(resultado.get("confiabilidade_aliquota", 0.0))

        if confirmado:
            texto = f"{cls._texto_percentual(confiabilidade or 100.0)} — CONFIRMADA"
        elif aliquota is not None:
            texto = f"{cls._texto_percentual(confiabilidade)} — CONDICIONAL"
        else:
            texto = "NÃO ANALISADA"

        status = str(resultado.get("aliquota_operacao_status", resultado.get("aliquota_status", "")) or "").strip()
        fundamento = str(resultado.get("fundamento_aliquota") or "").strip()
        detalhes = [x for x in (status, fundamento) if x]
        if not detalhes:
            detalhes.append("Informe origem e destino para analisar a alíquota do ICMS da operação.")
        return IndicadorSeguranca(
            campo=f"Segurança ICMS próprio/{uf}",
            resultado=texto,
            observacao="  •  ".join(detalhes),
        )

    @classmethod
    def icms_st_uf(
        cls, resultado_oficial: Mapping[str, Any] | None, uf: str = "MG"
    ) -> IndicadorSeguranca:
        """Indicador genérico do enquadramento ICMS-ST da UF consultada."""
        resultado = dict(resultado_oficial or {})
        uf = str(uf or "MG").strip().upper() or "MG"
        status = str(resultado.get("st_status", resultado.get("status", "")) or "").strip()
        confirmado = bool(resultado.get("st_confirmado", resultado.get("confirmado")))
        decisao = bool(resultado.get("st_decisao_confirmada", resultado.get("decisao_confirmada", confirmado)))
        confiabilidade = cls._percentual(resultado.get("confiabilidade_st", resultado.get("confiabilidade", 0.0)))
        cest = str(resultado.get("cest") or "").strip()
        segmento = str(resultado.get("segmento_st", resultado.get("segmento", "")) or "").strip()
        mva = resultado.get("mva_aplicada", resultado.get("mva_original"))

        decisao_st = str(resultado.get("decisao_st") or "").strip().upper()
        nao_aplicavel = bool(resultado.get("nao_aplicavel")) or decisao_st == "NAO"

        if nao_aplicavel and status:
            texto = "100% — NÃO APLICÁVEL"
        elif confirmado and decisao:
            texto = f"{cls._texto_percentual(confiabilidade or 100.0)} — CONFIRMADA"
        elif status and decisao:
            texto = f"{cls._texto_percentual(confiabilidade or 80.0)} — DECISÃO ESTRUTURADA"
        elif status:
            texto = "REVISÃO NECESSÁRIA"
        else:
            texto = "NÃO ANALISADA"

        detalhes = [status] if status else []
        if cest:
            detalhes.append(f"CEST {cest}")
        if mva is not None:
            try:
                detalhes.append(f"MVA {float(mva):.2f}%".replace(".", ","))
            except (TypeError, ValueError):
                pass
        if segmento:
            detalhes.append(segmento)
        if not detalhes:
            detalhes.append("Não há enquadramento ST estruturado para este contexto.")
        return IndicadorSeguranca(
            campo=f"Segurança ICMS-ST/{uf}",
            resultado=texto,
            observacao="  •  ".join(detalhes),
        )

    @classmethod
    def icms_proprio_mg(
        cls, resultado_oficial: Mapping[str, Any] | None
    ) -> IndicadorSeguranca:
        """Indica somente a confirmação da alíquota nominal do ICMS próprio."""

        resultado = dict(resultado_oficial or {})
        aliquota = resultado.get("aliquota_nominal")
        confirmado = bool(resultado.get("aliquota_confirmada"))
        confiabilidade = cls._percentual(resultado.get("confiabilidade_aliquota", 0.0))

        if confirmado:
            percentual = confiabilidade or 100.0
            texto = f"{cls._texto_percentual(percentual)} — CONFIRMADA"
        elif aliquota is not None:
            texto = f"{cls._texto_percentual(confiabilidade)} — CONDICIONAL"
        else:
            texto = "NÃO ANALISADA"

        observacoes = []
        status = str(resultado.get("aliquota_status") or "").strip()
        if status:
            observacoes.append(status)
        fundamento = str(resultado.get("fundamento_aliquota") or "").strip()
        if fundamento:
            observacoes.append(fundamento)
        if not observacoes:
            observacoes.append(
                "Informe origem e destino para analisar a alíquota nominal do ICMS da operação."
            )

        return IndicadorSeguranca(
            campo="Segurança ICMS próprio/MG",
            resultado=texto,
            observacao="  •  ".join(observacoes),
        )

    @classmethod
    def icms_st_mg(
        cls, resultado_oficial: Mapping[str, Any] | None
    ) -> IndicadorSeguranca:
        """Indica somente o enquadramento do produto e da operação no ICMS-ST/MG."""

        resultado = dict(resultado_oficial or {})
        status = str(resultado.get("st_status") or "").strip()
        status_normalizado = status.upper()
        confirmado = bool(resultado.get("st_confirmado"))
        exige_revisao = bool(resultado.get("st_exige_revisao", True))
        confiabilidade = cls._percentual(resultado.get("confiabilidade_st", 0.0))
        cest = str(resultado.get("cest") or "").strip()
        segmento = str(resultado.get("segmento_st") or "").strip()
        mva = resultado.get("mva_original")

        if "NÃO APLICÁVEL" in status_normalizado and not exige_revisao:
            texto = "100% — NÃO APLICÁVEL"
        elif confirmado and not exige_revisao:
            texto = f"{cls._texto_percentual(confiabilidade or 100.0)} — CONFIRMADA"
        elif confirmado:
            texto = f"{cls._texto_percentual(confiabilidade or 70.0)} — REVISAR DETALHES"
        elif status:
            texto = "REVISÃO NECESSÁRIA"
        else:
            texto = "NÃO ANALISADA"

        detalhes = []
        if status:
            detalhes.append(status)
        if cest:
            detalhes.append(f"CEST {cest}")
        if mva is not None:
            try:
                detalhes.append(f"MVA {float(mva):.2f}%".replace(".", ","))
            except (TypeError, ValueError):
                pass
        if segmento:
            detalhes.append(f"Segmento: {segmento}")
        aplicacao = str(resultado.get("aplicacao_st") or "").strip()
        if aplicacao:
            detalhes.append(aplicacao)
        observacao = str(resultado.get("observacao_st") or "").strip()
        if observacao and not detalhes:
            detalhes.append(observacao)
        if not detalhes:
            detalhes.append(
                "O enquadramento de ICMS-ST/MG ainda não foi confirmado para este produto e contexto."
            )

        return IndicadorSeguranca(
            campo="Segurança ICMS-ST/MG",
            resultado=texto,
            observacao="  •  ".join(detalhes),
        )

    @classmethod
    def icms_mg(cls, resultado_oficial: Mapping[str, Any] | None) -> IndicadorSeguranca:
        """Compatibilidade com integrações antigas do indicador combinado."""

        indicador = cls.icms_proprio_mg(resultado_oficial)
        return IndicadorSeguranca(
            campo="Segurança ICMS/MG",
            resultado=indicador.resultado,
            observacao=indicador.observacao,
        )

    @classmethod
    def geral(cls, parecer: Any) -> IndicadorSeguranca:
        percentual = cls._percentual(getattr(parecer, "confiabilidade", 0.0))
        nivel = str(getattr(parecer, "nivel_confiabilidade", "") or "").strip().upper()
        if not nivel:
            nivel = cls._nivel(percentual)

        return IndicadorSeguranca(
            campo="Segurança geral do parecer",
            resultado=f"{percentual:.0f}% — {nivel}",
            observacao=(
                "Indicador geral: considera também ICMS, ICMS-ST, IPI, benefícios, "
                "Reforma Tributária, aderência ao contexto e fontes cadastradas. "
                "Uma pontuação baixa aqui não invalida tributos confirmados individualmente."
            ),
        )
