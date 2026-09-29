from dataclasses import dataclass, field


@dataclass
class ResultadoTributario:
    """
    Resultado produzido pelo Motor de Regras.

    Contém todos os tributos, benefícios,
    fundamentações e mensagens geradas
    durante a decisão tributária.
    """

    impostos: dict = field(default_factory=dict)

    beneficios: list = field(default_factory=list)

    fundamentacao: list = field(default_factory=list)

    advertencias: list = field(default_factory=list)

    observacoes: list = field(default_factory=list)

    prioridade: int = 0

    regra_aplicada: str = ""

    sucesso: bool = True

    mensagem: str = ""

    def adicionar_imposto(self, nome, dados):
        self.impostos[nome.lower()] = dados

    def imposto(self, nome):
        return self.impostos.get(nome.lower())

    def adicionar_fundamento(self, texto):
        if texto not in self.fundamentacao:
            self.fundamentacao.append(texto)

    def adicionar_beneficio(self, beneficio):
        if beneficio:
            self.beneficios.append(beneficio)

    def adicionar_advertencia(self, texto):
        self.advertencias.append(texto)

    def adicionar_observacao(self, texto):
        self.observacoes.append(texto)

    @property
    def possui_inconsistencias(self):
        return len(self.advertencias) > 0