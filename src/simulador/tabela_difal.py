"""Tabela e regras auxiliares do DIFAL automático.

Versão 18.2.13 — revisão em 25/09/2026.

A tabela contém a alíquota interna modal (regra geral) de cada UF, sem somar
FCP/FECOP. Alíquotas específicas por mercadoria, benefícios, reduções de base,
isenções e fundos estaduais continuam exigindo a regra própria do produto.

Mudanças relevantes preservadas por data para auditoria de períodos anteriores:
* AL: 19% até 31/03/2026 e 20,5% a partir de 01/04/2026;
* MA: 22% até 22/02/2025 e 23% a partir de 23/02/2025;
* RN: 18% até 19/03/2025 e 20% a partir de 20/03/2025;
* BA: 17% até 09/03/2016, 18% de 10/03/2016 a 21/03/2023, 19% de 22/03/2023 a 06/02/2024 e 20,5% desde 07/02/2024.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Tuple


FONTE_TABELA_DIFAL = (
    "Tabela modal revisada em 25/09/2026; BA Lei 7.014/96, art. 15, com redação da Lei 14.629/2023 (20,5% desde 07/02/2024); "
    "AL Lei 9.776/2025; MA Lei 12.426/2024; RN alíquota modal 20% desde 20/03/2025; "
    "demais UFs conforme base estadual já instalada no FiscalPro."
)
VERSAO_TABELA_DIFAL = "18.2.13 — 25/09/2026"

# Alíquotas internas modais vigentes em 25/09/2026, sem FCP/FECOP.
ALIQUOTAS_INTERNAS: Dict[str, Decimal] = {
    "AC": Decimal("19"),
    "AL": Decimal("20.5"),
    "AM": Decimal("20"),
    "AP": Decimal("18"),
    "BA": Decimal("20.5"),
    "CE": Decimal("20"),
    "DF": Decimal("20"),
    "ES": Decimal("17"),
    "GO": Decimal("19"),
    "MA": Decimal("23"),
    "MT": Decimal("17"),
    "MS": Decimal("17"),
    "MG": Decimal("18"),
    "PA": Decimal("19"),
    "PB": Decimal("20"),
    "PR": Decimal("19.5"),
    "PE": Decimal("20.5"),
    "PI": Decimal("22.5"),
    "RN": Decimal("20"),
    "RS": Decimal("17"),
    "RJ": Decimal("20"),
    "RO": Decimal("19.5"),
    "RR": Decimal("20"),
    "SC": Decimal("17"),
    "SP": Decimal("18"),
    "SE": Decimal("19"),
    "TO": Decimal("20"),
}

_UFS_SUL_SUDESTE = {"ES", "MG", "PR", "RJ", "RS", "SC", "SP"}
_UFS_DESTINO_SETE = {
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
    "MS", "PA", "PB", "PE", "PI", "RN", "RO", "RR", "SE", "TO",
}

# Histórico apenas das alterações que impactam a tabela anterior instalada.
# Cada tupla = (data inicial inclusiva, alíquota modal).
_HISTORICO_MODAL: dict[str, tuple[tuple[date, Decimal], ...]] = {
    "BA": (
        (date.min, Decimal("17")),
        (date(2016, 3, 10), Decimal("18")),
        (date(2023, 3, 22), Decimal("19")),
        (date(2024, 2, 7), Decimal("20.5")),
    ),
    "AL": (
        (date.min, Decimal("19")),
        (date(2026, 4, 1), Decimal("20.5")),
    ),
    "MA": (
        (date.min, Decimal("22")),
        (date(2025, 2, 23), Decimal("23")),
    ),
    "RN": (
        (date.min, Decimal("18")),
        (date(2025, 3, 20), Decimal("20")),
    ),
}


def _uf(valor: str) -> str:
    uf = str(valor or "").strip().upper()
    if uf == "SO":
        uf = "RO"
    if uf not in ALIQUOTAS_INTERNAS:
        raise ValueError(f"UF inválida ou sem alíquota interna na tabela DIFAL: {valor!r}.")
    return uf


def _data(valor: Any) -> date | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d%m%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def aliquota_interna_destino(uf_destino: str, data_referencia: Any = None) -> Decimal:
    """Retorna a alíquota modal da UF na data informada.

    A data é usada para não aplicar alíquota de 2026 em SPEDs de períodos
    anteriores nas UFs que tiveram alteração recente.
    """
    uf = _uf(uf_destino)
    data_ref = _data(data_referencia)
    historico = _HISTORICO_MODAL.get(uf)
    if not historico or data_ref is None:
        return ALIQUOTAS_INTERNAS[uf]
    aliquota = historico[0][1]
    for inicio, valor in historico:
        if data_ref >= inicio:
            aliquota = valor
        else:
            break
    return aliquota


def aliquota_interestadual(
    uf_origem: str,
    uf_destino: str,
    mercadoria_importada: bool = False,
) -> Decimal:
    """Calcula a alíquota interestadual padrão de 4%, 7% ou 12%."""
    origem = _uf(uf_origem)
    destino = _uf(uf_destino)
    if origem == destino:
        return Decimal("0")
    if mercadoria_importada:
        return Decimal("4")
    if origem in _UFS_SUL_SUDESTE and destino in _UFS_DESTINO_SETE:
        return Decimal("7")
    return Decimal("12")


def aliquotas_automaticas(
    uf_origem: str,
    uf_destino: str,
    mercadoria_importada: bool = False,
    data_referencia: Any = None,
) -> Tuple[Decimal, Decimal]:
    return (
        aliquota_interna_destino(uf_destino, data_referencia),
        aliquota_interestadual(uf_origem, uf_destino, mercadoria_importada),
    )


__all__ = [
    "ALIQUOTAS_INTERNAS",
    "FONTE_TABELA_DIFAL",
    "VERSAO_TABELA_DIFAL",
    "aliquota_interna_destino",
    "aliquota_interestadual",
    "aliquotas_automaticas",
]
