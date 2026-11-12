"""ICMS proprio destacado nas SAIDAS - EFD-Contribuicoes NAO CUMULATIVA.

Tema 69/STF: ICMS destacado no documento fiscal nao integra a base do
PIS/COFINS sobre receitas tributadas. Este modulo NAO altera os creditos
das entradas, que sao tratados em outra rotina.

Escopo inicial e conservador:
- 0110 COD_INC_TRIB=1 e COD_TIPO_CONT=1;
- C100/C170 individual por chave de NF-e, CNPJ de estabelecimento e item;
- CST 01, aliquotas basicas de 1,65% e 7,60%, CFOP de vendas comuns;
- Bloco M com um unico COD_CONT=01 em M210 e M610, conciliado;
- manter os creditos ja utilizados quando o debito restante e suficiente;
- C180/C190/C800, apuracoes mistas e diferencas: somente REVISAR.

Sem rateio de ICMS entre receitas monofasicas, isentas ou CST distintos.
O PGE oficial deve validar uma copia antes de qualquer transmissao.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from .exclusor_icms_saidas_presumido import (
    ZERO, CENT, _campos, _campo, _num, _q, _fmt, _igual, _linha,
    _cnpj, _cabecalho, _venda, ExclusorICMSSaidasLucroPresumido,
)
from .leitor import LeitorSPEDUnificado
from .pre_validador import PreValidadorPVA

ALIQ_PIS = Decimal("1.65")
ALIQ_COFINS = Decimal("7.60")
CST_TRIBUTADOS = {"01", "02", "03", "05"}
REGISTROS_CONSOLIDADOS = {
    "C180", "C190", "C400", "C405", "C481", "C485",
    "C800", "C810", "C820", "C830", "C850", "C860", "C870",
}


def _assinatura(linhas: list[str]) -> str:
    return sha256("".join(linhas).encode("utf-8")).hexdigest()


def _soma(c: list[str], idx: int) -> Decimal:
    return _num(c, idx) or ZERO


@dataclass(frozen=True, slots=True)
class AjusteSaidaReal:
    indice: int
    pai: int
    referencia: str
    cfop: str
    icms: Decimal
    base_pis: Decimal
    base_cofins: Decimal
    pis_anterior: Decimal
    cofins_anterior: Decimal
    pis_novo: Decimal
    cofins_novo: Decimal

    @property
    def reducao_pis(self) -> Decimal:
        return self.pis_anterior - self.pis_novo

    @property
    def reducao_cofins(self) -> Decimal:
        return self.cofins_anterior - self.cofins_novo


@dataclass(slots=True)
class AnaliseSaidasReal:
    fiscal: Path
    cnpj_fiscal: str
    competencia: str
    assinatura_contrib: str
    assinatura_fiscal: str
    ajustes: list[AjusteSaidaReal] = field(default_factory=list)
    revisar: list[str] = field(default_factory=list)
    ja_excluidos: list[str] = field(default_factory=list)
    ignorados: int = 0

    @property
    def pode_gerar(self) -> bool:
        return bool(self.ajustes) and not self.revisar

    @property
    def icms(self) -> Decimal:
        return sum((a.icms for a in self.ajustes), ZERO)

    @property
    def pis(self) -> Decimal:
        return sum((a.reducao_pis for a in self.ajustes), ZERO)

    @property
    def cofins(self) -> Decimal:
        return sum((a.reducao_cofins for a in self.ajustes), ZERO)

    def resumo(self) -> str:
        detalhes = [
            "Regime: NAO CUMULATIVO (Lucro Real / 0110=1)",
            f"Estabelecimento Fiscal: {self.cnpj_fiscal}",
            f"Competencia: {self.competencia}",
            f"Linhas com exclusao comprovada: {len(self.ajustes)}",
            f"Ja excluidas: {len(self.ja_excluidos)}",
            f"Pendencias REVISAR: {len(self.revisar)}",
            f"ICMS proprio a excluir: R$ {_fmt(self.icms)}",
            f"Reducao de PIS (1,65%): R$ {_fmt(self.pis)}",
            f"Reducao de COFINS (7,60%): R$ {_fmt(self.cofins)}",
        ]
        if self.revisar:
            detalhes.extend(["", "REVISAR:", *self.revisar[:12]])
        return "\n".join(detalhes)


@dataclass(frozen=True, slots=True)
class GeracaoSaidasReal:
    caminho_sped: Path
    caminho_relatorio: Path
    linhas_ajustadas: int
    total_icms: Decimal
    reducao_pis: Decimal
    reducao_cofins: Decimal


class ExclusorICMSSaidasLucroReal:
    """Cruzamento conservador: nao reclassifica CST, nao rateia ICMS."""

    def __init__(self) -> None:
        self.leitor = LeitorSPEDUnificado()
        self.pre_validador = PreValidadorPVA()

    def analisar(
        self,
        linhas_contribuicoes: list[str],
        tipo_sped: str,
        caminho_fiscal: str | Path,
    ) -> AnaliseSaidasReal:
        if tipo_sped != "EFD Contribuições":
            raise RuntimeError("Abra primeiro a EFD Contribuicoes.")
        ini, fim, cnpj_contrib = _cabecalho(linhas_contribuicoes, False)
        registros_0110 = [_campos(l) for l in linhas_contribuicoes
                          if l.startswith("|0110|")]
        if len(registros_0110) != 1:
            raise RuntimeError("Nao foi encontrado um unico registro 0110.")
        c0110 = registros_0110[0]
        if _campo(c0110, 1) != "1":
            raise RuntimeError(
                "O 0110 nao indica incidencia exclusivamente NAO cumulativa "
                "(COD_INC_TRIB=1). Regime cumulativo ou misto: REVISAR."
            )
        if _campo(c0110, 3) != "1":
            raise RuntimeError(
                "COD_TIPO_CONT diferente de 1: ha aliquotas diferenciadas; "
                "revisao fiscal necessaria."
            )

        caminho = Path(caminho_fiscal)
        linhas_fiscal, _ = self.leitor.ler(caminho)
        ini_f, fim_f, cnpj_fiscal = _cabecalho(linhas_fiscal, True)
        if (ini, fim) != (ini_f, fim_f):
            raise RuntimeError(
                "Competencia diferente entre o SPED Fiscal e a EFD Contribuicoes."
            )
        if (len(cnpj_fiscal) != 14 or len(cnpj_contrib) != 14
                or cnpj_fiscal[:8] != cnpj_contrib[:8]):
            raise RuntimeError(
                "O SPED Fiscal e a EFD Contribuicoes possuem CNPJs de raizes diferentes."
            )
        analise = AnaliseSaidasReal(
            caminho, cnpj_fiscal, f"{ini} a {fim}",
            _assinatura(linhas_contribuicoes), _assinatura(linhas_fiscal),
        )

        fiscal_docs = ExclusorICMSSaidasLucroPresumido._fiscal_documentos(
            linhas_fiscal
        )
        docs_contrib, consolidados, contrib_duplicadas = self._documentos_contrib(
            linhas_contribuicoes, cnpj_fiscal, cnpj_contrib,
        )
        if consolidados:
            analise.revisar.append(
                "Este estabelecimento possui registros consolidados/alternativos "
                f"({', '.join(sorted(consolidados))}). Sem correspondencia individual "
                "do ICMS, a geracao automatica fica bloqueada."
            )
        if contrib_duplicadas:
            analise.revisar.append(
                "Chave(s) duplicada(s) na EFD Contribuicoes: "
                + ", ".join(sorted(contrib_duplicadas)[:8])
            )
        for doc in docs_contrib:
            self._analisar_documento(doc, fiscal_docs, analise)

        # Uma NFC-e pode aparecer em outra escrituracao, nao necessariamente
        # em C100. Nunca tratar o Fiscal parcialmente como todo o faturamento.
        chaves_contrib = {d["chave"] for d in docs_contrib}
        sem_pareamento = []
        for chave, fd in fiscal_docs.items():
            if chave in chaves_contrib:
                continue
            if fd.get("duplicado"):
                analise.revisar.append(
                    f"SPED Fiscal: chave duplicada {chave[-12:]}."
                )
                continue
            icms = fd.get("icms_c100")
            # Campo total do C100 pode vir vazio. Usa apenas C190/C170 como
            # evidencia da existencia de ICMS tributavel sem correspondencia.
            if icms is None or icms == ZERO:
                candidatos = [
                    self._origem_fiscal(fd, cfop)
                    for cfop in { _campo(c, 2) for c in fd["analiticos"] }
                    | { _campo(c, 10) for c in fd["itens"] }
                    if _venda(cfop)
                ]
                icms = sum((par[1] for par in candidatos if par is not None), ZERO)
            if icms and icms > ZERO:
                sem_pareamento.append(chave[-12:])
        if sem_pareamento:
            analise.revisar.append(
                f"{len(sem_pareamento)} documento(s) com ICMS do Fiscal "
                "nao foram vinculados a C100 da EFD Contribuicoes. "
                "Podem estar em C180/C800 ou em outra modalidade; REVISAR. "
                "Exemplos: " + ", ".join(sem_pareamento[:6])
            )

        if analise.ajustes and not analise.revisar:
            try:
                self._simular(linhas_contribuicoes, analise)
            except RuntimeError as erro:
                analise.revisar.append("Bloco M / totais: " + str(erro))
        if not analise.ajustes and not analise.revisar:
            analise.revisar.append(
                "Nenhum item de saida CST 01 com ICMS proprio comprovado "
                "e ainda nao excluido foi encontrado neste estabelecimento."
            )
        return analise

    @staticmethod
    def _documentos_contrib(
        linhas: list[str], cnpj_fiscal: str, cnpj_matriz: str
    ) -> tuple[list[dict], set[str], set[str]]:
        estabelecimento = cnpj_matriz
        docs = []
        consolidados: set[str] = set()
        chaves: set[str] = set()
        duplicadas: set[str] = set()
        atual = None
        for i, linha in enumerate(linhas):
            c = _campos(linha)
            reg = _campo(c, 0)
            if reg == "C010":
                estabelecimento = _cnpj(_campo(c, 1))
                atual = None
            elif reg == "C100":
                atual = None
                if (estabelecimento == cnpj_fiscal and _campo(c, 1) == "1"
                        and _campo(c, 4) in {"55", "65"}
                        and _campo(c, 5) == "00"):
                    chave = _campo(c, 8)
                    if len(chave) != 44 or not chave.isdigit():
                        consolidados.add("C100 sem CHV_NFE valida")
                        continue
                    if chave in chaves:
                        duplicadas.add(chave[-12:])
                    chaves.add(chave)
                    atual = {"i": i, "c": c, "chave": chave, "filhos": []}
                    docs.append(atual)
            elif reg in {"C990"}:
                atual = None
            elif reg in REGISTROS_CONSOLIDADOS and estabelecimento == cnpj_fiscal:
                consolidados.add(reg)
            elif reg in {"C170", "C175"} and atual is not None:
                atual["filhos"].append((i, c))
        return docs, consolidados, duplicadas

    @staticmethod
    def _origem_fiscal(
        doc_fiscal: dict, cfop: str
    ) -> tuple[Decimal, Decimal] | None:
        return ExclusorICMSSaidasLucroPresumido._fiscal_cfop(doc_fiscal, cfop)

    def _analisar_documento(
        self, doc: dict, fiscal: dict[str, dict],
        resultado: AnaliseSaidasReal,
    ) -> None:
        chave = doc["chave"]
        fonte = fiscal.get(chave)
        cfops = defaultdict(list)
        for i, c in doc["filhos"]:
            reg = _campo(c, 0)
            cfop = _campo(c, 10) if reg == "C170" else _campo(c, 1)
            cfops[cfop].append((i, c))
        elegiveis: list[tuple[int, list[str]]] = []
        for i, c in doc["filhos"]:
            reg = _campo(c, 0)
            cst_pis = _campo(c, 24) if reg == "C170" else _campo(c, 4)
            cst_cofins = _campo(c, 30) if reg == "C170" else _campo(c, 10)
            referencia = f"NF {chave[-12:]} / {reg} linha {i+1}"
            if cst_pis == "01" and cst_cofins == "01":
                if reg != "C170":
                    resultado.revisar.append(
                        f"{referencia}: registro {reg} nao suportado "
                        "para ajuste nao cumulativo; REVISAR."
                    )
                elif (len(c) < 36 or _num(c, 26) != ALIQ_PIS
                      or _num(c, 32) != ALIQ_COFINS):
                    resultado.revisar.append(
                        f"{referencia}: aliquotas nao sao as basicas "
                        "de 1,65% e 7,60%."
                    )
                else:
                    elegiveis.append((i, c))
            elif (cst_pis in CST_TRIBUTADOS or cst_cofins in CST_TRIBUTADOS):
                resultado.revisar.append(
                    f"{referencia}: PIS/COFINS com CSTs/aliquotas "
                    "diferenciados ou desencontrados."
                )
            else:
                resultado.ignorados += 1
        if not elegiveis:
            return
        if fonte is None or fonte.get("duplicado"):
            resultado.revisar.append(
                f"NF {chave[-12:]} nao possui chave fiscal unica correspondente."
            )
            return
        if fonte["modelo"] != _campo(doc["c"], 4):
            resultado.revisar.append(
                f"NF {chave[-12:]}: modelo do documento diverge."
            )
            return
        if not doc["filhos"]:
            resultado.revisar.append(
                f"NF {chave[-12:]}: C100 sem itens analiticos C170."
            )
            return
        # Os totais de C100 devem originalmente refletir TODOS os itens
        # escriturados, inclusive os CST 04/06/07 sem debito.
        soma_p = sum((_soma(c, 29) if _campo(c, 0) == "C170"
                      else _soma(c, 9) for _, c in doc["filhos"]), ZERO)
        soma_c = sum((_soma(c, 35) if _campo(c, 0) == "C170"
                      else _soma(c, 15) for _, c in doc["filhos"]), ZERO)
        if not (_igual(_num(doc["c"], 25), _q(soma_p))
                and _igual(_num(doc["c"], 26), _q(soma_c))):
            resultado.revisar.append(
                f"NF {chave[-12:]}: totais PIS/COFINS do C100 nao "
                "fecham com os itens; REVISAR."
            )
            return
        for i, c in elegiveis:
            ref = f"NF {chave[-12:]} / C170 linha {i+1}"
            cfop = _campo(c, 10)
            if not _venda(cfop):
                resultado.revisar.append(
                    f"{ref}: CFOP {cfop} nao esta entre as vendas comuns."
                )
                continue
            item_fiscal = None
            if fonte["itens"]:
                candidatos = [
                    f for f in fonte["itens"]
                    if _campo(f, 1) == _campo(c, 1)
                    and _campo(f, 2) == _campo(c, 2)
                    and _campo(f, 10) == cfop
                ]
                if len(candidatos) != 1:
                    resultado.revisar.append(
                        f"{ref}: nao existe item fiscal unico por "
                        "NUM_ITEM/COD_ITEM/CFOP."
                    )
                    continue
                item_fiscal = candidatos[0]
                valor = _num(item_fiscal, 6)
                desconto = _num(item_fiscal, 7) or ZERO
                icms = _num(item_fiscal, 14)
                origem = (_q(valor - desconto), icms) if valor is not None else None
            else:
                # Permite agrupar somente se 1 linha daquele CFOP representa
                # o TOTAL de um unico C190 do mesmo CFOP.
                c190 = [f for f in fonte["analiticos"] if _campo(f, 2) == cfop]
                if len(cfops[cfop]) != 1 or len(c190) != 1:
                    resultado.revisar.append(
                        f"{ref}: SPED Fiscal apenas agregado, sem vinculo "
                        "seguro por item."
                    )
                    continue
                origem = self._origem_fiscal(fonte, cfop)
            if origem is None:
                resultado.revisar.append(f"{ref}: valor/ICMS Fiscal nao comprovados.")
                continue
            valor_fiscal, icms_fiscal = origem
            bruto = _num(c, 6)
            desc = _num(c, 7) or ZERO
            if bruto is None or not _igual(_q(bruto - desc), valor_fiscal):
                resultado.revisar.append(f"{ref}: valor da venda difere do Fiscal.")
                continue
            self._candidato(i, doc["i"], c, ref, cfop, icms_fiscal, resultado)

    @staticmethod
    def _candidato(
        i: int, pai: int, c: list[str], ref: str, cfop: str,
        icms: Decimal | None, resultado: AnaliseSaidasReal,
    ) -> None:
        if icms is None or icms < ZERO:
            resultado.revisar.append(f"{ref}: ICMS proprio Fiscal ausente/invalido.")
            return
        icms = _q(icms)
        if icms == ZERO:
            resultado.ignorados += 1
            return
        bruta = _num(c, 6)
        if bruta is None:
            resultado.revisar.append(f"{ref}: VL_ITEM ausente.")
            return
        bruta = _q(bruta - (_num(c, 7) or ZERO))
        if bruta < icms:
            resultado.revisar.append(f"{ref}: ICMS proprio maior que venda.")
            return
        bc_pis, bc_cofins = _num(c, 25), _num(c, 31)
        vl_pis, vl_cofins = _num(c, 29), _num(c, 35)
        if any(v is None for v in (bc_pis, bc_cofins, vl_pis, vl_cofins)):
            resultado.revisar.append(f"{ref}: base/valor PIS/COFINS ausente.")
            return
        liquida = _q(bruta - icms)
        if _igual(bc_pis, liquida) and _igual(bc_cofins, liquida):
            resultado.ja_excluidos.append(ref)
            return
        if not (_igual(bc_pis, bruta) and _igual(bc_cofins, bruta)):
            resultado.revisar.append(
                f"{ref}: base tributavel ja contem ajustes ou outra exclusao; "
                "ICMS nao sera abatido novamente."
            )
            return
        if (not _igual(vl_pis, _q(bc_pis * ALIQ_PIS / 100))
                or not _igual(vl_cofins, _q(bc_cofins * ALIQ_COFINS / 100))):
            resultado.revisar.append(
                f"{ref}: debitos escriturados nao fecham com as aliquotas basicas."
            )
            return
        novo_pis = _q(liquida * ALIQ_PIS / 100)
        novo_cofins = _q(liquida * ALIQ_COFINS / 100)
        resultado.ajustes.append(
            AjusteSaidaReal(
                i, pai, ref, cfop, icms, bc_pis, bc_cofins,
                vl_pis, vl_cofins, novo_pis, novo_cofins,
            )
        )

    @staticmethod
    def _subtrair(
        c: list[str], pos: int, delta: Decimal, contexto: str
    ) -> None:
        valor = _num(c, pos)
        if valor is None or valor + CENT < delta:
            raise RuntimeError(
                f"{contexto}: campo {pos} sem saldo para reducao {_fmt(delta)}."
            )
        c[pos] = _fmt(valor - delta)

    def _simular(
        self, originais: list[str], analise: AnaliseSaidasReal
    ) -> list[str]:
        novas = list(originais)
        por_doc: dict[int, list[AjusteSaidaReal]] = defaultdict(list)
        for a in analise.ajustes:
            c = _campos(novas[a.indice])
            if _campo(c, 0) != "C170":
                raise RuntimeError(f"{a.referencia}: registro alterado.")
            if (not _igual(_num(c, 25), a.base_pis)
                    or not _igual(_num(c, 31), a.base_cofins)
                    or not _igual(_num(c, 29), a.pis_anterior)
                    or not _igual(_num(c, 35), a.cofins_anterior)):
                raise RuntimeError(f"{a.referencia}: valores de origem mudaram.")
            self._subtrair(c, 25, a.icms, "C170 VL_BC_PIS")
            self._subtrair(c, 31, a.icms, "C170 VL_BC_COFINS")
            c[29] = _fmt(a.pis_novo)
            c[35] = _fmt(a.cofins_novo)
            novas[a.indice] = _linha(novas[a.indice], c)
            por_doc[a.pai].append(a)
        for i, ajustes in por_doc.items():
            c = _campos(novas[i])
            if _campo(c, 0) != "C100":
                raise RuntimeError(f"C100 linha {i+1} alterado.")
            self._subtrair(
                c, 25, sum((a.reducao_pis for a in ajustes), ZERO), "C100 PIS"
            )
            self._subtrair(
                c, 26, sum((a.reducao_cofins for a in ajustes), ZERO),
                "C100 COFINS",
            )
            novas[i] = _linha(novas[i], c)
        self._reapurar(novas, analise)
        return novas

    def _reapurar(
        self, novas: list[str], analise: AnaliseSaidasReal
    ) -> None:
        for detalhe, resumo, receita, aliquota, reduzir in (
            ("M210", "M200", "M205", ALIQ_PIS, analise.pis),
            ("M610", "M600", "M605", ALIQ_COFINS, analise.cofins),
        ):
            detalhes = [(i, _campos(l)) for i, l in enumerate(novas)
                        if l.startswith(f"|{detalhe}|")]
            resumos = [(i, _campos(l)) for i, l in enumerate(novas)
                       if l.startswith(f"|{resumo}|")]
            receitas = [(i, _campos(l)) for i, l in enumerate(novas)
                        if l.startswith(f"|{receita}|")]
            if len(detalhes) != 1 or len(resumos) != 1:
                raise RuntimeError(
                    f"{detalhe}/{resumo}: apuracao basica unica nao localizada."
                )
            idx_d, d = detalhes[0]
            idx_r, r = resumos[0]
            if (_campo(d, 1) != "01" or _num(d, 7) != aliquota):
                raise RuntimeError(
                    f"{detalhe}: COD_CONT nao e 01/aliquota basica."
                )
            if (len(d) < 16 or len(r) < 13
                    or any(_soma(d, p) != ZERO for p in (4, 5, 8, 9, 11, 12, 13, 14))
                    or not _igual(_num(d, 3), _num(d, 6))
                    or not _igual(_num(d, 10), _num(d, 15))):
                raise RuntimeError(
                    f"{detalhe}: bases ajustadas, diferimentos ou valores "
                    "nao conciliados; memoria fiscal necessaria."
                )
            if not _igual(_num(r, 1), _num(d, 15)):
                raise RuntimeError(
                    f"{resumo}: total nao cumulativo nao concilia com {detalhe}."
                )
            if any(_soma(r, p) != ZERO for p in (8, 9, 10, 11)):
                raise RuntimeError(
                    f"{resumo}: contem contribuicao cumulativa; REVISAR."
                )
            if not _igual(
                _num(r, 4), _q(_soma(r, 1) - _soma(r, 2) - _soma(r, 3))
            ):
                raise RuntimeError(
                    f"{resumo}: debito devido nao fecha com os creditos descontados."
                )
            if not _igual(
                _num(r, 7), _q(_soma(r, 4) - _soma(r, 5) - _soma(r, 6))
            ):
                raise RuntimeError(
                    f"{resumo}: debito a recolher nao fecha com retencoes."
                )
            if not _igual(_num(r, 12), _q(_soma(r, 7) + _soma(r, 11))):
                raise RuntimeError(
                    f"{resumo}: total a recolher nao fecha."
                )
            filhos = [(i, c) for i, c in receitas if _campo(c, 1) == "08"]
            if len(filhos) != 1 or len(receitas) != 1:
                raise RuntimeError(
                    f"{receita}: recolhimento nao cumulativo (NUM_CAMPO=08) "
                    "nao e unico."
                )
            idx_f, f = filhos[0]
            if not _igual(_num(f, 3), _num(r, 7)):
                raise RuntimeError(
                    f"{receita}: VL_DEBITO diverge do total {resumo}."
                )
            if reduzir < ZERO:
                raise RuntimeError(
                    "Reducao negativa das contribuicoes; REVISAR."
                )
            if (_num(d, 3) is None or _num(d, 6) is None
                    or _num(d, 10) is None or _num(d, 15) is None
                    or any(_num(r, p) is None for p in (1, 4, 7, 12))):
                raise RuntimeError(
                    f"{resumo}/{detalhe}: campos essenciais ausentes."
                )
            # Os creditos M100/M105/M500/M505 nao sao alterados.
            # Se os creditos/retencoes deixam o debito negativo apos excluir
            # o ICMS, nao ha distribuicao automatica de saldo de credito.
            for p in (3, 6):
                self._subtrair(d, p, analise.icms, detalhe)
            for p in (10, 15):
                self._subtrair(d, p, reduzir, detalhe)
            for p in (1, 4, 7, 12):
                self._subtrair(r, p, reduzir, resumo)
            self._subtrair(f, 3, reduzir, receita)
            novas[idx_d] = _linha(novas[idx_d], d)
            novas[idx_r] = _linha(novas[idx_r], r)
            novas[idx_f] = _linha(novas[idx_f], f)

    def gerar(
        self, linhas_contribuicoes: list[str], encoding: str,
        tipo_sped: str, analise: AnaliseSaidasReal, destino: str | Path,
    ) -> GeracaoSaidasReal:
        if tipo_sped != "EFD Contribuições" or not analise.pode_gerar:
            raise RuntimeError(
                "Analise nao autoriza gerar TXT; resolva os itens REVISAR."
            )
        if _assinatura(linhas_contribuicoes) != analise.assinatura_contrib:
            raise RuntimeError(
                "EFD Contribuicoes mudou depois da auditoria; execute novamente."
            )
        fiscal_agora, _ = self.leitor.ler(analise.fiscal)
        if _assinatura(fiscal_agora) != analise.assinatura_fiscal:
            raise RuntimeError(
                "SPED Fiscal mudou depois da auditoria; execute novamente."
            )
        caminho = Path(destino)
        memoria = caminho.with_name(caminho.stem + "_MEMORIA.txt")
        if caminho.resolve() == analise.fiscal.resolve():
            raise RuntimeError("O SPED Fiscal original nao pode ser sobrescrito.")
        if caminho.exists() or memoria.exists():
            raise FileExistsError(
                "Arquivo de saida/memoria ja existe: escolha nome novo."
            )
        novas = self._simular(linhas_contribuicoes, analise)
        antes = self.pre_validador.validar(linhas_contribuicoes, tipo_sped)
        depois = self.pre_validador.validar(novas, tipo_sped)
        chave = lambda e: (e.registro, e.campo, e.mensagem)
        novos = Counter(map(chave, depois.erros)) - Counter(map(chave, antes.erros))
        if novos:
            raise RuntimeError(
                "O pre-validador identificou novos erros: "
                + "; ".join(f"{k[0]}/{k[1]}" for k in list(novos)[:5])
            )
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with caminho.open("x", encoding=encoding, newline="") as arquivo:
            arquivo.writelines(novas)
        self.salvar_relatorio(analise, memoria)
        return GeracaoSaidasReal(
            caminho, memoria, len(analise.ajustes),
            analise.icms, analise.pis, analise.cofins,
        )

    @staticmethod
    def salvar_relatorio(
        analise: AnaliseSaidasReal, destino: str | Path
    ) -> Path:
        caminho = Path(destino)
        linhas = [
            "FISCALPRO - AUDITORIA DE ICMS PROPRIO SAIDAS - LUCRO REAL",
            "Tema 69 STF; SPED EFD-Contribuicoes NAO CUMULATIVO.",
            "Nao transmitir antes de validar no PGE e com a contabilidade.",
            f"Fiscal: {analise.fiscal}",
            "",
            analise.resumo(),
            "",
            "AJUSTES INDIVIDUAIS:",
        ]
        linhas.extend(
            f"{a.referencia} | CFOP {a.cfop} | ICMS {_fmt(a.icms)} | "
            f"PIS {_fmt(a.pis_anterior)} -> {_fmt(a.pis_novo)} | "
            f"COFINS {_fmt(a.cofins_anterior)} -> {_fmt(a.cofins_novo)}"
            for a in analise.ajustes
        )
        linhas.extend([
            "", "JA EXCLUIDOS:", *analise.ja_excluidos,
            "", "REVISAR:", *analise.revisar,
        ])
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        return caminho
