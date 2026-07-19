from dataclasses import dataclass, field


@dataclass
class ResultadoPesquisa:

    sucesso: bool = False

    fonte: str = ""

    mensagem: str = ""

    dados: dict = field(default_factory=dict)