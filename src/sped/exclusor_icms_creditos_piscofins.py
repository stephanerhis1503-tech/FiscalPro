from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Callable

from .consolidador_creditos_bloco_m import ConsolidadorCreditosBlocoM
from .estatisticas import CalculadorEstatisticasSPED
from .indice import IndiceSPED
from .leitor import LeitorSPEDUnificado
from .pre_validador import PreValidadorPVA
from .recalculador_piscofins import RecalculadorPISCOFINS
from .reapurador_bloco_m import ReapuradorBlocoM, ResultadoReapuracaoBlocoM

ProgressoCallback = Callable[[int, str], None]


@dataclass(slots=True)
class ItemExclusaoICMS:
    chave_nfe: str
    numero_documento: str
    numero_item: str
    codigo_item: str
    linha_contribuicoes: int
    linha_fiscal: int
    cfop: str
    cst_pis: str
    cst_cofins: str
    aliquota_pis: Decimal
    aliquota_cofins: Decimal
    base_pis_anterior: Decimal
    base_cofins_anterior: Decimal
    valor_icms: Decimal
    base_pis_nova: Decimal
    base_cofins_nova: Decimal
    ja_excluido: bool = False


@dataclass(slots=True)
class ResultadoAnaliseExclusaoICMS:
    caminho_fiscal: Path
    encoding_fiscal: str
    cnpj: str
    periodo: str
    documentos_aptos: int = 0
    itens_aptos: list[ItemExclusaoICMS] = field(default_factory=list)
    itens_ja_excluidos: list[ItemExclusaoICMS] = field(default_factory=list)
    inconsistencias: list[str] = field(default_factory=list)
    total_icms_excluir: Decimal = Decimal("0.00")
    reducao_pis_estimada: Decimal = Decimal("0.00")
    reducao_cofins_estimada: Decimal = Decimal("0.00")
    grupos_base: dict[tuple[str, str, str], Decimal] = field(default_factory=dict)

    @property
    def pode_gerar(self) -> bool:
        return bool(self.itens_aptos) and not self.inconsistencias

    @property
    def itens_alterar(self) -> int:
        return len(self.itens_aptos)


@dataclass(slots=True)
class ResultadoAplicacaoExclusaoICMS:
    caminho_sped: Path
    caminho_relatorio: Path
    documentos_alterados: int
    itens_alterados: int
    total_icms_excluido: Decimal
    reducao_pis: Decimal
    reducao_cofins: Decimal
    alteracoes_bloco_m: int
    pre_validador_erros: int
    pre_validador_avisos: int


@dataclass(slots=True)
class _Documento:
    numero_linha: int
    campos: list[str]
    itens: list[tuple[int, list[str]]]

    @property
    def chave(self) -> str:
        return self._campo(8)

    @property
    def numero(self) -> str:
        return self._campo(7)

    def _campo(self, indice: int) -> str:
        return self.campos[indice].strip() if indice < len(self.campos) else ""


class ExclusorICMSCreditosPISCOFINS:
    """Exclui ICMS próprio já confirmado no SPED Fiscal das bases de crédito.

    Hotfix 17.3.16. A fonte do valor de ICMS é exclusivamente um EFD ICMS/IPI
    corrigido. O cruzamento é estrito por CHV_NFE + NUM_ITEM + COD_ITEM e o
    arquivo de Contribuições só é alterado quando a base ainda contém o ICMS.

    O módulo não estima ICMS, não usa ICMS-ST e não reclassifica NAT_BC_CRED.
    Após a exclusão documental, sincroniza M105/M505, M100/M500 e M200/M600
    somente quando a apuração é simples e comprovadamente segura.
    """

    TOLERANCIA = Decimal("0.02")
    TOLERANCIA_MAPEAMENTO_ABS = Decimal("500.00")
    TOLERANCIA_MAPEAMENTO_REL = Decimal("0.005")  # 0,5%
    CST_CREDITO = {str(n) for n in range(50, 67)}
    CFOPS_FONTE_SEGURA = {"1102", "2102"}

    # Índices sem os separadores externos; REG está em 0.
    C170 = {
        "num_item": 1,
        "cod_item": 2,
        "cfop": 10,
        "vl_bc_icms": 12,
        "vl_icms": 14,
        "cst_pis": 24,
        "base_pis": 25,
        "aliq_pis": 26,
        "vl_pis": 29,
        "cst_cofins": 30,
        "base_cofins": 31,
        "aliq_cofins": 32,
        "vl_cofins": 35,
    }

    M_PARENT = {
        "PIS": {"reg": "M100", "child": "M105", "consol": "M200"},
        "COFINS": {"reg": "M500", "child": "M505", "consol": "M600"},
    }

    def __init__(self) -> None:
        self.leitor = LeitorSPEDUnificado()
        self.calculador = CalculadorEstatisticasSPED()
        self.consolidador_m = ConsolidadorCreditosBlocoM()
        self.recalculador = RecalculadorPISCOFINS()
        self.reapurador_m = ReapuradorBlocoM()
        self.pre_validador = PreValidadorPVA()

    def analisar(
        self,
        linhas_contribuicoes: list[str],
        tipo_contribuicoes: str,
        cnpj_contribuicoes: str,
        periodo_contribuicoes: str,
        caminho_fiscal: str | Path,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAnaliseExclusaoICMS:
        if str(tipo_contribuicoes or "").strip().upper() != "EFD CONTRIBUIÇÕES":
            raise RuntimeError(
                "Abra a EFD Contribuições antes de importar o ICMS do SPED Fiscal corrigido."
            )

        fiscal = Path(caminho_fiscal)
        self._progresso(progresso, 5, "Lendo o SPED Fiscal corrigido...")
        linhas_fiscal, encoding_fiscal = self.leitor.ler(fiscal)
        indice_fiscal = IndiceSPED().construir(linhas_fiscal)
        estat_fiscal = self.calculador.calcular(linhas_fiscal, indice_fiscal)

        if estat_fiscal.tipo_sped != "EFD ICMS/IPI (Fiscal)":
            raise RuntimeError("O arquivo selecionado não foi identificado como EFD ICMS/IPI (Fiscal).")
        if self._digitos(estat_fiscal.cnpj) != self._digitos(cnpj_contribuicoes):
            raise RuntimeError(
                "O CNPJ do SPED Fiscal é diferente do CNPJ da EFD Contribuições. "
                "Nenhuma alteração foi feita."
            )
        if self._normalizar_periodo(estat_fiscal.periodo) != self._normalizar_periodo(periodo_contribuicoes):
            raise RuntimeError(
                "A competência do SPED Fiscal é diferente da competência da EFD Contribuições. "
                "Nenhuma alteração foi feita."
            )

        resultado = ResultadoAnaliseExclusaoICMS(
            caminho_fiscal=fiscal,
            encoding_fiscal=encoding_fiscal,
            cnpj=estat_fiscal.cnpj,
            periodo=estat_fiscal.periodo,
        )

        self._progresso(progresso, 20, "Indexando notas de entrada nos dois arquivos...")
        docs_fiscal = self._mapear_documentos(linhas_fiscal)
        docs_contrib = self._mapear_documentos(linhas_contribuicoes)
        contrib_por_chave = {doc.chave: doc for doc in docs_contrib if doc.chave}

        documentos_encontrados: set[str] = set()
        candidatos = 0

        for doc_fiscal in docs_fiscal:
            # Somente entrada emitida por terceiros.
            if self._campo(doc_fiscal.campos, 1) != "0" or self._campo(doc_fiscal.campos, 2) != "1":
                continue
            if not doc_fiscal.chave:
                continue

            itens_fonte = []
            for linha_num, campos in doc_fiscal.itens:
                cfop = self._campo(campos, self.C170["cfop"])
                icms = self._decimal(self._campo(campos, self.C170["vl_icms"]))
                if cfop in self.CFOPS_FONTE_SEGURA and icms is not None and icms > 0:
                    itens_fonte.append((linha_num, campos, icms))
            if not itens_fonte:
                continue

            candidatos += len(itens_fonte)
            doc_contrib = contrib_por_chave.get(doc_fiscal.chave)
            if doc_contrib is None:
                resultado.inconsistencias.append(
                    f"NF {doc_fiscal.numero} — chave {doc_fiscal.chave}: não encontrada na EFD Contribuições."
                )
                continue

            mapa_itens_contrib: dict[tuple[str, str], list[tuple[int, list[str]]]] = {}
            for linha_num, campos in doc_contrib.itens:
                chave_item = (
                    self._campo(campos, self.C170["num_item"]),
                    self._campo(campos, self.C170["cod_item"]),
                )
                mapa_itens_contrib.setdefault(chave_item, []).append((linha_num, campos))

            doc_tem_item_apto = False
            for linha_fiscal, campos_fiscal, icms in itens_fonte:
                chave_item = (
                    self._campo(campos_fiscal, self.C170["num_item"]),
                    self._campo(campos_fiscal, self.C170["cod_item"]),
                )
                correspondencias = mapa_itens_contrib.get(chave_item, [])
                if len(correspondencias) != 1:
                    resultado.inconsistencias.append(
                        f"NF {doc_fiscal.numero}, item {chave_item[0]} / {chave_item[1]}: "
                        "não houve correspondência única na EFD Contribuições."
                    )
                    continue

                linha_contrib, campos_contrib = correspondencias[0]
                cst_pis = self._campo(campos_contrib, self.C170["cst_pis"])
                cst_cofins = self._campo(campos_contrib, self.C170["cst_cofins"])
                if cst_pis not in self.CST_CREDITO or cst_cofins not in self.CST_CREDITO:
                    resultado.inconsistencias.append(
                        f"NF {doc_fiscal.numero}, item {chave_item[0]} / {chave_item[1]}: "
                        f"CST PIS/COFINS {cst_pis or '-'} / {cst_cofins or '-'} não é um par de CSTs de crédito 50–66."
                    )
                    continue

                base_icms_fiscal = self._decimal(self._campo(campos_fiscal, self.C170["vl_bc_icms"]))
                base_fiscal_pis = self._decimal(self._campo(campos_fiscal, self.C170["base_pis"]))
                base_fiscal_cofins = self._decimal(self._campo(campos_fiscal, self.C170["base_cofins"]))
                base_contrib_pis = self._decimal(self._campo(campos_contrib, self.C170["base_pis"]))
                base_contrib_cofins = self._decimal(self._campo(campos_contrib, self.C170["base_cofins"]))
                aliq_pis = self._decimal(self._campo(campos_contrib, self.C170["aliq_pis"]))
                aliq_cofins = self._decimal(self._campo(campos_contrib, self.C170["aliq_cofins"]))

                valores = (
                    base_icms_fiscal,
                    base_fiscal_pis,
                    base_fiscal_cofins,
                    base_contrib_pis,
                    base_contrib_cofins,
                    aliq_pis,
                    aliq_cofins,
                )
                if any(valor is None for valor in valores):
                    resultado.inconsistencias.append(
                        f"NF {doc_fiscal.numero}, item {chave_item[0]} / {chave_item[1]}: "
                        "base ou alíquota de PIS/COFINS insuficiente para cálculo seguro."
                    )
                    continue
                assert base_icms_fiscal is not None
                assert base_fiscal_pis is not None
                assert base_fiscal_cofins is not None
                assert base_contrib_pis is not None
                assert base_contrib_cofins is not None
                assert aliq_pis is not None
                assert aliq_cofins is not None

                # Hotfix 17.3.16 — o SPED Fiscal corrigido de julho contém
                # duas situações legítimas: algumas bases de PIS/COFINS já
                # vieram líquidas do ICMS e outras ainda vieram brutas. A
                # referência segura para a base bruta da aquisição é a
                # VL_BC_ICMS do próprio item (que também preserva frete/seguro
                # rateados quando compõem o custo). O alvo é essa base menos
                # o ICMS próprio, uma única vez.
                base_bruta_ref = base_icms_fiscal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                nova_base_pis = (base_bruta_ref - icms).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                nova_base_cofins = nova_base_pis
                if nova_base_pis < 0:
                    resultado.inconsistencias.append(
                        f"NF {doc_fiscal.numero}, item {chave_item[0]} / {chave_item[1]}: ICMS maior que a base."
                    )
                    continue

                # A própria EFD Fiscal precisa provar que sua base de crédito
                # é uma das duas formas esperadas: bruta ou já líquida. Se
                # não for, bloqueamos para não substituir uma composição
                # diferente de base por aproximação.
                fiscal_pis_ok = self._aprox(base_fiscal_pis, base_bruta_ref) or self._aprox(base_fiscal_pis, nova_base_pis)
                fiscal_cofins_ok = self._aprox(base_fiscal_cofins, base_bruta_ref) or self._aprox(base_fiscal_cofins, nova_base_cofins)
                if not fiscal_pis_ok or not fiscal_cofins_ok:
                    resultado.inconsistencias.append(
                        f"NF {doc_fiscal.numero}, item {chave_item[0]} / {chave_item[1]}: "
                        "a base do SPED Fiscal não coincide nem com a base bruta de aquisição "
                        "nem com a base já líquida do ICMS."
                    )
                    continue

                bruto_ok = (
                    self._aprox(base_contrib_pis, base_bruta_ref)
                    and self._aprox(base_contrib_cofins, base_bruta_ref)
                )
                ja_liquido = (
                    self._aprox(base_contrib_pis, nova_base_pis)
                    and self._aprox(base_contrib_cofins, nova_base_cofins)
                )

                item = ItemExclusaoICMS(
                    chave_nfe=doc_fiscal.chave,
                    numero_documento=doc_fiscal.numero,
                    numero_item=chave_item[0],
                    codigo_item=chave_item[1],
                    linha_contribuicoes=linha_contrib,
                    linha_fiscal=linha_fiscal,
                    cfop=self._campo(campos_contrib, self.C170["cfop"]),
                    cst_pis=cst_pis,
                    cst_cofins=cst_cofins,
                    aliquota_pis=aliq_pis,
                    aliquota_cofins=aliq_cofins,
                    base_pis_anterior=base_contrib_pis,
                    base_cofins_anterior=base_contrib_cofins,
                    valor_icms=icms,
                    base_pis_nova=nova_base_pis,
                    base_cofins_nova=nova_base_cofins,
                    ja_excluido=ja_liquido,
                )

                if ja_liquido:
                    resultado.itens_ja_excluidos.append(item)
                    continue
                if not bruto_ok:
                    resultado.inconsistencias.append(
                        f"NF {doc_fiscal.numero}, item {chave_item[0]} / {chave_item[1]}: "
                        f"base da EFD Contribuições ({self._fmt(base_contrib_pis)}/{self._fmt(base_contrib_cofins)}) "
                        f"não coincide nem com a base bruta de aquisição ({self._fmt(base_bruta_ref)}) "
                        "nem com a base já líquida de ICMS."
                    )
                    continue

                resultado.itens_aptos.append(item)
                documentos_encontrados.add(doc_fiscal.chave)
                doc_tem_item_apto = True
                resultado.total_icms_excluir += icms
                resultado.reducao_pis_estimada += (
                    icms * aliq_pis / Decimal("100")
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                resultado.reducao_cofins_estimada += (
                    icms * aliq_cofins / Decimal("100")
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                for tributo, aliq, cst in (
                    ("PIS", aliq_pis, cst_pis),
                    ("COFINS", aliq_cofins, cst_cofins),
                ):
                    chave_grupo = (tributo, self._fmt_taxa(aliq), cst)
                    resultado.grupos_base[chave_grupo] = resultado.grupos_base.get(
                        chave_grupo, Decimal("0.00")
                    ) + icms

            if doc_tem_item_apto:
                documentos_encontrados.add(doc_fiscal.chave)

        resultado.documentos_aptos = len(documentos_encontrados)
        resultado.total_icms_excluir = resultado.total_icms_excluir.quantize(Decimal("0.01"))
        resultado.reducao_pis_estimada = resultado.reducao_pis_estimada.quantize(Decimal("0.01"))
        resultado.reducao_cofins_estimada = resultado.reducao_cofins_estimada.quantize(Decimal("0.01"))
        resultado.grupos_base = {
            chave: valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            for chave, valor in resultado.grupos_base.items()
        }

        self._progresso(
            progresso,
            100,
            f"Cruzamento concluído: {resultado.itens_alterar} de {candidatos} item(ns) apto(s).",
        )
        return resultado

    def gerar(
        self,
        linhas_contribuicoes: list[str],
        encoding_contribuicoes: str,
        tipo_contribuicoes: str,
        analise: ResultadoAnaliseExclusaoICMS,
        caminho_saida: str | Path,
        progresso: ProgressoCallback | None = None,
    ) -> ResultadoAplicacaoExclusaoICMS:
        if not analise.pode_gerar:
            detalhe = "\n".join(f"- {x}" for x in analise.inconsistencias[:8])
            if len(analise.inconsistencias) > 8:
                detalhe += f"\n- ... e mais {len(analise.inconsistencias) - 8} inconsistência(s)."
            raise RuntimeError(
                "A exclusão automática foi bloqueada porque o cruzamento não ficou 100% seguro."
                + (f"\n\n{detalhe}" if detalhe else "")
            )

        # O botão ICMS → PIS/COFINS precisa funcionar independentemente da ordem
        # em que a usuária executou as correções anteriores. Guardamos a validação
        # inicial para distinguir pendências que já existiam de qualquer problema
        # eventualmente introduzido por esta rotina.
        validacao_antes = self.pre_validador.validar(linhas_contribuicoes, tipo_contribuicoes)

        novas = list(linhas_contribuicoes)
        self._progresso(progresso, 10, "Excluindo o ICMS próprio das bases dos C170...")
        afetadas: set[tuple[int, str]] = set()
        pis_antes = Decimal("0.00")
        cofins_antes = Decimal("0.00")

        for item in analise.itens_aptos:
            idx = item.linha_contribuicoes - 1
            pis_antes += self._decimal(self._campo_linha(novas[idx], self.C170["vl_pis"])) or Decimal("0")
            cofins_antes += self._decimal(self._campo_linha(novas[idx], self.C170["vl_cofins"])) or Decimal("0")
            novas[idx] = self._substituir_campo(novas[idx], self.C170["base_pis"], self._fmt(item.base_pis_nova))
            novas[idx] = self._substituir_campo(novas[idx], self.C170["base_cofins"], self._fmt(item.base_cofins_nova))
            afetadas.add((item.linha_contribuicoes, "PIS"))
            afetadas.add((item.linha_contribuicoes, "COFINS"))

        self._progresso(progresso, 35, "Recalculando PIS/COFINS dos itens e totais C100...")
        recalculo = self.recalculador.recalcular(novas, afetadas, tipo_contribuicoes)
        novas = recalculo.linhas
        pis_depois = Decimal("0.00")
        cofins_depois = Decimal("0.00")
        for item in analise.itens_aptos:
            linha = novas[item.linha_contribuicoes - 1]
            pis_depois += self._decimal(self._campo_linha(linha, self.C170["vl_pis"])) or Decimal("0")
            cofins_depois += self._decimal(self._campo_linha(linha, self.C170["vl_cofins"])) or Decimal("0")

        self._progresso(progresso, 50, "Preparando o Bloco M para a reapuração...")
        alteracoes_m = 0

        # Se o arquivo ainda estiver numa etapa anterior do fluxo (por exemplo,
        # com M100/M500 duplicados), consolida primeiro SOMENTE os grupos que o
        # consolidador 17.3.9 já classifica como matematicamente seguros. Isso
        # elimina a dependência de a usuária ter gerado/reaberto uma cópia
        # intermediária antes de usar o botão ICMS → PIS/COFINS.
        planos = self.consolidador_m.analisar(novas)
        if planos:
            sementes = {numero for plano in planos for numero in plano.linhas_pais}
            consolidado = self.consolidador_m.consolidar(novas, sementes)
            novas = consolidado.linhas
            alteracoes_m += len(consolidado.alteracoes)
            if consolidado.estrutura_alterada:
                novas, qtd_totalizadores = self._recalcular_totalizadores(novas)
                alteracoes_m += qtd_totalizadores

        self._progresso(progresso, 60, "Sincronizando M105/M505 e M100/M500...")
        tamanho_antes_m = len(novas)
        alteracoes_m += self._sincronizar_bloco_m(novas, linhas_contribuicoes, analise)
        if len(novas) != tamanho_antes_m:
            novas, qtd_totalizadores = self._recalcular_totalizadores(novas)
            alteracoes_m += qtd_totalizadores

        self._progresso(progresso, 78, "Validando a nova apuração localmente...")
        validacao = self.pre_validador.validar(novas, tipo_contribuicoes)
        novos_erros = self._erros_novos(validacao_antes.erros, validacao.erros)
        if novos_erros:
            amostra = "\n".join(
                f"- linha {x.numero_linha} {x.registro} {x.campo}: {x.mensagem}"
                for x in novos_erros[:8]
            )
            raise RuntimeError(
                "A exclusão do ICMS criaria nova(s) pendência(s) no Pré-Validador. "
                "Nenhum arquivo foi salvo.\n\n" + amostra
            )

        saida = Path(caminho_saida)
        saida.parent.mkdir(parents=True, exist_ok=True)
        self._progresso(progresso, 88, "Salvando nova cópia da EFD Contribuições...")
        encoding_saida = self._encoding_saida_sem_bom(encoding_contribuicoes)
        with saida.open("w", encoding=encoding_saida, newline="") as stream:
            stream.writelines(novas)

        relatorio = saida.with_name(saida.stem + "_RELATORIO_ICMS_PISCOFINS.txt")
        reducao_pis = (pis_antes - pis_depois).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        reducao_cofins = (cofins_antes - cofins_depois).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self._salvar_relatorio(
            relatorio,
            analise,
            saida,
            reducao_pis,
            reducao_cofins,
            alteracoes_m,
            len(validacao.erros),
            len(validacao.avisos),
        )
        self._progresso(progresso, 100, "ICMS excluído das bases e Bloco M recalculado com sucesso.")
        return ResultadoAplicacaoExclusaoICMS(
            caminho_sped=saida,
            caminho_relatorio=relatorio,
            documentos_alterados=analise.documentos_aptos,
            itens_alterados=analise.itens_alterar,
            total_icms_excluido=analise.total_icms_excluir,
            reducao_pis=reducao_pis,
            reducao_cofins=reducao_cofins,
            alteracoes_bloco_m=alteracoes_m,
            pre_validador_erros=len(validacao.erros),
            pre_validador_avisos=len(validacao.avisos),
        )

    def _sincronizar_bloco_m(
        self,
        linhas: list[str],
        linhas_antes: list[str],
        analise: ResultadoAnaliseExclusaoICMS,
    ) -> int:
        alteracoes = 0

        # Arquivos mais antigos podem chegar aqui sem M600/M610. A criação
        # segura precisa ocorrer ANTES de o M200 ser atualizado pelos créditos
        # de PIS, pois a regra 17.3.8 usa o M200 original como prova de que não
        # havia deduções especiais a espelhar.
        tem_delta_cofins = any(
            trib == "COFINS" and delta > 0
            for (trib, _taxa, _cst), delta in analise.grupos_base.items()
        )
        if tem_delta_cofins and not any(self._codigo(l) == "M600" for l in linhas):
            resultado_cofins = ResultadoReapuracaoBlocoM(linhas=linhas)
            self.reapurador_m._criar_cofins_quando_seguro(linhas, resultado_cofins)
            if any(self._codigo(l) == "M600" for l in linhas):
                alteracoes += len(resultado_cofins.alteracoes)

        for tributo in ("PIS", "COFINS"):
            cfg = self.M_PARENT[tributo]
            grupos = {
                (taxa, cst): delta
                for (trib, taxa, cst), delta in analise.grupos_base.items()
                if trib == tributo and delta > 0
            }
            if not grupos:
                continue

            # Bases documentais C170 antes da exclusão, por alíquota/CST, para
            # identificar sem reclassificação qual M105/M505 representa o bloco C.
            c170_antes = self._agrupar_bases_c170(linhas_antes, tributo)
            # Hotfix 17.3.15 — este módulo só importa ICMS de compras para
            # revenda comprovadas pelos CFOPs 1102/2102. Para identificar o
            # M105/M505 correto, a base de comparação deve ser a base TOTAL
            # dessa família documental, e não a soma de todos os C170 CST 50
            # do arquivo (que também pode conter devoluções/outras entradas).
            c170_fonte_segura = self._agrupar_bases_c170_fonte_segura(linhas_antes, tributo)
            pais = self._mapear_pais_bloco_m(linhas, cfg["reg"], cfg["child"])

            for (taxa, cst), delta in grupos.items():
                candidatos_pai = [
                    pai for pai in pais
                    if self._taxa_igual(self._campo_linha(linhas[pai[0] - 1], 4), taxa)
                ]
                if len(candidatos_pai) != 1:
                    raise RuntimeError(
                        f"Bloco M: não foi possível identificar um único {cfg['reg']} para alíquota {taxa} ({tributo})."
                    )
                linha_pai, filhos = candidatos_pai[0]
                filhos_cst = [
                    linha_filho for linha_filho in filhos
                    if self._campo_linha(linhas[linha_filho - 1], 2) == cst
                ]
                if not filhos_cst:
                    raise RuntimeError(
                        f"Bloco M: não há {cfg['child']} CST {cst} sob {cfg['reg']} da alíquota {taxa}."
                    )

                base_c170 = c170_fonte_segura.get((taxa, cst))
                if base_c170 is None or base_c170 <= 0:
                    base_c170 = c170_antes.get((taxa, cst), Decimal("0.00"))
                linha_child = self._escolher_child_por_base(linhas, filhos_cst, base_c170)
                if linha_child is None:
                    # Hotfix 17.3.13 — quando o M105/M505 foi montado por
                    # naturezas distintas, a base dos C170 pode não coincidir
                    # exatamente com um filho isolado. Antes de bloquear,
                    # identificamos os outros filhos por suas origens
                    # documentais (A170 e D101/D105) e, se a composição global
                    # fechar com tolerância segura, o filho remanescente é o
                    # correspondente ao bloco C. Isso evita exigir que a
                    # usuária escolha manualmente um M105/M505 que o próprio
                    # arquivo permite rastrear.
                    linha_child = self._escolher_child_por_origem_documental(
                        linhas_antes, linhas, filhos_cst, tributo, taxa, cst
                    )
                if linha_child is None:
                    # Hotfix 17.3.14 — vínculo cruzado pela NAT_BC_CRED.
                    # Quando a base agregada do C170 não fecha exatamente com
                    # nenhum filho (por composição antiga do gerador), usamos
                    # uma segunda alíquota do MESMO crédito que seja exclusiva
                    # dos C170 para descobrir qual NAT_BC_CRED representa
                    # mercadorias. Ex.: em julho/2026, 0,65% PIS / 3,00% COFINS
                    # aparecem apenas em C170 e apontam inequivocamente para a
                    # NAT 02; a mesma NAT pode então ser localizada no grupo
                    # de 1,65% / 7,60%. Nenhum código de natureza é inventado.
                    linha_child = self._escolher_child_por_natureza_cruzada(
                        linhas_antes, linhas, pais, filhos_cst, tributo, taxa, cst
                    )
                if linha_child is None:
                    raise RuntimeError(
                        f"Bloco M: o {cfg['child']} correspondente aos C170 de alíquota {taxa} / CST {cst} "
                        "não pôde ser identificado com segurança."
                    )
                child = linhas[linha_child - 1]
                total = self._decimal(self._campo_linha(child, 3))
                cumulativa_txt = self._campo_linha(child, 4).strip()
                # No PGE/geradores é comum VL_BC_*_CUM vir vazio quando toda
                # a base é não cumulativa. Campo vazio, nesse contexto, vale
                # zero; não é motivo para bloquear uma identificação já
                # comprovada por CFOP + base + CST + alíquota.
                cumulativa = self._decimal(cumulativa_txt) if cumulativa_txt else Decimal("0.00")
                nao_cum = self._decimal(self._campo_linha(child, 5))
                base_credito = self._decimal(self._campo_linha(child, 6))
                if None in (total, nao_cum, base_credito):
                    raise RuntimeError(f"Bloco M: {cfg['child']} linha {linha_child} tem base inválida.")
                assert total is not None and cumulativa is not None and nao_cum is not None and base_credito is not None
                if cumulativa.copy_abs() > self.TOLERANCIA:
                    raise RuntimeError(
                        f"Bloco M: {cfg['child']} linha {linha_child} possui base cumulativa; revisão manual necessária."
                    )
                if not self._aprox(total, nao_cum) or not self._aprox(nao_cum, base_credito):
                    raise RuntimeError(
                        f"Bloco M: {cfg['child']} linha {linha_child} não possui bases não cumulativas coincidentes."
                    )
                nova = (base_credito - delta).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if nova < 0:
                    raise RuntimeError(f"Bloco M: a redução excederia a base do {cfg['child']} linha {linha_child}.")
                for campo in (3, 5, 6):
                    linhas[linha_child - 1] = self._substituir_campo(
                        linhas[linha_child - 1], campo, self._fmt(nova)
                    )
                    alteracoes += 1

            # Depois dos filhos, recalcula cada pai atingido pela soma dos seus filhos.
            for linha_pai, filhos in pais:
                taxa_txt = self._campo_linha(linhas[linha_pai - 1], 4)
                if not any(self._taxa_igual(taxa_txt, taxa) for taxa, _ in grupos):
                    continue
                linha = linhas[linha_pai - 1]
                self._validar_pai_credito_simples(linha, cfg["reg"], linha_pai)
                base = sum(
                    (self._decimal(self._campo_linha(linhas[f - 1], 5)) or Decimal("0"))
                    for f in filhos
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                taxa = self._decimal(taxa_txt)
                assert taxa is not None
                credito = (base * taxa / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                for campo, valor in ((3, base), (7, credito), (11, credito), (13, credito), (14, Decimal("0.00"))):
                    linhas[linha_pai - 1] = self._substituir_campo(
                        linhas[linha_pai - 1], campo, self._fmt(valor)
                    )
                    alteracoes += 1

            alteracoes += self._recalcular_consolidacao(linhas, tributo, cfg["reg"], cfg["consol"])
        return alteracoes

    def _recalcular_consolidacao(self, linhas: list[str], tributo: str, reg_pai: str, reg_consol: str) -> int:
        linhas_consol = [i for i, linha in enumerate(linhas, start=1) if self._codigo(linha) == reg_consol]
        criacoes = 0
        if not linhas_consol and reg_consol == "M600":
            # Arquivos anteriores à 17.3.8 podem não possuir M600/M610. Usa a
            # mesma regra conservadora já aprovada naquele hotfix: só cria a
            # COFINS quando existe um único M200/M210 básico, sem deduções
            # especiais, e as bases documentais PIS/COFINS estão pareadas.
            resultado = ResultadoReapuracaoBlocoM(linhas=linhas)
            self.reapurador_m._criar_cofins_quando_seguro(linhas, resultado)
            linhas_consol = [i for i, linha in enumerate(linhas, start=1) if self._codigo(linha) == reg_consol]
            criacoes = len(resultado.alteracoes)
            if not linhas_consol:
                detalhe = "; ".join(resultado.avisos) if resultado.avisos else "criação segura não comprovada"
                raise RuntimeError(f"Bloco M: {reg_consol} ausente e não pôde ser criado com segurança ({detalhe}).")
        if len(linhas_consol) != 1:
            raise RuntimeError(f"Bloco M: esperado um único {reg_consol}, encontrados {len(linhas_consol)}.")
        linha_num = linhas_consol[0]
        linha = linhas[linha_num - 1]
        valores = {i: self._decimal(self._campo_linha(linha, i)) for i in range(1, 13)}
        if any(valores[i] is None for i in range(1, 13)):
            raise RuntimeError(f"Bloco M: {reg_consol} linha {linha_num} possui campos numéricos inválidos.")
        v = {i: valores[i] or Decimal("0") for i in valores}

        creditos = Decimal("0.00")
        for linha_pai in (linha for linha in linhas if self._codigo(linha) == reg_pai):
            ind_desc = self._campo_linha(linha_pai, 12)
            saldo = self._decimal(self._campo_linha(linha_pai, 14)) or Decimal("0")
            if ind_desc != "0" or saldo.copy_abs() > self.TOLERANCIA:
                raise RuntimeError(
                    f"Bloco M: há {reg_pai} com desconto/saldo não simples; {reg_consol} não será recalculado automaticamente."
                )
            creditos += self._decimal(self._campo_linha(linha_pai, 13)) or Decimal("0")
        creditos = creditos.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        devido_nc = (v[1] - creditos - v[3]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        recolher_nc = (devido_nc - v[5] - v[6]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        recolher_cum = (v[8] - v[9] - v[10]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total = (recolher_nc + recolher_cum).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if min(devido_nc, recolher_nc, recolher_cum, total) < 0:
            raise RuntimeError(
                f"Bloco M: a nova apuração de {tributo} produziria saldo negativo em {reg_consol}; revisão manual necessária."
            )
        total_anterior = v[12].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        for campo, valor in ((2, creditos), (4, devido_nc), (7, recolher_nc), (11, recolher_cum), (12, total)):
            linhas[linha_num - 1] = self._substituir_campo(linhas[linha_num - 1], campo, self._fmt(valor))

        # Se há um único detalhamento M205/M605 e ele espelhava exatamente o
        # total anterior do M200/M600, o valor do débito deve acompanhar a nova
        # apuração. Não redistribuímos entre vários códigos de receita: nesse
        # cenário a rotina bloqueia em vez de inventar rateio.
        reg_detalhe = "M205" if reg_consol == "M200" else "M605"
        detalhes = [
            i for i, l in enumerate(linhas, start=1) if self._codigo(l) == reg_detalhe
        ]
        detalhe_alterado = 0
        if detalhes:
            if len(detalhes) != 1:
                raise RuntimeError(
                    f"Bloco M: existem {len(detalhes)} registros {reg_detalhe}; "
                    "não é seguro redistribuir automaticamente o novo débito entre códigos de receita."
                )
            dlinha = detalhes[0]
            debito_antigo = self._decimal(self._campo_linha(linhas[dlinha - 1], 3))
            if debito_antigo is None or not self._aprox(debito_antigo, total_anterior):
                raise RuntimeError(
                    f"Bloco M: {reg_detalhe} linha {dlinha} não espelhava o total anterior de {reg_consol}; "
                    "revisão manual necessária."
                )
            linhas[dlinha - 1] = self._substituir_campo(
                linhas[dlinha - 1], 3, self._fmt(total)
            )
            detalhe_alterado = 1

        return 5 + criacoes + detalhe_alterado

    def _validar_pai_credito_simples(self, linha: str, registro: str, linha_num: int) -> None:
        quantidade_txt = self._campo_linha(linha, 5).strip()
        aliq_qtd_txt = self._campo_linha(linha, 6).strip()
        quantidade = self._decimal(quantidade_txt) if quantidade_txt else Decimal("0.00")
        aliq_qtd = self._decimal(aliq_qtd_txt) if aliq_qtd_txt else Decimal("0.00")
        ajuste_acres = self._decimal(self._campo_linha(linha, 8)) or Decimal("0")
        ajuste_reduc = self._decimal(self._campo_linha(linha, 9)) or Decimal("0")
        diferido = self._decimal(self._campo_linha(linha, 10)) or Decimal("0")
        ind_desc = self._campo_linha(linha, 12).strip()
        saldo = self._decimal(self._campo_linha(linha, 14)) or Decimal("0")
        if quantidade is None or aliq_qtd is None:
            raise RuntimeError(f"Bloco M: {registro} linha {linha_num} possui campo de crédito por quantidade inválido.")
        if quantidade.copy_abs() > self.TOLERANCIA or aliq_qtd.copy_abs() > self.TOLERANCIA:
            raise RuntimeError(f"Bloco M: {registro} linha {linha_num} usa crédito por quantidade.")
        if any(x.copy_abs() > self.TOLERANCIA for x in (ajuste_acres, ajuste_reduc, diferido)):
            raise RuntimeError(f"Bloco M: {registro} linha {linha_num} possui ajustes/diferimento.")
        if ind_desc != "0" or saldo.copy_abs() > self.TOLERANCIA:
            raise RuntimeError(f"Bloco M: {registro} linha {linha_num} não está em desconto integral simples.")

    def _escolher_child_por_base(
        self, linhas: list[str], filhos: list[int], base_c170: Decimal
    ) -> int | None:
        if len(filhos) == 1:
            return filhos[0]
        candidatos: list[tuple[Decimal, int]] = []
        limite = max(self.TOLERANCIA_MAPEAMENTO_ABS, base_c170.copy_abs() * self.TOLERANCIA_MAPEAMENTO_REL)
        for linha_num in filhos:
            base = self._decimal(self._campo_linha(linhas[linha_num - 1], 6))
            if base is None:
                continue
            diferenca = (base - base_c170).copy_abs()
            if diferenca <= limite:
                candidatos.append((diferenca, linha_num))
        candidatos.sort()
        if not candidatos:
            return None
        if len(candidatos) > 1 and candidatos[0][0] == candidatos[1][0]:
            return None
        return candidatos[0][1]

    def _escolher_child_por_origem_documental(
        self,
        linhas_antes: list[str],
        linhas_atuais: list[str],
        filhos: list[int],
        tributo: str,
        taxa: str,
        cst: str,
    ) -> int | None:
        """Identifica o M105/M505 do bloco C por exclusão documental segura.

        Alguns geradores distribuem um mesmo crédito entre M105/M505 de
        naturezas diferentes. Nesses casos, comparar apenas a base agregada
        dos C170 com cada filho pode ser insuficiente. O hotfix 17.3.13 usa
        as bases de A170 e D101/D105, que são registros de origem distintos,
        para identificar seus respectivos filhos. Se esses vínculos fecham
        e resta exatamente um filho para o bloco C, ele é usado.

        A rotina não reclassifica NAT_BC_CRED e não inventa base: apenas
        identifica qual filho já existente corresponde aos C170.
        """
        if len(filhos) <= 1:
            return filhos[0] if filhos else None

        origens = self._agrupar_bases_origem_credito(linhas_antes, tributo)
        alvo = (taxa, cst)
        bases_origem: dict[str, Decimal] = {
            origem: grupos[alvo]
            for origem, grupos in origens.items()
            if alvo in grupos and grupos[alvo] > 0
        }
        base_c = bases_origem.get("C170")
        if base_c is None:
            return None

        bases_filhos: dict[int, Decimal] = {}
        for linha_num in filhos:
            base = self._decimal(self._campo_linha(linhas_atuais[linha_num - 1], 6))
            if base is None:
                return None
            bases_filhos[linha_num] = base

        # Para a exclusão por origem funcionar, as bases documentais conhecidas
        # precisam explicar praticamente toda a composição dos filhos.
        soma_origens = sum(bases_origem.values(), Decimal("0.00"))
        soma_filhos = sum(bases_filhos.values(), Decimal("0.00"))
        limite_total = max(
            self.TOLERANCIA_MAPEAMENTO_ABS,
            soma_filhos.copy_abs() * self.TOLERANCIA_MAPEAMENTO_REL,
        )
        if (soma_filhos - soma_origens).copy_abs() > limite_total:
            return None

        # Primeiro fixa as origens não-C170 que tenham correspondência
        # inequívoca. Em julho/2026 da Mega Mix, por exemplo, A170 e D101/D105
        # coincidem exatamente com dois M105/M505, deixando o terceiro para C170.
        disponiveis = set(filhos)
        atribuicoes: dict[str, int] = {}
        demais = [origem for origem in bases_origem if origem != "C170"]
        # Origens com base mais específica/maior primeiro reduzem colisões.
        demais.sort(key=lambda origem: bases_origem[origem], reverse=True)

        for origem in demais:
            base_origem = bases_origem[origem]
            limite = max(
                self.TOLERANCIA,
                base_origem.copy_abs() * Decimal("0.0001"),  # 0,01%
            )
            candidatos = [
                linha_num
                for linha_num in disponiveis
                if (bases_filhos[linha_num] - base_origem).copy_abs() <= limite
            ]
            if len(candidatos) == 1:
                escolhido = candidatos[0]
                atribuicoes[origem] = escolhido
                disponiveis.remove(escolhido)
            elif len(candidatos) > 1:
                return None

        # Se todas as origens não-C170 reconhecidas foram vinculadas e restou
        # exatamente um filho, ele é o filho documental do bloco C.
        if demais and len(atribuicoes) == len(demais) and len(disponiveis) == 1:
            return next(iter(disponiveis))

        # Fallback ainda conservador: resolve a atribuição global pelo menor
        # desvio quando o número de origens e filhos coincide e há um único
        # pareamento vencedor.
        if len(bases_origem) != len(filhos):
            return None

        from itertools import permutations

        nomes = tuple(sorted(bases_origem))
        melhores: list[tuple[Decimal, tuple[int, ...]]] = []
        for perm in permutations(filhos, len(nomes)):
            custo = Decimal("0.00")
            valido = True
            for origem, linha_num in zip(nomes, perm):
                base_origem = bases_origem[origem]
                diferenca = (bases_filhos[linha_num] - base_origem).copy_abs()
                limite = max(
                    self.TOLERANCIA_MAPEAMENTO_ABS,
                    base_origem.copy_abs() * self.TOLERANCIA_MAPEAMENTO_REL,
                )
                if diferenca > limite:
                    valido = False
                    break
                custo += diferenca
            if valido:
                melhores.append((custo, perm))

        if not melhores:
            return None
        melhores.sort(key=lambda item: item[0])
        if len(melhores) > 1 and melhores[0][0] == melhores[1][0]:
            return None
        melhor = melhores[0][1]
        mapa = dict(zip(nomes, melhor))
        return mapa.get("C170")

    def _escolher_child_por_natureza_cruzada(
        self,
        linhas_antes: list[str],
        linhas_atuais: list[str],
        pais: list[tuple[int, list[int]]],
        filhos_alvo: list[int],
        tributo: str,
        taxa_alvo: str,
        cst: str,
    ) -> int | None:
        """Identifica o filho do C170 usando uma NAT_BC_CRED comprovada em outra alíquota.

        A regra é conservadora: procura uma alíquota/CST em que exista base de
        C170, mas NÃO exista a mesma combinação em A170 nem D101/D105. Se o
        Bloco M possuir, nessa outra alíquota, exatamente um filho do mesmo CST,
        a NAT_BC_CRED desse filho fica comprovada como natureza de mercadorias.
        Então a rotina procura a mesma NAT, de forma única, entre os filhos da
        alíquota alvo.

        Isso resolve geradores que montaram o M105/M505 com bases agregadas que
        não coincidem perfeitamente com o total documental, sem adivinhar nem
        reclassificar NAT_BC_CRED.
        """
        if len(filhos_alvo) <= 1:
            return filhos_alvo[0] if filhos_alvo else None

        origens = self._agrupar_bases_origem_credito(linhas_antes, tributo)
        c170 = origens.get("C170", {})
        if not c170:
            return None

        outras_origens = [
            grupos for origem, grupos in origens.items() if origem != "C170"
        ]

        natures_comprovadas: set[str] = set()
        for (taxa_ref, cst_ref), base_ref in c170.items():
            if cst_ref != cst or taxa_ref == taxa_alvo or base_ref <= 0:
                continue
            # A combinação precisa ser exclusiva de C170 no documento.
            if any((taxa_ref, cst_ref) in grupos for grupos in outras_origens):
                continue

            pais_ref = [
                pai for pai in pais
                if self._taxa_igual(self._campo_linha(linhas_atuais[pai[0] - 1], 4), taxa_ref)
            ]
            if len(pais_ref) != 1:
                continue
            _, filhos_ref = pais_ref[0]
            filhos_ref_cst = [
                f for f in filhos_ref
                if self._campo_linha(linhas_atuais[f - 1], 2) == cst_ref
            ]
            if len(filhos_ref_cst) != 1:
                continue
            nat = self._campo_linha(linhas_atuais[filhos_ref_cst[0] - 1], 1).strip()
            if nat:
                natures_comprovadas.add(nat)

        if len(natures_comprovadas) != 1:
            return None
        nat_c170 = next(iter(natures_comprovadas))
        candidatos = [
            f for f in filhos_alvo
            if self._campo_linha(linhas_atuais[f - 1], 1).strip() == nat_c170
        ]
        return candidatos[0] if len(candidatos) == 1 else None

    def _agrupar_bases_origem_credito(
        self, linhas: list[str], tributo: str
    ) -> dict[str, dict[tuple[str, str], Decimal]]:
        """Agrupa bases de crédito por família documental e alíquota/CST.

        Só usa registros cujo leiaute é conhecido e paralelo no arquivo:
        A170 (serviços), C170 (mercadorias) e D101/D105 (transportes).
        """
        if tributo == "PIS":
            mapas = {
                "A170": (8, 9, 10),
                "C170": (24, 25, 26),
                "D101": (3, 5, 6),
            }
        else:
            mapas = {
                "A170": (12, 13, 14),
                "C170": (30, 31, 32),
                "D105": (3, 5, 6),
            }

        totais: dict[str, dict[tuple[str, str], Decimal]] = {}
        for linha in linhas:
            codigo = self._codigo(linha)
            mapa = mapas.get(codigo)
            if mapa is None:
                continue
            idx_cst, idx_base, idx_aliq = mapa
            cst = self._campo_linha(linha, idx_cst)
            if cst not in self.CST_CREDITO:
                continue
            base = self._decimal(self._campo_linha(linha, idx_base))
            aliq = self._decimal(self._campo_linha(linha, idx_aliq))
            if base is None or aliq is None or base <= 0:
                continue
            chave = (self._fmt_taxa(aliq), cst)
            grupo = totais.setdefault(codigo, {})
            grupo[chave] = grupo.get(chave, Decimal("0.00")) + base

        return {
            origem: {
                chave: valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                for chave, valor in grupos.items()
            }
            for origem, grupos in totais.items()
        }

    def _agrupar_bases_c170_fonte_segura(
        self, linhas: list[str], tributo: str
    ) -> dict[tuple[str, str], Decimal]:
        """Agrupa somente C170 de compra para revenda usados como fonte do ICMS.

        A rotina de exclusão aceita ICMS automaticamente apenas para os CFOPs
        definidos em ``CFOPS_FONTE_SEGURA`` (hoje 1102/2102). O Bloco M pode
        conter outros C170 do mesmo CST/alíquota, como devoluções, e somá-los
        tornava o vínculo com M105/M505 artificialmente ambíguo.
        """
        if tributo == "PIS":
            idx_cst, idx_base, idx_aliq = 24, 25, 26
        else:
            idx_cst, idx_base, idx_aliq = 30, 31, 32
        totais: dict[tuple[str, str], Decimal] = {}
        for linha in linhas:
            if self._codigo(linha) != "C170":
                continue
            cfop = self._campo_linha(linha, self.C170["cfop"]).strip()
            if cfop not in self.CFOPS_FONTE_SEGURA:
                continue
            cst = self._campo_linha(linha, idx_cst)
            if cst not in self.CST_CREDITO:
                continue
            base = self._decimal(self._campo_linha(linha, idx_base))
            aliq = self._decimal(self._campo_linha(linha, idx_aliq))
            if base is None or aliq is None or base <= 0:
                continue
            chave = (self._fmt_taxa(aliq), cst)
            totais[chave] = totais.get(chave, Decimal("0.00")) + base
        return {
            k: v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            for k, v in totais.items()
        }

    def _agrupar_bases_c170(self, linhas: list[str], tributo: str) -> dict[tuple[str, str], Decimal]:
        if tributo == "PIS":
            idx_cst, idx_base, idx_aliq = 24, 25, 26
        else:
            idx_cst, idx_base, idx_aliq = 30, 31, 32
        totais: dict[tuple[str, str], Decimal] = {}
        for linha in linhas:
            if self._codigo(linha) != "C170":
                continue
            cst = self._campo_linha(linha, idx_cst)
            if cst not in self.CST_CREDITO:
                continue
            base = self._decimal(self._campo_linha(linha, idx_base))
            aliq = self._decimal(self._campo_linha(linha, idx_aliq))
            if base is None or aliq is None:
                continue
            chave = (self._fmt_taxa(aliq), cst)
            totais[chave] = totais.get(chave, Decimal("0.00")) + base
        return {k: v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for k, v in totais.items()}

    def _mapear_pais_bloco_m(
        self, linhas: list[str], reg_pai: str, reg_child: str
    ) -> list[tuple[int, list[int]]]:
        saida: list[tuple[int, list[int]]] = []
        atual: tuple[int, list[int]] | None = None
        for numero, linha in enumerate(linhas, start=1):
            codigo = self._codigo(linha)
            if codigo == reg_pai:
                atual = (numero, [])
                saida.append(atual)
            elif codigo == reg_child and atual is not None:
                atual[1].append(numero)
            elif codigo.startswith("M") and codigo not in {reg_pai, reg_child}:
                atual = None
        return saida

    def _mapear_documentos(self, linhas: list[str]) -> list[_Documento]:
        docs: list[_Documento] = []
        atual: _Documento | None = None
        for numero, linha in enumerate(linhas, start=1):
            codigo = self._codigo(linha)
            if codigo == "C100":
                atual = _Documento(numero, self._partes(linha), [])
                docs.append(atual)
            elif codigo == "C170" and atual is not None:
                atual.itens.append((numero, self._partes(linha)))
            elif codigo and not codigo.startswith("C"):
                atual = None
        return docs


    def _recalcular_totalizadores(self, linhas: list[str]) -> tuple[list[str], int]:
        """Reconta 9900/fechamentos/9999 quando a consolidação remove linhas.

        A rotina é local e determinística: não muda valores fiscais, apenas os
        contadores estruturais que precisam acompanhar a quantidade final de
        registros depois de uma consolidação segura do Bloco M.
        """
        novas = list(linhas)
        alteracoes = 0
        quebra = "\r\n" if any(l.endswith("\r\n") for l in novas[:50]) else "\n"

        indices_9900 = [i for i, linha in enumerate(novas) if self._codigo(linha) == "9900"]
        indice_9990 = next((i for i, linha in enumerate(novas) if self._codigo(linha) == "9990"), None)
        if indice_9990 is not None:
            remover = set(indices_9900)
            sem_9900 = [linha for i, linha in enumerate(novas) if i not in remover]
            indice_9990 = next(i for i, linha in enumerate(sem_9900) if self._codigo(linha) == "9990")
            contagens = Counter(self._codigo(linha) for linha in sem_9900 if self._codigo(linha))
            codigos = sorted(set(contagens) | {"9900"})
            qtd_9900 = len(codigos)
            regs = [
                f"|9900|{codigo}|{qtd_9900 if codigo == '9900' else contagens[codigo]}|{quebra}"
                for codigo in codigos
            ]
            novas = sem_9900[:indice_9990] + regs + sem_9900[indice_9990:]
            alteracoes += 1

        posicoes: dict[str, list[int]] = defaultdict(list)
        for i, linha in enumerate(novas):
            codigo = self._codigo(linha)
            if codigo:
                posicoes[codigo].append(i)
        for fechamento, abertura in self.pre_validador.BLOCOS.items():
            if len(posicoes.get(fechamento, [])) != 1 or not posicoes.get(abertura):
                continue
            i_f = posicoes[fechamento][0]
            i_a = posicoes[abertura][0]
            esperado = (posicoes["9999"][0] - i_a + 1) if fechamento == "9990" and posicoes.get("9999") else (i_f - i_a + 1)
            anterior = self._campo_linha(novas[i_f], 1)
            if anterior != str(esperado):
                novas[i_f] = self._substituir_campo(novas[i_f], 1, str(esperado))
                alteracoes += 1

        i_9999 = next((i for i, linha in enumerate(novas) if self._codigo(linha) == "9999"), None)
        if i_9999 is not None:
            anterior = self._campo_linha(novas[i_9999], 1)
            if anterior != str(len(novas)):
                novas[i_9999] = self._substituir_campo(novas[i_9999], 1, str(len(novas)))
                alteracoes += 1
        return novas, alteracoes

    @staticmethod
    def _assinatura_erro(apontamento) -> tuple[str, str, str, str]:
        return (
            str(getattr(apontamento, "registro", "") or ""),
            str(getattr(apontamento, "campo", "") or ""),
            str(getattr(apontamento, "categoria", "") or ""),
            str(getattr(apontamento, "mensagem", "") or ""),
        )

    @classmethod
    def _erros_novos(cls, antes: list, depois: list) -> list:
        """Retorna apenas erros que aumentaram de quantidade após a rotina.

        Ignora número de linha porque consolidações estruturais deslocam as
        posições do arquivo. Assim, pendências preexistentes não impedem a
        geração, mas qualquer nova categoria/campo/mensagem continua bloqueando.
        """
        cont_antes = Counter(cls._assinatura_erro(x) for x in antes)
        usados = Counter()
        novos = []
        for item in depois:
            sig = cls._assinatura_erro(item)
            usados[sig] += 1
            if usados[sig] > cont_antes[sig]:
                novos.append(item)
        return novos

    def _salvar_relatorio(
        self,
        caminho: Path,
        analise: ResultadoAnaliseExclusaoICMS,
        saida: Path,
        reducao_pis: Decimal,
        reducao_cofins: Decimal,
        alteracoes_m: int,
        erros: int,
        avisos: int,
    ) -> None:
        linhas = [
            "FISCALPRO — HOTFIX 17.3.16 — ICMS DO SPED FISCAL → BASE PIS/COFINS",
            "=" * 78,
            f"Fonte Fiscal: {analise.caminho_fiscal}",
            f"Saída Contribuições: {saida}",
            f"CNPJ: {analise.cnpj}",
            f"Competência: {analise.periodo}",
            "",
            "CRUZAMENTO SEGURO",
            f"- Notas alteradas: {analise.documentos_aptos}",
            f"- Itens alterados: {analise.itens_alterar}",
            f"- Itens já líquidos de ICMS (não duplicados): {len(analise.itens_ja_excluidos)}",
            f"- ICMS próprio excluído das bases: R$ {self._fmt(analise.total_icms_excluir)}",
            f"- Redução efetiva de PIS nos C170: R$ {self._fmt(reducao_pis)}",
            f"- Redução efetiva de COFINS nos C170: R$ {self._fmt(reducao_cofins)}",
            f"- Campos do Bloco M sincronizados: {alteracoes_m}",
            "",
            "REGRAS DE SEGURANÇA",
            "- SPED Fiscal e EFD Contribuições devem ter o mesmo CNPJ e competência.",
            "- Cruzamento obrigatório por CHV_NFE + NUM_ITEM + COD_ITEM.",
            "- Somente entradas de terceiros e CFOP 1102/2102 com ICMS próprio > 0.",
            "- Somente CST de crédito PIS/COFINS 50 a 66.",
            "- ICMS-ST não é usado como exclusão.",
            "- Se a base já estiver líquida do ICMS, o item é preservado (sem dupla exclusão).",
            "- NAT_BC_CRED existente no M105/M505 é preservada; o FiscalPro só reduz a base comprovada.",
            "- M100/M500 duplicados só são consolidados quando a própria regra 17.3.9 os classifica como seguros.",
            "- Pendências que já existiam no arquivo aberto não bloqueiam esta rotina; somente erros novos introduzidos pelo ICMS bloqueiam.",
            "- Apuração complexa com ajustes, diferimento, saldo de crédito ou vínculo ambíguo bloqueia a geração automática.",
            "",
            f"PRÉ-VALIDADOR LOCAL: {erros} erro(s) / {avisos} aviso(s).",
            "Valide a nova cópia no PGE/PVA oficial antes da transmissão.",
            "",
            "ITENS ALTERADOS",
        ]
        for item in analise.itens_aptos:
            linhas.append(
                f"NF {item.numero_documento} | item {item.numero_item} | {item.codigo_item} | "
                f"ICMS R$ {self._fmt(item.valor_icms)} | "
                f"BC PIS {self._fmt(item.base_pis_anterior)} -> {self._fmt(item.base_pis_nova)} | "
                f"BC COFINS {self._fmt(item.base_cofins_anterior)} -> {self._fmt(item.base_cofins_nova)}"
            )
        caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")

    @staticmethod
    def _codigo(linha: str) -> str:
        partes = ExclusorICMSCreditosPISCOFINS._partes(linha)
        return partes[0].strip().upper() if partes else ""

    @staticmethod
    def _partes(linha: str) -> list[str]:
        texto = linha.rstrip("\r\n")
        if texto.startswith("|"):
            texto = texto[1:]
        if texto.endswith("|"):
            texto = texto[:-1]
        return texto.split("|") if texto else []

    @classmethod
    def _campo_linha(cls, linha: str, indice: int) -> str:
        return cls._campo(cls._partes(linha), indice)

    @staticmethod
    def _campo(campos: list[str], indice: int) -> str:
        return campos[indice].strip() if 0 <= indice < len(campos) else ""

    @classmethod
    def _substituir_campo(cls, linha: str, indice: int, valor: str) -> str:
        quebra = "\r\n" if linha.endswith("\r\n") else ("\n" if linha.endswith("\n") else "")
        partes = cls._partes(linha)
        while len(partes) <= indice:
            partes.append("")
        partes[indice] = valor
        return "|" + "|".join(partes) + "|" + quebra

    @staticmethod
    def _decimal(texto: str) -> Decimal | None:
        valor = (texto or "").strip().replace(".", "").replace(",", ".")
        if not valor:
            return None
        try:
            return Decimal(valor)
        except InvalidOperation:
            return None

    @classmethod
    def _aprox(cls, a: Decimal, b: Decimal) -> bool:
        return (a - b).copy_abs() <= cls.TOLERANCIA

    @staticmethod
    def _fmt(valor: Decimal) -> str:
        return f"{valor.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}".replace(".", ",")

    @staticmethod
    def _fmt_taxa(valor: Decimal) -> str:
        return f"{valor.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP):.4f}"

    @classmethod
    def _taxa_igual(cls, texto: str, taxa_normalizada: str) -> bool:
        valor = cls._decimal(texto)
        if valor is None:
            return False
        return cls._fmt_taxa(valor) == taxa_normalizada

    @staticmethod
    def _digitos(texto: str) -> str:
        return "".join(c for c in str(texto or "") if c.isdigit())

    @staticmethod
    def _normalizar_periodo(texto: str) -> str:
        return "".join(c for c in str(texto or "") if c.isdigit())

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
