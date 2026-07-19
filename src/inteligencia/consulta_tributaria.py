from dataclasses import dataclass


@dataclass
class ConsultaTributaria:
    ncm: str
    uf_origem: str
    uf_destino: str
    regime: str
    operacao: str
    consumidor_final: bool