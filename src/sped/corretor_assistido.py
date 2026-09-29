from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Callable

from .pre_validador import ApontamentoPVA, PreValidadorPVA, ResultadoPreValidacaoPVA
from .recalculador_piscofins import RecalculadorPISCOFINS
from .reapurador_bloco_m import ReapuradorBlocoM
from .consolidador_creditos_bloco_m import ConsolidadorCreditosBlocoM
from .saneador_cod_item import SaneadorCODItem

ProgressoCallback = Callable[[int, str], None]


@dataclass(slots=True)
class PropostaCorrecaoAssistida:
    identificador: int
    selecionada: bool
    modo: str
    nivel: str
    categoria: str
    registro: str
    numero_linha: int | None
    campo: str
    valor_atual: str
    valor_sugerido: str
    justificativa: str
    documento: str = ""
    codigo_item: str = ""
    indice_campo: int | None = None
    tipo_acao: str = "CAMPO"
    editavel: bool = False
    segura: bool = False

    @property
    def aplicavel(self) -> bool:
        if self.tipo_acao in {"TOTALIZADORES", "SEPARADORES", "CONSOLIDAR_CREDITO_M", "SANEAR_COD_ITEM_DUPLICADO"}:
            return True
        return self.numero_linha is not None and self.indice_campo is not None and bool(self.valor_sugerido)


@dataclass(slots=True)
class ResultadoPreparacaoAssistida:
    propostas: list[PropostaCorrecaoAssistida] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.propostas)

    @property
    def selecionadas(self) -> list[PropostaCorrecaoAssistida]:
        return [p for p in self.propostas if p.selecionada and p.aplicavel]

    @property
    def automaticas_seguras(self) -> list[PropostaCorrecaoAssistida]:
        return [p for p in self.propostas if p.segura and p.aplicavel]

    @property
    def sugestoes(self) -> list[PropostaCorrecaoAssistida]:
        return [p for p in self.propostas if p.modo == "Sugestão para confirmar"]

    @property
    def preenchimentos(self) -> list[PropostaCorrecaoAssistida]:
        return [p for p in self.propostas if p.modo == "Preencher manualmente"]

    @property
    def somente_revisao(self) -> list[PropostaCorrecaoAssistida]:
        return [p for p in self.propostas if p.modo == "Somente revisão"]

    def marcar_todas_aplicaveis(self) -> int:
        """Marca em lote apenas propostas que já possuem ação/valor aplicável."""
        total = 0
        for proposta in self.propostas:
            if proposta.aplicavel:
                proposta.selecionada = True
                total += 1
        return total

    def obter(self, identificador: int) -> PropostaCorrecaoAssistida:
        for proposta in self.propostas:
            if proposta.identificador == identificador:
                return proposta
        raise KeyError(f"Proposta {identificador} não encontrada.")


@dataclass(frozen=True, slots=True)
class CorrecaoAplicada:
    numero_linha: int | None
    registro: str
    campo: str
    valor_anterior: str
    valor_novo: str
    justificativa: str


@dataclass(frozen=True, slots=True)
class ResultadoAplicacaoAssistida:
    caminho_sped: Path
    caminho_relatorio: Path
    total_aplicadas: int
    total_ignoradas: int
    erros_antes: int
    avisos_antes: int
    erros_depois: int
    avisos_depois: int
    aplicadas: tuple[CorrecaoAplicada, ...]


class CorretorAssistidoPVA:
    """Transforma apontamentos do pré-validador em correções confirmáveis.

    O módulo nunca altera o arquivo original. Formatações determinísticas podem
    vir marcadas por padrão. Cálculos, unidades e preenchimentos fiscais ficam
    desmarcados até a confirmação da usuária.
    """

    # Índices no registro sem os separadores externos: 0 = código do registro.
    CAMPOS: dict[str, dict[str, int]] = {
        "0150": {"COD_PART": 1, "CNPJ": 4, "CPF": 5},
        "0190": {"UNID": 1},
        "0200": {"COD_ITEM": 1, "DESCR_ITEM": 2, "UNID_INV": 5, "COD_NCM": 7},
        "A100": {
            "COD_PART": 3, "COD_SIT": 4, "NUM_DOC": 7, "CHV_DOC": 8,
            "DT_DOC": 9, "DT_EXE_SERV": 10, "VL_DOC": 11,
            "VL_PIS": 15, "VL_COFINS": 17,
        },
        "A170": {
            "NUM_ITEM": 1, "COD_ITEM": 2, "VL_ITEM": 4, "CST_PIS": 8,
            "VL_BC_PIS": 9, "ALIQ_PIS": 10, "VL_PIS": 11,
            "CST_COFINS": 12, "VL_BC_COFINS": 13, "ALIQ_COFINS": 14,
            "VL_COFINS": 15,
        },
        "C100": {
            "COD_PART": 3, "COD_MOD": 4, "COD_SIT": 5, "NUM_DOC": 7,
            "CHV_DOC": 8, "DT_DOC": 9, "DT_E_S": 10, "VL_DOC": 11,
            "VL_MERC": 15, "VL_PIS": 25, "VL_COFINS": 26,
        },
        "C170": {
            "NUM_ITEM": 1, "COD_ITEM": 2, "QTD": 4, "UNID": 5,
            "VL_ITEM": 6, "CST_ICMS": 9, "CFOP": 10,
            "CST_PIS": 24, "VL_BC_PIS": 25, "ALIQ_PIS": 26,
            "QUANT_BC_PIS": 27, "ALIQ_PIS_QUANT": 28, "VL_PIS": 29,
            "CST_COFINS": 30, "VL_BC_COFINS": 31, "ALIQ_COFINS": 32,
            "QUANT_BC_COFINS": 33, "ALIQ_COFINS_QUANT": 34, "VL_COFINS": 35,
        },
        "C190": {"CST_ICMS": 1, "CFOP": 2, "ALIQ_ICMS": 3, "VL_OPR": 4},
        "D100": {
            "COD_PART": 3, "COD_MOD": 4, "COD_SIT": 5, "NUM_DOC": 8,
            "CHV_DOC": 9, "DT_DOC": 10, "DT_A_P": 11,
        },
        "D101": {
            "CST_PIS": 3, "VL_BC_PIS": 5, "ALIQ_PIS": 6, "VL_PIS": 7,
        },
        "D105": {
            "CST_COFINS": 3, "VL_BC_COFINS": 5, "ALIQ_COFINS": 6,
            "VL_COFINS": 7,
        },
        "M100": {
            "VL_BC_PIS": 3, "ALIQ_PIS": 4, "QUANT_BC_PIS": 5,
            "ALIQ_PIS_QUANT": 6, "VL_PIS": 7,
        },
        "M500": {
            "VL_BC_COFINS": 3, "ALIQ_COFINS": 4, "QUANT_BC_COFINS": 5,
            "ALIQ_COFINS_QUANT": 6, "VL_COFINS": 7,
        },
        "0990": {"QTD_LIN": 1}, "A990": {"QTD_LIN": 1},
        "B990": {"QTD_LIN": 1}, "C990": {"QTD_LIN": 1},
        "D990": {"QTD_LIN": 1}, "E990": {"QTD_LIN": 1},
        "F990": {"QTD_LIN": 1}, "G990": {"QTD_LIN": 1},
        "H990": {"QTD_LIN": 1}, "I990": {"QTD_LIN": 1},
        "K990": {"QTD_LIN": 1}, "M990": {"QTD_LIN": 1},
        "P990": {"QTD_LIN": 1}, "1990": {"QTD_LIN": 1},
        "9900": {"REG_BLC": 1, "QTD_REG_BLC": 2},
        "9990": {"QTD_LIN": 1}, "9999": {"QTD_LIN": 1},
    }

    TAMANHOS_CODIGO = {
        "COD_MOD": 2, "COD_SIT": 2, "CST_PIS": 2, "CST_COFINS": 2,
        "CST_ICMS": 3, "CFOP": 4, "COD_NCM": 8, "CNPJ": 14, "CPF": 11,
    }

    CAMPOS_DECIMAIS = {
        "VL_ITEM", "VL_DOC", "VL_MERC", "VL_OPR", "VL_PIS", "VL_COFINS",
        "VL_BC_PIS", "VL_BC_COFINS", "ALIQ_PIS", "ALIQ_COFINS",
        "ALIQ_ICMS", "QTD", "QUANT_BC_PIS", "QUANT_BC_COFINS",
        "ALIQ_PIS_QUANT", "ALIQ_COFINS_QUANT",
    }

    def preparar(
        self,
        linhas: list[str],
        pre_validacao: ResultadoPreValidacaoPVA,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoPreparacaoAssistida:
        self._progresso(progresso, 5, "Lendo apontamentos do Pré-Validador PVA...")
        registros = self._mapear_linhas(linhas)
        unidades_0200, unidades_c170 = self._mapear_unidades(registros)
        ind_inc_trib = self._indicador_incidencia(registros)
        produtos_0200 = self._mapear_produtos_0200(registros)
        contexto_c170 = self._mapear_contexto_c170(linhas)
        uf_empresa = self._uf_empresa(registros)
        propostas: list[PropostaCorrecaoAssistida] = []
        vistos: set[tuple[int | None, str, str]] = set()
        precisa_totalizadores = False
        precisa_separadores = False

        # Hotfix 17.3.9 — as duplicidades M100/M500 que podem ser
        # consolidadas sem decisão fiscal viram uma única ação automática
        # por chave, em vez de duas linhas "Somente revisão".
        consolidador_m = ConsolidadorCreditosBlocoM()
        planos_credito_por_linha = consolidador_m.mapa_por_linha_pai(linhas)
        grupos_credito_vistos: set[tuple[str, tuple[str, str, str, str]]] = set()

        # Hotfix 17.3.10 — saneamento em lote do COD_ITEM duplicado.
        # Em vez de várias linhas vermelhas, a interface mostra uma única ação:
        # exclui cópias 0200 realmente idênticas e renomeia cadastros divergentes
        # preservando os dados, sem adivinhar o vínculo dos C170.
        saneador_cod_item = SaneadorCODItem()
        planos_cod_item = saneador_cod_item.analisar(linhas)
        codigos_cod_item_trataveis = {p.codigo_original for p in planos_cod_item}
        if planos_cod_item:
            qtd_grupos, qtd_exclusoes, qtd_renomeacoes = saneador_cod_item.resumo(linhas)
            propostas.append(
                PropostaCorrecaoAssistida(
                    identificador=len(propostas) + 1,
                    selecionada=True,
                    modo="Automática segura",
                    nivel="ERRO",
                    categoria="Saneamento COD_ITEM",
                    registro="0200",
                    numero_linha=planos_cod_item[0].linhas_0200[0],
                    campo="COD_ITEM",
                    valor_atual=f"{qtd_grupos} grupo(s) de COD_ITEM duplicado",
                    valor_sugerido=(
                        f"Remover {qtd_exclusoes} cópia(s) idêntica(s) e renomear "
                        f"{qtd_renomeacoes} cadastro(s) divergente(s)"
                    ),
                    justificativa=(
                        "O PGE exige COD_ITEM único. O FiscalPro remove somente cópias "
                        "integralmente idênticas; quando o mesmo código representa produtos "
                        "diferentes, preserva ambos e renomeia o cadastro posterior com sufixo "
                        "-D2/-D3, sem remapear documentos por aproximação."
                    ),
                    tipo_acao="SANEAR_COD_ITEM_DUPLICADO",
                    editavel=False,
                    segura=True,
                )
            )

        total = max(len(pre_validacao.apontamentos), 1)
        for posicao, apontamento in enumerate(pre_validacao.apontamentos, start=1):
            if (
                apontamento.registro.upper() == "0200"
                and apontamento.campo == "COD_ITEM"
                and apontamento.codigo_item in codigos_cod_item_trataveis
                and (
                    apontamento.categoria in {"Duplicidade PGE", "Coerência COD_ITEM"}
                    or "duplic" in apontamento.mensagem.lower()
                    or "mesma identificação" in apontamento.mensagem.lower()
                )
            ):
                # A ocorrência já está coberta pela ação única de saneamento em lote.
                continue
            if (
                apontamento.registro.upper() in {"M100", "M500"}
                and apontamento.numero_linha is not None
                and (
                    "COD_CRED/IND_CRED_ORI" in (apontamento.campo or "")
                    or "COD_CRED/IND_CRED_ORI" in apontamento.mensagem
                )
            ):
                plano = planos_credito_por_linha.get(apontamento.numero_linha)
                if plano is not None and plano.identificador not in grupos_credito_vistos:
                    grupos_credito_vistos.add(plano.identificador)
                    propostas.append(
                        PropostaCorrecaoAssistida(
                            identificador=len(propostas) + 1,
                            selecionada=True,
                            modo="Automática segura",
                            nivel="ERRO",
                            categoria="Consolidação Bloco M",
                            registro=plano.registro,
                            numero_linha=plano.linhas_pais[0],
                            campo="COD_CRED/IND_CRED_ORI/ALIQ",
                            valor_atual=(
                                f"{len(plano.linhas_pais)} registros duplicados — linhas "
                                + ", ".join(str(n) for n in plano.linhas_pais)
                            ),
                            valor_sugerido=(
                                f"Consolidar em 1 — base {self._decimal_sped(plano.base_total, 2)}; "
                                f"crédito {self._decimal_sped(plano.credito_total, 2)}"
                            ),
                            justificativa=(
                                f"O PGE exige uma única chave de crédito. Os {plano.registro_filho} "
                                "dos registros duplicados têm bases conciliadas, chaves distintas, "
                                "sem ajustes e com desconto integral. O FiscalPro pode consolidar "
                                "e recalcular o crédito com segurança, preservando os filhos."
                            ),
                            tipo_acao="CONSOLIDAR_CREDITO_M",
                            editavel=False,
                            segura=True,
                        )
                    )
                # Se o grupo é seguro, todas as ocorrências da mesma chave já
                # estão representadas pela proposta acima. Se não é seguro,
                # cai no fluxo normal e continua como revisão.
                if plano is not None:
                    continue
            if apontamento.categoria == "Totalizadores":
                precisa_totalizadores = True
                continue
            if apontamento.categoria == "Estrutura" and apontamento.numero_linha:
                texto = linhas[apontamento.numero_linha - 1].rstrip("\r\n")
                if texto and (not texto.startswith("|") or not texto.endswith("|")):
                    precisa_separadores = True
                    continue

            chave = (apontamento.numero_linha, apontamento.registro, apontamento.campo)
            if chave in vistos and apontamento.campo:
                continue
            vistos.add(chave)
            propostas.append(
                self._criar_proposta(
                    len(propostas) + 1,
                    apontamento,
                    registros,
                    unidades_0200,
                    unidades_c170,
                    ind_inc_trib,
                    produtos_0200,
                    contexto_c170,
                    uf_empresa,
                )
            )
            if posicao % 100 == 0:
                percentual = 10 + int((posicao / total) * 70)
                self._progresso(progresso, percentual, f"Preparando correções: {posicao}/{total}...")

        if precisa_separadores:
            propostas.insert(
                0,
                PropostaCorrecaoAssistida(
                    identificador=0,
                    selecionada=True,
                    modo="Automática segura",
                    nivel="ERRO",
                    categoria="Estrutura",
                    registro="-",
                    numero_linha=None,
                    campo="SEPARADORES",
                    valor_atual="Linhas sem delimitadores",
                    valor_sugerido="Restaurar | no início/fim",
                    justificativa="Restaura somente os delimitadores externos das linhas apontadas.",
                    tipo_acao="SEPARADORES",
                    editavel=False,
                    segura=True,
                ),
            )

        if precisa_totalizadores:
            propostas.insert(
                0,
                PropostaCorrecaoAssistida(
                    identificador=-1,
                    selecionada=True,
                    modo="Automática segura",
                    nivel="ERRO",
                    categoria="Totalizadores",
                    registro="Bloco 9",
                    numero_linha=None,
                    campo="TOTALIZADORES",
                    valor_atual="Contagens divergentes",
                    valor_sugerido="Recalcular 9900, fechamentos e 9999",
                    justificativa=(
                        "Reconta os registros da cópia final, reconstrói o 9900 e atualiza "
                        "os fechamentos dos blocos sem alterar valores fiscais."
                    ),
                    tipo_acao="TOTALIZADORES",
                    editavel=False,
                    segura=True,
                ),
            )

        # Reatribui IDs positivos e estáveis para a interface.
        for indice, proposta in enumerate(propostas, start=1):
            proposta.identificador = indice

        self._progresso(
            progresso,
            100,
            f"Correção assistida preparada: {len(propostas)} item(ns) para análise.",
        )
        return ResultadoPreparacaoAssistida(propostas=propostas)

    def atualizar_proposta(
        self,
        resultado: ResultadoPreparacaoAssistida,
        identificador: int,
        valor_novo: str | None = None,
        selecionada: bool | None = None,
    ) -> PropostaCorrecaoAssistida:
        proposta = resultado.obter(identificador)
        if valor_novo is not None:
            if not proposta.editavel:
                raise RuntimeError("Esta linha é apenas informativa e não aceita edição direta.")
            if "|" in valor_novo or "\n" in valor_novo or "\r" in valor_novo:
                raise RuntimeError("O valor não pode conter '|', quebra de linha ou retorno de carro.")
            proposta.valor_sugerido = valor_novo.strip()
            proposta.selecionada = bool(proposta.valor_sugerido)
            if proposta.modo in {"Preencher manualmente", "Somente revisão"}:
                proposta.modo = "Valor informado pela usuária"
        if selecionada is not None:
            if selecionada and not proposta.aplicavel:
                raise RuntimeError("Informe um valor válido antes de marcar esta correção.")
            proposta.selecionada = selecionada
        return proposta

    def aplicar(
        self,
        linhas: list[str],
        encoding: str,
        tipo_sped: str,
        pre_validacao: ResultadoPreValidacaoPVA,
        preparacao: ResultadoPreparacaoAssistida,
        caminho_saida: str | Path,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAplicacaoAssistida:
        selecionadas = preparacao.selecionadas
        if not selecionadas:
            raise RuntimeError("Nenhuma correção foi marcada para aplicar.")

        self._progresso(progresso, 5, "Criando uma nova cópia para correção assistida...")
        novas_linhas = list(linhas)
        aplicadas: list[CorrecaoAplicada] = []
        recalcular_totalizadores = any(p.tipo_acao == "TOTALIZADORES" for p in selecionadas)
        restaurar_separadores = any(p.tipo_acao == "SEPARADORES" for p in selecionadas)
        consolidacoes_credito_m = [
            p for p in selecionadas if p.tipo_acao == "CONSOLIDAR_CREDITO_M"
        ]
        sanear_cod_item = any(
            p.tipo_acao == "SANEAR_COD_ITEM_DUPLICADO" for p in selecionadas
        )

        campos = [p for p in selecionadas if p.tipo_acao == "CAMPO"]
        for posicao, proposta in enumerate(campos, start=1):
            assert proposta.numero_linha is not None and proposta.indice_campo is not None
            indice_linha = proposta.numero_linha - 1
            anterior = self._obter_campo(novas_linhas[indice_linha], proposta.indice_campo)
            novas_linhas[indice_linha] = self._substituir_campo(
                novas_linhas[indice_linha], proposta.indice_campo, proposta.valor_sugerido
            )
            aplicadas.append(
                CorrecaoAplicada(
                    numero_linha=proposta.numero_linha,
                    registro=proposta.registro,
                    campo=proposta.campo,
                    valor_anterior=anterior,
                    valor_novo=proposta.valor_sugerido,
                    justificativa=proposta.justificativa,
                )
            )
            if posicao % 100 == 0:
                percentual = 10 + int((posicao / max(len(campos), 1)) * 45)
                self._progresso(progresso, percentual, f"Aplicando campos: {posicao}/{len(campos)}...")

        # Alíquotas básicas alteradas no C170 possuem dependências determinísticas:
        # o VL_PIS/VL_COFINS do item e os totais correspondentes do C100 pai.
        afetadas_piscofins: set[tuple[int, str]] = set()
        houve_correcao_tributaria_c170 = False
        for proposta in campos:
            if proposta.registro != "C170" or proposta.numero_linha is None:
                continue
            if proposta.campo in {"ALIQ_PIS", "ALIQ_COFINS", "CST_PIS", "CST_COFINS"}:
                houve_correcao_tributaria_c170 = True
            if proposta.campo == "ALIQ_PIS":
                afetadas_piscofins.add((proposta.numero_linha, "PIS"))
            elif proposta.campo == "ALIQ_COFINS":
                afetadas_piscofins.add((proposta.numero_linha, "COFINS"))

        if afetadas_piscofins:
            self._progresso(
                progresso, 60,
                "Recalculando PIS/COFINS dos itens e totais dos C100 afetados...",
            )
            recalculo = RecalculadorPISCOFINS().recalcular(
                novas_linhas, afetadas_piscofins, tipo_sped
            )
            novas_linhas = recalculo.linhas
            for alteracao in recalculo.alteracoes:
                aplicadas.append(
                    CorrecaoAplicada(
                        numero_linha=alteracao.numero_linha,
                        registro=alteracao.registro,
                        campo=alteracao.campo,
                        valor_anterior=alteracao.valor_anterior,
                        valor_novo=alteracao.valor_novo,
                        justificativa=alteracao.justificativa,
                    )
                )

        if houve_correcao_tributaria_c170:
            self._progresso(
                progresso, 68,
                "Sincronizando a apuração do Bloco M com os C170 corrigidos...",
            )
            reapuracao_m = ReapuradorBlocoM().sincronizar(linhas, novas_linhas, tipo_sped)
            novas_linhas = reapuracao_m.linhas
            if reapuracao_m.alteracoes:
                # O Bloco M alterado muda M990, 9900 e 9999. Reconta tudo na
                # mesma geração, sem exigir uma segunda ação da usuária.
                recalcular_totalizadores = True
            for alteracao in reapuracao_m.alteracoes:
                aplicadas.append(
                    CorrecaoAplicada(
                        numero_linha=alteracao.numero_linha,
                        registro=alteracao.registro,
                        campo=alteracao.campo,
                        valor_anterior=alteracao.valor_anterior,
                        valor_novo=alteracao.valor_novo,
                        justificativa=alteracao.justificativa,
                    )
                )

        if consolidacoes_credito_m:
            self._progresso(
                progresso, 72,
                "Consolidando créditos duplicados M100/M500 e recalculando o crédito...",
            )
            sementes = {
                p.numero_linha for p in consolidacoes_credito_m
                if p.numero_linha is not None
            }
            consolidacao = ConsolidadorCreditosBlocoM().consolidar(novas_linhas, sementes)
            novas_linhas = consolidacao.linhas
            if consolidacao.estrutura_alterada:
                recalcular_totalizadores = True
            for alteracao in consolidacao.alteracoes:
                aplicadas.append(
                    CorrecaoAplicada(
                        numero_linha=alteracao.numero_linha,
                        registro=alteracao.registro,
                        campo=alteracao.campo,
                        valor_anterior=alteracao.valor_anterior,
                        valor_novo=alteracao.valor_novo,
                        justificativa=alteracao.justificativa,
                    )
                )

        if sanear_cod_item:
            self._progresso(
                progresso, 76,
                "Saneando COD_ITEM duplicado no 0200 em lote...",
            )
            saneamento = SaneadorCODItem().sanear(novas_linhas)
            novas_linhas = saneamento.linhas
            if saneamento.estrutura_alterada:
                recalcular_totalizadores = True
            for alteracao in saneamento.alteracoes:
                aplicadas.append(
                    CorrecaoAplicada(
                        numero_linha=alteracao.numero_linha,
                        registro=alteracao.registro,
                        campo=alteracao.campo,
                        valor_anterior=alteracao.valor_anterior,
                        valor_novo=alteracao.valor_novo,
                        justificativa=alteracao.justificativa,
                    )
                )

        if restaurar_separadores:
            novas_linhas, aplicadas_sep = self._restaurar_separadores(novas_linhas)
            aplicadas.extend(aplicadas_sep)

        if recalcular_totalizadores:
            self._progresso(progresso, 62, "Recalculando bloco 9 e fechamentos...")
            novas_linhas, aplicadas_tot = self._recalcular_totalizadores(novas_linhas)
            aplicadas.extend(aplicadas_tot)

        self._progresso(progresso, 78, "Executando nova pré-validação na cópia corrigida...")
        resultado_depois = PreValidadorPVA().validar(novas_linhas, tipo_sped)

        destino = Path(caminho_saida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            raise FileExistsError(f"O arquivo de destino já existe: {destino}")
        encoding_saida = self._encoding_saida_sem_bom(encoding)
        with destino.open("w", encoding=encoding_saida, newline="") as stream:
            stream.writelines(novas_linhas)

        relatorio = destino.with_name(f"{destino.stem}_RELATORIO_CORRECAO_ASSISTIDA.txt")
        self._salvar_relatorio(
            relatorio,
            destino,
            pre_validacao,
            resultado_depois,
            aplicadas,
            preparacao,
        )
        self._progresso(progresso, 100, "Cópia corrigida, revalidada e relatada com sucesso.")
        return ResultadoAplicacaoAssistida(
            caminho_sped=destino,
            caminho_relatorio=relatorio,
            total_aplicadas=len(aplicadas),
            total_ignoradas=len([p for p in preparacao.propostas if not p.selecionada]),
            erros_antes=len(pre_validacao.erros),
            avisos_antes=len(pre_validacao.avisos),
            erros_depois=len(resultado_depois.erros),
            avisos_depois=len(resultado_depois.avisos),
            aplicadas=tuple(aplicadas),
        )

    def _criar_proposta(
        self,
        identificador: int,
        apontamento: ApontamentoPVA,
        registros: dict[int, tuple[str, tuple[str, ...]]],
        unidades_0200: dict[str, str],
        unidades_c170: dict[str, set[str]],
        ind_inc_trib: str,
        produtos_0200: dict[str, tuple[str, str]],
        contexto_c170: dict[int, tuple[str, str]],
        uf_empresa: str,
    ) -> PropostaCorrecaoAssistida:
        registro = apontamento.registro.upper()
        indice = self.CAMPOS.get(registro, {}).get(apontamento.campo)
        campos = registros.get(apontamento.numero_linha or -1, ("", tuple()))[1]
        atual = campos[indice] if indice is not None and indice < len(campos) else ""
        sugerido, seguro, justificativa = self._sugerir(
            apontamento, campos, indice, unidades_0200, unidades_c170, ind_inc_trib,
            produtos_0200, contexto_c170, uf_empresa
        )

        editavel = indice is not None and apontamento.numero_linha is not None
        if sugerido:
            modo = "Automática segura" if seguro else "Sugestão para confirmar"
        elif (
            editavel
            and apontamento.categoria not in {"Duplicidade", "Hierarquia"}
            and "duplicad" not in apontamento.mensagem.lower()
        ):
            modo = "Preencher manualmente"
        else:
            modo = "Somente revisão"
            editavel = False

        return PropostaCorrecaoAssistida(
            identificador=identificador,
            selecionada=bool(sugerido and seguro),
            modo=modo,
            nivel=apontamento.nivel,
            categoria=apontamento.categoria,
            registro=registro or "-",
            numero_linha=apontamento.numero_linha,
            campo=apontamento.campo or "-",
            valor_atual=atual,
            valor_sugerido=sugerido,
            justificativa=justificativa or apontamento.sugestao or apontamento.mensagem,
            documento=apontamento.documento,
            codigo_item=apontamento.codigo_item,
            indice_campo=indice,
            editavel=editavel,
            segura=seguro,
        )

    def _sugerir(
        self,
        apontamento: ApontamentoPVA,
        campos: tuple[str, ...],
        indice: int | None,
        unidades_0200: dict[str, str],
        unidades_c170: dict[str, set[str]],
        ind_inc_trib: str,
        produtos_0200: dict[str, tuple[str, str]],
        contexto_c170: dict[int, tuple[str, str]],
        uf_empresa: str,
    ) -> tuple[str, bool, str]:
        if indice is None:
            return "", False, apontamento.sugestao
        atual = campos[indice].strip() if indice < len(campos) else ""
        campo = apontamento.campo
        registro = apontamento.registro.upper()

        if campo in {"CNPJ", "CPF", "COD_NCM", "CFOP", "COD_MOD", "COD_SIT", "CST_PIS", "CST_COFINS", "CST_ICMS"}:
            digitos = re.sub(r"\D", "", atual)
            tamanho = self.TAMANHOS_CODIGO[campo]
            if len(digitos) == tamanho and digitos != atual:
                return digitos, True, f"Remove pontuação e mantém os {tamanho} dígitos existentes."
            if digitos and len(digitos) < tamanho and atual.strip().isdigit():
                return digitos.zfill(tamanho), False, (
                    f"Completa o formato para {tamanho} dígitos. Confirme o conteúdo fiscal antes de aplicar."
                )

        # Hotfix 17.3.11 — CFOP de combustível rejeitado pelo PGE.
        # No arquivo real o CFOP 1929 foi usado para uma compra de GASOLINA
        # destinada ao próprio consumo. Quando o 0200 confirma combustível e
        # a chave da NF-e permite determinar a UF do emitente, o CFOP correto
        # pode ser definido sem intervenção: 1.653 (mesma UF) ou 2.653 (outra UF).
        if registro == "C170" and campo == "CFOP" and atual == "1929":
            codigo_item = campos[2].strip() if len(campos) > 2 else ""
            descricao, ncm = produtos_0200.get(codigo_item, ("", ""))
            descricao_norm = self._sem_acentos(descricao).upper()
            combustivel = (
                ncm.startswith("271012")
                or any(
                    termo in descricao_norm
                    for termo in ("GASOLINA", "ETANOL", "DIESEL", "GNV", "COMBUSTIVEL")
                )
            )
            ind_oper, chave = contexto_c170.get(apontamento.numero_linha or -1, ("", ""))
            codigo_uf_empresa = self._CODIGO_UF.get(uf_empresa.upper(), "")
            codigo_uf_emitente = chave[:2] if len(chave) == 44 and chave.isdigit() else ""
            if combustivel and ind_oper == "0" and codigo_uf_empresa and codigo_uf_emitente:
                cfop_correto = "1653" if codigo_uf_emitente == codigo_uf_empresa else "2653"
                return cfop_correto, True, (
                    f"O item '{descricao or codigo_item}' é combustível e o documento é uma entrada. "
                    f"A chave indica emitente {'da mesma UF' if cfop_correto == '1653' else 'de outra UF'}; "
                    f"o FiscalPro substitui o CFOP 1929 por {cfop_correto} — compra de combustível "
                    "por consumidor ou usuário final."
                )

        # Hotfix 17.3.8 — CST de entrada em lote.
        # O PGE rejeita CST 08 em operações de aquisição. Quando o próprio
        # C170 mostra CFOP de entrada (1xxx/2xxx/3xxx), a conversão 08 -> 74
        # preserva a natureza "sem incidência" e é determinística.
        if registro == "C170" and campo in {"CST_PIS", "CST_COFINS"}:
            cfop = campos[10].strip() if len(campos) > 10 else ""
            entrada = len(cfop) == 4 and cfop.isdigit() and cfop[0] in {"1", "2", "3"}
            if entrada and atual == "08":
                return "74", True, (
                    f"CST 08 é código de saída e foi usado em operação de entrada (CFOP {cfop}). "
                    "O FiscalPro converte em lote para CST 74 — aquisição sem incidência — "
                    "mantendo bases e valores zerados."
                )

        if campo in {"DT_DOC", "DT_E_S", "DT_EXE_SERV", "DT_A_P"}:
            digitos = re.sub(r"\D", "", atual)
            if len(digitos) == 8 and digitos != atual:
                return digitos, True, "Remove separadores da data e preserva DDMMAAAA."

        if campo == "CHV_DOC":
            digitos = re.sub(r"\D", "", atual)
            if len(digitos) == 44 and digitos != atual:
                return digitos, True, "Remove espaços e pontuação, preservando os 44 dígitos da chave."

        if campo == "UNID_INV" and registro == "0200":
            codigo = campos[1].strip() if len(campos) > 1 else ""
            candidatas = {u for u in unidades_c170.get(codigo, set()) if u}
            if not atual and len(candidatas) == 1:
                unidade = next(iter(candidatas))
                return unidade, False, "Unidade encontrada de forma única nos C170 desse produto."

        if campo == "UNID" and registro == "C170":
            codigo = campos[2].strip() if len(campos) > 2 else ""
            unidade = unidades_0200.get(codigo, "")
            if unidade and unidade != atual:
                return unidade, False, (
                    "Sugestão baseada no 0200. Confirme se há conversão de unidade/registro 0220."
                )

        if registro == "C170" and campo in {"ALIQ_PIS", "ALIQ_COFINS"}:
            aliquotas_basicas = {
                "1": {"ALIQ_PIS": "1,6500", "ALIQ_COFINS": "7,6000"},
                "2": {"ALIQ_PIS": "0,6500", "ALIQ_COFINS": "3,0000"},
            }
            esperada = aliquotas_basicas.get(ind_inc_trib, {}).get(campo, "")
            valor_atual = self._normalizar_numero(atual) if atual else Decimal("0")
            if esperada and (not atual or valor_atual == 0):
                return esperada, True, (
                    f"Alíquota básica determinada pelo registro 0110 (IND_INC_TRIB={ind_inc_trib}). "
                    "É uma correção determinística para CST 01 e pode ser marcada automaticamente."
                )

        if campo in {"VL_PIS", "VL_COFINS"}:
            calculado = self._calcular_tributo(registro, campo, campos)
            if calculado is not None:
                return self._decimal_sped(calculado, 2), False, (
                    "Valor recalculado pelas bases e alíquotas do próprio registro. Confirme antes de aplicar."
                )

        if campo in self.CAMPOS_DECIMAIS and atual:
            normalizado = self._normalizar_numero(atual)
            if normalizado is not None:
                casas = 2 if campo.startswith("VL_") else None
                texto_normalizado = self._decimal_sped(normalizado, casas)
                if texto_normalizado != atual:
                    return texto_normalizado, True, (
                        "Normaliza o separador decimal para vírgula sem alterar o valor numérico."
                    )

        # Totais já calculados aparecem na mensagem do pré-validador.
        if apontamento.categoria in {"Totais do documento", "Cálculo"}:
            encontrado = re.search(r"(?:calculado|resulta em)\s+(-?[\d.]+(?:,\d+)?)", apontamento.mensagem)
            if encontrado:
                valor = self._decimal_texto(encontrado.group(1))
                if valor is not None:
                    return self._decimal_sped(valor, 2), False, (
                        "Total sugerido pelo cruzamento dos registros filhos; requer confirmação fiscal."
                    )

        return "", False, apontamento.sugestao

    _CODIGO_UF = {
        "RO": "11", "AC": "12", "AM": "13", "RR": "14", "PA": "15",
        "AP": "16", "TO": "17", "MA": "21", "PI": "22", "CE": "23",
        "RN": "24", "PB": "25", "PE": "26", "AL": "27", "SE": "28",
        "BA": "29", "MG": "31", "ES": "32", "RJ": "33", "SP": "35",
        "PR": "41", "SC": "42", "RS": "43", "MS": "50", "MT": "51",
        "GO": "52", "DF": "53",
    }

    @staticmethod
    def _sem_acentos(texto: str) -> str:
        import unicodedata
        return "".join(
            c for c in unicodedata.normalize("NFD", texto or "")
            if unicodedata.category(c) != "Mn"
        )

    @staticmethod
    def _mapear_produtos_0200(
        registros: dict[int, tuple[str, tuple[str, ...]]]
    ) -> dict[str, tuple[str, str]]:
        produtos: dict[str, tuple[str, str]] = {}
        for _, (codigo, campos) in registros.items():
            if codigo != "0200" or len(campos) <= 7:
                continue
            cod_item = campos[1].strip()
            if cod_item and cod_item not in produtos:
                produtos[cod_item] = (campos[2].strip(), campos[7].strip())
        return produtos

    @staticmethod
    def _mapear_contexto_c170(linhas: list[str]) -> dict[int, tuple[str, str]]:
        contexto: dict[int, tuple[str, str]] = {}
        ind_oper = ""
        chave = ""
        for numero, linha in enumerate(linhas, start=1):
            texto = linha.rstrip("\r\n")
            if not (texto.startswith("|") and texto.endswith("|")):
                continue
            partes = texto.split("|")[1:-1]
            if not partes:
                continue
            registro = partes[0].upper()
            if registro == "C100":
                ind_oper = partes[1].strip() if len(partes) > 1 else ""
                chave = partes[8].strip() if len(partes) > 8 else ""
            elif registro == "C170":
                contexto[numero] = (ind_oper, chave)
            elif registro not in {"C110", "C111", "C120", "C130", "C140", "C141", "C160", "C165", "C171", "C172", "C173", "C174", "C175", "C176", "C177", "C178", "C179", "C180", "C181", "C185", "C186", "C190", "C191", "C195", "C197"}:
                # Fora da família do documento C100, não reaproveitar contexto.
                if registro != "C100":
                    ind_oper = ""
                    chave = ""
        return contexto

    @staticmethod
    def _uf_empresa(registros: dict[int, tuple[str, tuple[str, ...]]]) -> str:
        for _, (codigo, campos) in registros.items():
            if codigo == "0000" and len(campos) > 9:
                return campos[9].strip().upper()
        return ""

    def _mapear_linhas(self, linhas: list[str]) -> dict[int, tuple[str, tuple[str, ...]]]:
        mapa: dict[int, tuple[str, tuple[str, ...]]] = {}
        for numero, linha in enumerate(linhas, start=1):
            texto = linha.rstrip("\r\n")
            if texto.startswith("|") and texto.endswith("|"):
                partes = texto.split("|")[1:-1]
                if partes:
                    mapa[numero] = (partes[0].upper(), tuple(partes))
        return mapa

    @staticmethod
    def _indicador_incidencia(
        registros: dict[int, tuple[str, tuple[str, ...]]]
    ) -> str:
        for _, (codigo, campos) in registros.items():
            if codigo == "0110" and len(campos) > 1:
                return campos[1].strip()
        return ""

    def _mapear_unidades(
        self, registros: dict[int, tuple[str, tuple[str, ...]]]
    ) -> tuple[dict[str, str], dict[str, set[str]]]:
        unidades_0200: dict[str, str] = {}
        unidades_c170: dict[str, set[str]] = defaultdict(set)
        for _, (codigo_reg, campos) in registros.items():
            if codigo_reg == "0200" and len(campos) > 5:
                unidades_0200[campos[1].strip()] = campos[5].strip()
            elif codigo_reg == "C170" and len(campos) > 5:
                codigo_item = campos[2].strip()
                unidade = campos[5].strip()
                if codigo_item and unidade:
                    unidades_c170[codigo_item].add(unidade)
        return unidades_0200, unidades_c170

    def _calcular_tributo(
        self, registro: str, campo: str, campos: tuple[str, ...]
    ) -> Decimal | None:
        mapas = {
            ("C170", "VL_PIS"): (25, 26, 27, 28),
            ("C170", "VL_COFINS"): (31, 32, 33, 34),
            ("A170", "VL_PIS"): (9, 10, None, None),
            ("A170", "VL_COFINS"): (13, 14, None, None),
            ("D101", "VL_PIS"): (5, 6, None, None),
            ("D105", "VL_COFINS"): (5, 6, None, None),
            ("M100", "VL_PIS"): (3, 4, 5, 6),
            ("M500", "VL_COFINS"): (3, 4, 5, 6),
        }
        mapa = mapas.get((registro, campo))
        if mapa is None:
            return None
        base_i, aliq_i, qtd_i, aliq_qtd_i = mapa
        base = self._decimal_campo(campos, base_i)
        aliq = self._decimal_campo(campos, aliq_i)
        if base is not None and aliq is not None and campos[base_i].strip() and campos[aliq_i].strip():
            return (base * aliq / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if qtd_i is not None and aliq_qtd_i is not None:
            qtd = self._decimal_campo(campos, qtd_i)
            aliq_qtd = self._decimal_campo(campos, aliq_qtd_i)
            if qtd is not None and aliq_qtd is not None and campos[qtd_i].strip() and campos[aliq_qtd_i].strip():
                return (qtd * aliq_qtd).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return None

    def _restaurar_separadores(
        self, linhas: list[str]
    ) -> tuple[list[str], list[CorrecaoAplicada]]:
        novas = list(linhas)
        aplicadas: list[CorrecaoAplicada] = []
        for indice, linha in enumerate(novas):
            texto, fim = self._separar_quebra(linha)
            if not texto:
                continue
            novo = texto
            if not novo.startswith("|"):
                novo = "|" + novo
            if not novo.endswith("|"):
                novo += "|"
            if novo != texto:
                novas[indice] = novo + fim
                aplicadas.append(
                    CorrecaoAplicada(
                        numero_linha=indice + 1,
                        registro="-",
                        campo="SEPARADORES",
                        valor_anterior=texto,
                        valor_novo=novo,
                        justificativa="Restauração dos delimitadores externos do registro.",
                    )
                )
        return novas, aplicadas

    def _recalcular_totalizadores(
        self, linhas: list[str]
    ) -> tuple[list[str], list[CorrecaoAplicada]]:
        novas = list(linhas)
        quebra_padrao = self._quebra_padrao(novas)
        aplicadas: list[CorrecaoAplicada] = []

        # Reconstrói todos os 9900 existentes imediatamente antes do 9990.
        indices_9900 = [i for i, linha in enumerate(novas) if self._codigo(linha) == "9900"]
        indice_9990 = next((i for i, linha in enumerate(novas) if self._codigo(linha) == "9990"), None)
        if indice_9990 is not None:
            sem_9900 = [linha for i, linha in enumerate(novas) if i not in set(indices_9900)]
            indice_9990 = next(i for i, linha in enumerate(sem_9900) if self._codigo(linha) == "9990")
            contagens = Counter(self._codigo(linha) for linha in sem_9900 if self._codigo(linha))
            codigos = sorted(set(contagens) | {"9900"})
            qtd_9900 = len(codigos)
            registros_9900 = []
            for codigo in codigos:
                quantidade = qtd_9900 if codigo == "9900" else contagens[codigo]
                registros_9900.append(f"|9900|{codigo}|{quantidade}|{quebra_padrao}")
            novas = sem_9900[:indice_9990] + registros_9900 + sem_9900[indice_9990:]
            aplicadas.append(
                CorrecaoAplicada(
                    numero_linha=None,
                    registro="9900",
                    campo="QTD_REG_BLC",
                    valor_anterior=f"{len(indices_9900)} linha(s) 9900",
                    valor_novo=f"{len(registros_9900)} linha(s) 9900 recalculadas",
                    justificativa="Reconstrução do inventário de registros do bloco 9.",
                )
            )

        # Atualiza fechamentos dos blocos com base nas posições finais.
        blocos = PreValidadorPVA.BLOCOS
        posicoes: dict[str, list[int]] = defaultdict(list)
        for i, linha in enumerate(novas):
            codigo = self._codigo(linha)
            if codigo:
                posicoes[codigo].append(i)
        for fechamento, abertura in blocos.items():
            if len(posicoes.get(fechamento, [])) != 1 or not posicoes.get(abertura):
                continue
            i_fechamento = posicoes[fechamento][0]
            i_abertura = posicoes[abertura][0]
            if fechamento == "9990" and posicoes.get("9999"):
                esperado = posicoes["9999"][0] - i_abertura + 1
            else:
                esperado = i_fechamento - i_abertura + 1
            anterior = self._obter_campo(novas[i_fechamento], 1)
            novo = str(esperado)
            if anterior != novo:
                novas[i_fechamento] = self._substituir_campo(novas[i_fechamento], 1, novo)
                aplicadas.append(
                    CorrecaoAplicada(
                        numero_linha=i_fechamento + 1,
                        registro=fechamento,
                        campo="QTD_LIN",
                        valor_anterior=anterior,
                        valor_novo=novo,
                        justificativa=f"Recontagem das linhas do bloco iniciado em {abertura}.",
                    )
                )

        # Total geral precisa ser o último, pois o 9900 pode ter mudado o número de linhas.
        i_9999 = next((i for i, linha in enumerate(novas) if self._codigo(linha) == "9999"), None)
        if i_9999 is not None:
            anterior = self._obter_campo(novas[i_9999], 1)
            novo = str(len(novas))
            if anterior != novo:
                novas[i_9999] = self._substituir_campo(novas[i_9999], 1, novo)
                aplicadas.append(
                    CorrecaoAplicada(
                        numero_linha=i_9999 + 1,
                        registro="9999",
                        campo="QTD_LIN",
                        valor_anterior=anterior,
                        valor_novo=novo,
                        justificativa="Recontagem do total geral de linhas da cópia final.",
                    )
                )
        return novas, aplicadas

    def _salvar_relatorio(
        self,
        caminho: Path,
        sped: Path,
        antes: ResultadoPreValidacaoPVA,
        depois: ResultadoPreValidacaoPVA,
        aplicadas: list[CorrecaoAplicada],
        preparacao: ResultadoPreparacaoAssistida,
    ) -> None:
        linhas = [
            "FISCALPRO — CORREÇÃO ASSISTIDA ANTES DO PVA",
            "=" * 78,
            f"Gerado em: {datetime.now():%d/%m/%Y %H:%M:%S}",
            f"Nova cópia: {sped}",
            "",
            f"Erros antes: {len(antes.erros)}",
            f"Avisos antes: {len(antes.avisos)}",
            f"Erros depois: {len(depois.erros)}",
            f"Avisos depois: {len(depois.avisos)}",
            f"Ações aplicadas: {len(aplicadas)}",
            f"Itens não marcados: {len([p for p in preparacao.propostas if not p.selecionada])}",
            "",
            "ALTERAÇÕES APLICADAS",
            "-" * 78,
        ]
        if not aplicadas:
            linhas.append("Nenhuma alteração foi aplicada.")
        for numero, item in enumerate(aplicadas, start=1):
            linhas.extend(
                [
                    f"{numero}. Registro {item.registro} | Linha {item.numero_linha or '-'} | Campo {item.campo}",
                    f"   Anterior: {item.valor_anterior}",
                    f"   Novo: {item.valor_novo}",
                    f"   Motivo: {item.justificativa}",
                    "",
                ]
            )
        linhas.extend(
            [
                "RESULTADO DA NOVA PRÉ-VALIDAÇÃO",
                "-" * 78,
            ]
        )
        if not depois.apontamentos:
            linhas.append("Nenhum erro ou aviso encontrado pelas regras locais.")
        else:
            for item in depois.apontamentos:
                linhas.append(
                    f"[{item.nivel}] {item.registro or '-'} linha {item.numero_linha or '-'} "
                    f"{item.campo or '-'} — {item.mensagem}"
                )
        linhas.extend(
            [
                "",
                "IMPORTANTE",
                "- O arquivo original não foi alterado.",
                "- Correções desmarcadas ou sem valor permaneceram inalteradas.",
                "- A nova cópia deve ser validada no PVA oficial.",
            ]
        )
        caminho.write_text("\n".join(linhas), encoding="utf-8")

    @staticmethod
    def _codigo(linha: str) -> str:
        texto = linha.rstrip("\r\n")
        if texto.startswith("|") and texto.endswith("|"):
            partes = texto.split("|")
            return partes[1].strip().upper() if len(partes) > 2 else ""
        return ""

    @staticmethod
    def _obter_campo(linha: str, indice_campo: int) -> str:
        texto = linha.rstrip("\r\n")
        partes = texto.split("|")
        indice = indice_campo + 1
        return partes[indice] if indice < len(partes) else ""

    @staticmethod
    def _substituir_campo(linha: str, indice_campo: int, valor: str) -> str:
        texto, fim = CorretorAssistidoPVA._separar_quebra(linha)
        partes = texto.split("|")
        indice = indice_campo + 1
        if not (texto.startswith("|") and texto.endswith("|")) or indice >= len(partes) - 1:
            raise RuntimeError(f"Não foi possível localizar o campo {indice_campo} na linha SPED.")
        partes[indice] = valor
        return "|".join(partes) + fim

    @staticmethod
    def _separar_quebra(linha: str) -> tuple[str, str]:
        if linha.endswith("\r\n"):
            return linha[:-2], "\r\n"
        if linha.endswith("\n"):
            return linha[:-1], "\n"
        if linha.endswith("\r"):
            return linha[:-1], "\r"
        return linha, ""

    @staticmethod
    def _quebra_padrao(linhas: list[str]) -> str:
        for linha in linhas:
            _, fim = CorretorAssistidoPVA._separar_quebra(linha)
            if fim:
                return fim
        return "\r\n"

    @staticmethod
    def _decimal_texto(texto: str) -> Decimal | None:
        valor = texto.strip().replace(".", "").replace(",", ".")
        try:
            return Decimal(valor)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _normalizar_numero(texto: str) -> Decimal | None:
        bruto = texto.strip().replace(" ", "")
        if not bruto:
            return None
        # SPED usa vírgula decimal. Aceita ponto decimal quando não há vírgula.
        if "," in bruto:
            normalizado = bruto.replace(".", "").replace(",", ".")
        else:
            normalizado = bruto
        try:
            return Decimal(normalizado)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _decimal_campo(campos: tuple[str, ...], indice: int) -> Decimal | None:
        if indice >= len(campos):
            return None
        return CorretorAssistidoPVA._normalizar_numero(campos[indice])

    @staticmethod
    def _decimal_sped(valor: Decimal, casas: int | None = None) -> str:
        if casas is not None:
            quantizador = Decimal("1").scaleb(-casas)
            valor = valor.quantize(quantizador, rounding=ROUND_HALF_UP)
            texto = f"{valor:.{casas}f}"
        else:
            texto = format(valor, "f")
            if "." in texto:
                texto = texto.rstrip("0").rstrip(".")
        return texto.replace(".", ",")

    @staticmethod
    def _encoding_saida_sem_bom(encoding: str | None) -> str:
        normalizado = (encoding or "").strip().lower().replace("_", "-")
        if normalizado in {"utf-8-sig", "utf8-sig", "utf-8", "utf8"}:
            return "utf-8"
        return encoding or "utf-8"

    @staticmethod
    def _progresso(callback: ProgressoCallback | None, percentual: int, mensagem: str) -> None:
        if callback:
            callback(percentual, mensagem)
