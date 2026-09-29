from dataclasses import dataclass, field
from collections import Counter

from src.modelos.diagnostico import Diagnostico


@dataclass
class ResultadoAuditoria:

    registros: Counter = field(default_factory=Counter)

    diagnosticos: list[Diagnostico] = field(default_factory=list)

    avisos: list[str] = field(default_factory=list)

    erros: list[str] = field(default_factory=list)

    def adicionar_diagnostico(self, diagnostico):
        self.diagnosticos.append(diagnostico)

    @property
    def total_diagnosticos(self):
        return len(self.diagnosticos)

    @property
    def diagnosticos_criticos(self):
        return [
            d for d in self.diagnosticos
            if d.gravidade == "Alta"
        ]