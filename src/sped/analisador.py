from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AlertaEstrutural:
    nivel: str
    mensagem: str


class AnalisadorEstruturalSPED:
    """Validações estruturais seguras da primeira fase do Motor SPED."""

    def analisar(self, linhas: list[str], contagens: dict[str, int]) -> list[AlertaEstrutural]:
        alertas: list[AlertaEstrutural] = []

        if not linhas:
            return [AlertaEstrutural("ERRO", "O arquivo está vazio.")]
        if contagens.get("0000", 0) == 0:
            alertas.append(AlertaEstrutural("ERRO", "Registro 0000 não encontrado."))
        elif contagens.get("0000", 0) > 1:
            alertas.append(AlertaEstrutural("ERRO", "Existe mais de um registro 0000."))
        if contagens.get("9999", 0) == 0:
            alertas.append(AlertaEstrutural("ALERTA", "Registro 9999 não encontrado."))

        linhas_invalidas = sum(
            1 for linha in linhas if linha.strip() and not linha.lstrip().startswith("|")
        )
        if linhas_invalidas:
            alertas.append(
                AlertaEstrutural(
                    "ALERTA", f"Foram encontradas {linhas_invalidas} linhas fora do padrão |REG|."
                )
            )

        return alertas
