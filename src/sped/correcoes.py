from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .leitor import LeitorSPEDUnificado

ProgressoCallback = Callable[[int, str], None]


@dataclass(frozen=True, slots=True)
class CorrecaoSPED:
    numero_linha: int
    registro: str
    codigo_item: str
    gravidade: str
    problema: str
    acao: str
    automatica: bool = False
    indice_campo: int | None = None
    valor_anterior: str = ""
    valor_novo: str = ""

    @property
    def modo(self) -> str:
        return "Automática" if self.automatica else "Revisão manual"


@dataclass(slots=True)
class ResultadoAnaliseCorrecoes:
    correcoes: list[CorrecaoSPED] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.correcoes)

    @property
    def automaticas(self) -> list[CorrecaoSPED]:
        return [item for item in self.correcoes if item.automatica]

    @property
    def manuais(self) -> list[CorrecaoSPED]:
        return [item for item in self.correcoes if not item.automatica]

    @property
    def total_automaticas(self) -> int:
        return len(self.automaticas)

    @property
    def total_manuais(self) -> int:
        return len(self.manuais)


@dataclass(frozen=True, slots=True)
class ResultadoGeracaoSPED:
    caminho_sped: Path
    caminho_relatorio: Path
    total_aplicadas: int
    total_pendencias_manuais: int


class AuditorCorrecoesSPED:
    """Audita 0200 e C170 e propõe somente correções estruturais seguras.

    As correções automáticas permanecem conservadoras. Além das normalizações
    estruturais, a Sprint 17.3.4 aplica somente duas correções tributárias que o
    próprio PGE torna determinísticas: alíquota básica quando CST=01 (conforme
    IND_INC_TRIB do 0110) e CST 08 de saída convertido para CST 74 quando o CFOP
    é inequivocamente de entrada/aquisição.
    """

    REGISTRO_0200 = "0200"
    REGISTRO_C170 = "C170"

    def analisar(
        self,
        linhas: list[str],
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAnaliseCorrecoes:
        self._progresso(progresso, 5, "Mapeando cadastros e itens...")

        registros_0200: dict[str, tuple[int, list[str]]] = {}
        duplicados_0200: dict[str, list[tuple[int, list[str]]]] = defaultdict(list)
        unidades_c170: dict[str, set[str]] = defaultdict(set)
        linhas_c170: list[tuple[int, list[str]]] = []
        ind_inc_trib = ""

        for numero_linha, registro, campos in LeitorSPEDUnificado.iterar_registros(linhas):
            if registro == "0110" and not ind_inc_trib:
                ind_inc_trib = self._campo(campos, 2).strip()
            if registro == self.REGISTRO_0200:
                codigo = self._campo(campos, 2)
                if codigo in registros_0200:
                    duplicados_0200[codigo].append(registros_0200[codigo])
                    duplicados_0200[codigo].append((numero_linha, campos))
                else:
                    registros_0200[codigo] = (numero_linha, campos)
            elif registro == self.REGISTRO_C170:
                linhas_c170.append((numero_linha, campos))
                codigo = self._campo(campos, 3)
                unidade = self._campo(campos, 6).strip()
                if codigo and unidade:
                    unidades_c170[codigo].add(unidade)

        correcoes: list[CorrecaoSPED] = []
        self._progresso(progresso, 30, "Auditando cadastro de produtos (0200)...")

        for codigo, (numero_linha, campos) in registros_0200.items():
            descricao = self._campo(campos, 3)
            unidade = self._campo(campos, 6)
            tipo_item = self._campo(campos, 7)
            ncm = self._campo(campos, 8)

            if not codigo:
                correcoes.append(
                    self._manual(
                        numero_linha,
                        "0200",
                        codigo,
                        "Alta",
                        "Código do item não informado.",
                        "Preencher o COD_ITEM no cadastro do produto.",
                    )
                )
            if not descricao.strip():
                correcoes.append(
                    self._manual(
                        numero_linha,
                        "0200",
                        codigo,
                        "Alta",
                        "Descrição do item não informada.",
                        "Preencher a descrição do produto no cadastro.",
                    )
                )

            # Serviços (TIPO_ITEM 09) podem não possuir unidade de estoque/NCM.
            if tipo_item != "09" and not unidade.strip():
                candidatas = {valor.strip() for valor in unidades_c170.get(codigo, set()) if valor.strip()}
                if len(candidatas) == 1:
                    unidade_inferida = next(iter(candidatas))
                    correcoes.append(
                        self._automatica(
                            numero_linha,
                            "0200",
                            codigo,
                            "Média",
                            "Unidade do item não informada no 0200.",
                            f"Preencher UNID_INV com '{unidade_inferida}', encontrada de forma única nos C170 do item.",
                            indice_campo=6,
                            anterior=unidade,
                            novo=unidade_inferida,
                        )
                    )
                else:
                    correcoes.append(
                        self._manual(
                            numero_linha,
                            "0200",
                            codigo,
                            "Média",
                            "Unidade do item não informada no 0200.",
                            "Revisar a unidade de inventário do produto.",
                        )
                    )

            if tipo_item != "09":
                if not ncm.strip():
                    correcoes.append(
                        self._manual(
                            numero_linha,
                            "0200",
                            codigo,
                            "Alta",
                            "NCM não informado.",
                            "Consultar e preencher o NCM correto do produto.",
                        )
                    )
                elif not self._ncm_valido(ncm):
                    ncm_normalizado = self._somente_digitos(ncm)
                    if len(ncm_normalizado) == 8:
                        correcoes.append(
                            self._automatica(
                                numero_linha,
                                "0200",
                                codigo,
                                "Média",
                                f"NCM fora do formato numérico de 8 dígitos: '{ncm}'.",
                                f"Normalizar o NCM para '{ncm_normalizado}'.",
                                indice_campo=8,
                                anterior=ncm,
                                novo=ncm_normalizado,
                            )
                        )
                    else:
                        correcoes.append(
                            self._manual(
                                numero_linha,
                                "0200",
                                codigo,
                                "Alta",
                                f"NCM inválido: '{ncm}'.",
                                "Consultar e preencher um NCM válido com 8 dígitos.",
                            )
                        )

        for codigo, ocorrencias in duplicados_0200.items():
            unicas = {(self._campo(campos, 3), self._campo(campos, 6), self._campo(campos, 8)) for _, campos in ocorrencias}
            gravidade = "Alta" if len(unicas) > 1 else "Média"
            linhas_texto = ", ".join(str(numero) for numero, _ in sorted(set((n, tuple(c)) for n, c in ocorrencias)))
            correcoes.append(
                self._manual(
                    min(numero for numero, _ in ocorrencias),
                    "0200",
                    codigo,
                    gravidade,
                    f"Código de item duplicado no 0200 (linhas {linhas_texto}).",
                    "Revisar os cadastros duplicados; não remover automaticamente.",
                )
            )

        self._progresso(progresso, 60, "Auditando itens de documentos (C170)...")
        for numero_linha, campos in linhas_c170:
            codigo = self._campo(campos, 3)
            quantidade = self._campo(campos, 5)
            unidade = self._campo(campos, 6)
            valor_item = self._campo(campos, 7)
            cst_icms = self._campo(campos, 10)
            cfop = self._campo(campos, 11)
            cst_pis = self._campo(campos, 25).strip()
            aliquota_pis = self._campo(campos, 27).strip()
            cst_cofins = self._campo(campos, 31).strip()
            aliquota_cofins = self._campo(campos, 33).strip()

            if not codigo:
                correcoes.append(
                    self._manual(
                        numero_linha,
                        "C170",
                        codigo,
                        "Alta",
                        "Código do item não informado.",
                        "Identificar o produto e preencher o COD_ITEM do C170.",
                    )
                )
            elif codigo not in registros_0200:
                correcoes.append(
                    self._manual(
                        numero_linha,
                        "C170",
                        codigo,
                        "Alta",
                        "Produto utilizado no C170 não existe no cadastro 0200.",
                        "Incluir o produto no 0200 ou corrigir o código do item.",
                    )
                )

            cadastro = registros_0200.get(codigo)
            unidade_0200 = self._campo(cadastro[1], 6).strip() if cadastro else ""
            if not unidade.strip():
                if unidade_0200:
                    correcoes.append(
                        self._automatica(
                            numero_linha,
                            "C170",
                            codigo,
                            "Média",
                            "Unidade não informada no item C170.",
                            f"Preencher UNID com '{unidade_0200}', conforme o cadastro 0200.",
                            indice_campo=6,
                            anterior=unidade,
                            novo=unidade_0200,
                        )
                    )
                else:
                    correcoes.append(
                        self._manual(
                            numero_linha,
                            "C170",
                            codigo,
                            "Média",
                            "Unidade não informada no item C170.",
                            "Revisar a unidade do item e o cadastro 0200.",
                        )
                    )
            elif unidade_0200 and unidade.strip() != unidade_0200:
                correcoes.append(
                    self._manual(
                        numero_linha,
                        "C170",
                        codigo,
                        "Média",
                        f"Unidade do C170 ('{unidade.strip()}') difere do 0200 ('{unidade_0200}').",
                        "Confirmar se existe conversão de unidade; não alterar automaticamente.",
                    )
                )

            if self._numero_zerado_ou_invalido(quantidade):
                correcoes.append(
                    self._manual(
                        numero_linha,
                        "C170",
                        codigo,
                        "Alta",
                        f"Quantidade zerada ou inválida: '{quantidade}'.",
                        "Revisar a quantidade escriturada do item.",
                    )
                )
            if self._numero_zerado_ou_invalido(valor_item):
                correcoes.append(
                    self._manual(
                        numero_linha,
                        "C170",
                        codigo,
                        "Alta",
                        f"Valor do item zerado ou inválido: '{valor_item}'.",
                        "Revisar o valor escriturado do item.",
                    )
                )

            if not cst_icms.strip():
                correcoes.append(
                    self._manual(
                        numero_linha,
                        "C170",
                        codigo,
                        "Alta",
                        "CST do ICMS não informado.",
                        "Revisar a tributação do item antes de gerar nova escrituração.",
                    )
                )
            elif not (len(cst_icms.strip()) == 3 and cst_icms.strip().isdigit()):
                correcoes.append(
                    self._manual(
                        numero_linha,
                        "C170",
                        codigo,
                        "Alta",
                        f"CST do ICMS fora do formato esperado: '{cst_icms}'.",
                        "Revisar origem e CST/CSOSN; não completar zeros automaticamente.",
                    )
                )

            if not cfop.strip():
                correcoes.append(
                    self._manual(
                        numero_linha,
                        "C170",
                        codigo,
                        "Alta",
                        "CFOP não informado.",
                        "Revisar a natureza da operação e preencher o CFOP correto.",
                    )
                )
            elif not (len(cfop.strip()) == 4 and cfop.strip().isdigit()):
                cfop_normalizado = self._somente_digitos(cfop)
                if len(cfop_normalizado) == 4:
                    correcoes.append(
                        self._automatica(
                            numero_linha,
                            "C170",
                            codigo,
                            "Média",
                            f"CFOP fora do formato numérico de 4 dígitos: '{cfop}'.",
                            f"Normalizar o CFOP para '{cfop_normalizado}'.",
                            indice_campo=11,
                            anterior=cfop,
                            novo=cfop_normalizado,
                        )
                    )
                else:
                    correcoes.append(
                        self._manual(
                            numero_linha,
                            "C170",
                            codigo,
                            "Alta",
                            f"CFOP inválido: '{cfop}'.",
                            "Revisar e preencher um CFOP válido com 4 dígitos.",
                        )
                    )

            # Sprint 17.3.4 — correções determinísticas espelhadas do PGE.
            if cfop.strip() == "1929":
                correcoes.append(
                    self._manual(
                        numero_linha,
                        "C170",
                        codigo,
                        "Alta",
                        "CFOP 1929 foi rejeitado pelo PGE 6.1.2.",
                        "Revisar a natureza da operação e escolher o CFOP correto; não há troca automática segura.",
                    )
                )

            entrada = len(cfop.strip()) == 4 and cfop.strip().isdigit() and cfop.strip()[0] in {"1", "2", "3"}
            if entrada:
                if cst_pis == "08":
                    correcoes.append(
                        self._automatica(
                            numero_linha,
                            "C170",
                            codigo,
                            "Alta",
                            "CST_PIS 08 é código de saída e foi usado em operação de entrada/aquisição.",
                            "Converter para CST 74 (aquisição sem incidência), preservando a natureza sem incidência.",
                            indice_campo=25,
                            anterior=cst_pis,
                            novo="74",
                        )
                    )
                elif cst_pis and not self._cst_entrada_valido(cst_pis):
                    correcoes.append(
                        self._manual(
                            numero_linha,
                            "C170",
                            codigo,
                            "Alta",
                            f"CST_PIS '{cst_pis}' inválido para operação de entrada/aquisição.",
                            "Selecionar CST entre 50-66, 70-75, 98 ou 99 conforme o direito ao crédito.",
                        )
                    )

                if cst_cofins == "08":
                    correcoes.append(
                        self._automatica(
                            numero_linha,
                            "C170",
                            codigo,
                            "Alta",
                            "CST_COFINS 08 é código de saída e foi usado em operação de entrada/aquisição.",
                            "Converter para CST 74 (aquisição sem incidência), preservando a natureza sem incidência.",
                            indice_campo=31,
                            anterior=cst_cofins,
                            novo="74",
                        )
                    )
                elif cst_cofins and not self._cst_entrada_valido(cst_cofins):
                    correcoes.append(
                        self._manual(
                            numero_linha,
                            "C170",
                            codigo,
                            "Alta",
                            f"CST_COFINS '{cst_cofins}' inválido para operação de entrada/aquisição.",
                            "Selecionar CST entre 50-66, 70-75, 98 ou 99 conforme o direito ao crédito.",
                        )
                    )

            aliquotas_basicas = {
                "1": ("1,6500", "7,6000"),
                "2": ("0,6500", "3,0000"),
            }
            esperadas = aliquotas_basicas.get(ind_inc_trib)
            if esperadas:
                pis_esperada, cofins_esperada = esperadas
                if cst_pis == "01" and self._numero_zerado_ou_invalido(aliquota_pis):
                    correcoes.append(
                        self._automatica(
                            numero_linha,
                            "C170",
                            codigo,
                            "Alta",
                            f"CST_PIS 01 com alíquota básica zerada ({aliquota_pis or 'vazia'}).",
                            f"Preencher ALIQ_PIS com {pis_esperada} conforme IND_INC_TRIB={ind_inc_trib}.",
                            indice_campo=27,
                            anterior=aliquota_pis,
                            novo=pis_esperada,
                        )
                    )
                if cst_cofins == "01" and self._numero_zerado_ou_invalido(aliquota_cofins):
                    correcoes.append(
                        self._automatica(
                            numero_linha,
                            "C170",
                            codigo,
                            "Alta",
                            f"CST_COFINS 01 com alíquota básica zerada ({aliquota_cofins or 'vazia'}).",
                            f"Preencher ALIQ_COFINS com {cofins_esperada} conforme IND_INC_TRIB={ind_inc_trib}.",
                            indice_campo=33,
                            anterior=aliquota_cofins,
                            novo=cofins_esperada,
                        )
                    )

        correcoes.sort(key=lambda item: (item.numero_linha, 0 if item.automatica else 1, item.registro))
        self._progresso(
            progresso,
            100,
            f"Análise concluída: {sum(1 for c in correcoes if c.automatica)} automáticas e "
            f"{sum(1 for c in correcoes if not c.automatica)} para revisão.",
        )
        return ResultadoAnaliseCorrecoes(correcoes=correcoes)

    def aplicar_automaticas(
        self,
        linhas: list[str],
        analise: ResultadoAnaliseCorrecoes,
        progresso: ProgressoCallback | None = None,
    ) -> list[str]:
        novas_linhas = list(linhas)
        por_linha: dict[int, list[CorrecaoSPED]] = defaultdict(list)
        for correcao in analise.automaticas:
            por_linha[correcao.numero_linha].append(correcao)

        total = max(len(por_linha), 1)
        for posicao, (numero_linha, correcoes) in enumerate(sorted(por_linha.items()), start=1):
            indice_lista = numero_linha - 1
            original = novas_linhas[indice_lista]
            fim_linha = self._fim_linha(original)
            texto = original.rstrip("\r\n")
            campos = texto.split("|")

            for correcao in correcoes:
                if correcao.indice_campo is None:
                    continue
                while len(campos) <= correcao.indice_campo:
                    campos.append("")
                campos[correcao.indice_campo] = correcao.valor_novo

            novas_linhas[indice_lista] = "|".join(campos) + fim_linha
            percentual = 10 + int((posicao / total) * 80)
            self._progresso(progresso, percentual, f"Aplicando correções seguras: {posicao}/{len(por_linha)} linhas.")

        self._progresso(progresso, 100, "Correções automáticas aplicadas em uma nova cópia do SPED.")
        return novas_linhas

    def salvar(
        self,
        linhas_corrigidas: list[str],
        caminho_saida: str | Path,
        encoding: str,
        analise: ResultadoAnaliseCorrecoes,
    ) -> ResultadoGeracaoSPED:
        destino = Path(caminho_saida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("w", encoding=encoding, newline="") as stream:
            stream.writelines(linhas_corrigidas)

        relatorio = destino.with_name(destino.stem + "_RELATORIO.txt")
        self._salvar_relatorio(relatorio, destino, analise)
        return ResultadoGeracaoSPED(
            caminho_sped=destino,
            caminho_relatorio=relatorio,
            total_aplicadas=analise.total_automaticas,
            total_pendencias_manuais=analise.total_manuais,
        )

    @staticmethod
    def _salvar_relatorio(
        caminho: Path,
        sped_gerado: Path,
        analise: ResultadoAnaliseCorrecoes,
    ) -> None:
        with caminho.open("w", encoding="utf-8") as stream:
            stream.write("FiscalPro — Relatório de Correções Inteligentes\n")
            stream.write("=" * 58 + "\n\n")
            stream.write(f"SPED gerado: {sped_gerado}\n")
            stream.write(f"Correções automáticas aplicadas: {analise.total_automaticas}\n")
            stream.write(f"Pendências para revisão manual: {analise.total_manuais}\n\n")
            stream.write(
                "IMPORTANTE: a Sprint 17.3.5 só altera automaticamente os casos determinísticos "
                "espelhados do PGE (alíquota básica CST 01 e CST 08->74 em entrada), além das "
                "normalizações estruturais já aprovadas. Bases e valores fiscais não são inventados.\n\n"
            )
            for item in analise.correcoes:
                stream.write(
                    f"Linha {item.numero_linha} | {item.registro} | Item {item.codigo_item or '-'} | "
                    f"{item.gravidade} | {item.modo}\n"
                )
                stream.write(f"Problema: {item.problema}\n")
                stream.write(f"Ação: {item.acao}\n")
                if item.automatica:
                    stream.write(f"Antes: {item.valor_anterior!r}\nDepois: {item.valor_novo!r}\n")
                stream.write("-" * 58 + "\n")

    @staticmethod
    def _manual(
        numero_linha: int,
        registro: str,
        codigo: str,
        gravidade: str,
        problema: str,
        acao: str,
    ) -> CorrecaoSPED:
        return CorrecaoSPED(
            numero_linha=numero_linha,
            registro=registro,
            codigo_item=codigo,
            gravidade=gravidade,
            problema=problema,
            acao=acao,
            automatica=False,
        )

    @staticmethod
    def _automatica(
        numero_linha: int,
        registro: str,
        codigo: str,
        gravidade: str,
        problema: str,
        acao: str,
        indice_campo: int,
        anterior: str,
        novo: str,
    ) -> CorrecaoSPED:
        return CorrecaoSPED(
            numero_linha=numero_linha,
            registro=registro,
            codigo_item=codigo,
            gravidade=gravidade,
            problema=problema,
            acao=acao,
            automatica=True,
            indice_campo=indice_campo,
            valor_anterior=anterior,
            valor_novo=novo,
        )

    @staticmethod
    def _campo(campos: list[str], indice: int) -> str:
        return campos[indice] if indice < len(campos) else ""

    @staticmethod
    def _somente_digitos(valor: str) -> str:
        return re.sub(r"\D", "", valor or "")

    @classmethod
    def _ncm_valido(cls, valor: str) -> bool:
        texto = (valor or "").strip()
        return len(texto) == 8 and texto.isdigit()


    @staticmethod
    def _cst_entrada_valido(valor: str) -> bool:
        texto = (valor or "").strip()
        if not (len(texto) == 2 and texto.isdigit()):
            return False
        numero = int(texto)
        return 50 <= numero <= 66 or 70 <= numero <= 75 or texto in {"98", "99"}


    @staticmethod
    def _numero_zerado_ou_invalido(valor: str) -> bool:
        texto = (valor or "").strip()
        if not texto:
            return True
        try:
            if "," in texto and "." in texto:
                normalizado = texto.replace(".", "").replace(",", ".")
            elif "," in texto:
                normalizado = texto.replace(",", ".")
            else:
                normalizado = texto
            return float(normalizado) <= 0
        except ValueError:
            return True

    @staticmethod
    def _fim_linha(linha: str) -> str:
        if linha.endswith("\r\n"):
            return "\r\n"
        if linha.endswith("\n"):
            return "\n"
        if linha.endswith("\r"):
            return "\r"
        return ""

    @staticmethod
    def _progresso(callback: ProgressoCallback | None, percentual: int, mensagem: str) -> None:
        if callback:
            callback(percentual, mensagem)
