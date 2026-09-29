"""Motor do Simulador Tributário — Sprint 13.7.

O simulador usa exclusivamente as regras já cadastradas na Ficha Tributária
Inteligente. Os cálculos são estimativas de conferência e deixam explícitas as
premissas utilizadas. Bases manuais e alíquotas substitutas podem ser informadas
quando a operação exigir tratamento específico.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.parecer.motor_parecer import MotorParecer
from src.simulador.tabela_difal import FONTE_TABELA_DIFAL, aliquotas_automaticas


CENTAVOS = Decimal("0.01")
QUATRO_CASAS = Decimal("0.0001")
ZERO = Decimal("0")
CEM = Decimal("100")


def _texto(valor: Any) -> str:
    return str(valor or "").strip()


def _normalizar_numero(valor: Any, campo: str = "valor") -> Decimal:
    if valor in (None, ""):
        return ZERO
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, bool):
        return Decimal(int(valor))
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))
    texto = str(valor).strip().replace("R$", "").replace("%", "").replace(" ", "")
    if not texto:
        return ZERO
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation as erro:
        raise ValueError(f"Informe um número válido para {campo}.") from erro


def _dinheiro(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _percentual(valor: Decimal) -> Decimal:
    return valor.quantize(QUATRO_CASAS, rounding=ROUND_HALF_UP)


def _data_iso(valor: Any) -> str:
    texto = _texto(valor)
    if not texto:
        return date.today().isoformat()
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto[:10], formato).date().isoformat()
        except ValueError:
            continue
    raise ValueError("Data da operação inválida. Use dd/mm/aaaa.")


def _sim(valor: Any) -> bool:
    texto = _texto(valor).upper()
    return texto in {"SIM", "S", "1", "TRUE", "VERDADEIRO", "ST", "CONTRIBUINTE"}


def _ncm(valor: Any) -> str:
    digitos = "".join(c for c in str(valor or "") if c.isdigit())
    if len(digitos) != 8:
        raise ValueError("Informe um NCM com 8 dígitos.")
    return digitos


@dataclass
class EntradaSimulacao:
    ncm: str
    empresa: str = "Todas as empresas"
    regime: str = ""
    operacao: str = "SAÍDA"
    finalidade: str = "REVENDA"
    uf_origem: str = "MG"
    uf_destino: str = "MG"
    contribuinte: str = "TODOS"
    data_operacao: str = field(default_factory=lambda: date.today().isoformat())
    descricao_cenario: str = "Cenário principal"

    quantidade: Decimal = Decimal("1")
    valor_unitario: Decimal = ZERO
    desconto: Decimal = ZERO
    frete: Decimal = ZERO
    seguro: Decimal = ZERO
    outras_despesas: Decimal = ZERO

    base_icms_manual: Decimal = ZERO
    base_pis_cofins_manual: Decimal = ZERO
    base_ipi_manual: Decimal = ZERO
    base_reforma_manual: Decimal = ZERO
    base_difal_manual: Decimal = ZERO

    aliquota_icms_override: Optional[Decimal] = None
    aliquota_fcp_override: Optional[Decimal] = None
    aliquota_pis_override: Optional[Decimal] = None
    aliquota_cofins_override: Optional[Decimal] = None
    aliquota_ipi_override: Optional[Decimal] = None
    aliquota_ibs_override: Optional[Decimal] = None
    aliquota_cbs_override: Optional[Decimal] = None
    reducao_ibs_override: Optional[Decimal] = None
    reducao_cbs_override: Optional[Decimal] = None

    incluir_ipi_base_icms: bool = False
    calcular_fcp: bool = True
    calcular_icms_st: bool = False
    mva: Decimal = ZERO
    aliquota_interna_st: Decimal = ZERO
    aliquota_interestadual: Decimal = ZERO
    incluir_ipi_base_st: bool = True
    calcular_difal: bool = False
    aliquota_interna_destino: Decimal = ZERO
    modalidade_difal: str = "POR FORA"
    aliquotas_difal_automaticas: bool = False
    mercadoria_importada: bool = False
    considerar_creditos_potenciais: bool = False

    @classmethod
    def de_dict(cls, dados: Dict[str, Any]) -> "EntradaSimulacao":
        campos_decimais = {
            "quantidade", "valor_unitario", "desconto", "frete", "seguro", "outras_despesas",
            "base_icms_manual", "base_pis_cofins_manual", "base_ipi_manual", "base_reforma_manual",
            "base_difal_manual", "mva", "aliquota_interna_st", "aliquota_interestadual",
            "aliquota_interna_destino",
        }
        campos_opcionais = {
            "aliquota_icms_override", "aliquota_fcp_override", "aliquota_pis_override",
            "aliquota_cofins_override", "aliquota_ipi_override", "aliquota_ibs_override",
            "aliquota_cbs_override", "reducao_ibs_override", "reducao_cbs_override",
        }
        valores: Dict[str, Any] = dict(dados)
        valores["ncm"] = _ncm(valores.get("ncm"))
        valores["data_operacao"] = _data_iso(valores.get("data_operacao"))
        for campo in campos_decimais:
            valores[campo] = _normalizar_numero(valores.get(campo), campo.replace("_", " "))
        for campo in campos_opcionais:
            valor = valores.get(campo)
            valores[campo] = None if valor in (None, "") else _normalizar_numero(valor, campo.replace("_", " "))
        for campo in (
            "incluir_ipi_base_icms", "calcular_fcp", "calcular_icms_st", "incluir_ipi_base_st",
            "calcular_difal", "aliquotas_difal_automaticas", "mercadoria_importada",
            "considerar_creditos_potenciais",
        ):
            valor = valores.get(campo, False)
            valores[campo] = valor if isinstance(valor, bool) else _sim(valor)
        modalidade = _texto(valores.get("modalidade_difal") or "POR FORA").upper().replace("_", " ")
        if modalidade not in {"POR DENTRO", "POR FORA"}:
            raise ValueError("Modalidade do DIFAL inválida. Use POR DENTRO ou POR FORA.")
        valores["modalidade_difal"] = modalidade
        return cls(**valores)

    def contexto(self) -> Dict[str, str]:
        return {
            "empresa": self.empresa,
            "regime": self.regime,
            "operacao": self.operacao,
            "finalidade": self.finalidade,
            "uf_origem": self.uf_origem,
            "uf_destino": self.uf_destino,
            "contribuinte": self.contribuinte,
            "data_operacao": self.data_operacao,
        }

    def para_dict(self) -> Dict[str, Any]:
        resultado = asdict(self)
        for chave, valor in list(resultado.items()):
            if isinstance(valor, Decimal):
                resultado[chave] = str(valor)
        return resultado


@dataclass
class LinhaCalculo:
    tributo: str
    base: Decimal
    aliquota: Decimal
    valor: Decimal
    observacao: str = ""

    def para_dict(self) -> Dict[str, Any]:
        return {
            "tributo": self.tributo,
            "base": str(self.base),
            "aliquota": str(self.aliquota),
            "valor": str(self.valor),
            "observacao": self.observacao,
        }


@dataclass
class ResultadoSimulacao:
    entrada: EntradaSimulacao
    descricao_ncm: str
    linhas: List[LinhaCalculo]
    valor_produtos: Decimal
    valor_operacao: Decimal
    valor_estimado_documento: Decimal
    total_tributos_atual: Decimal
    total_reforma: Decimal
    diferenca_reforma_atual: Decimal
    creditos_potenciais: Decimal
    carga_percentual_atual: Decimal
    carga_percentual_reforma: Decimal
    regra_atual_id: str = ""
    regra_reforma_id: str = ""
    aderencia_regra_atual: str = "0%"
    aderencia_regra_reforma: str = "0%"
    fonte_regra_atual: str = ""
    fonte_regra_reforma: str = ""
    confiabilidade: Decimal = ZERO
    nivel_confiabilidade: str = "BAIXA"
    alertas: List[str] = field(default_factory=list)
    premissas: List[str] = field(default_factory=list)
    gerado_em: str = field(default_factory=lambda: datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    versao_motor: str = "13.7.1"

    def valor_tributo(self, nome: str) -> Decimal:
        nome = nome.upper()
        for linha in self.linhas:
            if linha.tributo.upper() == nome:
                return linha.valor
        return ZERO

    def para_dict(self) -> Dict[str, Any]:
        return {
            "entrada": self.entrada.para_dict(),
            "descricao_ncm": self.descricao_ncm,
            "linhas": [linha.para_dict() for linha in self.linhas],
            "valor_produtos": str(self.valor_produtos),
            "valor_operacao": str(self.valor_operacao),
            "valor_estimado_documento": str(self.valor_estimado_documento),
            "total_tributos_atual": str(self.total_tributos_atual),
            "total_reforma": str(self.total_reforma),
            "diferenca_reforma_atual": str(self.diferenca_reforma_atual),
            "creditos_potenciais": str(self.creditos_potenciais),
            "carga_percentual_atual": str(self.carga_percentual_atual),
            "carga_percentual_reforma": str(self.carga_percentual_reforma),
            "regra_atual_id": self.regra_atual_id,
            "regra_reforma_id": self.regra_reforma_id,
            "aderencia_regra_atual": self.aderencia_regra_atual,
            "aderencia_regra_reforma": self.aderencia_regra_reforma,
            "fonte_regra_atual": self.fonte_regra_atual,
            "fonte_regra_reforma": self.fonte_regra_reforma,
            "confiabilidade": str(self.confiabilidade),
            "nivel_confiabilidade": self.nivel_confiabilidade,
            "alertas": list(self.alertas),
            "premissas": list(self.premissas),
            "gerado_em": self.gerado_em,
            "versao_motor": self.versao_motor,
        }

    @classmethod
    def de_dict(cls, dados: Dict[str, Any]) -> "ResultadoSimulacao":
        return cls(
            entrada=EntradaSimulacao.de_dict(dados["entrada"]),
            descricao_ncm=dados.get("descricao_ncm", ""),
            linhas=[
                LinhaCalculo(
                    tributo=item.get("tributo", ""),
                    base=_normalizar_numero(item.get("base")),
                    aliquota=_normalizar_numero(item.get("aliquota")),
                    valor=_normalizar_numero(item.get("valor")),
                    observacao=item.get("observacao", ""),
                )
                for item in dados.get("linhas", [])
            ],
            valor_produtos=_normalizar_numero(dados.get("valor_produtos")),
            valor_operacao=_normalizar_numero(dados.get("valor_operacao")),
            valor_estimado_documento=_normalizar_numero(dados.get("valor_estimado_documento")),
            total_tributos_atual=_normalizar_numero(dados.get("total_tributos_atual")),
            total_reforma=_normalizar_numero(dados.get("total_reforma")),
            diferenca_reforma_atual=_normalizar_numero(dados.get("diferenca_reforma_atual")),
            creditos_potenciais=_normalizar_numero(dados.get("creditos_potenciais")),
            carga_percentual_atual=_normalizar_numero(dados.get("carga_percentual_atual")),
            carga_percentual_reforma=_normalizar_numero(dados.get("carga_percentual_reforma")),
            regra_atual_id=str(dados.get("regra_atual_id", "")),
            regra_reforma_id=str(dados.get("regra_reforma_id", "")),
            aderencia_regra_atual=str(dados.get("aderencia_regra_atual", "0%")),
            aderencia_regra_reforma=str(dados.get("aderencia_regra_reforma", "0%")),
            fonte_regra_atual=str(dados.get("fonte_regra_atual", "")),
            fonte_regra_reforma=str(dados.get("fonte_regra_reforma", "")),
            confiabilidade=_normalizar_numero(dados.get("confiabilidade")),
            nivel_confiabilidade=str(dados.get("nivel_confiabilidade", "BAIXA")),
            alertas=list(dados.get("alertas", [])),
            premissas=list(dados.get("premissas", [])),
            gerado_em=str(dados.get("gerado_em", "")),
            versao_motor=str(dados.get("versao_motor", "13.7.1")),
        )


class MotorSimuladorTributario:
    """Calcula cenários tributários a partir da Ficha Tributária."""

    @staticmethod
    def _aliquota(valor_override: Optional[Decimal], valor_regra: Any) -> Decimal:
        if valor_override is not None:
            return max(ZERO, valor_override)
        return max(ZERO, _normalizar_numero(valor_regra))

    @staticmethod
    def _base(manual: Decimal, automatica: Decimal) -> Decimal:
        return _dinheiro(manual if manual > ZERO else automatica)

    @staticmethod
    def _calcular(base: Decimal, aliquota: Decimal) -> Decimal:
        if base <= ZERO or aliquota <= ZERO:
            return ZERO
        return _dinheiro(base * aliquota / CEM)

    @classmethod
    def simular(cls, dados_ficha: Dict[str, Any], entrada: EntradaSimulacao | Dict[str, Any]) -> ResultadoSimulacao:
        if not isinstance(entrada, EntradaSimulacao):
            entrada = EntradaSimulacao.de_dict(entrada)
        if entrada.quantidade <= ZERO:
            raise ValueError("A quantidade deve ser maior que zero.")
        if entrada.valor_unitario < ZERO:
            raise ValueError("O valor unitário não pode ser negativo.")
        for nome, valor in (
            ("desconto", entrada.desconto), ("frete", entrada.frete), ("seguro", entrada.seguro),
            ("outras despesas", entrada.outras_despesas),
        ):
            if valor < ZERO:
                raise ValueError(f"O campo {nome} não pode ser negativo.")

        parecer = MotorParecer.gerar(dados_ficha, entrada.contexto())
        regra = parecer.tributacao_atual
        reforma = parecer.reforma

        valor_produtos = _dinheiro(entrada.quantidade * entrada.valor_unitario)
        valor_operacao = _dinheiro(
            valor_produtos - entrada.desconto + entrada.frete + entrada.seguro + entrada.outras_despesas
        )
        if valor_operacao < ZERO:
            raise ValueError("O desconto não pode resultar em valor de operação negativo.")

        aliquota_ipi = cls._aliquota(entrada.aliquota_ipi_override, regra.get("IPI"))
        base_ipi = cls._base(entrada.base_ipi_manual, valor_operacao)
        valor_ipi = cls._calcular(base_ipi, aliquota_ipi)

        # O preenchimento automático usa a tabela transcrita da planilha DIFAL CAROL.
        # Os valores continuam editáveis: basta desmarcar a opção automática na tela.
        difal_automatico_aplicado = False
        if entrada.calcular_difal and entrada.aliquotas_difal_automaticas:
            interna_auto, interestadual_auto = aliquotas_automaticas(
                entrada.uf_origem, entrada.uf_destino, entrada.mercadoria_importada
            )
            entrada.aliquota_interna_destino = interna_auto
            entrada.aliquota_interestadual = interestadual_auto
            difal_automatico_aplicado = True

        base_icms_auto = valor_operacao + (valor_ipi if entrada.incluir_ipi_base_icms else ZERO)
        base_icms = cls._base(entrada.base_icms_manual, base_icms_auto)
        aliquota_icms_regra = cls._aliquota(entrada.aliquota_icms_override, regra.get("ICMS"))

        operacao_interna_difal = (
            entrada.calcular_difal
            and _texto(entrada.uf_origem).upper() == _texto(entrada.uf_destino).upper()
        )
        base_difal = ZERO
        base_difal_exata = ZERO
        diferencial_difal = ZERO
        aliquota_interna_difal = entrada.aliquota_interna_destino
        aliquota_interestadual_difal = entrada.aliquota_interestadual

        if entrada.calcular_difal:
            base_difal_origem = cls._base(entrada.base_difal_manual, base_icms)
            if operacao_interna_difal:
                base_difal_exata = base_difal_origem
                base_difal = base_difal_origem
            else:
                if aliquota_interna_difal <= ZERO or aliquota_interestadual_difal <= ZERO:
                    raise ValueError(
                        "Não foi possível definir as alíquotas do DIFAL. "
                        "Use o preenchimento automático ou informe as alíquotas interna e interestadual."
                    )
                diferencial_difal = max(ZERO, aliquota_interna_difal - aliquota_interestadual_difal)
                if entrada.modalidade_difal == "POR DENTRO":
                    divisor = Decimal("1") - aliquota_interna_difal / CEM
                    if divisor <= ZERO:
                        raise ValueError("A alíquota interna não permite calcular o DIFAL por dentro.")
                    # Mantém a precisão da fórmula da planilha antes do arredondamento final.
                    base_difal_exata = base_difal_origem / divisor
                else:
                    base_difal_exata = base_difal_origem
                base_difal = _dinheiro(base_difal_exata)

        aliquota_icms_calculo = (
            aliquota_interestadual_difal
            if entrada.calcular_difal and aliquota_interestadual_difal > ZERO
            else aliquota_icms_regra
        )
        # Na modalidade POR DENTRO a planilha usa o valor ajustado também para
        # demonstrar o ICMS interestadual. Nas demais situações, mantém a base normal.
        base_icms_demonstrativa = (
            base_difal
            if entrada.calcular_difal and entrada.modalidade_difal == "POR DENTRO" and not operacao_interna_difal
            else base_icms
        )
        valor_icms = (
            _dinheiro(base_difal_exata * aliquota_icms_calculo / CEM)
            if entrada.calcular_difal and entrada.modalidade_difal == "POR DENTRO" and not operacao_interna_difal
            else cls._calcular(base_icms, aliquota_icms_calculo)
        )

        aliquota_fcp = cls._aliquota(entrada.aliquota_fcp_override, regra.get("FCP"))
        valor_fcp = cls._calcular(base_icms, aliquota_fcp) if entrada.calcular_fcp else ZERO

        base_pis_cofins = cls._base(entrada.base_pis_cofins_manual, valor_operacao)
        aliquota_pis = cls._aliquota(entrada.aliquota_pis_override, regra.get("PIS"))
        aliquota_cofins = cls._aliquota(entrada.aliquota_cofins_override, regra.get("COFINS"))
        valor_pis = cls._calcular(base_pis_cofins, aliquota_pis)
        valor_cofins = cls._calcular(base_pis_cofins, aliquota_cofins)

        base_st = ZERO
        valor_icms_st = ZERO
        valor_fcp_st = ZERO
        if entrada.calcular_icms_st:
            if entrada.mva <= ZERO:
                raise ValueError("Informe a MVA para calcular o ICMS-ST.")
            aliquota_interna_st = entrada.aliquota_interna_st or entrada.aliquota_interna_destino or aliquota_icms_regra
            if aliquota_interna_st <= ZERO:
                raise ValueError("Informe a alíquota interna de destino para calcular o ICMS-ST.")
            base_st_origem = valor_operacao + (valor_ipi if entrada.incluir_ipi_base_st else ZERO)
            base_st = _dinheiro(base_st_origem * (Decimal("1") + entrada.mva / CEM))
            debito_destino = cls._calcular(base_st, aliquota_interna_st)
            valor_icms_st = max(ZERO, _dinheiro(debito_destino - valor_icms))
            valor_fcp_st = cls._calcular(base_st, aliquota_fcp) if entrada.calcular_fcp else ZERO

        valor_difal = ZERO
        valor_fcp_difal = ZERO
        if entrada.calcular_difal and not operacao_interna_difal:
            valor_difal = _dinheiro(base_difal_exata * diferencial_difal / CEM)
            valor_fcp_difal = (
                _dinheiro(base_difal_exata * aliquota_fcp / CEM)
                if entrada.calcular_fcp and aliquota_fcp > ZERO
                else ZERO
            )

        base_reforma = cls._base(entrada.base_reforma_manual, valor_operacao)
        aliquota_ibs = cls._aliquota(entrada.aliquota_ibs_override, reforma.get("IBS"))
        aliquota_cbs = cls._aliquota(entrada.aliquota_cbs_override, reforma.get("CBS"))
        reducao_ibs = cls._aliquota(entrada.reducao_ibs_override, reforma.get("Redução IBS"))
        reducao_cbs = cls._aliquota(entrada.reducao_cbs_override, reforma.get("Redução CBS"))
        reducao_ibs = min(CEM, reducao_ibs)
        reducao_cbs = min(CEM, reducao_cbs)
        aliquota_ibs_efetiva = _percentual(aliquota_ibs * (CEM - reducao_ibs) / CEM)
        aliquota_cbs_efetiva = _percentual(aliquota_cbs * (CEM - reducao_cbs) / CEM)
        valor_ibs = cls._calcular(base_reforma, aliquota_ibs_efetiva)
        valor_cbs = cls._calcular(base_reforma, aliquota_cbs_efetiva)

        linhas = [
            LinhaCalculo(
                "ICMS próprio", base_icms_demonstrativa, _percentual(aliquota_icms_calculo), valor_icms,
                "Base ajustada conforme a modalidade DIFAL"
                if entrada.calcular_difal and entrada.modalidade_difal == "POR DENTRO" and not operacao_interna_difal
                else "Alíquota da operação ou substituição manual",
            ),
            LinhaCalculo("FCP próprio", base_icms if entrada.calcular_fcp else ZERO, _percentual(aliquota_fcp), valor_fcp, "Calculado somente quando habilitado"),
            LinhaCalculo("PIS", base_pis_cofins, _percentual(aliquota_pis), valor_pis, f"CST {regra.get('CST PIS', 'não informado')}"),
            LinhaCalculo("COFINS", base_pis_cofins, _percentual(aliquota_cofins), valor_cofins, f"CST {regra.get('CST COFINS', 'não informado')}"),
            LinhaCalculo("IPI", base_ipi, _percentual(aliquota_ipi), valor_ipi, f"CST {regra.get('CST IPI', 'não informado')}"),
        ]
        if entrada.calcular_icms_st:
            linhas.extend(
                [
                    LinhaCalculo("ICMS-ST", base_st, _percentual(entrada.aliquota_interna_st or entrada.aliquota_interna_destino or aliquota_icms_regra), valor_icms_st, f"MVA utilizada: {_percentual(entrada.mva)}%"),
                    LinhaCalculo("FCP-ST", base_st if entrada.calcular_fcp else ZERO, _percentual(aliquota_fcp), valor_fcp_st, "Estimativa sobre a base de ST"),
                ]
            )
        if entrada.calcular_difal:
            observacao_difal = (
                "Operação interna: DIFAL não aplicável"
                if operacao_interna_difal
                else f"{entrada.modalidade_difal.title()} | interna { _percentual(aliquota_interna_difal) }% "
                     f"menos interestadual { _percentual(aliquota_interestadual_difal) }%"
            )
            linhas.extend(
                [
                    LinhaCalculo("DIFAL", base_difal, _percentual(diferencial_difal), valor_difal, observacao_difal),
                    LinhaCalculo(
                        "FCP DIFAL", base_difal if entrada.calcular_fcp and not operacao_interna_difal else ZERO,
                        _percentual(aliquota_fcp), valor_fcp_difal,
                        "Calculado sobre a mesma base do DIFAL" if not operacao_interna_difal else "Não aplicável",
                    ),
                ]
            )
        linhas.extend(
            [
                LinhaCalculo("IBS", base_reforma, aliquota_ibs_efetiva, valor_ibs, f"Alíquota nominal {_percentual(aliquota_ibs)}% | redução {_percentual(reducao_ibs)}%"),
                LinhaCalculo("CBS", base_reforma, aliquota_cbs_efetiva, valor_cbs, f"Alíquota nominal {_percentual(aliquota_cbs)}% | redução {_percentual(reducao_cbs)}%"),
            ]
        )

        total_atual = _dinheiro(
            valor_icms + valor_fcp + valor_pis + valor_cofins + valor_ipi + valor_icms_st
            + valor_fcp_st + valor_difal + valor_fcp_difal
        )
        total_reforma = _dinheiro(valor_ibs + valor_cbs)
        diferenca = _dinheiro(total_reforma - total_atual)
        valor_documento = _dinheiro(valor_operacao + valor_ipi + valor_icms_st + valor_fcp_st + valor_difal + valor_fcp_difal)

        creditos = ZERO
        if entrada.considerar_creditos_potenciais:
            creditos = _dinheiro(valor_icms + valor_pis + valor_cofins + valor_ipi + valor_ibs + valor_cbs)

        carga_atual = _percentual((total_atual / valor_operacao * CEM) if valor_operacao > ZERO else ZERO)
        carga_reforma = _percentual((total_reforma / valor_operacao * CEM) if valor_operacao > ZERO else ZERO)

        alertas = list(parecer.alertas)
        premissas = [
            "Os cálculos usam as regras cadastradas na Ficha Tributária e as bases informadas nesta simulação.",
            "A soma dos tributos é demonstrativa: ICMS, PIS e COFINS podem estar embutidos no preço e não devem ser somados ao documento sem análise da operação.",
            "ICMS-ST e DIFAL são memórias demonstrativas; confirme benefícios, reduções, FCP e enquadramento da operação na legislação vigente.",
            "IBS e CBS são demonstrados conforme alíquotas e reduções cadastradas, sem substituir a apuração oficial do período de transição.",
        ]
        if entrada.base_icms_manual > ZERO:
            premissas.append("A base de ICMS foi substituída manualmente.")
        if entrada.base_pis_cofins_manual > ZERO:
            premissas.append("A base de PIS/COFINS foi substituída manualmente.")
        if entrada.base_reforma_manual > ZERO:
            premissas.append("A base de IBS/CBS foi substituída manualmente.")
        if entrada.calcular_difal:
            premissas.append(
                f"DIFAL calculado na modalidade {entrada.modalidade_difal}, com alíquota interna "
                f"de {_percentual(aliquota_interna_difal)}% e interestadual de "
                f"{_percentual(aliquota_interestadual_difal)}%."
            )
            if entrada.modalidade_difal == "POR DENTRO" and not operacao_interna_difal:
                premissas.append(
                    f"Base original do DIFAL: R$ {_dinheiro(cls._base(entrada.base_difal_manual, base_icms))}; "
                    f"base ajustada: R$ {base_difal}."
                )
            if difal_automatico_aplicado:
                premissas.append(f"Alíquotas do DIFAL preenchidas automaticamente com base em: {FONTE_TABELA_DIFAL}.")
            if entrada.mercadoria_importada:
                premissas.append("A opção de mercadoria importada foi ativada e a alíquota interestadual automática utilizada foi 4%.")
            if operacao_interna_difal:
                alertas.append("UF de origem e destino são iguais; o DIFAL foi mantido em zero.")
        if entrada.considerar_creditos_potenciais:
            alertas.append("Créditos potenciais foram estimados sem validar as condições materiais de creditamento.")
        if not regra.get("ID da regra"):
            alertas.append("A simulação atual não possui uma regra tributária versionada plenamente identificada.")
        if not reforma.get("ID da regra"):
            alertas.append("A simulação da Reforma Tributária não possui regra versionada identificada.")

        return ResultadoSimulacao(
            entrada=entrada,
            descricao_ncm=parecer.descricao,
            linhas=linhas,
            valor_produtos=valor_produtos,
            valor_operacao=valor_operacao,
            valor_estimado_documento=valor_documento,
            total_tributos_atual=total_atual,
            total_reforma=total_reforma,
            diferenca_reforma_atual=diferenca,
            creditos_potenciais=creditos,
            carga_percentual_atual=carga_atual,
            carga_percentual_reforma=carga_reforma,
            regra_atual_id=str(regra.get("ID da regra") or ""),
            regra_reforma_id=str(reforma.get("ID da regra") or ""),
            aderencia_regra_atual=str(regra.get("Aderência ao contexto") or "0%"),
            aderencia_regra_reforma=str(reforma.get("Aderência ao contexto") or "0%"),
            fonte_regra_atual=str(regra.get("Fonte da regra") or ""),
            fonte_regra_reforma=str(reforma.get("Fonte da regra") or ""),
            confiabilidade=_percentual(Decimal(str(parecer.confiabilidade))),
            nivel_confiabilidade=parecer.nivel_confiabilidade,
            alertas=list(dict.fromkeys(alertas)),
            premissas=list(dict.fromkeys(premissas)),
        )

    @staticmethod
    def comparar(resultados: Sequence[ResultadoSimulacao]) -> List[Dict[str, Any]]:
        comparacao: List[Dict[str, Any]] = []
        for indice, resultado in enumerate(resultados, start=1):
            entrada = resultado.entrada
            comparacao.append(
                {
                    "indice": indice,
                    "cenario": entrada.descricao_cenario or f"Cenário {indice}",
                    "ncm": entrada.ncm,
                    "uf": f"{entrada.uf_origem} → {entrada.uf_destino}",
                    "regime": entrada.regime,
                    "operacao": entrada.operacao,
                    "finalidade": entrada.finalidade,
                    "valor_operacao": resultado.valor_operacao,
                    "tributos_atual": resultado.total_tributos_atual,
                    "carga_atual": resultado.carga_percentual_atual,
                    "reforma": resultado.total_reforma,
                    "carga_reforma": resultado.carga_percentual_reforma,
                    "diferenca": resultado.diferenca_reforma_atual,
                    "valor_documento": resultado.valor_estimado_documento,
                    "confiabilidade": resultado.confiabilidade,
                }
            )
        return comparacao


__all__ = [
    "EntradaSimulacao",
    "LinhaCalculo",
    "ResultadoSimulacao",
    "MotorSimuladorTributario",
]
