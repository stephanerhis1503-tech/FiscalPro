"""Consolidação segura de créditos duplicados M100/M500.

Hotfix 17.3.9
--------------
O PGE exige unicidade da chave composta do crédito em M100/M500. Este módulo
consolida automaticamente apenas os casos em que a operação é determinística:

* mesma chave COD_CRED + IND_CRED_ORI + alíquota + alíquota por quantidade;
* crédito apurado por base monetária (não por quantidade);
* sem ajustes de acréscimo/redução/diferimento;
* desconto integral no período (IND_DESC_CRED = 0 e saldo = 0);
* filhos M105/M505 sem chaves repetidas entre os pais que serão unidos;
* base de cada pai confere com a soma da base não cumulativa dos seus filhos.

Nos casos fora desses critérios o FiscalPro mantém a pendência como revisão,
sem tentar adivinhar a utilização do crédito.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


@dataclass(frozen=True, slots=True)
class PlanoConsolidacaoCreditoM:
    registro: str
    registro_filho: str
    chave: tuple[str, str, str, str]
    linhas_pais: tuple[int, ...]
    blocos: tuple[tuple[int, int], ...]  # índices 0-based, fim exclusivo
    base_total: Decimal
    aliquota: Decimal
    credito_total: Decimal
    filhos: tuple[str, ...]
    linha_consolidada: str

    @property
    def identificador(self) -> tuple[str, tuple[str, str, str, str]]:
        return (self.registro, self.chave)


@dataclass(frozen=True, slots=True)
class AlteracaoConsolidacaoCreditoM:
    numero_linha: int | None
    registro: str
    campo: str
    valor_anterior: str
    valor_novo: str
    justificativa: str


@dataclass(slots=True)
class ResultadoConsolidacaoCreditosM:
    linhas: list[str]
    alteracoes: list[AlteracaoConsolidacaoCreditoM] = field(default_factory=list)
    grupos_consolidados: int = 0
    estrutura_alterada: bool = False


@dataclass(slots=True)
class _BlocoCredito:
    registro: str
    registro_filho: str
    inicio: int
    fim: int
    campos_pai: list[str]
    filhos_linhas: list[str]
    filhos_campos: list[list[str]]
    chave: tuple[str, str, str, str]
    seguro_individual: bool


class ConsolidadorCreditosBlocoM:
    PARES = {"M100": "M105", "M500": "M505"}
    # Registros nível 2 / encerramento que delimitam um crédito no Bloco M.
    LIMITES = {
        "M100", "M200", "M300", "M350", "M400", "M500",
        "M600", "M700", "M800", "M990",
    }

    def analisar(self, linhas: list[str]) -> list[PlanoConsolidacaoCreditoM]:
        planos: list[PlanoConsolidacaoCreditoM] = []
        for pai, filho in self.PARES.items():
            blocos = self._blocos(linhas, pai, filho)
            por_chave: dict[tuple[str, str, str, str], list[_BlocoCredito]] = {}
            for bloco in blocos:
                por_chave.setdefault(bloco.chave, []).append(bloco)

            for chave, grupo in por_chave.items():
                if len(grupo) <= 1:
                    continue
                plano = self._plano_seguro(grupo)
                if plano is not None:
                    planos.append(plano)
        return planos

    def mapa_por_linha_pai(
        self, linhas: list[str]
    ) -> dict[int, PlanoConsolidacaoCreditoM]:
        mapa: dict[int, PlanoConsolidacaoCreditoM] = {}
        for plano in self.analisar(linhas):
            for numero in plano.linhas_pais:
                mapa[numero] = plano
        return mapa

    def consolidar(
        self, linhas: list[str], linhas_semente: set[int]
    ) -> ResultadoConsolidacaoCreditosM:
        resultado = ResultadoConsolidacaoCreditosM(linhas=list(linhas))
        if not linhas_semente:
            return resultado

        planos = [
            p for p in self.analisar(linhas)
            if any(numero in linhas_semente for numero in p.linhas_pais)
        ]
        if not planos:
            return resultado

        substituir: dict[int, list[str]] = {}
        remover: set[int] = set()
        for plano in planos:
            primeiro_inicio = plano.blocos[0][0]
            quebra = self._quebra(linhas[primeiro_inicio])
            bloco_novo = [plano.linha_consolidada + quebra]
            bloco_novo.extend(self._normalizar_quebra(linha, quebra) for linha in plano.filhos)
            substituir[primeiro_inicio] = bloco_novo

            for inicio, fim in plano.blocos:
                remover.update(range(inicio, fim))

            bases_anteriores = []
            creditos_anteriores = []
            for numero in plano.linhas_pais:
                campos = self._campos(linhas[numero - 1])
                bases_anteriores.append(self._campo(campos, 3))
                creditos_anteriores.append(self._campo(campos, 7))

            resultado.alteracoes.extend(
                [
                    AlteracaoConsolidacaoCreditoM(
                        numero_linha=plano.linhas_pais[0],
                        registro=plano.registro,
                        campo="CHAVE_CREDITO",
                        valor_anterior=f"{len(plano.linhas_pais)} registros duplicados",
                        valor_novo="1 registro consolidado",
                        justificativa=(
                            "Consolidação da chave COD_CRED/IND_CRED_ORI/alíquota exigida como única pelo PGE."
                        ),
                    ),
                    AlteracaoConsolidacaoCreditoM(
                        numero_linha=plano.linhas_pais[0],
                        registro=plano.registro,
                        campo="VL_BC_CREDITO",
                        valor_anterior=" + ".join(bases_anteriores),
                        valor_novo=self._fmt(plano.base_total, 2),
                        justificativa=(
                            f"Base consolidada pela soma dos {plano.registro_filho} vinculados aos créditos duplicados."
                        ),
                    ),
                    AlteracaoConsolidacaoCreditoM(
                        numero_linha=plano.linhas_pais[0],
                        registro=plano.registro,
                        campo="VL_CRED",
                        valor_anterior=" + ".join(creditos_anteriores),
                        valor_novo=self._fmt(plano.credito_total, 2),
                        justificativa=(
                            "Crédito recalculado sobre a base consolidada para eliminar diferença de arredondamento entre pais separados."
                        ),
                    ),
                ]
            )

        novas: list[str] = []
        for indice, linha in enumerate(linhas):
            if indice in substituir:
                novas.extend(substituir[indice])
            if indice in remover:
                continue
            novas.append(linha)

        resultado.linhas = novas
        resultado.grupos_consolidados = len(planos)
        resultado.estrutura_alterada = bool(planos)
        return resultado

    def _blocos(
        self, linhas: list[str], registro_pai: str, registro_filho: str
    ) -> list[_BlocoCredito]:
        blocos: list[_BlocoCredito] = []
        i = 0
        while i < len(linhas):
            if self._codigo(linhas[i]) != registro_pai:
                i += 1
                continue

            campos_pai = self._campos(linhas[i])
            inicio = i
            j = i + 1
            filhos_linhas: list[str] = []
            filhos_campos: list[list[str]] = []
            extra_encontrado = False

            while j < len(linhas):
                codigo = self._codigo(linhas[j])
                if codigo in self.LIMITES:
                    break
                if codigo == registro_filho:
                    filhos_linhas.append(linhas[j])
                    filhos_campos.append(self._campos(linhas[j]))
                elif codigo.startswith("M"):
                    # M110/M115/M510/... exigem tratamento próprio e tornam a
                    # consolidação automática insegura.
                    extra_encontrado = True
                j += 1

            chave = (
                self._campo(campos_pai, 1).strip(),
                self._campo(campos_pai, 2).strip(),
                self._normalizar_numero_texto(self._campo(campos_pai, 4), 4),
                self._normalizar_numero_texto(self._campo(campos_pai, 6), 4),
            )
            seguro = self._pai_basico_seguro(campos_pai) and not extra_encontrado
            blocos.append(
                _BlocoCredito(
                    registro=registro_pai,
                    registro_filho=registro_filho,
                    inicio=inicio,
                    fim=j,
                    campos_pai=campos_pai,
                    filhos_linhas=filhos_linhas,
                    filhos_campos=filhos_campos,
                    chave=chave,
                    seguro_individual=seguro,
                )
            )
            i = j
        return blocos

    def _plano_seguro(
        self, grupo: list[_BlocoCredito]
    ) -> PlanoConsolidacaoCreditoM | None:
        if not grupo or not all(bloco.seguro_individual for bloco in grupo):
            return None

        # Todos os pais precisam estar em modo de desconto integral, sem saldo.
        if any(self._campo(b.campos_pai, 12).strip() != "0" for b in grupo):
            return None
        if any((self._decimal(self._campo(b.campos_pai, 14)) or Decimal("0")) != 0 for b in grupo):
            return None

        # Não consolidamos automaticamente créditos por quantidade neste hotfix.
        if any(self._campo(b.campos_pai, 5).strip() or self._campo(b.campos_pai, 6).strip() for b in grupo):
            return None

        aliquota = self._decimal(self._campo(grupo[0].campos_pai, 4))
        if aliquota is None or aliquota <= 0:
            return None

        filhos_todos: list[tuple[str, list[str]]] = []
        chaves_filhos: set[tuple[str, str]] = set()
        base_total = Decimal("0")

        for bloco in grupo:
            if not bloco.filhos_campos:
                return None
            base_pai = self._decimal(self._campo(bloco.campos_pai, 3))
            if base_pai is None:
                return None

            soma_base_filho = Decimal("0")
            for linha_filho, campos_filho in zip(bloco.filhos_linhas, bloco.filhos_campos):
                # M105/M505: campo 06 do PGE = índice 5 sem o delimitador REG.
                base_nc = self._decimal(self._campo(campos_filho, 5))
                if base_nc is None:
                    return None
                soma_base_filho += base_nc
                chave_filho = (
                    self._campo(campos_filho, 1).strip(),
                    self._campo(campos_filho, 2).strip(),
                )
                if chave_filho in chaves_filhos:
                    return None
                chaves_filhos.add(chave_filho)
                filhos_todos.append((linha_filho, campos_filho))

            if abs(soma_base_filho - base_pai) > Decimal("0.01"):
                return None
            base_total += soma_base_filho

        credito_total = (base_total * aliquota / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        novo = list(grupo[0].campos_pai)
        novo[3] = self._fmt(base_total, 2)
        novo[7] = self._fmt(credito_total, 2)
        # Sem ajustes e com desconto integral, disponível e descontado devem
        # acompanhar o crédito consolidado; saldo permanece zerado.
        novo[8] = "0,00"
        novo[9] = "0,00"
        novo[10] = "0,00"
        novo[11] = self._fmt(credito_total, 2)
        novo[12] = "0"
        novo[13] = self._fmt(credito_total, 2)
        novo[14] = "0,00"

        return PlanoConsolidacaoCreditoM(
            registro=grupo[0].registro,
            registro_filho=grupo[0].registro_filho,
            chave=grupo[0].chave,
            linhas_pais=tuple(bloco.inicio + 1 for bloco in grupo),
            blocos=tuple((bloco.inicio, bloco.fim) for bloco in grupo),
            base_total=base_total,
            aliquota=aliquota,
            credito_total=credito_total,
            filhos=tuple(item[0] for item in filhos_todos),
            linha_consolidada="|" + "|".join(novo) + "|",
        )

    def _pai_basico_seguro(self, campos: list[str]) -> bool:
        if len(campos) < 15:
            return False
        if not self._campo(campos, 1).strip() or not self._campo(campos, 2).strip():
            return False
        if self._decimal(self._campo(campos, 3)) is None:
            return False
        if self._decimal(self._campo(campos, 4)) is None:
            return False
        # Ajustes de acréscimo, redução e diferimento precisam ser zero para
        # que a consolidação seja puramente aritmética.
        for indice in (8, 9, 10):
            if (self._decimal(self._campo(campos, indice)) or Decimal("0")) != 0:
                return False
        return True

    @staticmethod
    def _codigo(linha: str) -> str:
        campos = ConsolidadorCreditosBlocoM._campos(linha)
        return campos[0].strip().upper() if campos else ""

    @staticmethod
    def _campos(linha: str) -> list[str]:
        texto = linha.rstrip("\r\n")
        if not (texto.startswith("|") and texto.endswith("|")):
            return []
        return texto.split("|")[1:-1]

    @staticmethod
    def _campo(campos: list[str], indice: int) -> str:
        return campos[indice] if 0 <= indice < len(campos) else ""

    @staticmethod
    def _decimal(valor: str) -> Decimal | None:
        texto = (valor or "").strip()
        if not texto:
            return None
        try:
            return Decimal(texto.replace(".", "").replace(",", "."))
        except InvalidOperation:
            return None

    @classmethod
    def _normalizar_numero_texto(cls, valor: str, casas: int) -> str:
        numero = cls._decimal(valor)
        return cls._fmt(numero, casas) if numero is not None else ""

    @staticmethod
    def _fmt(valor: Decimal, casas: int) -> str:
        quant = Decimal("1").scaleb(-casas)
        return f"{valor.quantize(quant, rounding=ROUND_HALF_UP):.{casas}f}".replace(".", ",")

    @staticmethod
    def _quebra(linha: str) -> str:
        if linha.endswith("\r\n"):
            return "\r\n"
        if linha.endswith("\n"):
            return "\n"
        if linha.endswith("\r"):
            return "\r"
        return "\n"

    @staticmethod
    def _normalizar_quebra(linha: str, quebra: str) -> str:
        return linha.rstrip("\r\n") + quebra
