"""Saneamento estrutural de COD_ITEM duplicado no registro 0200.

Hotfix 17.3.10
---------------
O PGE exige unicidade do COD_ITEM no 0200. Este módulo corrige em lote sem
inventar o vínculo transacional quando a origem não permite distingui-lo:

* duplicatas realmente idênticas: mantém o primeiro cadastro e remove as cópias;
* mesmo COD_ITEM com cadastros materialmente diferentes: preserva todos os
  cadastros, renomeando somente os posteriores com um sufixo único ``-D2``,
  ``-D3`` etc.;
* não remapeia C170/A170 de forma heurística. Se o arquivo não traz evidência
  objetiva de qual cadastro divergente cada documento pretendia usar, os
  documentos permanecem exatamente como vieram da origem.

A estratégia elimina a chave duplicada do PGE, preserva os dados cadastrais e
não cria uma associação fiscal que o arquivo-fonte não comprova.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass(frozen=True, slots=True)
class AlteracaoSaneamentoCODItem:
    numero_linha: int | None
    registro: str
    campo: str
    valor_anterior: str
    valor_novo: str
    justificativa: str


@dataclass(frozen=True, slots=True)
class PlanoSaneamentoCODItem:
    codigo_original: str
    linhas_0200: tuple[int, ...]
    linhas_remover: tuple[int, ...]
    renomeacoes: tuple[tuple[int, str], ...]

    @property
    def registros_duplicados(self) -> int:
        return max(len(self.linhas_0200) - 1, 0)

    @property
    def exclusoes(self) -> int:
        return len(self.linhas_remover)

    @property
    def renomeados(self) -> int:
        return len(self.renomeacoes)


@dataclass(slots=True)
class ResultadoSaneamentoCODItem:
    linhas: list[str]
    alteracoes: list[AlteracaoSaneamentoCODItem] = field(default_factory=list)
    grupos_tratados: int = 0
    removidos: int = 0
    renomeados: int = 0
    estrutura_alterada: bool = False


@dataclass(frozen=True, slots=True)
class _Ocorrencia0200:
    indice: int
    numero_linha: int
    campos: tuple[str, ...]
    filhos: tuple[str, ...]

    @property
    def codigo(self) -> str:
        return self.campos[1].strip() if len(self.campos) > 1 else ""

    @property
    def assinatura(self) -> tuple[str, ...]:
        # Para exclusão automática exigimos equivalência do cadastro inteiro e
        # também dos filhos estruturais. Diferença de GTIN, descrição, unidade,
        # NCM ou qualquer outro campo transforma o caso em renomeação, não em
        # exclusão.
        pai = tuple(_normalizar_texto(campo) for campo in self.campos[2:])
        filhos = tuple(_normalizar_linha(linha) for linha in self.filhos)
        return pai + ("<FILHOS>",) + filhos


class SaneadorCODItem:
    """Analisa e resolve duplicidades do COD_ITEM no 0200 em uma única ação."""

    FILHOS_0200 = {"0205", "0206", "0210", "0220", "0221"}
    TAM_MAX_COD_ITEM = 60

    def analisar(self, linhas: list[str]) -> list[PlanoSaneamentoCODItem]:
        ocorrencias = self._ocorrencias_0200(linhas)
        por_codigo: dict[str, list[_Ocorrencia0200]] = {}
        for ocorrencia in ocorrencias:
            if ocorrencia.codigo:
                por_codigo.setdefault(ocorrencia.codigo, []).append(ocorrencia)

        codigos_existentes = {o.codigo for o in ocorrencias if o.codigo}
        planos: list[PlanoSaneamentoCODItem] = []

        for codigo, grupo in por_codigo.items():
            if len(grupo) <= 1:
                continue

            # Agrupa cadastros equivalentes. O primeiro grupo mantém o COD_ITEM
            # original; grupos materialmente diferentes ganham um código novo.
            por_assinatura: dict[tuple[str, ...], list[_Ocorrencia0200]] = {}
            ordem_assinaturas: list[tuple[str, ...]] = []
            for ocorrencia in grupo:
                assinatura = ocorrencia.assinatura
                if assinatura not in por_assinatura:
                    por_assinatura[assinatura] = []
                    ordem_assinaturas.append(assinatura)
                por_assinatura[assinatura].append(ocorrencia)

            remover: list[int] = []
            renomear: list[tuple[int, str]] = []

            for posicao_assinatura, assinatura in enumerate(ordem_assinaturas, start=1):
                iguais = por_assinatura[assinatura]
                representante = iguais[0]

                if posicao_assinatura > 1:
                    novo_codigo = self._gerar_codigo_unico(
                        codigo, posicao_assinatura, codigos_existentes
                    )
                    codigos_existentes.add(novo_codigo)
                    renomear.append((representante.numero_linha, novo_codigo))

                # As demais ocorrências do mesmo cadastro são redundantes. Só
                # removemos o bloco inteiro quando a assinatura (inclusive
                # filhos) é igual ao representante.
                for redundante in iguais[1:]:
                    remover.append(redundante.numero_linha)

            planos.append(
                PlanoSaneamentoCODItem(
                    codigo_original=codigo,
                    linhas_0200=tuple(o.numero_linha for o in grupo),
                    linhas_remover=tuple(sorted(remover)),
                    renomeacoes=tuple(renomear),
                )
            )

        return planos

    def sanear(self, linhas: list[str]) -> ResultadoSaneamentoCODItem:
        planos = self.analisar(linhas)
        resultado = ResultadoSaneamentoCODItem(linhas=list(linhas))
        if not planos:
            return resultado

        # Mapeamos os blocos completos 0200 + filhos para remover duplicatas
        # idênticas sem deixar um 0205/0220 órfão no arquivo.
        blocos_por_linha = {
            o.numero_linha: self._indices_bloco(o, linhas)
            for o in self._ocorrencias_0200(linhas)
        }

        novas = list(linhas)
        for plano in planos:
            for numero_linha, novo_codigo in plano.renomeacoes:
                indice = numero_linha - 1
                anterior = self._campo(novas[indice], 1)
                novas[indice] = self._substituir_campo(novas[indice], 1, novo_codigo)
                resultado.alteracoes.append(
                    AlteracaoSaneamentoCODItem(
                        numero_linha=numero_linha,
                        registro="0200",
                        campo="COD_ITEM",
                        valor_anterior=anterior,
                        valor_novo=novo_codigo,
                        justificativa=(
                            "Mesmo COD_ITEM aparecia em cadastros materialmente diferentes. "
                            "O FiscalPro preservou ambos e renomeou apenas o cadastro posterior, "
                            "sem remapear documentos por aproximação."
                        ),
                    )
                )
                resultado.renomeados += 1

        indices_remover: set[int] = set()
        for plano in planos:
            for numero_linha in plano.linhas_remover:
                indices = blocos_por_linha.get(numero_linha, (numero_linha - 1,))
                indices_remover.update(indices)
                resultado.alteracoes.append(
                    AlteracaoSaneamentoCODItem(
                        numero_linha=numero_linha,
                        registro="0200",
                        campo="COD_ITEM",
                        valor_anterior=plano.codigo_original,
                        valor_novo="(registro duplicado removido)",
                        justificativa=(
                            "Cadastro 0200 idêntico a outro já mantido no arquivo; "
                            "a cópia redundante e seus filhos equivalentes foram removidos."
                        ),
                    )
                )
                resultado.removidos += 1

        if indices_remover:
            novas = [linha for indice, linha in enumerate(novas) if indice not in indices_remover]

        resultado.linhas = novas
        resultado.grupos_tratados = len(planos)
        resultado.estrutura_alterada = bool(indices_remover)
        return resultado

    def resumo(self, linhas: list[str]) -> tuple[int, int, int]:
        planos = self.analisar(linhas)
        return (
            len(planos),
            sum(p.exclusoes for p in planos),
            sum(p.renomeados for p in planos),
        )

    def _ocorrencias_0200(self, linhas: list[str]) -> list[_Ocorrencia0200]:
        ocorrencias: list[_Ocorrencia0200] = []
        for indice, linha in enumerate(linhas):
            if self._codigo(linha) != "0200":
                continue
            filhos: list[str] = []
            j = indice + 1
            while j < len(linhas) and self._codigo(linhas[j]) in self.FILHOS_0200:
                filhos.append(linhas[j])
                j += 1
            ocorrencias.append(
                _Ocorrencia0200(
                    indice=indice,
                    numero_linha=indice + 1,
                    campos=tuple(self._campos(linha)),
                    filhos=tuple(filhos),
                )
            )
        return ocorrencias

    def _indices_bloco(self, ocorrencia: _Ocorrencia0200, linhas: list[str]) -> tuple[int, ...]:
        indices = [ocorrencia.indice]
        j = ocorrencia.indice + 1
        while j < len(linhas) and self._codigo(linhas[j]) in self.FILHOS_0200:
            indices.append(j)
            j += 1
        return tuple(indices)

    def _gerar_codigo_unico(
        self, codigo: str, numero_variante: int, existentes: set[str]
    ) -> str:
        tentativa = max(numero_variante, 2)
        while True:
            sufixo = f"-D{tentativa}"
            base = codigo[: self.TAM_MAX_COD_ITEM - len(sufixo)]
            novo = f"{base}{sufixo}"
            if novo not in existentes:
                return novo
            tentativa += 1

    @staticmethod
    def _codigo(linha: str) -> str:
        campos = SaneadorCODItem._campos(linha)
        return campos[0].strip() if campos else ""

    @staticmethod
    def _campos(linha: str) -> list[str]:
        texto = linha.rstrip("\r\n")
        if texto.startswith("|"):
            texto = texto[1:]
        if texto.endswith("|"):
            texto = texto[:-1]
        return texto.split("|") if texto else []

    @staticmethod
    def _campo(linha: str, indice: int) -> str:
        campos = SaneadorCODItem._campos(linha)
        return campos[indice] if indice < len(campos) else ""

    @staticmethod
    def _substituir_campo(linha: str, indice: int, valor: str) -> str:
        quebra = "\r\n" if linha.endswith("\r\n") else "\n" if linha.endswith("\n") else ""
        campos = SaneadorCODItem._campos(linha)
        while len(campos) <= indice:
            campos.append("")
        campos[indice] = valor
        return "|" + "|".join(campos) + "|" + quebra


def _normalizar_texto(valor: str) -> str:
    return re.sub(r"\s+", " ", valor.strip()).casefold()


def _normalizar_linha(linha: str) -> str:
    texto = linha.rstrip("\r\n")
    return re.sub(r"\s+", " ", texto.strip()).casefold()
