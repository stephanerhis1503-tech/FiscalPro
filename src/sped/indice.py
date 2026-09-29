from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .leitor import LeitorSPEDUnificado


@dataclass(frozen=True, slots=True)
class ReferenciaRegistro:
    numero_linha: int
    indice_lista: int


class IndiceSPED:
    """Índice rápido dos registros existentes no arquivo."""

    def __init__(self) -> None:
        self._dados: dict[str, list[ReferenciaRegistro]] = {}

    def construir(self, linhas: list[str]) -> "IndiceSPED":
        temporario: dict[str, list[ReferenciaRegistro]] = defaultdict(list)
        for numero_linha, codigo, _ in LeitorSPEDUnificado.iterar_registros(linhas):
            temporario[codigo].append(
                ReferenciaRegistro(numero_linha=numero_linha, indice_lista=numero_linha - 1)
            )
        self._dados = dict(temporario)
        return self

    def codigos(self) -> list[str]:
        return sorted(self._dados)

    def referencias(self, codigo: str) -> list[ReferenciaRegistro]:
        return list(self._dados.get(codigo.upper(), []))

    def quantidade(self, codigo: str) -> int:
        return len(self._dados.get(codigo.upper(), []))

    def contagens(self) -> dict[str, int]:
        return {codigo: len(refs) for codigo, refs in self._dados.items()}
