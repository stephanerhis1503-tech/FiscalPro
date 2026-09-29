"""Cálculo assistido de MVA ajustada e ICMS-ST para Minas Gerais.

A rotina aplica a regra geral do Anexo VII do RICMS/MG/2023. Ela não decide
sozinha se a mercadoria está sujeita à substituição tributária; o enquadramento
deve vir da consulta oficial da Sprint 14.3.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional


CENTAVOS = Decimal("0.01")
DUAS_CASAS = Decimal("0.01")
CEM = Decimal("100")

FUNDAMENTO_BASE = "RICMS/MG/2023 — Anexo VII, Parte 1, art. 20, I, b, item 2"
FUNDAMENTO_MVA = "RICMS/MG/2023 — Anexo VII, Parte 1, art. 20, §§ 5º e 6º"
FUNDAMENTO_IMPOSTO = "RICMS/MG/2023 — Anexo VII, Parte 1, art. 22, I"
URL_RICMS_MG = (
    "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/"
    "ricms2023/anexovii2023.pdf"
)


def _decimal(valor: Any, nome: str, minimo: Optional[Decimal] = Decimal("0")) -> Decimal:
    """Converte número em formato brasileiro ou internacional para Decimal."""
    if isinstance(valor, Decimal):
        numero = valor
    elif isinstance(valor, (int, float)):
        numero = Decimal(str(valor))
    else:
        texto = str(valor or "").strip().replace("R$", "").replace("%", "").strip()
        if not texto:
            texto = "0"
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        try:
            numero = Decimal(texto)
        except InvalidOperation as erro:
            raise ValueError(f"{nome} deve ser um número válido.") from erro
    if minimo is not None and numero < minimo:
        raise ValueError(f"{nome} não pode ser menor que {minimo}.")
    return numero


def _moeda(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _percentual(valor: Decimal) -> Decimal:
    return valor.quantize(DUAS_CASAS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ResultadoCalculoICMSSTMG:
    status: str
    tipo_mva: str
    mva_original: Decimal
    mva_ajustada: Optional[Decimal]
    mva_utilizada: Decimal
    aliquota_interestadual: Decimal
    aliquota_interna: Decimal
    aliquota_fcp_st: Decimal
    valor_mercadoria: Decimal
    frete: Decimal
    seguro: Decimal
    ipi: Decimal
    outros_encargos: Decimal
    valor_total_com_ipi: Decimal
    base_partida_st: Decimal
    base_calculo_st: Decimal
    icms_presumido: Decimal
    icms_proprio_deduzir: Decimal
    icms_st: Decimal
    fcp_st: Decimal
    total_st_fcp: Decimal
    operacao_interestadual: bool
    remetente_simples: bool
    fundamento_base: str
    fundamento_mva: str
    fundamento_imposto: str
    fonte_url: str
    observacoes: List[str]

    def para_dict(self) -> Dict[str, Any]:
        dados = asdict(self)
        for chave, valor in list(dados.items()):
            if isinstance(valor, Decimal):
                dados[chave] = float(valor)
        return dados


class CalculadoraICMSSTMGService:
    """Executa a memória de cálculo da regra geral de ICMS-ST/MG."""

    @classmethod
    def calcular_mva_ajustada(
        cls,
        mva_original: Any,
        aliquota_interestadual: Any,
        aliquota_interna: Any,
    ) -> Decimal:
        mva = _decimal(mva_original, "MVA original") / CEM
        alq_inter = _decimal(aliquota_interestadual, "Alíquota interestadual") / CEM
        alq_intra = _decimal(aliquota_interna, "Alíquota interna") / CEM
        if alq_inter >= Decimal("1") or alq_intra >= Decimal("1"):
            raise ValueError("As alíquotas devem ser menores que 100%.")
        if alq_intra <= alq_inter:
            return _percentual(mva * CEM)
        resultado = (((Decimal("1") + mva) * (Decimal("1") - alq_inter)) /
                     (Decimal("1") - alq_intra) - Decimal("1")) * CEM
        return _percentual(resultado)

    @classmethod
    def calcular(
        cls,
        *,
        valor_mercadoria: Any,
        frete: Any = 0,
        seguro: Any = 0,
        ipi: Any = 0,
        outros_encargos: Any = 0,
        mva_original: Any,
        aliquota_interestadual: Any,
        aliquota_interna: Any,
        icms_proprio_deduzir: Any = 0,
        aliquota_fcp_st: Any = 0,
        operacao_interestadual: bool = True,
        aplicar_mva_ajustada: bool = True,
        remetente_simples: bool = False,
    ) -> Dict[str, Any]:
        mercadoria = _moeda(_decimal(valor_mercadoria, "Valor da mercadoria"))
        valor_frete = _moeda(_decimal(frete, "Frete"))
        valor_seguro = _moeda(_decimal(seguro, "Seguro"))
        valor_ipi = _moeda(_decimal(ipi, "IPI"))
        outros = _moeda(_decimal(outros_encargos, "Outros encargos"))
        icms_proprio = _moeda(_decimal(icms_proprio_deduzir, "ICMS próprio a deduzir"))

        mva_orig = _percentual(_decimal(mva_original, "MVA original"))
        alq_inter = _percentual(_decimal(aliquota_interestadual, "Alíquota interestadual"))
        alq_intra = _percentual(_decimal(aliquota_interna, "Alíquota interna"))
        alq_fcp = _percentual(_decimal(aliquota_fcp_st, "Alíquota FCP-ST"))
        for nome, valor in (
            ("MVA original", mva_orig),
            ("Alíquota interestadual", alq_inter),
            ("Alíquota interna", alq_intra),
            ("Alíquota FCP-ST", alq_fcp),
        ):
            if valor >= CEM:
                raise ValueError(f"{nome} deve ser menor que 100%.")

        observacoes: List[str] = []
        mva_ajustada: Optional[Decimal] = None
        mva_utilizada = mva_orig
        tipo_mva = "MVA ORIGINAL"

        if operacao_interestadual and aplicar_mva_ajustada and not remetente_simples:
            if alq_intra > alq_inter:
                mva_ajustada = cls.calcular_mva_ajustada(mva_orig, alq_inter, alq_intra)
                mva_utilizada = mva_ajustada
                tipo_mva = "MVA AJUSTADA"
            else:
                observacoes.append(
                    "A alíquota interna não é maior que a interestadual; foi mantida a MVA original."
                )
        elif operacao_interestadual and remetente_simples:
            observacoes.append(
                "A MVA ajustada não foi aplicada porque o remetente foi informado como optante pelo Simples Nacional."
            )
        elif not operacao_interestadual:
            observacoes.append(
                "Operação interna: foi utilizada a MVA original. Regime especial individual não é calculado nesta etapa."
            )
        elif not aplicar_mva_ajustada:
            observacoes.append("A opção de MVA ajustada foi desmarcada; foi utilizada a MVA original.")

        valor_total_com_ipi = _moeda(mercadoria + valor_ipi)
        base_partida = _moeda(mercadoria + valor_frete + valor_seguro + valor_ipi + outros)
        base_st = _moeda(base_partida * (Decimal("1") + (mva_utilizada / CEM)))
        icms_presumido = _moeda(base_st * (alq_intra / CEM))
        icms_st_bruto = _moeda(icms_presumido - icms_proprio)
        icms_st = max(Decimal("0.00"), icms_st_bruto)
        fcp_st = _moeda(base_st * (alq_fcp / CEM))
        total = _moeda(icms_st + fcp_st)

        if icms_proprio > icms_presumido:
            observacoes.append(
                "O ICMS próprio informado superou o ICMS presumido; o ICMS-ST foi limitado a zero."
            )
        if icms_proprio == 0:
            observacoes.append(
                "ICMS próprio a deduzir informado como zero. Confira a nota fiscal antes de usar o resultado."
            )
        if remetente_simples:
            observacoes.append(
                "Para remetente do Simples Nacional, o art. 22, § 1º do Anexo VII determina a dedução da operação própria "
                "pela alíquota interna ou interestadual, conforme a operação. No fluxo por XML, o FiscalPro calcula essa parcela "
                "automaticamente; nesta calculadora manual, confirme o valor informado em ICMS próprio a deduzir."
            )
        if alq_fcp > 0:
            observacoes.append(
                "O FCP-ST foi calculado separadamente. Confirme se o produto está sujeito ao adicional em Minas Gerais."
            )
        observacoes.append(
            "O valor da mercadoria deve ser informado antes do desconto, pois o art. 20 inclui os descontos concedidos "
            "na formação da base da substituição tributária."
        )
        observacoes.append(
            "Este cálculo usa a regra geral por MVA; PMPF, preço tabelado, redução de base, benefício ou regime especial "
            "exigem tratamento próprio."
        )

        resultado = ResultadoCalculoICMSSTMG(
            status="CÁLCULO CONCLUÍDO — CONFERIR DADOS INFORMADOS",
            tipo_mva=tipo_mva,
            mva_original=mva_orig,
            mva_ajustada=mva_ajustada,
            mva_utilizada=mva_utilizada,
            aliquota_interestadual=alq_inter,
            aliquota_interna=alq_intra,
            aliquota_fcp_st=alq_fcp,
            valor_mercadoria=mercadoria,
            frete=valor_frete,
            seguro=valor_seguro,
            ipi=valor_ipi,
            outros_encargos=outros,
            valor_total_com_ipi=valor_total_com_ipi,
            base_partida_st=base_partida,
            base_calculo_st=base_st,
            icms_presumido=icms_presumido,
            icms_proprio_deduzir=icms_proprio,
            icms_st=icms_st,
            fcp_st=fcp_st,
            total_st_fcp=total,
            operacao_interestadual=bool(operacao_interestadual),
            remetente_simples=bool(remetente_simples),
            fundamento_base=FUNDAMENTO_BASE,
            fundamento_mva=FUNDAMENTO_MVA,
            fundamento_imposto=FUNDAMENTO_IMPOSTO,
            fonte_url=URL_RICMS_MG,
            observacoes=observacoes,
        )
        return resultado.para_dict()

    @staticmethod
    def memoria_texto(resultado: Dict[str, Any]) -> str:
        def moeda(chave: str) -> str:
            valor = Decimal(str(resultado.get(chave, 0)))
            texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return f"R$ {texto}"

        def pct(chave: str) -> str:
            valor = Decimal(str(resultado.get(chave, 0)))
            return f"{valor:.2f}%".replace(".", ",")

        linhas = [
            "FISCALPRO — MEMÓRIA DE CÁLCULO ICMS-ST/MG",
            "",
            f"MVA original: {pct('mva_original')}",
            f"MVA ajustada: {pct('mva_ajustada') if resultado.get('mva_ajustada') is not None else 'Não aplicada'}",
            f"MVA utilizada: {pct('mva_utilizada')} ({resultado.get('tipo_mva', '')})",
            f"Alíquota interestadual: {pct('aliquota_interestadual')}",
            f"Alíquota interna MG: {pct('aliquota_interna')}",
            "",
            f"Valor da mercadoria: {moeda('valor_mercadoria')}",
            f"IPI: {moeda('ipi')}",
            f"Valor da mercadoria + IPI: {moeda('valor_total_com_ipi')}",
            f"Frete: {moeda('frete')}",
            f"Seguro: {moeda('seguro')}",
            f"Outros encargos: {moeda('outros_encargos')}",
            f"Base de partida: {moeda('base_partida_st')}",
            "",
            f"Base de cálculo do ICMS-ST: {moeda('base_calculo_st')}",
            f"ICMS presumido: {moeda('icms_presumido')}",
            f"ICMS próprio a deduzir: {moeda('icms_proprio_deduzir')}",
            f"ICMS-ST: {moeda('icms_st')}",
            f"FCP-ST: {moeda('fcp_st')}",
            f"Total ICMS-ST + FCP-ST: {moeda('total_st_fcp')}",
            "",
            f"Base legal da base: {resultado.get('fundamento_base', '')}",
            f"Base legal da MVA: {resultado.get('fundamento_mva', '')}",
            f"Base legal do imposto: {resultado.get('fundamento_imposto', '')}",
            "",
            "Observações:",
            *[f"• {item}" for item in resultado.get("observacoes", [])],
        ]
        return "\n".join(linhas)
