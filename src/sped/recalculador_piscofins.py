"""Recalculo encadeado de PIS/COFINS para a Correção Tributária.

A rotina atua somente sobre registros efetivamente afetados por uma correção
confirmada pela usuária. Ela recalcula o valor da contribuição no C170 usando a
base e a alíquota já gravadas no próprio registro e, em seguida, atualiza os
totais de PIS/COFINS do C100 pai.

O Bloco M não é alterado por aproximação: sua apuração pode envolver códigos de
crédito, ajustes, diferimentos, retenções e saldos de períodos anteriores. A
rotina registra uma pendência explícita para que a apuração seja regenerada e
validada no PVA oficial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable


@dataclass(frozen=True, slots=True)
class AlteracaoRecalculoPISCOFINS:
    numero_linha: int
    registro: str
    campo: str
    valor_anterior: str
    valor_novo: str
    tributo: str
    justificativa: str


@dataclass(slots=True)
class ResultadoRecalculoPISCOFINS:
    linhas: list[str]
    alteracoes: list[AlteracaoRecalculoPISCOFINS] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    documentos_retotalizados: int = 0
    linhas_c170_recalculadas: int = 0
    requer_reapuracao_bloco_m: bool = False


class RecalculadorPISCOFINS:
    """Recalcula dependências documentais de PIS/COFINS com rastreabilidade."""

    # Índices sem os separadores externos: 0 = código do registro.
    C170 = {
        "PIS": {
            "cst": 24,
            "base": 25,
            "aliquota": 26,
            "quantidade": 27,
            "aliquota_quantidade": 28,
            "valor": 29,
        },
        "COFINS": {
            "cst": 30,
            "base": 31,
            "aliquota": 32,
            "quantidade": 33,
            "aliquota_quantidade": 34,
            "valor": 35,
        },
    }
    C100_TOTAIS = {"PIS": 25, "COFINS": 26}

    def recalcular(
        self,
        linhas: list[str],
        afetadas: Iterable[tuple[int, str]],
        tipo_sped: str,
    ) -> ResultadoRecalculoPISCOFINS:
        novas = list(linhas)
        resultado = ResultadoRecalculoPISCOFINS(linhas=novas)
        afetadas_normalizadas = {
            (int(numero_linha), str(tributo).strip().upper())
            for numero_linha, tributo in afetadas
            if str(tributo).strip().upper() in self.C170
        }
        if not afetadas_normalizadas:
            return resultado

        if str(tipo_sped or "").strip().upper() != "EFD CONTRIBUIÇÕES":
            resultado.avisos.append(
                "O recálculo encadeado de PIS/COFINS foi ignorado porque o arquivo aberto "
                "não foi identificado como EFD Contribuições."
            )
            return resultado

        mapa_documentos = self._mapear_documentos_c100(novas)
        documentos_afetados: dict[int, set[str]] = {}
        linhas_recalculadas: set[int] = set()

        for numero_linha, tributo in sorted(afetadas_normalizadas):
            indice_linha = numero_linha - 1
            if indice_linha < 0 or indice_linha >= len(novas):
                resultado.avisos.append(
                    f"Linha {numero_linha}: não foi possível recalcular {tributo}; a linha não existe."
                )
                continue
            if self._codigo(novas[indice_linha]) != "C170":
                resultado.avisos.append(
                    f"Linha {numero_linha}: não foi possível recalcular {tributo}; o registro não é C170."
                )
                continue

            calculado, motivo = self._calcular_contribuicao_c170(novas[indice_linha], tributo)
            if calculado is None:
                resultado.avisos.append(f"Linha {numero_linha} — {tributo}: {motivo}")
                continue

            indice_valor = self.C170[tributo]["valor"]
            anterior = self._obter_campo(novas[indice_linha], indice_valor)
            novo = self._decimal_sped(calculado, 2)
            if self._normalizar_decimal(anterior) != calculado:
                novas[indice_linha] = self._substituir_campo(
                    novas[indice_linha], indice_valor, novo
                )
                resultado.alteracoes.append(
                    AlteracaoRecalculoPISCOFINS(
                        numero_linha=numero_linha,
                        registro="C170",
                        campo=f"VL_{tributo}",
                        valor_anterior=anterior,
                        valor_novo=novo,
                        tributo=tributo,
                        justificativa=motivo,
                    )
                )
            linhas_recalculadas.add(numero_linha)
            pai = mapa_documentos.get(numero_linha)
            if pai is not None:
                documentos_afetados.setdefault(pai, set()).add(tributo)

        for linha_c100 in sorted(documentos_afetados):
            filhos = self._filhos_c170_do_documento(novas, linha_c100)
            if not filhos:
                resultado.avisos.append(
                    f"C100 linha {linha_c100}: nenhum C170 foi localizado para retotalizar o documento."
                )
                continue
            houve_alteracao = False
            for tributo in sorted(documentos_afetados[linha_c100]):
                soma = Decimal("0")
                campo_valor = self.C170[tributo]["valor"]
                for linha_filho in filhos:
                    valor = self._normalizar_decimal(
                        self._obter_campo(novas[linha_filho - 1], campo_valor)
                    )
                    if valor is not None:
                        soma += valor
                soma = soma.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                indice_total = self.C100_TOTAIS[tributo]
                anterior = self._obter_campo(novas[linha_c100 - 1], indice_total)
                novo = self._decimal_sped(soma, 2)
                if self._normalizar_decimal(anterior) != soma:
                    novas[linha_c100 - 1] = self._substituir_campo(
                        novas[linha_c100 - 1], indice_total, novo
                    )
                    resultado.alteracoes.append(
                        AlteracaoRecalculoPISCOFINS(
                            numero_linha=linha_c100,
                            registro="C100",
                            campo=f"VL_{tributo}",
                            valor_anterior=anterior,
                            valor_novo=novo,
                            tributo=tributo,
                            justificativa=(
                                f"Total do documento recalculado pela soma dos valores de {tributo} "
                                "dos registros C170 filhos."
                            ),
                        )
                    )
                    houve_alteracao = True
            if houve_alteracao:
                resultado.documentos_retotalizados += 1

        resultado.linhas_c170_recalculadas = len(linhas_recalculadas)
        resultado.requer_reapuracao_bloco_m = bool(linhas_recalculadas)
        if resultado.requer_reapuracao_bloco_m:
            resultado.avisos.append(
                "Os valores documentais de PIS/COFINS foram recalculados. O Bloco M não foi "
                "alterado automaticamente, pois a apuração pode conter créditos, ajustes, "
                "retenções e saldos. Gere/recalcule a apuração no PVA oficial antes de transmitir."
            )
        return resultado

    def _calcular_contribuicao_c170(
        self, linha: str, tributo: str
    ) -> tuple[Decimal | None, str]:
        mapa = self.C170[tributo]
        base_texto = self._obter_campo(linha, mapa["base"]).strip()
        aliquota_texto = self._obter_campo(linha, mapa["aliquota"]).strip()
        quantidade_texto = self._obter_campo(linha, mapa["quantidade"]).strip()
        aliquota_qtd_texto = self._obter_campo(
            linha, mapa["aliquota_quantidade"]
        ).strip()

        base = self._normalizar_decimal(base_texto)
        aliquota = self._normalizar_decimal(aliquota_texto)
        if base is not None and aliquota is not None and base_texto and aliquota_texto:
            valor = (base * aliquota / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            return valor, (
                f"{tributo} recalculado por VL_BC_{tributo} × ALIQ_{tributo} ÷ 100, "
                "com arredondamento para duas casas decimais."
            )

        quantidade = self._normalizar_decimal(quantidade_texto)
        aliquota_qtd = self._normalizar_decimal(aliquota_qtd_texto)
        if (
            quantidade is not None
            and aliquota_qtd is not None
            and quantidade_texto
            and aliquota_qtd_texto
        ):
            valor = (quantidade * aliquota_qtd).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            return valor, (
                f"{tributo} recalculado por QUANT_BC_{tributo} × ALIQ_{tributo}_QUANT, "
                "com arredondamento para duas casas decimais."
            )

        cst = self._obter_campo(linha, mapa["cst"]).strip()
        return None, (
            f"não há base/alíquota ad valorem nem quantidade/alíquota por unidade suficientes "
            f"para recalcular o valor (CST {cst or 'não informado'}). O valor existente foi preservado."
        )

    @classmethod
    def _mapear_documentos_c100(cls, linhas: list[str]) -> dict[int, int]:
        mapa: dict[int, int] = {}
        linha_pai: int | None = None
        for numero, linha in enumerate(linhas, start=1):
            codigo = cls._codigo(linha)
            if codigo == "C100":
                linha_pai = numero
            elif codigo == "C170" and linha_pai is not None:
                mapa[numero] = linha_pai
            elif codigo.startswith("C") and codigo not in {
                "C101", "C105", "C110", "C111", "C112", "C113", "C114",
                "C115", "C116", "C120", "C130", "C140", "C141", "C160",
                "C165", "C170", "C171", "C172", "C173", "C174", "C175",
                "C176", "C177", "C178", "C179", "C190", "C191", "C195",
                "C197", "C199",
            }:
                linha_pai = None
            elif codigo and not codigo.startswith("C"):
                linha_pai = None
        return mapa

    @classmethod
    def _filhos_c170_do_documento(cls, linhas: list[str], linha_c100: int) -> list[int]:
        filhos: list[int] = []
        for numero in range(linha_c100 + 1, len(linhas) + 1):
            codigo = cls._codigo(linhas[numero - 1])
            if codigo == "C100":
                break
            if codigo and not codigo.startswith("C"):
                break
            if codigo == "C170":
                filhos.append(numero)
        return filhos

    @staticmethod
    def _codigo(linha: str) -> str:
        texto = linha.rstrip("\r\n")
        if not (texto.startswith("|") and texto.endswith("|")):
            return ""
        partes = texto.split("|")
        return partes[1].strip().upper() if len(partes) > 2 else ""

    @staticmethod
    def _obter_campo(linha: str, indice_campo: int) -> str:
        texto = linha.rstrip("\r\n")
        partes = texto.split("|")
        indice = indice_campo + 1
        return partes[indice] if indice < len(partes) else ""

    @staticmethod
    def _substituir_campo(linha: str, indice_campo: int, valor: str) -> str:
        if linha.endswith("\r\n"):
            texto, fim = linha[:-2], "\r\n"
        elif linha.endswith("\n"):
            texto, fim = linha[:-1], "\n"
        elif linha.endswith("\r"):
            texto, fim = linha[:-1], "\r"
        else:
            texto, fim = linha, ""
        partes = texto.split("|")
        indice = indice_campo + 1
        if not (texto.startswith("|") and texto.endswith("|")) or indice >= len(partes) - 1:
            raise RuntimeError(
                f"Não foi possível localizar o campo {indice_campo} na linha SPED."
            )
        partes[indice] = valor
        return "|".join(partes) + fim

    @staticmethod
    def _normalizar_decimal(valor: str) -> Decimal | None:
        bruto = str(valor or "").strip().replace(" ", "")
        if not bruto:
            return None
        if "," in bruto:
            bruto = bruto.replace(".", "").replace(",", ".")
        try:
            return Decimal(bruto)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _decimal_sped(valor: Decimal, casas: int = 2) -> str:
        quantizador = Decimal("1").scaleb(-casas)
        numero = valor.quantize(quantizador, rounding=ROUND_HALF_UP)
        return f"{numero:.{casas}f}".replace(".", ",")
