"""Exclusao auditavel do ICMS destacado nas SAIDAS - lucro presumido.

Nao reutiliza a rotina de exclusao de creditos das ENTRADAS (Lucro Real).
Criterios seguros: 0110 cumulativo; documento/CFOP/item vinculado ao Fiscal;
CST 01 e aliquotas basicas; F500/agrupamentos ambiguos ficam em REVISAO.
Base: Tema 69/STF e Guia Pratico EFD-Contribuicoes 1.35, secao 12.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from .leitor import LeitorSPEDUnificado
from .pre_validador import PreValidadorPVA

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
MARCADOR = "FISCALPRO_ICMS_T69"


def _campos(linha: str) -> list[str]:
    texto = linha.rstrip("\r\n")
    if not texto.startswith("|") or not texto.endswith("|"):
        return []
    return texto.split("|")[1:-1]


def _campo(c: list[str], pos: int) -> str:
    return c[pos].strip() if pos < len(c) else ""


def _dinheiro(texto: str) -> Decimal | None:
    if not texto.strip():
        return None
    try:
        valor = Decimal(texto.strip().replace(".", "").replace(",", "."))
        return valor if valor.is_finite() else None
    except InvalidOperation:
        return None


def _num(c: list[str], pos: int) -> Decimal | None:
    return _dinheiro(_campo(c, pos))


def _q(valor: Decimal) -> Decimal:
    return valor.quantize(CENT, rounding=ROUND_HALF_UP)


def _fmt(valor: Decimal) -> str:
    return f"{_q(valor):.2f}".replace(".", ",")


def _igual(a: Decimal | None, b: Decimal | None) -> bool:
    return a is not None and b is not None and abs(a - b) <= CENT


def _linha(original: str, campos: list[str]) -> str:
    sufixo = "\r\n" if original.endswith("\r\n") else "\n" if original.endswith("\n") else ""
    return "|" + "|".join(campos) + "|" + sufixo


def _cnpj(valor: str) -> str:
    return "".join(ch for ch in valor if ch.isdigit())


def _cabecalho(linhas: list[str], fiscal: bool) -> tuple[str, str, str]:
    registros = [_campos(l) for l in linhas if l.startswith("|0000|")]
    if len(registros) != 1:
        raise RuntimeError("Arquivo sem registro 0000 unico.")
    c = registros[0]
    inicio, fim, cnpj = (3, 4, 6) if fiscal else (5, 6, 8)
    return _campo(c, inicio), _campo(c, fim), _cnpj(_campo(c, cnpj))


def _taxavel(c: list[str], reg: str) -> bool:
    if reg == "C170":
        return (_campo(c, 24) == "01" and _campo(c, 30) == "01"
                and _num(c, 26) == Decimal("0.6500")
                and _num(c, 32) == Decimal("3.0000"))
    if reg == "C175":
        return (_campo(c, 4) == "01" and _campo(c, 10) == "01"
                and _num(c, 6) == Decimal("0.6500")
                and _num(c, 12) == Decimal("3.0000"))
    if reg == "F550":
        return (_campo(c, 2) == "01" and _campo(c, 7) == "01"
                and _num(c, 5) == Decimal("0.6500")
                and _num(c, 10) == Decimal("3.0000"))
    return False


def _venda(cfop: str) -> bool:
    # Escopo inicial explicitamente restrito a vendas comuns de mercadorias.
    return cfop in {"5101", "5102", "6101", "6102"}


@dataclass(frozen=True, slots=True)
class AjusteSaidaPresumido:
    indice_linha: int
    registro: str
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
class AnaliseSaidasPresumido:
    fiscal: Path
    cnpj_fiscal: str
    competencia: str
    criterio: str
    ajustes: list[AjusteSaidaPresumido] = field(default_factory=list)
    revisar: list[str] = field(default_factory=list)
    ja_excluidos: list[str] = field(default_factory=list)
    ignorados: int = 0
    _originais: list[str] = field(default_factory=list, repr=False)

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
        return (
            f"Escrituracao: {self.criterio}\n"
            f"Estabelecimento Fiscal: {self.cnpj_fiscal}\n"
            f"Competencia: {self.competencia}\n"
            f"Linhas com exclusao comprovada: {len(self.ajustes)}\n"
            f"Ja excluidas: {len(self.ja_excluidos)}\n"
            f"Pendencias REVISAR: {len(self.revisar)}\n"
            f"ICMS proprio a excluir: R$ {_fmt(self.icms)}\n"
            f"Reducao de PIS: R$ {_fmt(self.pis)}\n"
            f"Reducao de COFINS: R$ {_fmt(self.cofins)}\n"
            + ("\n".join(self.revisar[:8]) if self.revisar else "")
        )


@dataclass(frozen=True, slots=True)
class GeracaoSaidasPresumido:
    caminho_sped: Path
    caminho_relatorio: Path
    linhas_ajustadas: int
    total_icms: Decimal
    reducao_pis: Decimal
    reducao_cofins: Decimal


class ExclusorICMSSaidasLucroPresumido:
    """Cruzamento conservador do ICMS de SAIDAS com incidencia cumulativa."""

    def __init__(self) -> None:
        self.leitor = LeitorSPEDUnificado()
        self.pre_validador = PreValidadorPVA()

    @staticmethod
    def _fiscal_documentos(linhas: list[str]) -> dict[str, dict]:
        docs: dict[str, dict] = {}
        atual = None
        for linha in linhas:
            c = _campos(linha)
            reg = _campo(c, 0)
            if reg == "C100":
                atual = None
                if (_campo(c, 1) == "1" and _campo(c, 5) == "00"
                        and _campo(c, 4) in {"55", "65"}
                        and len(_campo(c, 8)) == 44):
                    chave = _campo(c, 8)
                    if chave in docs:
                        docs[chave]["duplicado"] = True
                        continue
                    atual = {"chave": chave, "modelo": _campo(c, 4),
                             "numero": _campo(c, 7), "itens": [], "analiticos": [],
                             "icms_c100": _num(c, 21)}
                    docs[chave] = atual
            elif reg in {"C990", "C010"}:
                atual = None
            elif atual is not None and reg == "C170":
                atual["itens"].append(c)
            elif atual is not None and reg == "C190":
                atual["analiticos"].append(c)
        return docs

    @staticmethod
    def _fiscal_cfop(doc: dict, cfop: str) -> tuple[Decimal, Decimal] | None:
        # Nunca somar C170 e C190 do mesmo documento: seria ICMS duplicado.
        grupo = [c for c in doc["analiticos"] if _campo(c, 2) == cfop]
        if grupo:
            valores = [(_num(c, 4), _num(c, 6)) for c in grupo]
        else:
            grupo = [c for c in doc["itens"] if _campo(c, 10) == cfop]
            valores = [((_num(c, 6) or ZERO) - (_num(c, 7) or ZERO),
                        _num(c, 14)) for c in grupo]
        if not valores or any(a is None or b is None for a, b in valores):
            return None
        return _q(sum((v[0] for v in valores), ZERO)), _q(sum((v[1] for v in valores), ZERO))

    @staticmethod
    def _grupo_f550(docs: dict[str, dict], modelo: str, cfop: str) -> tuple[Decimal, Decimal] | None:
        operacao, imposto = ZERO, ZERO
        achou = False
        for doc in docs.values():
            if doc["modelo"] != modelo:
                continue
            grupo = ExclusorICMSSaidasLucroPresumido._fiscal_cfop(doc, cfop)
            if grupo:
                achou = True
                operacao += grupo[0]
                imposto += grupo[1]
        return (_q(operacao), _q(imposto)) if achou else None

    def analisar(self, linhas_contribuicoes: list[str], tipo_sped: str,
                caminho_fiscal: str | Path) -> AnaliseSaidasPresumido:
        if tipo_sped != "EFD Contribuições":
            raise RuntimeError("Abra primeiro uma EFD Contribuicoes.")
        ini, fim, cnpj_contrib = _cabecalho(linhas_contribuicoes, False)
        cab_0110 = [_campos(l) for l in linhas_contribuicoes if l.startswith("|0110|")]
        if len(cab_0110) != 1 or _campo(cab_0110[0], 1) != "2":
            raise RuntimeError("O 0110 nao comprova incidencia exclusivamente cumulativa (codigo 2).")
        criterio = _campo(cab_0110[0], 4)
        if criterio not in {"1", "2", "9"}:
            raise RuntimeError("IND_REG_CUM do 0110 ausente ou nao reconhecido.")

        caminho = Path(caminho_fiscal)
        fiscal, _ = self.leitor.ler(caminho)
        ini_f, fim_f, cnpj_fiscal = _cabecalho(fiscal, True)
        if (ini, fim) != (ini_f, fim_f):
            raise RuntimeError("Competencia do SPED Fiscal diferente da EFD Contribuicoes.")
        if (len(cnpj_contrib) != 14 or len(cnpj_fiscal) != 14
                or cnpj_contrib[:8] != cnpj_fiscal[:8]):
            raise RuntimeError("CNPJs nao pertencem a mesma raiz da pessoa juridica.")

        modo = {"1": "F500 - caixa (somente auditoria)",
                "2": "F550 - competencia consolidada",
                "9": "Detalhada C170/C175"}[criterio]
        resultado = AnaliseSaidasPresumido(caminho, cnpj_fiscal, f"{ini} a {fim}", modo)
        docs = self._fiscal_documentos(fiscal)

        if criterio == "1":
            resultado.revisar.append(
                "F500 (caixa): recebimentos nao coincidem necessariamente com as vendas da competencia. "
                "Cruzamento documental e ajuste automatico bloqueados."
            )
            return resultado

        if criterio == "2":
            self._analisar_f550(linhas_contribuicoes, docs, cnpj_fiscal, cnpj_contrib, resultado)
        else:
            self._analisar_detalhado(linhas_contribuicoes, docs, cnpj_fiscal, cnpj_contrib, resultado)
        if not resultado.ajustes and not resultado.ja_excluidos and not resultado.revisar:
            resultado.revisar.append(
                "Nenhuma venda tributada com ICMS proprio comprovado foi encontrada para este estabelecimento."
            )
        return resultado

    def _analisar_detalhado(self, linhas: list[str], docs: dict[str, dict],
                           cnpj_fiscal: str, cnpj_matriz: str,
                           res: AnaliseSaidasPresumido) -> None:
        estabelecimento = cnpj_matriz
        documento: dict | None = None
        documentos = []
        for i, linha in enumerate(linhas):
            c = _campos(linha)
            reg = _campo(c, 0)
            if reg == "C010":
                estabelecimento = _cnpj(_campo(c, 1))
                documento = None
            elif reg == "C100":
                documento = None
                if (estabelecimento == cnpj_fiscal and _campo(c, 1) == "1"
                        and _campo(c, 5) == "00" and _campo(c, 4) in {"55", "65"}):
                    documento = {"i": i, "campos": c, "chave": _campo(c, 8), "filhos": []}
                    documentos.append(documento)
            elif reg == "C990":
                documento = None
            elif reg in {"C170", "C175"} and documento is not None:
                documento["filhos"].append((i, c))

        for doc in documentos:
            chave = doc["chave"]
            fonte = docs.get(chave)
            tributados = [(i, c) for i, c in doc["filhos"]
                          if _taxavel(c, _campo(c, 0))]
            if not tributados:
                res.ignorados += len(doc["filhos"])
                continue
            if fonte is None or fonte.get("duplicado"):
                res.revisar.append(f"NF {chave[-12:]}: chave inexistente/duplicada no SPED Fiscal.")
                continue
            if fonte["modelo"] != _campo(doc["campos"], 4):
                res.revisar.append(f"NF {chave[-12:]}: modelo diferente nos arquivos.")
                continue
            # O PVA pode escriturar multiplos grupos de PIS no mesmo CFOP.
            por_cfop: dict[str, list[tuple[int, list[str]]]] = defaultdict(list)
            for item in doc["filhos"]:
                c = item[1]
                cfop = _campo(c, 10) if _campo(c, 0) == "C170" else _campo(c, 1)
                por_cfop[cfop].append(item)
            for i, c in tributados:
                reg = _campo(c, 0)
                cfop = _campo(c, 10) if reg == "C170" else _campo(c, 1)
                ref = f"NF {chave[-12:]} / {reg} linha {i + 1}"
                if not _venda(cfop):
                    res.revisar.append(f"{ref}: CFOP {cfop} fora do escopo seguro.")
                    continue
                origem = None
                if reg == "C170" and fonte["itens"]:
                    itens = [f for f in fonte["itens"]
                             if _campo(f, 1) == _campo(c, 1)
                             and _campo(f, 2) == _campo(c, 2)
                             and _campo(f, 10) == cfop]
                    if len(itens) == 1:
                        origem = ((_num(itens[0], 6) or ZERO) - (_num(itens[0], 7) or ZERO),
                                  _num(itens[0], 14))
                if origem is None:
                    if len(por_cfop[cfop]) != 1:
                        res.revisar.append(f"{ref}: CFOP {cfop} misto ou sem item fiscal unico.")
                        continue
                    origem = self._fiscal_cfop(fonte, cfop)
                if origem is None:
                    res.revisar.append(f"{ref}: ICMS/VL_OPR do Fiscal nao comprovados.")
                    continue
                operacao, imposto = origem
                bruto = (_num(c, 6) or ZERO) - (_num(c, 7) or ZERO) if reg == "C170" else _num(c, 2)
                if bruto is None or not _igual(_q(bruto), _q(operacao)):
                    res.revisar.append(f"{ref}: valor da venda diverge do SPED Fiscal.")
                    continue
                self._candidato(i, c, reg, ref, cfop, imposto, res)

    def _analisar_f550(self, linhas: list[str], docs: dict[str, dict],
                       cnpj_fiscal: str, cnpj_matriz: str,
                       res: AnaliseSaidasPresumido) -> None:
        estabelecimento = cnpj_matriz
        grupos: dict[tuple[str, str], list[tuple[int, list[str]]]] = defaultdict(list)
        for i, linha in enumerate(linhas):
            c = _campos(linha)
            reg = _campo(c, 0)
            if reg == "F010":
                estabelecimento = _cnpj(_campo(c, 1))
            elif reg == "F550" and estabelecimento == cnpj_fiscal:
                grupos[(_campo(c, 12), _campo(c, 13))].append((i, c))
        if not grupos:
            res.revisar.append("Nenhum F550 do estabelecimento informado foi localizado (F010).")
        for (modelo, cfop), registros in grupos.items():
            elegiveis = [(i, c) for i, c in registros if _taxavel(c, "F550")]
            if not elegiveis:
                res.ignorados += len(registros)
                continue
            ref = f"F550 modelo {modelo} CFOP {cfop}"
            if not _venda(cfop) or modelo not in {"55", "65"}:
                res.revisar.append(f"{ref}: modelo/CFOP fora do escopo seguro.")
                continue
            if len(registros) != 1:
                res.revisar.append(
                    f"{ref}: ha CSTs/grupos distintos no mesmo modelo/CFOP; "
                    "ICMS nao pode ser rateado sem XML ou demonstrativo por item."
                )
                continue
            fonte = self._grupo_f550(docs, modelo, cfop)
            if fonte is None:
                res.revisar.append(f"{ref}: grupo inexistente no SPED Fiscal.")
                continue
            operacao, imposto = fonte
            i, c = elegiveis[0]
            if not _igual(_num(c, 1), operacao):
                res.revisar.append(f"{ref}: receita consolidada diferente do Fiscal.")
                continue
            self._candidato(i, c, "F550", ref, cfop, imposto, res)

    @staticmethod
    def _candidato(i: int, c: list[str], reg: str, ref: str, cfop: str,
                   imposto: Decimal | None, res: AnaliseSaidasPresumido) -> None:
        if imposto is None or imposto < ZERO:
            res.revisar.append(f"{ref}: ICMS fiscal ausente/invalido.")
            return
        imposto = _q(imposto)
        if imposto == ZERO:
            res.ignorados += 1
            return
        if MARCADOR in "|".join(c):
            res.ja_excluidos.append(ref)
            return

        if reg == "C170":
            bruta = (_num(c, 6) or ZERO) - (_num(c, 7) or ZERO)
            p_base, c_base, p_val, c_val = 25, 31, 29, 35
            descontar = False
        elif reg == "C175":
            bruta = _num(c, 2)
            p_base, c_base, p_val, c_val = 5, 11, 9, 15
            descontar = True
            d = _num(c, 3)
            if d is None or d != ZERO:
                res.revisar.append(f"{ref}: VL_DESC existente; risco de exclusao duplicada.")
                return
        else:
            bruta = _num(c, 1)
            p_base, c_base, p_val, c_val = 4, 9, 6, 11
            descontar = True
            if _num(c, 3) != ZERO or _num(c, 8) != ZERO:
                res.revisar.append(f"{ref}: descontos/exclusoes existentes; requer memoria de calculo.")
                return

        bp, bc = _num(c, p_base), _num(c, c_base)
        vp, vc = _num(c, p_val), _num(c, c_val)
        if bruta is None or any(v is None for v in (bp, bc, vp, vc)):
            res.revisar.append(f"{ref}: base/valor ausente.")
            return
        if bruta < imposto:
            res.revisar.append(f"{ref}: ICMS maior que a operacao.")
            return
        base_liquida = _q(bruta - imposto)
        if not descontar and _igual(bp, base_liquida) and _igual(bc, base_liquida):
            res.ja_excluidos.append(ref)
            return
        if not (_igual(bp, bruta) and _igual(bc, bruta)):
            res.revisar.append(f"{ref}: base atual diferente da bruta e da liquida esperadas.")
            return
        if not (_igual(vp, _q(bp * Decimal("0.0065")))
                and _igual(vc, _q(bc * Decimal("0.03")))):
            res.revisar.append(f"{ref}: PIS/COFINS atuais nao fecham com alíquotas basicas.")
            return

        novo_pis = _q(base_liquida * Decimal("0.0065"))
        novo_cofins = _q(base_liquida * Decimal("0.03"))
        res.ajustes.append(AjusteSaidaPresumido(
            i, reg, ref, cfop, imposto, bp, bc, vp, vc, novo_pis, novo_cofins
        ))

    @staticmethod
    def _somar_reducao(c: list[str], pos: int, delta: Decimal,
                       registro: str, nome: str) -> None:
        atual = _num(c, pos)
        if atual is None or atual + CENT < delta:
            raise RuntimeError(f"{registro}: {nome} invalido para reduzir {_fmt(delta)}.")
        c[pos] = _fmt(atual - delta)

    @classmethod
    def _reapurar_cumulativo(cls, linhas: list[str], analise: AnaliseSaidasPresumido) -> None:
        # Exclusivamente CST 01 + aliquota basica + COD_CONT 51.
        for detalhe, total, recolher, delta_base, delta_valor in (
            ("M210", "M200", "M205", analise.icms, analise.pis),
            ("M610", "M600", "M605", analise.icms, analise.cofins),
        ):
            ids = {reg: [(i, _campos(l)) for i, l in enumerate(linhas)
                         if l.startswith(f"|{reg}|")]
                   for reg in (detalhe, total, recolher)}
            det = [(i, c) for i, c in ids[detalhe]
                   if _campo(c, 1) == "51"
                   and _num(c, 7) == (Decimal("0.65") if detalhe == "M210" else Decimal("3.00"))]
            if len(det) != 1 or len(ids[total]) != 1:
                raise RuntimeError(f"{detalhe}/{total}: apuracao cumulativa basica nao e unica. Gere o Bloco M no PGE.")
            filhos = [(i, c) for i, c in ids[recolher] if _campo(c, 1) == "12"]
            if len(filhos) != 1:
                raise RuntimeError(f"{recolher}: exige um unico detalhamento de debito cumulativo (NUM_CAMPO 12).")
            idd, cd = det[0]
            idt, ct = ids[total][0]
            idr, cr = filhos[0]
            if _num(ct, 1) not in (ZERO, None) or _num(ct, 7) not in (ZERO, None):
                raise RuntimeError(f"{total}: existe contribuicao nao cumulativa; ajuste automatico bloqueado.")
            # Receita bruta (M210/M610 VL_REC_BRT) fica INALTERADA.
            for pos, nome, delta in ((3, "VL_BC_CONT", delta_base),
                                     (6, "VL_BC_CONT_AJUS", delta_base),
                                     (10, "VL_CONT_APUR", delta_valor),
                                     (15, "VL_CONT_PER", delta_valor)):
                cls._somar_reducao(cd, pos, delta, detalhe, nome)
            for pos, nome in ((8, "VL_TOT_CONT_CUM_PER"), (11, "VL_CONT_CUM_REC"),
                              (12, "VL_TOT_CONT_REC")):
                cls._somar_reducao(ct, pos, delta_valor, total, nome)
            cls._somar_reducao(cr, 3, delta_valor, recolher, "VL_DEBITO")
            linhas[idd] = _linha(linhas[idd], cd)
            linhas[idt] = _linha(linhas[idt], ct)
            linhas[idr] = _linha(linhas[idr], cr)

    @classmethod
    def _aplicar_documentos(cls, linhas: list[str], analise: AnaliseSaidasPresumido) -> None:
        for a in analise.ajustes:
            origem = linhas[a.indice_linha]
            c = _campos(origem)
            if _campo(c, 0) != a.registro:
                raise RuntimeError(f"Registro mudou na linha {a.indice_linha + 1}.")
            if a.registro == "C170":
                bp, bc, vp, vc = 25, 31, 29, 35
            elif a.registro == "C175":
                bp, bc, vp, vc = 5, 11, 9, 15
                c[3] = _fmt((_num(c, 3) or ZERO) + a.icms)
                if len(c) < 18:
                    raise RuntimeError("C175 incompleto; REVISAR.")
                c[17] = (_campo(c, 17) + " " + MARCADOR + "=" + _fmt(a.icms)).strip()
            else:
                bp, bc, vp, vc = 4, 9, 6, 11
                c[3] = _fmt((_num(c, 3) or ZERO) + a.icms)
                c[8] = _fmt((_num(c, 8) or ZERO) + a.icms)
                if len(c) < 16:
                    raise RuntimeError("F550 incompleto; REVISAR.")
                c[15] = (_campo(c, 15) + " " + MARCADOR + "=" + _fmt(a.icms)).strip()
            c[bp], c[bc] = _fmt(a.base_pis - a.icms), _fmt(a.base_cofins - a.icms)
            c[vp], c[vc] = _fmt(a.pis_novo), _fmt(a.cofins_novo)
            linhas[a.indice_linha] = _linha(origem, c)

        # C100 reflete a soma de filhos, apenas para documentos alterados.
        alteradas = {a.indice_linha for a in analise.ajustes if a.registro in {"C170", "C175"}}
        pai = None
        filhos: list[int] = []

        def finalizar() -> None:
            if pai is None or not (alteradas & set(filhos)):
                return
            c = _campos(linhas[pai])
            total_p = total_c = ZERO
            for j in filhos:
                f = _campos(linhas[j])
                pp, cc = (29, 35) if _campo(f, 0) == "C170" else (9, 15)
                total_p += _num(f, pp) or ZERO
                total_c += _num(f, cc) or ZERO
            # Confere totalizacao anterior: um documento pode ter valores de
            # outros grupos que nao sao representados pelos filhos informados.
            anterior = _campos(analise._originais[pai])
            soma_original_p = soma_original_c = ZERO
            for j in filhos:
                f = _campos(analise._originais[j])
                pp, cc = (29, 35) if _campo(f, 0) == "C170" else (9, 15)
                soma_original_p += _num(f, pp) or ZERO
                soma_original_c += _num(f, cc) or ZERO
            if not (_igual(_num(anterior, 25), soma_original_p)
                    and _igual(_num(anterior, 26), soma_original_c)):
                raise RuntimeError("C100: total original nao confere com filhos; REVISAR.")
            c[25], c[26] = _fmt(total_p), _fmt(total_c)
            linhas[pai] = _linha(linhas[pai], c)

        for i, linha in enumerate(linhas):
            reg = _campo(_campos(linha), 0)
            if reg == "C100":
                finalizar()
                pai, filhos = i, []
            elif reg in {"C010", "C990"}:
                finalizar()
                pai, filhos = None, []
            elif reg in {"C170", "C175"} and pai is not None:
                filhos.append(i)
        finalizar()

    def gerar(self, linhas_contribuicoes: list[str], encoding: str, tipo_sped: str,
              analise: AnaliseSaidasPresumido, destino: str | Path) -> GeracaoSaidasPresumido:
        if tipo_sped != "EFD Contribuições" or not analise.pode_gerar:
            raise RuntimeError("Analise com pendencias; nao sera gravado SPED parcial.")
        caminho = Path(destino)
        if caminho.resolve() == analise.fiscal.resolve():
            raise RuntimeError("O SPED Fiscal de origem nunca pode ser sobrescrito.")
        originais = list(linhas_contribuicoes)
        # Guarda a origem somente durante o procedimento de retotalizacao.
        analise._originais = originais
        novas = list(originais)
        self._aplicar_documentos(novas, analise)
        self._reapurar_cumulativo(novas, analise)
        antes = self.pre_validador.validar(originais, tipo_sped)
        depois = self.pre_validador.validar(novas, tipo_sped)
        chave = lambda e: (e.registro, e.campo, e.mensagem)
        novos_erros = Counter(map(chave, depois.erros)) - Counter(map(chave, antes.erros))
        if novos_erros:
            raise RuntimeError(
                "Pre-PGE detectou novas pendencias. Nenhum arquivo gerado: "
                + "; ".join(f"{x[0]}/{x[1]}" for x in list(novos_erros)[:5])
            )

        caminho.parent.mkdir(parents=True, exist_ok=True)
        if caminho.exists() or caminho.with_name(caminho.stem + "_MEMORIA.txt").exists():
            raise FileExistsError("Arquivo de saida ou memoria ja existe; selecione outro nome.")
        if caminho.resolve() == analise.fiscal.resolve():
            raise RuntimeError("Arquivo Fiscal de origem nao pode ser sobrescrito.")
        # Grava exclusivamente uma COPIA; jamais altera arquivos de entrada.
        with caminho.open("x", encoding=encoding, newline="") as arq:
            arq.writelines(novas)
        relatorio = caminho.with_name(caminho.stem + "_MEMORIA.txt")
        self.salvar_relatorio(analise, relatorio)
        return GeracaoSaidasPresumido(caminho, relatorio, len(analise.ajustes),
                                     analise.icms, analise.pis, analise.cofins)

    @staticmethod
    def salvar_relatorio(analise: AnaliseSaidasPresumido, destino: str | Path) -> Path:
        caminho = Path(destino)
        linhas = [
            "FISCALPRO - EXCLUSAO ICMS DESTACADO DAS SAIDAS - LUCRO PRESUMIDO",
            "Tema 69/STF - Guia Pratico EFD Contribuicoes secao 12",
            "Valores nao devem ser transmitidos sem validar no PGE e conferir a memoria.",
            f"SPED Fiscal de referencia: {analise.fiscal}",
            analise.resumo(),
            "\nAJUSTES:",
        ]
        for a in analise.ajustes:
            linhas.append(
                f"{a.referencia}: CFOP {a.cfop}; ICMS {_fmt(a.icms)}; "
                f"PIS {_fmt(a.pis_anterior)} -> {_fmt(a.pis_novo)}; "
                f"COFINS {_fmt(a.cofins_anterior)} -> {_fmt(a.cofins_novo)}"
            )
        linhas.extend(["\nJA EXCLUIDOS:", *analise.ja_excluidos,
                       "\nREVISAR:", *analise.revisar])
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        return caminho
