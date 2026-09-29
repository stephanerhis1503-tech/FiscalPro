"""Integração segura do Bloco M no fluxo Excel -> SPED TXT.

Hotfix 17.6.5 + 17.6.8 + 17.6.9 + 17.7.3.

O fluxo Excel já reconstrói os registros documentais. Este módulo reaplica as
rotinas seguras que antes estavam disponíveis somente nos fluxos de correção do
TXT, sem inventar natureza de receita, rateio ou crédito.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable

from .consolidador_creditos_bloco_m import ConsolidadorCreditosBlocoM
from .exclusor_icms_creditos_piscofins import (
    ExclusorICMSCreditosPISCOFINS,
)
from .reapurador_bloco_m import ReapuradorBlocoM


@dataclass(frozen=True, slots=True)
class AjusteBlocoMExcel:
    registro: str
    campo: str
    original: str
    novo: str
    justificativa: str
    numero_linha: int | None = None


@dataclass(slots=True)
class ResultadoSincronizacaoBlocoMExcel:
    linhas: list[str]
    ajustes: list[AjusteBlocoMExcel] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)
    grupos_credito_consolidados: int = 0
    campos_bloco_m_sincronizados: int = 0
    estrutura_alterada: bool = False

    @property
    def alterou(self) -> bool:
        return bool(self.ajustes or self.grupos_credito_consolidados or self.campos_bloco_m_sincronizados)


class SincronizadorBlocoMExcel:
    """Reaplica a inteligência já aprovada do Bloco M após o Excel.

    Guardas principais:
    * só atua em EFD Contribuições;
    * consolida somente M100/M500 que o consolidador 17.3.9 classifica como seguros;
    * sincroniza reduções de crédito C170 -> M105/M505/M100/M500/M200/M600
      somente quando o mapeamento existente consegue provar o vínculo;
    * não inventa NAT_REC de M410/M810;
    * não aumenta crédito automaticamente;
    * totaliza M400/M800 somente quando a origem sem incidência pode ser
      comprovada exclusivamente por A170/C170 e há um único filho correspondente.
    """

    CST_CREDITO = {str(n) for n in range(50, 67)}
    CST_RECEITA_SEM_INCIDENCIA = {"04", "05", "06", "07", "08", "09"}

    # Hotfix 17.8.121 — famílias documentais usadas SOMENTE para provar o
    # vínculo C170 -> M105/M505 no retorno Excel -> TXT. Não ampliam a rotina
    # de exclusão automática de ICMS próprio, que continua conservadora.
    CFOPS_CREDITO_REVENDA = frozenset({"1102", "2102", "1403", "2403"})
    CFOPS_CREDITO_USO_CONSUMO_ST = frozenset({"1407", "2407"})

    # Registros citados pelo PGE como possíveis fontes de VL_TOT_REC. Enquanto
    # não houver mapeamento exato de todos eles, a retotalização de M400/M800
    # fica restrita a arquivos em que só A170/C170 estão presentes.
    OUTRAS_FONTES_RECEITA = {
        # C175 passou a ser fonte suportada na 17.8.124. As demais continuam
        # bloqueando a retotalização enquanto não houver mapeamento oficial
        # implementado, para evitar aproximar receita.
        "C181", "C185", "C381", "C385", "C481", "C485",
        "C491", "C495", "C601", "C605", "C870", "C880",
        "D201", "D205", "D601", "D605", "D300", "D350",
        "F100", "F200", "F500", "F510", "F550", "F560", "I100",
    }

    def __init__(self) -> None:
        self.consolidador = ConsolidadorCreditosBlocoM()
        self.exclusor = ExclusorICMSCreditosPISCOFINS()
        self.reapurador = ReapuradorBlocoM()

    def sincronizar(
        self,
        linhas_originais: list[str],
        linhas_reconstruidas: list[str],
        referencias: Iterable,
        posicao_gerada_por_sequencia: dict[int, int],
        tipo_sped: str,
    ) -> ResultadoSincronizacaoBlocoMExcel:
        resultado = ResultadoSincronizacaoBlocoMExcel(linhas=list(linhas_reconstruidas))
        if str(tipo_sped or "").strip().upper() != "EFD CONTRIBUIÇÕES":
            return resultado

        novas = list(linhas_reconstruidas)

        # 1) Débitos determinísticos (M210/M200 e, quando seguro, M610/M600).
        # O reapurador trabalha por delta entre C170 original e reconstruído.
        reap = self.reapurador.sincronizar(linhas_originais, novas, tipo_sped)
        novas = reap.linhas
        resultado.avisos.extend(reap.avisos)
        for alt in reap.alteracoes:
            resultado.ajustes.append(
                AjusteBlocoMExcel(
                    registro=alt.registro,
                    campo=alt.campo,
                    original=alt.valor_anterior,
                    novo=alt.valor_novo,
                    justificativa=alt.justificativa,
                    numero_linha=alt.numero_linha,
                )
            )
        resultado.campos_bloco_m_sincronizados += len(reap.alteracoes)
        resultado.estrutura_alterada = resultado.estrutura_alterada or reap.estrutura_alterada

        # 2) Descobre os deltas de crédito antes de alterar a estrutura do M.
        # O delta é assinado: positivo acrescenta crédito; negativo reduz.
        deltas_credito, erros_credito = self._deltas_creditos_c170(
            referencias, novas, posicao_gerada_por_sequencia
        )
        if erros_credito:
            resultado.erros.extend(erros_credito)
            resultado.linhas = novas
            return resultado

        # 3) Consolidação segura das chaves duplicadas M100/M500.
        planos = self.consolidador.analisar(novas)
        if planos:
            sementes = {numero for plano in planos for numero in plano.linhas_pais}
            consolidado = self.consolidador.consolidar(novas, sementes)
            novas = consolidado.linhas
            resultado.grupos_credito_consolidados = consolidado.grupos_consolidados
            resultado.campos_bloco_m_sincronizados += len(consolidado.alteracoes)
            resultado.estrutura_alterada = (
                resultado.estrutura_alterada or consolidado.estrutura_alterada
            )
            for alt in consolidado.alteracoes:
                resultado.ajustes.append(
                    AjusteBlocoMExcel(
                        registro=alt.registro,
                        campo=alt.campo,
                        original=alt.valor_anterior,
                        novo=alt.valor_novo,
                        justificativa=alt.justificativa,
                        numero_linha=alt.numero_linha,
                    )
                )

        # 4) Créditos causados pelo Excel: sincroniza reduções E aumentos
        # determinísticos usando o mesmo mapeamento seguro de M105/M505 já
        # aprovado no fluxo ICMS Fiscal -> PIS/COFINS.
        if deltas_credito:
            antes_m = list(novas)
            try:
                qtd, avisos_credito = self._sincronizar_creditos_assinados(
                    novas, linhas_originais, deltas_credito
                )
            except RuntimeError as erro:
                resultado.erros.append(
                    "Bloco M: as alterações de crédito do Excel não puderam ser "
                    f"sincronizadas com segurança. {erro}"
                )
                resultado.linhas = antes_m
                return resultado
            resultado.avisos.extend(avisos_credito)
            resultado.campos_bloco_m_sincronizados += qtd
            if qtd:
                resultado.ajustes.append(
                    AjusteBlocoMExcel(
                        registro="M105/M505",
                        campo="Créditos derivados dos C170",
                        original="Apuração anterior",
                        novo=f"{qtd} campo(s) sincronizado(s)",
                        justificativa=(
                            "As bases de crédito do Bloco M foram reapuradas a partir dos "
                            "deltas determinísticos feitos nos C170 pelo Excel."
                        ),
                    )
                )

        # 5) Devolução de compra é uma operação de saída. Se o arquivo traz
        # CST de aquisição (70-75) numa devolução claramente identificada pelo
        # CFOP e não há base/valor de contribuição preenchidos, normaliza para
        # CST 49 antes de recompormos as receitas sem incidência. Isso evita que
        # o PGE trate a saída com uma classificação incompatível e contamine o
        # fechamento de M400/M800.
        ajustes_dev, avisos_dev = self._normalizar_devolucoes_compra_saida(novas)
        resultado.ajustes.extend(ajustes_dev)
        resultado.avisos.extend(avisos_dev)
        resultado.campos_bloco_m_sincronizados += len(ajustes_dev)

        # 6) Receitas sem incidência/monofásicas. Atualiza valores de M400/M800
        # a partir das fontes documentais suportadas (A170/C170/C175),
        # preservando NAT_REC. Quando há múltiplos filhos, só ajusta se existir
        # um NAT_REC 999 capaz de absorver o residual sem alterar naturezas
        # específicas já escrituradas.
        ajustes_receita, avisos_receita = self._retotalizar_m400_m800(novas)
        resultado.ajustes.extend(ajustes_receita)
        resultado.avisos.extend(avisos_receita)
        resultado.campos_bloco_m_sincronizados += len(ajustes_receita)

        # 7) O PGE exige M205/M605 quando há contribuição a recolher em
        # M200/M600. Arquivos legados podem não trazer esses filhos. A 17.8.124
        # cria somente o cenário padrão comprovável pelo 0110 (não cumulativo
        # ou cumulativo exclusivo), usando os códigos de receita oficiais.
        ajustes_debito, avisos_debito, estrutura_debito = self._garantir_m205_m605(novas)
        resultado.ajustes.extend(ajustes_debito)
        resultado.avisos.extend(avisos_debito)
        resultado.campos_bloco_m_sincronizados += len(ajustes_debito)
        resultado.estrutura_alterada = resultado.estrutura_alterada or estrutura_debito

        # 8) Qualquer inclusão/remoção no M exige recontagem do bloco 9.
        if resultado.estrutura_alterada or len(novas) != len(linhas_reconstruidas):
            novas, qtd_tot = self.exclusor._recalcular_totalizadores(novas)
            resultado.campos_bloco_m_sincronizados += qtd_tot

        # O importador Excel trabalha internamente sem terminadores de linha;
        # os módulos antigos de correção do TXT preservam/adicionam quebras.
        # Normaliza antes de devolver para evitar linhas em branco na gravação.
        novas = [str(linha).rstrip("\r\n") for linha in novas]
        resultado.linhas = novas
        return resultado

    def recalcular_modo_manual(
        self,
        linhas_reconstruidas: list[str],
        tipo_sped: str,
    ) -> ResultadoSincronizacaoBlocoMExcel:
        """Ajuda aritmética para o Bloco M quando a usuária assumiu a edição.

        O Hotfix 17.7.3 separa duas decisões:

        * a decisão TRIBUTÁRIA (quais M100/M105/M500/M505 existem, alíquota,
          CST/natureza, exclusões) pertence à edição manual da usuária;
        * os campos ARITMÉTICOS dependentes podem ser recalculados pelo
          FiscalPro quando o grupo é simples e comprovável.

        Assim, este método nunca cria grupo de crédito, nunca recupera linha
        apagada e nunca muda COD_CRED/NAT_BC_CRED/CST. Ele apenas retotaliza
        M100/M500 simples a partir dos filhos atuais e tenta atualizar M200/M600
        quando a própria rotina conservadora já aprovada considera seguro.
        """

        resultado = ResultadoSincronizacaoBlocoMExcel(linhas=list(linhas_reconstruidas))
        if str(tipo_sped or "").strip().upper() != "EFD CONTRIBUIÇÕES":
            return resultado

        linhas = list(linhas_reconstruidas)
        campos_por_tributo = {
            "PIS": {
                "reg": "M100",
                "child": "M105",
                "consol": "M200",
                "base": "VL_BC_PIS",
                "aliq": "ALIQ_PIS",
                "cred": "VL_CRED",
            },
            "COFINS": {
                "reg": "M500",
                "child": "M505",
                "consol": "M600",
                "base": "VL_BC_COFINS",
                "aliq": "ALIQ_COFINS",
                "cred": "VL_CRED",
            },
        }

        for tributo, cfg in campos_por_tributo.items():
            pais = self.exclusor._mapear_pais_bloco_m(
                linhas, cfg["reg"], cfg["child"]
            )
            alterou_tributo = False
            for linha_pai, filhos in pais:
                if not filhos:
                    resultado.avisos.append(
                        f"Bloco M manual: {cfg['reg']} linha {linha_pai} ficou sem "
                        f"{cfg['child']} filho. O FiscalPro preservou o registro e não "
                        "inventou uma base; confira no PGE."
                    )
                    continue

                try:
                    self.exclusor._validar_pai_credito_simples(
                        linhas[linha_pai - 1], cfg["reg"], linha_pai
                    )
                except RuntimeError as erro:
                    resultado.avisos.append(
                        f"Bloco M manual: {erro} A aritmética deste grupo foi preservada "
                        "como digitada para revisão no PGE."
                    )
                    continue

                bases: list[Decimal] = []
                grupo_valido = True
                for linha_filho in filhos:
                    filho = linhas[linha_filho - 1]
                    total = self.exclusor._decimal(
                        self.exclusor._campo_linha(filho, 3)
                    )
                    cumulativa_txt = self.exclusor._campo_linha(filho, 4).strip()
                    cumulativa = (
                        self.exclusor._decimal(cumulativa_txt)
                        if cumulativa_txt else Decimal("0.00")
                    )
                    nao_cum = self.exclusor._decimal(
                        self.exclusor._campo_linha(filho, 5)
                    )
                    base_credito = self.exclusor._decimal(
                        self.exclusor._campo_linha(filho, 6)
                    )
                    if None in (total, cumulativa, nao_cum, base_credito):
                        resultado.avisos.append(
                            f"Bloco M manual: {cfg['child']} linha {linha_filho} possui "
                            "base inválida; o pai não foi recalculado."
                        )
                        grupo_valido = False
                        break
                    if cumulativa.copy_abs() > self.exclusor.TOLERANCIA:
                        resultado.avisos.append(
                            f"Bloco M manual: {cfg['child']} linha {linha_filho} possui "
                            "base cumulativa; o FiscalPro não rateou automaticamente."
                        )
                        grupo_valido = False
                        break
                    if not self.exclusor._aprox(total, nao_cum) or not self.exclusor._aprox(
                        nao_cum, base_credito
                    ):
                        resultado.avisos.append(
                            f"Bloco M manual: {cfg['child']} linha {linha_filho} possui bases "
                            "divergentes; preservei a edição para conferência no PGE."
                        )
                        grupo_valido = False
                        break
                    bases.append(nao_cum)

                if not grupo_valido:
                    continue

                base = sum(bases, Decimal("0.00")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                taxa = self.exclusor._decimal(
                    self.exclusor._campo_linha(linhas[linha_pai - 1], 4)
                )
                if taxa is None:
                    resultado.avisos.append(
                        f"Bloco M manual: {cfg['reg']} linha {linha_pai} possui alíquota "
                        "inválida; a aritmética foi preservada como digitada."
                    )
                    continue
                credito = (base * taxa / Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

                for campo, nome, valor in (
                    (3, cfg["base"], base),
                    (7, cfg["cred"], credito),
                    (11, "VL_CRED_DISP", credito),
                    (13, "VL_CRED_DESC", credito),
                    (14, "SLD_CRED", Decimal("0.00")),
                ):
                    anterior = self.exclusor._campo_linha(
                        linhas[linha_pai - 1], campo
                    )
                    novo = self.exclusor._fmt(valor)
                    if self._normalizar_numero_texto(anterior) == self._normalizar_numero_texto(novo):
                        continue
                    linhas[linha_pai - 1] = self.exclusor._substituir_campo(
                        linhas[linha_pai - 1], campo, novo
                    )
                    resultado.ajustes.append(
                        AjusteBlocoMExcel(
                            registro=cfg["reg"],
                            campo=nome,
                            original=anterior,
                            novo=novo,
                            justificativa=(
                                "Recalculo aritmético do modo manual do Bloco M; "
                                "a classificação tributária digitada pela usuária foi preservada."
                            ),
                            numero_linha=linha_pai,
                        )
                    )
                    resultado.campos_bloco_m_sincronizados += 1
                    alterou_tributo = True

            if alterou_tributo:
                try:
                    qtd = self.exclusor._recalcular_consolidacao(
                        linhas, tributo, cfg["reg"], cfg["consol"]
                    )
                    resultado.campos_bloco_m_sincronizados += qtd
                    if qtd:
                        resultado.ajustes.append(
                            AjusteBlocoMExcel(
                                registro=cfg["consol"],
                                campo="Totalização do crédito",
                                original="Apuração anterior",
                                novo=f"{qtd} campo(s) recalculado(s)",
                                justificativa=(
                                    "O consolidado foi atualizado a partir dos créditos manuais "
                                    "já existentes, sem criar ou reclassificar grupo tributário."
                                ),
                            )
                        )
                except RuntimeError as erro:
                    resultado.avisos.append(
                        f"Bloco M manual: {erro} O consolidado foi mantido como digitado "
                        "para conferência no PGE."
                    )

        resultado.linhas = [str(linha).rstrip("\r\n") for linha in linhas]
        return resultado

    @staticmethod
    def _normalizar_numero_texto(valor: str) -> str:
        texto = str(valor or "").strip().replace(".", "").replace(",", ".")
        if not texto:
            return ""
        try:
            return format(Decimal(texto).normalize(), "f")
        except (InvalidOperation, ValueError):
            return texto

    def _deltas_creditos_c170(

        self,
        referencias: Iterable,
        linhas_atuais: list[str],
        posicoes: dict[int, int],
    ) -> tuple[dict[tuple[str, str, str], Decimal], list[str]]:
        """Retorna delta NOVO - ANTIGO por tributo/alíquota/CST de crédito."""
        grupos: dict[tuple[str, str, str], Decimal] = {}
        grupos_familia: dict[tuple[str, str, str, str], Decimal] = {}
        erros: list[str] = []
        mapas = {
            "PIS": (24, 25, 26),
            "COFINS": (30, 31, 32),
        }

        for ref in referencias:
            if str(getattr(ref, "registro", "") or "").upper() != "C170":
                continue
            pos = posicoes.get(getattr(ref, "sequencia", 0))
            if pos is None or pos >= len(linhas_atuais):
                continue
            antigos = self._campos(getattr(ref, "linha_original", ""))
            atuais = self._campos(linhas_atuais[pos])
            if not antigos or not atuais or atuais[0].upper() != "C170":
                continue

            cfop_ant = self._campo(antigos, 10).strip()
            cfop_nov = self._campo(atuais, 10).strip()
            familia_ant = self._familia_credito_c170(cfop_ant)
            familia_nov = self._familia_credito_c170(cfop_nov)

            for tributo, (idx_cst, idx_base, idx_aliq) in mapas.items():
                cst_ant = self._campo(antigos, idx_cst).strip()
                cst_nov = self._campo(atuais, idx_cst).strip()
                base_ant = self._decimal(self._campo(antigos, idx_base)) or Decimal("0")
                base_nov = self._decimal(self._campo(atuais, idx_base)) or Decimal("0")
                aliq_ant = self._normalizar_taxa(self._campo(antigos, idx_aliq))
                aliq_nov = self._normalizar_taxa(self._campo(atuais, idx_aliq))

                # Retira a parcela antiga do grupo em que ela estava.
                if cst_ant in self.CST_CREDITO and base_ant:
                    if not aliq_ant:
                        erros.append(
                            f"C170 sequência {getattr(ref, 'sequencia', '?')}: alíquota antiga "
                            f"de crédito de {tributo} inválida."
                        )
                    else:
                        chave = (tributo, aliq_ant, cst_ant)
                        grupos[chave] = grupos.get(chave, Decimal("0")) - base_ant
                        chave_familia = (tributo, aliq_ant, cst_ant, familia_ant)
                        grupos_familia[chave_familia] = (
                            grupos_familia.get(chave_familia, Decimal("0")) - base_ant
                        )

                # Acrescenta a parcela nova ao grupo em que passou a estar.
                if cst_nov in self.CST_CREDITO and base_nov:
                    if not aliq_nov:
                        erros.append(
                            f"C170 sequência {getattr(ref, 'sequencia', '?')}: alíquota nova "
                            f"de crédito de {tributo} inválida."
                        )
                    else:
                        chave = (tributo, aliq_nov, cst_nov)
                        grupos[chave] = grupos.get(chave, Decimal("0")) + base_nov
                        chave_familia = (tributo, aliq_nov, cst_nov, familia_nov)
                        grupos_familia[chave_familia] = (
                            grupos_familia.get(chave_familia, Decimal("0")) + base_nov
                        )

        # Remove grupos sem mudança líquida.
        grupos = {
            chave: valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            for chave, valor in grupos.items()
            if valor.copy_abs() > Decimal("0.01")
        }
        self._deltas_familia_cache = {
            chave: valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            for chave, valor in grupos_familia.items()
            if valor.copy_abs() > Decimal("0.01")
        }
        return grupos, erros

    @classmethod
    def _familia_credito_c170(cls, cfop: str) -> str:
        codigo = str(cfop or "").strip()
        if codigo in cls.CFOPS_CREDITO_REVENDA:
            return "REVENDA"
        if codigo in cls.CFOPS_CREDITO_USO_CONSUMO_ST:
            return "USO_CONSUMO_ST"
        return f"CFOP:{codigo}" if codigo else "CFOP:SEM_CODIGO"

    def _base_c170_por_familia(
        self,
        linhas: list[str],
        tributo: str,
        taxa: str,
        cst: str,
        familia: str,
    ) -> Decimal:
        if tributo == "PIS":
            idx_cst, idx_base, idx_aliq = 24, 25, 26
        else:
            idx_cst, idx_base, idx_aliq = 30, 31, 32
        total = Decimal("0.00")
        for linha in linhas:
            campos = self._campos(linha)
            if not campos or campos[0].upper() != "C170":
                continue
            cfop = self._campo(campos, 10).strip()
            if self._familia_credito_c170(cfop) != familia:
                continue
            if self._campo(campos, idx_cst).strip() != cst:
                continue
            aliq = self._normalizar_taxa(self._campo(campos, idx_aliq))
            if aliq != taxa:
                continue
            base = self._decimal(self._campo(campos, idx_base)) or Decimal("0.00")
            total += base
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _sincronizar_creditos_assinados(
        self,
        linhas: list[str],
        linhas_antes: list[str],
        deltas: dict[tuple[str, str, str], Decimal],
    ) -> tuple[int, list[str]]:
        """Aplica delta assinado em M105/M505 e recalcula pais/consolidação.

        Hotfix 17.6.9: uma redução de crédito nos C170 não deve exigir a
        criação de M100/M500 quando o SPED original nunca possuía aquele
        grupo. Nesse cenário não há crédito apurado no Bloco M a reduzir; o
        grupo é ignorado com aviso. Aumento de crédito sem pai existente
        continua bloqueado, pois exigiria criar uma apuração nova.
        """
        alteracoes = 0
        avisos: list[str] = []
        for tributo in ("PIS", "COFINS"):
            cfg = self.exclusor.M_PARENT[tributo]
            grupos = {
                (taxa, cst): delta
                for (trib, taxa, cst), delta in deltas.items()
                if trib == tributo and delta.copy_abs() > Decimal("0.01")
            }
            if not grupos:
                continue

            c170_antes = self.exclusor._agrupar_bases_c170(linhas_antes, tributo)
            c170_fonte_segura = self.exclusor._agrupar_bases_c170_fonte_segura(
                linhas_antes, tributo
            )
            pais = self.exclusor._mapear_pais_bloco_m(
                linhas, cfg["reg"], cfg["child"]
            )

            pais_afetados: set[int] = set()
            for (taxa, cst), delta in grupos.items():
                # Hotfix 17.8.121 — quando o Excel altera crédito de C170,
                # tenta provar primeiro a família documental que originou o
                # delta. No arquivo real de agosto/2026 da Mega Motos, por
                # exemplo, 1102/2102/1403/2403 compõem exatamente o M105 de
                # NAT_BC_CRED 01, enquanto 1407 compõe o filho de base 5,82.
                # Isso evita comparar o M105 com TODOS os C170 CST 50 do mês,
                # que também podem conter 2910/2949 fora da apuração do M105.
                base_c170 = None
                cache = getattr(self, "_deltas_familia_cache", {}) or {}
                familias = [
                    (familia, valor)
                    for (trib, tx, cst_cache, familia), valor in cache.items()
                    if trib == tributo and tx == taxa and cst_cache == cst
                    and valor.copy_abs() > Decimal("0.01")
                ]
                if len(familias) == 1:
                    familia, delta_familia = familias[0]
                    if (delta_familia - delta).copy_abs() <= self.exclusor.TOLERANCIA:
                        base_familia = self._base_c170_por_familia(
                            linhas_antes, tributo, taxa, cst, familia
                        )
                        if base_familia > 0:
                            base_c170 = base_familia

                if base_c170 is None:
                    base_c170 = c170_fonte_segura.get((taxa, cst))
                if base_c170 is None or base_c170 <= 0:
                    base_c170 = c170_antes.get((taxa, cst), Decimal("0.00"))

                resolvido = self._identificar_pai_e_filho_credito(
                    linhas_antes=linhas_antes,
                    linhas_atuais=linhas,
                    pais=pais,
                    tributo=tributo,
                    taxa=taxa,
                    cst=cst,
                    base_c170=base_c170,
                )
                if resolvido is None:
                    candidatos = [
                        pai for pai in pais
                        if self.exclusor._taxa_igual(
                            self.exclusor._campo_linha(linhas[pai[0] - 1], 4), taxa
                        )
                    ]
                    if not candidatos:
                        pais_antes = self.exclusor._mapear_pais_bloco_m(
                            linhas_antes, cfg["reg"], cfg["child"]
                        )
                        candidatos_antes = [
                            pai for pai in pais_antes
                            if self.exclusor._taxa_igual(
                                self.exclusor._campo_linha(
                                    linhas_antes[pai[0] - 1], 4
                                ),
                                taxa,
                            )
                        ]

                        # Se o Excel apenas REDUZIU crédito e o próprio SPED
                        # original já não possuía M100/M500 para essa alíquota,
                        # não existe crédito apurado no Bloco M a reduzir.
                        # Criar um pai zerado seria artificial e desnecessário.
                        if delta < 0 and not candidatos_antes:
                            avisos.append(
                                f"Bloco M: os C170 reduziram crédito de {tributo} "
                                f"na alíquota {taxa}, mas o SPED original não possuía "
                                f"{cfg['reg']} correspondente. Nenhum {cfg['reg']} foi "
                                "criado; a redução documental foi preservada e será "
                                "confirmada pelo Pré-PVA/PGE."
                            )
                            continue

                        if candidatos_antes:
                            raise RuntimeError(
                                f"o SPED original possuía {cfg['reg']} para alíquota "
                                f"{taxa} ({tributo}), mas ele não está disponível após "
                                "a reconstrução do Bloco M; revisão estrutural necessária."
                            )

                        raise RuntimeError(
                            f"não há {cfg['reg']} para alíquota {taxa} ({tributo}). "
                            "Como a alteração aumentaria crédito, o FiscalPro não cria "
                            f"{cfg['reg']} automaticamente sem uma apuração original que "
                            "comprove o grupo de crédito."
                        )
                    raise RuntimeError(
                        f"há {len(candidatos)} {cfg['reg']} para alíquota {taxa} ({tributo}), "
                        f"mas o {cfg['child']} dos C170 CST {cst} não pôde ser vinculado "
                        "a um único grupo de crédito com segurança."
                    )

                linha_pai, filhos, linha_child = resolvido
                pais_afetados.add(linha_pai)

                child = linhas[linha_child - 1]
                total = self.exclusor._decimal(
                    self.exclusor._campo_linha(child, 3)
                )
                cumulativa_txt = self.exclusor._campo_linha(child, 4).strip()
                cumulativa = (
                    self.exclusor._decimal(cumulativa_txt)
                    if cumulativa_txt else Decimal("0.00")
                )
                nao_cum = self.exclusor._decimal(
                    self.exclusor._campo_linha(child, 5)
                )
                base_credito = self.exclusor._decimal(
                    self.exclusor._campo_linha(child, 6)
                )
                if None in (total, cumulativa, nao_cum, base_credito):
                    raise RuntimeError(
                        f"{cfg['child']} linha {linha_child} possui base inválida."
                    )
                if cumulativa.copy_abs() > self.exclusor.TOLERANCIA:
                    raise RuntimeError(
                        f"{cfg['child']} linha {linha_child} possui base cumulativa; "
                        "revisão manual necessária."
                    )
                if not self.exclusor._aprox(total, nao_cum) or not self.exclusor._aprox(
                    nao_cum, base_credito
                ):
                    raise RuntimeError(
                        f"{cfg['child']} linha {linha_child} não possui bases não "
                        "cumulativas coincidentes."
                    )

                nova = (base_credito + delta).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                if nova < 0:
                    raise RuntimeError(
                        f"o delta do Excel excederia a base do {cfg['child']} "
                        f"linha {linha_child}."
                    )
                for campo in (3, 5, 6):
                    linhas[linha_child - 1] = self.exclusor._substituir_campo(
                        linhas[linha_child - 1], campo, self.exclusor._fmt(nova)
                    )
                    alteracoes += 1

            # Recalcula somente os pais efetivamente vinculados aos C170 alterados.
            # Dois M100/M500 podem usar a mesma alíquota e representar origens
            # legítimas distintas (ex.: frete, serviço e mercadoria). Recalcular
            # todos apenas pela alíquota poderia tocar um grupo não relacionado.
            for linha_pai, filhos in pais:
                if linha_pai not in pais_afetados:
                    continue
                taxa_txt = self.exclusor._campo_linha(linhas[linha_pai - 1], 4)
                self.exclusor._validar_pai_credito_simples(
                    linhas[linha_pai - 1], cfg["reg"], linha_pai
                )
                base = sum(
                    (
                        self.exclusor._decimal(
                            self.exclusor._campo_linha(linhas[f - 1], 5)
                        )
                        or Decimal("0")
                    )
                    for f in filhos
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                taxa = self.exclusor._decimal(taxa_txt)
                if taxa is None:
                    raise RuntimeError(
                        f"{cfg['reg']} linha {linha_pai} possui alíquota inválida."
                    )
                credito = (base * taxa / Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                for campo, valor in (
                    (3, base), (7, credito), (11, credito),
                    (13, credito), (14, Decimal("0.00")),
                ):
                    linhas[linha_pai - 1] = self.exclusor._substituir_campo(
                        linhas[linha_pai - 1], campo, self.exclusor._fmt(valor)
                    )
                    alteracoes += 1

            if pais_afetados:
                alteracoes += self.exclusor._recalcular_consolidacao(
                    linhas, tributo, cfg["reg"], cfg["consol"]
                )
        return alteracoes, avisos

    def _identificar_pai_e_filho_credito(
        self,
        linhas_antes: list[str],
        linhas_atuais: list[str],
        pais: list[tuple[int, list[int]]],
        tributo: str,
        taxa: str,
        cst: str,
        base_c170: Decimal,
    ) -> tuple[int, list[int], int] | None:
        """Resolve o M100/M500 pelo filho M105/M505 que pertence aos C170.

        Hotfix 17.6.8. A alíquota, sozinha, não identifica o grupo de crédito:
        um arquivo pode possuir mais de um M100 a 1,65% (ou M500 a 7,60%)
        para origens documentais distintas. O vínculo é provado primeiro no
        nível do filho usando base, origem documental e NAT_BC_CRED já existente;
        só depois o pai é inferido pela hierarquia. Nenhuma natureza é criada.
        """
        cfg = self.exclusor.M_PARENT[tributo]
        candidatos_pai = [
            (linha_pai, filhos)
            for linha_pai, filhos in pais
            if self.exclusor._taxa_igual(
                self.exclusor._campo_linha(linhas_atuais[linha_pai - 1], 4), taxa
            )
        ]
        if not candidatos_pai:
            return None

        filhos_cst: list[int] = []
        pai_por_filho: dict[int, tuple[int, list[int]]] = {}
        for linha_pai, filhos in candidatos_pai:
            for linha_filho in filhos:
                if self.exclusor._campo_linha(
                    linhas_atuais[linha_filho - 1], 2
                ) != cst:
                    continue
                filhos_cst.append(linha_filho)
                pai_por_filho[linha_filho] = (linha_pai, filhos)

        if not filhos_cst:
            return None

        # Mesmo com vários pais, um único filho elegível já prova o vínculo.
        linha_child = self.exclusor._escolher_child_por_base(
            linhas_atuais, filhos_cst, base_c170
        )
        if linha_child is None:
            linha_child = self.exclusor._escolher_child_por_origem_documental(
                linhas_antes, linhas_atuais, filhos_cst, tributo, taxa, cst
            )
        if linha_child is None:
            # Mantém todos os pais no contexto para que a natureza cruzada possa
            # usar uma segunda alíquota comprovada do mesmo crédito.
            linha_child = self.exclusor._escolher_child_por_natureza_cruzada(
                linhas_antes, linhas_atuais, pais, filhos_cst, tributo, taxa, cst
            )
        if linha_child is None:
            return None

        pai = pai_por_filho.get(linha_child)
        if pai is None:
            return None
        linha_pai, filhos = pai

        # Guarda hierárquica final: o filho escolhido precisa estar realmente
        # sob o pai inferido e o registro deve ser o esperado para o tributo.
        if linha_child not in filhos:
            return None
        if self.exclusor._codigo(linhas_atuais[linha_pai - 1]) != cfg["reg"]:
            return None
        if self.exclusor._codigo(linhas_atuais[linha_child - 1]) != cfg["child"]:
            return None
        return linha_pai, filhos, linha_child


    # CFOPs de devolução de compras mais usuais no varejo/comércio e operações
    # correlatas. A guarda adicional por IND_OPER=1 + CST 70-75 + ausência de
    # base/valor torna a normalização conservadora.
    CFOPS_DEVOLUCAO_COMPRA = frozenset({
        "5201", "5202", "5208", "5209", "5210", "5410", "5411",
        "5553", "5556", "5660", "5661", "5662",
        "6201", "6202", "6208", "6209", "6210", "6410", "6411",
        "6553", "6556", "6660", "6661", "6662",
        "7201", "7202",
    })

    def _normalizar_devolucoes_compra_saida(
        self, linhas: list[str]
    ) -> tuple[list[AjusteBlocoMExcel], list[str]]:
        """Converte CST 70-75 para 49 em devolução de compra inequivocamente de saída.

        O Guia Prático da EFD-Contribuições orienta CST 49 para devolução de
        compras porque se trata de operação de saída. O FiscalPro só corrige
        automaticamente quando:

        * o C100 pai é saída (IND_OPER=1);
        * o CFOP do C170 pertence ao conjunto de devoluções de compra;
        * PIS e/ou COFINS usam CST 70-75; e
        * os campos de base/alíquota/quantidade/valor daquele tributo estão
          vazios ou zerados.

        Se houver valor tributário preenchido, apenas emite aviso para não
        apagar uma decisão fiscal da usuária.
        """
        ajustes: list[AjusteBlocoMExcel] = []
        avisos: list[str] = []
        ind_oper = ""

        cfg = {
            "PIS": {"cst": 24, "dependentes": (25, 26, 27, 28, 29)},
            "COFINS": {"cst": 30, "dependentes": (31, 32, 33, 34, 35)},
        }
        csts_aquisicao = {str(n) for n in range(70, 76)}

        for i, linha in enumerate(list(linhas)):
            campos = self._campos(linha)
            if not campos:
                continue
            codigo = campos[0].upper()
            if codigo == "C100":
                ind_oper = self._campo(campos, 1).strip()
                continue
            if codigo != "C170" or ind_oper != "1":
                continue

            cfop = self._campo(campos, 10).strip()
            if cfop not in self.CFOPS_DEVOLUCAO_COMPRA:
                continue

            alterou_linha = False
            for tributo, meta in cfg.items():
                idx_cst = int(meta["cst"])
                cst = self._campo(campos, idx_cst).strip().zfill(2)
                if cst not in csts_aquisicao:
                    continue

                preenchidos = []
                for idx in meta["dependentes"]:
                    bruto = self._campo(campos, int(idx)).strip()
                    if not bruto:
                        continue
                    numero = self._decimal(bruto)
                    if numero is None or numero != 0:
                        preenchidos.append(bruto)
                if preenchidos:
                    avisos.append(
                        f"C170 linha {i + 1}, CFOP {cfop}: CST {cst} de {tributo} é de aquisição "
                        "em uma devolução de compra (saída), mas existem base/alíquota/valor preenchidos. "
                        "O FiscalPro preservou a linha para revisão manual em vez de apagar valores."
                    )
                    continue

                campos[idx_cst] = "49"
                alterou_linha = True
                ajustes.append(
                    AjusteBlocoMExcel(
                        registro="C170",
                        campo=f"CST_{tributo}",
                        original=cst,
                        novo="49",
                        justificativa=(
                            f"CFOP {cfop} identifica devolução de compra em operação de saída; "
                            "CST de aquisição 70-75 foi substituído por CST 49 sem alterar bases/valores."
                        ),
                        numero_linha=i + 1,
                    )
                )

            if alterou_linha:
                linhas[i] = self._linha(campos)

        return ajustes, avisos

    def _retotalizar_m400_m800(
        self, linhas: list[str]
    ) -> tuple[list[AjusteBlocoMExcel], list[str]]:
        codigos = {self._codigo(linha) for linha in linhas}
        fontes_nao_suportadas = codigos & self.OUTRAS_FONTES_RECEITA
        if fontes_nao_suportadas:
            lista = ", ".join(sorted(fontes_nao_suportadas))
            return [], [
                "M400/M800 não foram retotalizados automaticamente porque o arquivo possui "
                f"fonte(s) de receita ainda não mapeada(s): {lista}. O FiscalPro não fará "
                "rateio por aproximação."
            ]

        somas = {
            "PIS": self._somar_receita_sem_incidencia(linhas, "PIS"),
            "COFINS": self._somar_receita_sem_incidencia(linhas, "COFINS"),
        }
        contas = {
            "PIS": self._contas_receita_sem_incidencia(linhas, "PIS"),
            "COFINS": self._contas_receita_sem_incidencia(linhas, "COFINS"),
        }
        contas_0500 = {
            self._campo(self._campos(linha), 5).strip()
            for linha in linhas
            if self._codigo(linha) == "0500"
            and self._campo(self._campos(linha), 5).strip()
        }
        ajustes: list[AjusteBlocoMExcel] = []
        avisos: list[str] = []
        configuracoes = {
            "PIS": ("M400", "M410"),
            "COFINS": ("M800", "M810"),
        }

        for tributo, (pai, filho) in configuracoes.items():
            for cst, total in sorted(somas[tributo].items()):
                indices_pai = [
                    i for i, linha in enumerate(linhas)
                    if self._codigo(linha) == pai
                    and self._campo(self._campos(linha), 1).strip() == cst
                ]
                if len(indices_pai) != 1:
                    continue
                i = indices_pai[0]
                campos_pai = self._campos(linhas[i])
                antigo = self._decimal(self._campo(campos_pai, 2))
                if antigo is None:
                    continue
                total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                # COD_CTA de M400/M800 é obrigatório no PGE. Preenche somente
                # quando TODAS as fontes documentais daquele CST convergem para
                # uma única conta já cadastrada no 0500.
                conta_atual = self._campo(campos_pai, 3).strip()
                candidatas_conta = {
                    conta for conta in contas[tributo].get(cst, set()) if conta
                }
                if not conta_atual and len(candidatas_conta) == 1:
                    conta = next(iter(candidatas_conta))
                    if conta in contas_0500:
                        campos_pai[3] = conta
                        linhas[i] = self._linha(campos_pai)
                        ajustes.append(
                            AjusteBlocoMExcel(
                                registro=pai,
                                campo="COD_CTA",
                                original="",
                                novo=conta,
                                justificativa=(
                                    f"Conta contábil recomposta porque todas as fontes documentais "
                                    f"do CST {cst} usam a conta {conta}, previamente cadastrada no 0500."
                                ),
                                numero_linha=i + 1,
                            )
                        )
                    else:
                        avisos.append(
                            f"{pai} CST {cst}: a conta documental {conta} não foi localizada no 0500; "
                            "COD_CTA não foi preenchido automaticamente."
                        )
                elif not conta_atual and len(candidatas_conta) > 1:
                    avisos.append(
                        f"{pai} CST {cst}: as fontes documentais usam mais de uma conta contábil "
                        f"({', '.join(sorted(candidatas_conta))}); COD_CTA não foi escolhido por aproximação."
                    )

                if self._aprox(antigo, total):
                    continue

                # Localiza todos os filhos contíguos M410/M810 do pai atual.
                filhos: list[int] = []
                j = i + 1
                while j < len(linhas):
                    codigo = self._codigo(linhas[j])
                    if codigo == filho:
                        filhos.append(j)
                        j += 1
                        continue
                    if codigo.startswith("M"):
                        break
                    j += 1
                if not filhos:
                    avisos.append(
                        f"{pai} CST {cst}: total documental calculado em {self._fmt(total)}, "
                        f"mas não existe {filho} para preservar NAT_REC; ajuste automático bloqueado."
                    )
                    continue

                valores_filhos: list[tuple[int, str, Decimal]] = []
                filhos_validos = True
                for jf in filhos:
                    cf = self._campos(linhas[jf])
                    nat = self._campo(cf, 1).strip()
                    valor = self._decimal(self._campo(cf, 2))
                    if valor is None:
                        filhos_validos = False
                        break
                    valores_filhos.append((jf, nat, valor))
                if not filhos_validos:
                    avisos.append(
                        f"{pai} CST {cst}: há {filho} com valor inválido; retotalização bloqueada."
                    )
                    continue

                soma_filhos = sum((valor for _, _, valor in valores_filhos), Decimal("0"))
                if not self._aprox(soma_filhos, antigo):
                    avisos.append(
                        f"{pai} CST {cst}: a soma anterior dos {filho} ({self._fmt(soma_filhos)}) "
                        f"já divergia do pai ({self._fmt(antigo)}); ajuste automático bloqueado."
                    )
                    continue

                novos_filhos: dict[int, Decimal] = {}
                if len(valores_filhos) == 1:
                    novos_filhos[valores_filhos[0][0]] = total
                else:
                    # Não rateia entre naturezas específicas. Se existir uma única
                    # natureza genérica 999, preserva as demais e coloca nela apenas
                    # o residual necessário para fechar o pai.
                    genericos = [item for item in valores_filhos if item[1] == "999"]
                    if len(genericos) != 1:
                        avisos.append(
                            f"{pai} CST {cst}: existem {len(valores_filhos)} {filho} e não há "
                            "um único NAT_REC 999 para absorver o residual; rateio automático bloqueado."
                        )
                        continue
                    jf_gen, _, _ = genericos[0]
                    soma_especificos = sum(
                        (valor for jf, _, valor in valores_filhos if jf != jf_gen),
                        Decimal("0"),
                    )
                    residual = (total - soma_especificos).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    if residual < 0:
                        avisos.append(
                            f"{pai} CST {cst}: o total documental {self._fmt(total)} é menor que "
                            f"as naturezas específicas preservadas ({self._fmt(soma_especificos)}); "
                            "ajuste automático bloqueado."
                        )
                        continue
                    for jf, _, valor in valores_filhos:
                        novos_filhos[jf] = residual if jf == jf_gen else valor

                novo = self._fmt(total)
                campos_pai[2] = novo
                linhas[i] = self._linha(campos_pai)
                ajustes.append(
                    AjusteBlocoMExcel(
                        registro=pai,
                        campo="VL_TOT_REC",
                        original=self._fmt(antigo),
                        novo=novo,
                        justificativa=(
                            f"Total de receita CST {cst} recomposto a partir das fontes "
                            "documentais suportadas (A170/C170/C175), conforme regra do PGE."
                        ),
                        numero_linha=i + 1,
                    )
                )

                for jf, _, valor_antigo in valores_filhos:
                    valor_novo = novos_filhos[jf]
                    if self._aprox(valor_antigo, valor_novo):
                        continue
                    cf = self._campos(linhas[jf])
                    nat = self._campo(cf, 1).strip()
                    cf[2] = self._fmt(valor_novo)
                    linhas[jf] = self._linha(cf)
                    ajustes.append(
                        AjusteBlocoMExcel(
                            registro=filho,
                            campo="VL_REC",
                            original=self._fmt(valor_antigo),
                            novo=self._fmt(valor_novo),
                            justificativa=(
                                f"{filho} NAT_REC {nat} sincronizado com {pai}. "
                                + (
                                    "A natureza 999 absorveu somente o residual; naturezas específicas foram preservadas."
                                    if nat == "999" and len(valores_filhos) > 1
                                    else "O único filho acompanha integralmente o total do pai."
                                )
                            ),
                            numero_linha=jf + 1,
                        )
                    )
        return ajustes, avisos

    def _somar_receita_sem_incidencia(
        self, linhas: list[str], tributo: str
    ) -> dict[str, Decimal]:
        """Replica as fontes documentais já suportadas da validação M400/M800.

        17.8.124 adiciona o C175 (NFC-e analítica) e passa a respeitar o
        IND_ESCRI do C010/COD_MOD do C100 para não somar C170 indevido.
        """
        somas: dict[str, Decimal] = {}
        ind_a = ""
        ind_c = ""
        cod_mod_c = ""
        ind_escri_c010 = ""
        for linha in linhas:
            campos = self._campos(linha)
            if not campos:
                continue
            codigo = campos[0].upper()
            if codigo == "C010":
                ind_escri_c010 = self._campo(campos, 2).strip()
                continue
            if codigo == "A100":
                ind_a = self._campo(campos, 1).strip()
                continue
            if codigo == "C100":
                ind_c = self._campo(campos, 1).strip()
                cod_mod_c = self._campo(campos, 4).strip()
                continue

            if codigo == "A170" and ind_a == "1":
                idx_cst = 8 if tributo == "PIS" else 12
                idx_valor = 4
            elif (
                codigo == "C170"
                and ind_c == "1"
                and (cod_mod_c != "55" or ind_escri_c010 == "2")
            ):
                idx_cst = 24 if tributo == "PIS" else 30
                idx_valor = 6
            elif codigo == "C175":
                # C175: REG, CFOP, VL_OPR, VL_DESC, CST_PIS, ..., CST_COFINS...
                idx_cst = 4 if tributo == "PIS" else 10
                idx_valor = 2
            else:
                continue

            cst = self._campo(campos, idx_cst).strip().zfill(2)
            if cst not in self.CST_RECEITA_SEM_INCIDENCIA:
                continue
            valor = self._decimal(self._campo(campos, idx_valor)) or Decimal("0")
            somas[cst] = somas.get(cst, Decimal("0")) + valor
        return somas

    def _contas_receita_sem_incidencia(
        self, linhas: list[str], tributo: str
    ) -> dict[str, set[str]]:
        """Mapeia CST sem incidência -> contas contábeis das fontes suportadas."""
        contas: dict[str, set[str]] = {}
        ind_a = ""
        ind_c = ""
        cod_mod_c = ""
        ind_escri_c010 = ""
        for linha in linhas:
            campos = self._campos(linha)
            if not campos:
                continue
            codigo = campos[0].upper()
            if codigo == "C010":
                ind_escri_c010 = self._campo(campos, 2).strip()
                continue
            if codigo == "A100":
                ind_a = self._campo(campos, 1).strip()
                continue
            if codigo == "C100":
                ind_c = self._campo(campos, 1).strip()
                cod_mod_c = self._campo(campos, 4).strip()
                continue

            if codigo == "A170" and ind_a == "1":
                idx_cst = 8 if tributo == "PIS" else 12
                idx_conta = 16
            elif (
                codigo == "C170"
                and ind_c == "1"
                and (cod_mod_c != "55" or ind_escri_c010 == "2")
            ):
                idx_cst = 24 if tributo == "PIS" else 30
                idx_conta = 36
            elif codigo == "C175":
                idx_cst = 4 if tributo == "PIS" else 10
                idx_conta = 16
            else:
                continue

            cst = self._campo(campos, idx_cst).strip().zfill(2)
            if cst not in self.CST_RECEITA_SEM_INCIDENCIA:
                continue
            conta = self._campo(campos, idx_conta).strip()
            contas.setdefault(cst, set()).add(conta)
        return contas

    def _garantir_m205_m605(
        self, linhas: list[str]
    ) -> tuple[list[AjusteBlocoMExcel], list[str], bool]:
        """Cria M205/M605 ausentes apenas em cenários padronizados e comprováveis.

        O código 0110 indica incidência exclusivamente não cumulativa (1) ou
        exclusivamente cumulativa (2). Nesses dois casos, quando o M200/M600
        possui valor a recolher e não há filho para o NUM_CAMPO correspondente,
        o código de receita padrão é determinístico para PJ em geral.
        """
        ajustes: list[AjusteBlocoMExcel] = []
        avisos: list[str] = []
        ind_incidencia = ""
        for linha in linhas:
            if self._codigo(linha) == "0110":
                ind_incidencia = self._campo(self._campos(linha), 1).strip()
                break

        # Somente regimes exclusivos. Em incidência mista/especial, o código de
        # receita pode depender da origem e não deve ser inventado.
        if ind_incidencia not in {"1", "2"}:
            return ajustes, avisos, False

        config = {
            "M200": {
                "filho": "M205",
                "tributo": "PIS",
                "codigos": {"08": "691201", "12": "810902"},
            },
            "M600": {
                "filho": "M605",
                "tributo": "COFINS",
                "codigos": {"08": "585601", "12": "217201"},
            },
        }
        campo_por_num = {"08": 7, "12": 11}
        num_permitido = "08" if ind_incidencia == "1" else "12"
        insercoes: list[tuple[int, str, AjusteBlocoMExcel]] = []

        for pai, cfg in config.items():
            pais = [i for i, linha in enumerate(linhas) if self._codigo(linha) == pai]
            if len(pais) != 1:
                continue
            ip = pais[0]
            cp = self._campos(linhas[ip])
            filho = str(cfg["filho"])

            filhos_existentes: dict[str, list[int]] = {"08": [], "12": []}
            for jf, linha in enumerate(linhas):
                if self._codigo(linha) != filho:
                    continue
                cf = self._campos(linhas[jf])
                num = self._campo(cf, 1).strip().zfill(2)
                if num in filhos_existentes:
                    filhos_existentes[num].append(jf)

            for num, idx_pai in campo_por_num.items():
                valor = self._decimal(self._campo(cp, idx_pai)) or Decimal("0")
                if valor <= 0 or filhos_existentes[num]:
                    continue
                if num != num_permitido:
                    avisos.append(
                        f"{filho}: {pai} possui valor a recolher no NUM_CAMPO {num}, mas o 0110 "
                        f"indica incidência exclusiva {'não cumulativa' if ind_incidencia == '1' else 'cumulativa'}. "
                        "O FiscalPro não inventou código de receita; confira no PGE/DCTFWeb."
                    )
                    continue

                cod_rec = str(cfg["codigos"][num])
                nova_linha = self._linha([filho, num, cod_rec, self._fmt(valor)])
                # Insere logo após o pai e após outros filhos já existentes.
                pos = ip + 1
                while pos < len(linhas) and self._codigo(linhas[pos]) == filho:
                    pos += 1
                ajuste = AjusteBlocoMExcel(
                    registro=filho,
                    campo="REGISTRO COMPLETO",
                    original="(ausente)",
                    novo=nova_linha,
                    justificativa=(
                        f"{filho} criado porque {pai} possui contribuição a recolher no NUM_CAMPO {num}. "
                        f"Código de receita padrão de {cfg['tributo']} para incidência "
                        f"{'não cumulativa' if num == '08' else 'cumulativa'} conforme 0110."
                    ),
                    numero_linha=pos + 1,
                )
                insercoes.append((pos, nova_linha, ajuste))

        if not insercoes:
            return ajustes, avisos, False

        # Inserções em ordem crescente com compensação do deslocamento.
        deslocamento = 0
        for pos, nova_linha, ajuste in sorted(insercoes, key=lambda x: x[0]):
            real = pos + deslocamento
            linhas.insert(real, nova_linha)
            ajustes.append(
                AjusteBlocoMExcel(
                    registro=ajuste.registro,
                    campo=ajuste.campo,
                    original=ajuste.original,
                    novo=ajuste.novo,
                    justificativa=ajuste.justificativa,
                    numero_linha=real + 1,
                )
            )
            deslocamento += 1
        return ajustes, avisos, True

    @staticmethod
    def _campos(linha: str) -> list[str]:
        texto = str(linha or "").rstrip("\r\n")
        if texto.startswith("|"):
            texto = texto[1:]
        if texto.endswith("|"):
            texto = texto[:-1]
        return texto.split("|") if texto else []

    @staticmethod
    def _linha(campos: list[str]) -> str:
        return "|" + "|".join(campos) + "|"

    @staticmethod
    def _codigo(linha: str) -> str:
        campos = SincronizadorBlocoMExcel._campos(linha)
        return campos[0].upper() if campos else ""

    @staticmethod
    def _campo(campos: list[str], indice: int) -> str:
        return campos[indice] if 0 <= indice < len(campos) else ""

    @staticmethod
    def _decimal(valor: str) -> Decimal | None:
        texto = str(valor or "").strip()
        if not texto:
            return None
        texto = texto.replace(".", "").replace(",", ".") if "," in texto else texto
        try:
            return Decimal(texto)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _normalizar_taxa(valor: str) -> str:
        numero = SincronizadorBlocoMExcel._decimal(valor)
        if numero is None:
            return ""
        return f"{numero:.4f}"

    @staticmethod
    def _fmt(valor: Decimal) -> str:
        return f"{valor.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}".replace(".", ",")

    @staticmethod
    def _aprox(a: Decimal, b: Decimal) -> bool:
        return (a - b).copy_abs() <= Decimal("0.01")
