"""Motor conservador de DIFAL e FCP para operações interestaduais.

Sprint 16.8.0

O serviço não presume que toda venda interestadual tenha DIFAL. Primeiro ele
valida a natureza da operação, o destino a consumidor final e a condição de
contribuinte do destinatário. Depois separa:

1. aplicabilidade do DIFAL;
2. responsável pelo recolhimento;
3. alíquota interestadual de 4%, 7% ou 12%;
4. alíquota interna da UF de destino;
5. adicional de FCP informado;
6. memória de cálculo, quando houver valor de operação suficiente.

Para destinos fora de Minas Gerais, a tabela interna instalada serve somente
como referência operacional e permanece condicional até confirmação do usuário.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Optional
import unicodedata

from src.services.icms_mg_nacional_service import ICMSMGNacionalService, UFS_BRASIL
from src.services.icms_uf_service import ICMSUFService, UFS_COBERTURA
from src.simulador.tabela_difal import (
    FONTE_TABELA_DIFAL,
    aliquota_interna_destino as aliquota_interna_referencia,
)


URL_LC_87 = "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp87.htm"
URL_LC_190 = "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp190.htm"
URL_PORTAL_DIFAL = "https://dfe-portal.svrs.rs.gov.br/Difal/"
URL_RICMS_MG = (
    "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/"
    "ricms2023/regulamento2023.pdf"
)

CENTAVOS = Decimal("0.01")
CEM = Decimal("100")
ZERO = Decimal("0")


@dataclass(frozen=True)
class ResultadoDIFALFCP:
    ncm: str
    uf_origem: str
    uf_destino: str
    status: str
    aplicavel: bool
    confirmado: bool
    exige_revisao: bool
    motivo: str = ""
    responsavel: str = ""
    destinatario_contribuinte: Optional[bool] = None
    consumidor_final: bool = False
    aliquota_interestadual: Optional[float] = None
    aliquota_interestadual_status: str = ""
    aliquota_interestadual_confirmada: bool = False
    aliquota_interna_destino: Optional[float] = None
    aliquota_interna_status: str = ""
    aliquota_interna_confirmada: bool = False
    diferencial_percentual: Optional[float] = None
    aliquota_fcp: Optional[float] = None
    fcp_status: str = ""
    fcp_confirmado: bool = False
    valor_operacao: Optional[float] = None
    valor_inclui_icms: bool = True
    modalidade_calculo: str = ""
    base_origem: Optional[float] = None
    base_destino: Optional[float] = None
    valor_icms_origem: Optional[float] = None
    valor_icms_destino: Optional[float] = None
    valor_difal: Optional[float] = None
    valor_fcp: Optional[float] = None
    confiabilidade: float = 0.0
    fundamento: str = ""
    fontes: str = ""
    observacao: str = ""

    def para_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DIFALFCPNacionalService:
    """Analisa e calcula DIFAL/FCP com premissas explícitas e rastreáveis."""

    @staticmethod
    def _normalizar_ncm(valor: Any) -> str:
        codigo = "".join(c for c in str(valor or "") if c.isdigit())
        if codigo and len(codigo) != 8:
            raise ValueError("O NCM deve possuir 8 dígitos.")
        return codigo

    @staticmethod
    def _normalizar_uf(valor: Any) -> str:
        uf = str(valor or "").strip().upper()
        if uf and uf not in UFS_BRASIL:
            raise ValueError(f"UF inválida: {uf}.")
        return uf

    @staticmethod
    def _normalizar_texto(valor: Any) -> str:
        texto = str(valor or "").strip().upper()
        texto = "".join(
            c for c in unicodedata.normalize("NFD", texto)
            if unicodedata.category(c) != "Mn"
        )
        return " ".join(texto.split())

    @staticmethod
    def _booleano(valor: Any, padrao: Optional[bool] = False) -> Optional[bool]:
        if valor is None or str(valor).strip() == "":
            return padrao
        if isinstance(valor, bool):
            return valor
        texto = str(valor).strip().upper()
        if texto in {"1", "SIM", "S", "TRUE", "VERDADEIRO", "YES", "CONTRIBUINTE"}:
            return True
        if texto in {"0", "NAO", "NÃO", "N", "FALSE", "FALSO", "NO", "NAO CONTRIBUINTE", "NÃO CONTRIBUINTE"}:
            return False
        if texto in {"TODOS", "INFORMAR", "DESCONHECIDO", "NAO INFORMADO", "NÃO INFORMADO"}:
            return None
        return padrao

    @staticmethod
    def _decimal(valor: Any, nome: str, permitir_vazio: bool = True) -> Optional[Decimal]:
        if valor in (None, ""):
            if permitir_vazio:
                return None
            raise ValueError(f"Informe {nome}.")
        try:
            numero = Decimal(str(valor).strip().replace(".", "").replace(",", ".") if isinstance(valor, str) and "," in valor else str(valor))
        except (InvalidOperation, ValueError):
            raise ValueError(f"Valor inválido para {nome}: {valor!r}.") from None
        if numero < ZERO:
            raise ValueError(f"{nome.capitalize()} não pode ser negativo.")
        return numero

    @staticmethod
    def _dinheiro(valor: Decimal) -> Decimal:
        return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)

    @classmethod
    def _operacao_compativel(cls, operacao: Any) -> bool:
        texto = cls._normalizar_texto(operacao)
        if not texto:
            return True
        bloqueios = ("EXPORT", "IMPORT", "TRANSFER", "REMESSA", "DEVOLU")
        return not any(chave in texto for chave in bloqueios)

    @classmethod
    def _aliquota_interestadual(
        cls,
        ncm: str,
        descricao: str,
        contexto: Dict[str, Any],
        origem: str,
        destino: str,
    ) -> Dict[str, Any]:
        if not origem or not destino or origem == destino:
            return {
                "aliquota": None,
                "status": "NÃO APLICÁVEL À OPERAÇÃO INTERNA",
                "confirmada": True,
                "confiabilidade": 100.0,
                "fundamento": "Operação sem circulação interestadual.",
            }

        resultado = ICMSMGNacionalService.analisar(
            ncm or "00000000",
            contexto={
                "uf_origem": origem,
                "uf_destino": destino,
                "mercadoria_importada": contexto.get("mercadoria_importada"),
                "excecao_aliquota_importacao": contexto.get("excecao_aliquota_importacao"),
            },
            descricao=descricao,
        )
        return {
            "aliquota": resultado.get("aliquota_nominal"),
            "status": str(resultado.get("aliquota_status") or ""),
            "confirmada": bool(resultado.get("aliquota_confirmada")),
            "confiabilidade": float(resultado.get("confiabilidade_aliquota") or 0.0),
            "fundamento": str(resultado.get("fundamento_aliquota") or ""),
        }

    @classmethod
    def _aliquota_interna(
        cls,
        ncm: str,
        descricao: str,
        contexto: Dict[str, Any],
        destino: str,
    ) -> Dict[str, Any]:
        manual = cls._decimal(contexto.get("aliquota_interna_destino"), "a alíquota interna")
        confirmar_manual = bool(cls._booleano(contexto.get("confirmar_aliquota_interna"), False))
        if manual is not None:
            return {
                "aliquota": float(manual),
                "status": (
                    "INFORMADA E CONFIRMADA PELO USUÁRIO"
                    if confirmar_manual
                    else "INFORMADA MANUALMENTE — REVISAR NA LEGISLAÇÃO DA UF DE DESTINO"
                ),
                "confirmada": confirmar_manual,
                "confiabilidade": 100.0 if confirmar_manual else 75.0,
                "fundamento": "Alíquota interna informada no contexto da operação.",
                "fonte": "Informação do usuário",
            }

        if destino == "MG":
            resultado = ICMSMGNacionalService.analisar(
                ncm or "00000000",
                contexto={"uf_origem": "MG", "uf_destino": "MG"},
                descricao=descricao,
            )
            return {
                "aliquota": resultado.get("aliquota_nominal"),
                "status": str(resultado.get("aliquota_status") or ""),
                "confirmada": bool(resultado.get("aliquota_confirmada")),
                "confiabilidade": float(resultado.get("confiabilidade_aliquota") or 0.0),
                "fundamento": str(resultado.get("fundamento_aliquota") or ""),
                "fonte": str(resultado.get("fonte_aliquota") or URL_RICMS_MG),
            }

        usar_motor_uf = bool(cls._booleano(contexto.get("usar_motor_icms_uf"), False))
        if usar_motor_uf and destino in UFS_COBERTURA and ncm:
            resultado_uf = ICMSUFService.analisar(
                ncm,
                contexto={
                    **contexto,
                    "uf_origem": destino,
                    "uf_destino": destino,
                },
                descricao=descricao,
            )
            aliquota_uf = resultado_uf.get("aliquota_interna_destino")
            if aliquota_uf is not None:
                return {
                    "aliquota": aliquota_uf,
                    "status": str(resultado_uf.get("aliquota_interna_status") or ""),
                    "confirmada": bool(resultado_uf.get("aliquota_interna_confirmada")),
                    "confiabilidade": float(resultado_uf.get("confiabilidade_aliquota") or 0.0),
                    "fundamento": str(resultado_uf.get("fundamento_aliquota") or ""),
                    "fonte": str(resultado_uf.get("fonte_aliquota") or ""),
                }

        usar_referencia = bool(cls._booleano(contexto.get("usar_tabela_referencia"), True))
        if destino and usar_referencia:
            aliquota = aliquota_interna_referencia(destino)
            return {
                "aliquota": float(aliquota),
                "status": "REFERÊNCIA OPERACIONAL LOCAL — CONFIRMAR NA UF DE DESTINO",
                "confirmada": False,
                "confiabilidade": 55.0,
                "fundamento": "Tabela operacional instalada; não substitui a legislação estadual vigente.",
                "fonte": FONTE_TABELA_DIFAL,
            }

        return {
            "aliquota": None,
            "status": "INFORME A ALÍQUOTA INTERNA DA UF DE DESTINO",
            "confirmada": False,
            "confiabilidade": 0.0,
            "fundamento": "",
            "fonte": "",
        }

    @classmethod
    def _calcular(
        cls,
        valor: Decimal,
        aliquota_interna: Decimal,
        aliquota_interestadual: Decimal,
        aliquota_fcp: Decimal,
        modalidade: str,
        valor_inclui_icms: bool,
    ) -> Dict[str, Decimal]:
        modalidade = cls._normalizar_texto(modalidade or "BASE UNICA POR DENTRO")
        if modalidade not in {
            "POR FORA",
            "BASE UNICA POR DENTRO",
            "BASE DUPLA POR DENTRO",
        }:
            raise ValueError("Modalidade de cálculo do DIFAL inválida.")

        ai = aliquota_interna / CEM
        ae = aliquota_interestadual / CEM
        if ai >= Decimal("1") or ae >= Decimal("1"):
            raise ValueError("As alíquotas informadas não permitem o cálculo por dentro.")

        if modalidade == "POR FORA":
            base_origem = valor
            base_destino = valor
        elif modalidade == "BASE UNICA POR DENTRO":
            base_destino = valor if valor_inclui_icms else valor / (Decimal("1") - ai)
            base_origem = base_destino
        else:
            if valor_inclui_icms:
                base_origem = valor
                valor_sem_icms_origem = valor - (valor * ae)
                base_destino = valor_sem_icms_origem / (Decimal("1") - ai)
            else:
                base_origem = valor / (Decimal("1") - ae)
                base_destino = valor / (Decimal("1") - ai)

        icms_origem = base_origem * ae
        icms_destino = base_destino * ai
        difal = max(ZERO, icms_destino - icms_origem)
        fcp = base_destino * (aliquota_fcp / CEM)
        return {
            "base_origem": cls._dinheiro(base_origem),
            "base_destino": cls._dinheiro(base_destino),
            "icms_origem": cls._dinheiro(icms_origem),
            "icms_destino": cls._dinheiro(icms_destino),
            "difal": cls._dinheiro(difal),
            "fcp": cls._dinheiro(fcp),
        }

    @classmethod
    def analisar(
        cls,
        ncm: Any = "",
        contexto: Optional[Dict[str, Any]] = None,
        descricao: str = "",
    ) -> Dict[str, Any]:
        contexto = dict(contexto or {})
        codigo = cls._normalizar_ncm(ncm)
        origem = cls._normalizar_uf(contexto.get("uf_origem"))
        destino = cls._normalizar_uf(contexto.get("uf_destino"))
        consumidor_final = bool(cls._booleano(contexto.get("consumidor_final"), False))
        destinatario_contribuinte = cls._booleano(
            contexto.get("destinatario_contribuinte", contexto.get("contribuinte")),
            None,
        )
        operacao_compativel = cls._operacao_compativel(contexto.get("operacao"))
        regime = cls._normalizar_texto(contexto.get("regime"))

        if not origem or not destino:
            return ResultadoDIFALFCP(
                ncm=codigo,
                uf_origem=origem,
                uf_destino=destino,
                status="CONTEXTO INCOMPLETO",
                aplicavel=False,
                confirmado=False,
                exige_revisao=True,
                motivo="Informe UF de origem e UF de destino.",
                consumidor_final=consumidor_final,
                destinatario_contribuinte=destinatario_contribuinte,
                confiabilidade=0.0,
                fundamento="Lei Complementar nº 87/1996, arts. 4º, 12 e 13.",
                fontes=f"{URL_LC_87} | {URL_PORTAL_DIFAL}",
            ).para_dict()

        if origem == destino:
            return ResultadoDIFALFCP(
                ncm=codigo,
                uf_origem=origem,
                uf_destino=destino,
                status="NÃO APLICÁVEL",
                aplicavel=False,
                confirmado=True,
                exige_revisao=False,
                motivo="Operação interna: não existe diferença entre alíquota interna e interestadual.",
                consumidor_final=consumidor_final,
                destinatario_contribuinte=destinatario_contribuinte,
                confiabilidade=100.0,
                fundamento="DIFAL pressupõe operação ou prestação interestadual.",
                fontes=f"{URL_LC_87} | {URL_LC_190}",
            ).para_dict()

        if not consumidor_final:
            return ResultadoDIFALFCP(
                ncm=codigo,
                uf_origem=origem,
                uf_destino=destino,
                status="NÃO APLICÁVEL AO CONTEXTO INFORMADO",
                aplicavel=False,
                confirmado=True,
                exige_revisao=False,
                motivo="O destinatário não foi informado como consumidor final.",
                consumidor_final=False,
                destinatario_contribuinte=destinatario_contribuinte,
                confiabilidade=100.0,
                fundamento="Lei Complementar nº 87/1996, art. 4º, § 2º.",
                fontes=f"{URL_LC_87} | {URL_LC_190}",
            ).para_dict()

        if not operacao_compativel:
            return ResultadoDIFALFCP(
                ncm=codigo,
                uf_origem=origem,
                uf_destino=destino,
                status="REVISÃO NECESSÁRIA",
                aplicavel=False,
                confirmado=False,
                exige_revisao=True,
                motivo="A operação informada não é uma venda/saída interestadual comum para consumidor final.",
                consumidor_final=True,
                destinatario_contribuinte=destinatario_contribuinte,
                confiabilidade=35.0,
                fundamento="A incidência depende da natureza jurídica da operação.",
                fontes=f"{URL_LC_87} | {URL_LC_190}",
            ).para_dict()

        interestadual = cls._aliquota_interestadual(codigo, descricao, contexto, origem, destino)
        interna = cls._aliquota_interna(codigo, descricao, contexto, destino)

        aliquota_interestadual = interestadual.get("aliquota")
        aliquota_interna = interna.get("aliquota")
        diferencial = None
        if aliquota_interestadual is not None and aliquota_interna is not None:
            diferencial = max(0.0, float(aliquota_interna) - float(aliquota_interestadual))

        if destinatario_contribuinte is True:
            responsavel = "DESTINATÁRIO — CONTRIBUINTE DO ICMS"
        elif destinatario_contribuinte is False:
            responsavel = "REMETENTE/PRESTADOR — DESTINATÁRIO NÃO CONTRIBUINTE"
        else:
            responsavel = "INFORMAR SE O DESTINATÁRIO É CONTRIBUINTE DO ICMS"

        fcp_informado = contexto.get("aliquota_fcp")
        fcp_manual = cls._decimal(fcp_informado, "a alíquota do FCP")
        confirmar_fcp = bool(cls._booleano(contexto.get("confirmar_fcp"), False))
        fcp_fonte = ""
        if fcp_manual is not None:
            fcp = fcp_manual
            fcp_status = (
                "NÃO INFORMADO / NÃO APLICÁVEL"
                if fcp == ZERO and not confirmar_fcp
                else (
                    "INFORMADO E CONFIRMADO PELO USUÁRIO"
                    if confirmar_fcp
                    else "INFORMADO — CONFIRMAR O ADICIONAL NA UF DE DESTINO"
                )
            )
        elif bool(cls._booleano(contexto.get("usar_motor_icms_uf"), False)) and destino in UFS_COBERTURA and codigo:
            resultado_uf = ICMSUFService.analisar(
                codigo,
                contexto={
                    **contexto,
                    "uf_origem": destino,
                    "uf_destino": destino,
                },
                descricao=descricao,
            )
            fcp = Decimal(str(resultado_uf.get("fcp") or 0))
            confirmar_fcp = bool(resultado_uf.get("fcp_confirmado"))
            fcp_status = str(resultado_uf.get("fcp_status") or "")
            fcp_fonte = str(resultado_uf.get("fonte_fcp") or "")
        else:
            fcp = ZERO
            confirmar_fcp = True
            fcp_status = "NÃO INFORMADO / NÃO APLICÁVEL"

        valor = cls._decimal(contexto.get("valor_operacao"), "o valor da operação")
        valor_inclui_icms = bool(cls._booleano(contexto.get("valor_inclui_icms"), True))
        modalidade = cls._normalizar_texto(contexto.get("modalidade_calculo") or "AUTO")
        if modalidade == "AUTO":
            modalidade = (
                "BASE DUPLA POR DENTRO"
                if destinatario_contribuinte is True
                else "BASE UNICA POR DENTRO"
            )

        memoria: Dict[str, Decimal] = {}
        if (
            valor is not None
            and aliquota_interna is not None
            and aliquota_interestadual is not None
        ):
            memoria = cls._calcular(
                valor=valor,
                aliquota_interna=Decimal(str(aliquota_interna)),
                aliquota_interestadual=Decimal(str(aliquota_interestadual)),
                aliquota_fcp=fcp,
                modalidade=modalidade,
                valor_inclui_icms=valor_inclui_icms,
            )

        confianca = min(
            float(interestadual.get("confiabilidade") or 0.0),
            float(interna.get("confiabilidade") or 0.0),
        )
        if destinatario_contribuinte is None:
            confianca = min(confianca, 45.0)
        if fcp > ZERO and not confirmar_fcp:
            confianca = min(confianca, 70.0)
        if regime in {"SIMPLES NACIONAL", "MEI"}:
            confianca = min(confianca, 50.0)

        confirmado = bool(
            destinatario_contribuinte is not None
            and interestadual.get("confirmada")
            and interna.get("confirmada")
            and (fcp == ZERO or confirmar_fcp)
            and regime not in {"SIMPLES NACIONAL", "MEI"}
        )
        exige_revisao = not confirmado

        observacoes = []
        if destinatario_contribuinte is None:
            observacoes.append("Informe a condição de contribuinte do destinatário para definir o responsável.")
        if not interna.get("confirmada"):
            observacoes.append("A alíquota interna da UF de destino ainda é condicional.")
        if not interestadual.get("confirmada"):
            observacoes.append("A alíquota interestadual exige conferência do conteúdo de importação ou de exceção legal.")
        if regime in {"SIMPLES NACIONAL", "MEI"}:
            observacoes.append("Operação de optante do Simples/MEI exige análise específica antes do recolhimento.")
        if fcp > ZERO and not confirmar_fcp:
            observacoes.append("O FCP informado não foi marcado como confirmado.")
        if valor is None:
            observacoes.append("Informe o valor da operação para gerar a memória de cálculo.")
        observacoes.append("Benefícios, reduções de base e regras especiais da UF de destino podem alterar o resultado.")

        status = "DIFAL CONFIRMADO" if confirmado else "DIFAL APLICÁVEL — REVISAR PREMISSAS"
        fundamento = (
            "Lei Complementar nº 87/1996, art. 4º, § 2º; art. 13, incisos IX e X, "
            "§§ 3º, 6º e 7º, com redação da Lei Complementar nº 190/2022."
        )
        fontes = f"{URL_LC_87} | {URL_LC_190} | {URL_PORTAL_DIFAL}"
        if destino == "MG":
            fontes += f" | {URL_RICMS_MG}"
        elif fcp_fonte:
            fontes += f" | {fcp_fonte}"

        return ResultadoDIFALFCP(
            ncm=codigo,
            uf_origem=origem,
            uf_destino=destino,
            status=status,
            aplicavel=True,
            confirmado=confirmado,
            exige_revisao=exige_revisao,
            motivo="Operação interestadual destinada a consumidor final.",
            responsavel=responsavel,
            destinatario_contribuinte=destinatario_contribuinte,
            consumidor_final=True,
            aliquota_interestadual=float(aliquota_interestadual) if aliquota_interestadual is not None else None,
            aliquota_interestadual_status=str(interestadual.get("status") or ""),
            aliquota_interestadual_confirmada=bool(interestadual.get("confirmada")),
            aliquota_interna_destino=float(aliquota_interna) if aliquota_interna is not None else None,
            aliquota_interna_status=str(interna.get("status") or ""),
            aliquota_interna_confirmada=bool(interna.get("confirmada")),
            diferencial_percentual=diferencial,
            aliquota_fcp=float(fcp),
            fcp_status=fcp_status,
            fcp_confirmado=(fcp == ZERO or confirmar_fcp),
            valor_operacao=float(valor) if valor is not None else None,
            valor_inclui_icms=valor_inclui_icms,
            modalidade_calculo=modalidade,
            base_origem=float(memoria["base_origem"]) if memoria else None,
            base_destino=float(memoria["base_destino"]) if memoria else None,
            valor_icms_origem=float(memoria["icms_origem"]) if memoria else None,
            valor_icms_destino=float(memoria["icms_destino"]) if memoria else None,
            valor_difal=float(memoria["difal"]) if memoria else None,
            valor_fcp=float(memoria["fcp"]) if memoria else None,
            confiabilidade=confianca,
            fundamento=fundamento,
            fontes=fontes,
            observacao=" ".join(observacoes),
        ).para_dict()


__all__ = ["DIFALFCPNacionalService", "ResultadoDIFALFCP"]
