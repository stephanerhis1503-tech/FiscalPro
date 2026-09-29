from dataclasses import dataclass


@dataclass
class Diagnostico:

    codigo: str

    titulo: str

    nota: str

    item: int

    gravidade: str

    problema: str

    causa: str

    correcao: str

    automatico: bool = False