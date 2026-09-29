"""Robô Tributário Inteligente — Sprint 17.5.2.

A camada reúne os motores tributários já aprovados pelo FiscalPro, preserva a
integração ICMS próprio × ICMS-ST do Hotfix 17.5.1 e acrescenta uma decisão
operacional conservadora com CFOP provável, CSTs e DIFAL/FCP.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from src.inteligencia.consulta_tributaria import ConsultaTributaria
from src.inteligencia.motor_tributario import MotorTributario
from src.services.empresas_regimes_service import EmpresasRegimesService
from src.services.decisao_operacao_tributaria_service import (
    DecisaoOperacaoTributaria,
    DecisaoOperacaoTributariaService,
    FONTE_CFOP,
)


FUNDAMENTO_SAIDA_ST_RETIDA = (
    "RICMS/MG/2023, Anexo VII, Parte 1, art. 27 — mercadoria recebida com ICMS-ST "
    "retido: saída sem destaque do imposto, CST 060 ou CSOSN 500."
)


@dataclass(frozen=True, slots=True)
class DiagnosticoRoboTributario:
    tributo: str
    status: str
    confiabilidade: float
    resumo: str
    fundamento: str = ""


@dataclass(slots=True)
class ResultadoRoboTributario:
    consulta: ConsultaTributaria
    ficha: object | None
    status: str
    confiabilidade: float
    diagnosticos: list[DiagnosticoRoboTributario] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)
    decisao_operacao: DecisaoOperacaoTributaria | None = None
    relatorio: str = ""

    @property
    def exige_revisao(self) -> bool:
        return self.status != "CONSISTENTE"


class RoboTributarioService:
    """Analisa uma operação usando somente regras e bases já instaladas."""

    STATUS_CONFIRMADO = "CONFIRMADO"
    STATUS_REVISAR = "REVISAR"
    STATUS_PENDENTE = "PENDENTE"
    STATUS_INFORMATIVO = "INFORMATIVO"

    ST_NAO_INFORMADO = "NAO INFORMADO"
    ST_RETIDO_ENTRADA = "ICMS-ST JA RETIDO NA ENTRADA"
    ST_RETER_SAIDA = "RESPONSAVEL POR RETER ICMS-ST NESTA SAIDA"
    ST_SEM_RETENCAO = "MERCADORIA SEM RETENCAO DE ICMS-ST"

    @classmethod
    def analisar(cls, consulta: ConsultaTributaria) -> ResultadoRoboTributario:
        cls._aplicar_empresa_regime(consulta)
        cls._validar_consulta(consulta)
        ficha = MotorTributario().consultar(consulta)
        return cls.avaliar_ficha(consulta, ficha)

    @staticmethod
    def _aplicar_empresa_regime(consulta: ConsultaTributaria) -> None:
        empresa = str(getattr(consulta, "empresa", "") or "").strip()
        regime = str(getattr(consulta, "regime", "") or "").strip()
        resolvido = EmpresasRegimesService.resolver_regime(empresa, regime)
        if resolvido:
            consulta.regime = resolvido

    @classmethod
    def avaliar_ficha(
        cls,
        consulta: ConsultaTributaria,
        ficha: object | None,
    ) -> ResultadoRoboTributario:
        cls._aplicar_empresa_regime(consulta)
        cls._validar_consulta(consulta)

        alertas: list[str] = []
        if not str(getattr(consulta, "descricao_produto", "") or "").strip():
            alertas.append(
                "Descrição do produto não informada. Alguns enquadramentos por NCM/CEST "
                "podem exigir conferência manual da descrição legal."
            )

        if ficha is None:
            alertas.append(
                "NCM/tributação não encontrados em base validada. Atualize as fontes oficiais "
                "ou faça a revisão fiscal antes de utilizar a operação."
            )
            resultado = ResultadoRoboTributario(
                consulta=consulta,
                ficha=None,
                status="PENDENTE",
                confiabilidade=0.0,
                diagnosticos=[],
                alertas=alertas,
            )
            resultado.relatorio = cls._montar_relatorio(resultado)
            return resultado

        decisao = DecisaoOperacaoTributariaService.analisar(consulta, ficha)
        diagnosticos = [
            cls._diagnostico_piscofins(ficha),
            cls._diagnostico_icms(consulta, ficha),
            cls._diagnostico_st(consulta, ficha),
            cls._diagnostico_difal(decisao),
            cls._diagnostico_ipi(ficha),
            cls._diagnostico_reforma(ficha),
        ]

        if bool(getattr(ficha, "piscofins_divergencia", False)):
            alertas.append(
                "Divergência entre a regra nacional de PIS/COFINS e a tributação já cadastrada. "
                "O FiscalPro preservou o cadastro existente para revisão humana."
            )

        variacoes = int(getattr(ficha, "quantidade_variacoes", 0) or 0)
        if variacoes > 1:
            alertas.append(
                f"Existem {variacoes} perfis tributários diferentes para este NCM na base operacional. "
                "Confirme descrição, operação, regime e CEST."
            )

        cls._adicionar_alertas_integracao_st(consulta, ficha, alertas)
        alertas.extend(decisao.alertas)

        status = cls._status_geral(diagnosticos)
        if decisao.status == cls.STATUS_PENDENTE:
            status = "PENDENTE"
        elif decisao.status == cls.STATUS_REVISAR and status != "PENDENTE":
            status = "REVISAR"

        confiabilidade = cls._confiabilidade_geral(diagnosticos)
        if decisao.confiabilidade > 0:
            confiabilidade = min(confiabilidade, decisao.confiabilidade) if confiabilidade > 0 else decisao.confiabilidade

        resultado = ResultadoRoboTributario(
            consulta=consulta,
            ficha=ficha,
            status=status,
            confiabilidade=confiabilidade,
            diagnosticos=diagnosticos,
            alertas=alertas,
            decisao_operacao=decisao,
        )
        resultado.relatorio = cls._montar_relatorio(resultado)
        return resultado

    @staticmethod
    def _validar_consulta(consulta: ConsultaTributaria) -> None:
        ncm = "".join(c for c in str(getattr(consulta, "ncm", "") or "") if c.isdigit())
        if len(ncm) != 8:
            raise ValueError("Informe um NCM com 8 dígitos.")

        origem = str(getattr(consulta, "uf_origem", "") or "").strip().upper()
        destino = str(getattr(consulta, "uf_destino", "") or "").strip().upper()
        if len(origem) != 2 or len(destino) != 2:
            raise ValueError("Informe UF de origem e destino com 2 caracteres.")
        if not str(getattr(consulta, "regime", "") or "").strip():
            raise ValueError("Informe o regime tributário.")
        if not str(getattr(consulta, "operacao", "") or "").strip():
            raise ValueError("Informe o tipo de operação.")

    @staticmethod
    def _normalizar_texto(valor: object) -> str:
        texto = str(valor or "").strip().upper()
        texto = "".join(
            c for c in unicodedata.normalize("NFD", texto)
            if unicodedata.category(c) != "Mn"
        )
        return " ".join(texto.split())

    @classmethod
    def _situacao_st(cls, consulta: ConsultaTributaria) -> str:
        valor = cls._normalizar_texto(getattr(consulta, "situacao_icms_st", ""))
        return valor or cls.ST_NAO_INFORMADO

    @classmethod
    def _eh_venda_interna_mg(cls, consulta: ConsultaTributaria) -> bool:
        origem = cls._normalizar_texto(getattr(consulta, "uf_origem", ""))
        destino = cls._normalizar_texto(getattr(consulta, "uf_destino", ""))
        operacao = cls._normalizar_texto(getattr(consulta, "operacao", ""))
        return origem == "MG" and destino == "MG" and operacao in {"VENDA", "REVENDA"}

    @classmethod
    def _codigo_saida_st_retida(cls, consulta: ConsultaTributaria) -> str:
        regime = cls._normalizar_texto(getattr(consulta, "regime", ""))
        return "CSOSN 500" if "SIMPLES" in regime else "CST 060"

    @classmethod
    def _adicionar_alertas_integracao_st(
        cls,
        consulta: ConsultaTributaria,
        ficha: object,
        alertas: list[str],
    ) -> None:
        if not bool(getattr(ficha, "icms_mg_st_confirmado", False)):
            return
        if not cls._eh_venda_interna_mg(consulta):
            return

        situacao = cls._situacao_st(consulta)
        if situacao == cls.ST_NAO_INFORMADO:
            alertas.append(
                "O produto está enquadrado no ICMS-ST/MG, mas a situação da retenção não foi informada. "
                "Indique se o ICMS-ST já foi retido na entrada ou se a empresa é responsável por reter nesta saída."
            )
        elif situacao == cls.ST_SEM_RETENCAO:
            alertas.append(
                "O produto foi confirmado na tabela de ICMS-ST/MG, porém a operação foi marcada como sem retenção. "
                "Confirme a exceção legal antes da emissão/escrituração."
            )

    @classmethod
    def _diagnostico_piscofins(cls, ficha: object) -> DiagnosticoRoboTributario:
        status_motor = str(getattr(ficha, "piscofins_status", "") or "").strip()
        confirmado = bool(getattr(ficha, "piscofins_confirmado", False))
        revisao = bool(getattr(ficha, "piscofins_exige_revisao", True))
        divergencia = bool(getattr(ficha, "piscofins_divergencia", False))
        confianca = float(getattr(ficha, "piscofins_confiabilidade", 0.0) or 0.0)

        if divergencia:
            status = cls.STATUS_REVISAR
        elif confirmado and not revisao:
            status = cls.STATUS_CONFIRMADO
        elif status_motor:
            status = cls.STATUS_REVISAR
        else:
            status = cls.STATUS_PENDENTE

        cst_pis = str(getattr(ficha, "pis_cst", "") or "").strip()
        cst_cofins = str(getattr(ficha, "cofins_cst", "") or "").strip()
        aliq_pis = float(getattr(ficha, "aliquota_pis", 0.0) or 0.0)
        aliq_cofins = float(getattr(ficha, "aliquota_cofins", 0.0) or 0.0)
        origem_valores = "confirmado/local"
        if not cst_pis and not cst_cofins:
            sug_pis = str(getattr(ficha, "piscofins_sugestao_cst_pis", "") or "").strip()
            sug_cofins = str(getattr(ficha, "piscofins_sugestao_cst_cofins", "") or "").strip()
            if sug_pis or sug_cofins:
                cst_pis = sug_pis
                cst_cofins = sug_cofins
                aliq_pis = float(getattr(ficha, "piscofins_sugestao_aliquota_pis", 0.0) or 0.0)
                aliq_cofins = float(getattr(ficha, "piscofins_sugestao_aliquota_cofins", 0.0) or 0.0)
                origem_valores = "sugestão condicional"
        resumo = (
            f"{status_motor or 'Sem conclusão do motor'} | "
            f"PIS CST {cst_pis or '-'} {aliq_pis:.2f}% | "
            f"COFINS CST {cst_cofins or '-'} {aliq_cofins:.2f}% | {origem_valores}"
        )
        fundamento = str(getattr(ficha, "piscofins_fundamento", "") or "")
        return DiagnosticoRoboTributario("PIS/COFINS", status, confianca, resumo, fundamento)

    @classmethod
    def _diagnostico_icms(
        cls,
        consulta: ConsultaTributaria,
        ficha: object,
    ) -> DiagnosticoRoboTributario:
        status_motor = str(getattr(ficha, "icms_mg_aliquota_status", "") or "").strip()
        confirmado = bool(getattr(ficha, "icms_mg_confirmado", False))
        confianca = float(getattr(ficha, "icms_mg_confiabilidade", 0.0) or 0.0)
        aliquota = float(
            getattr(ficha, "icms_mg_aliquota_nominal", 0.0)
            or getattr(ficha, "icms", 0.0)
            or 0.0
        )
        st_confirmado = bool(getattr(ficha, "icms_mg_st_confirmado", False))
        situacao = cls._situacao_st(consulta)

        # Integração principal do Hotfix 17.5.1: em venda interna mineira de
        # mercadoria já recebida com ST retido, a alíquota nominal não deve ser
        # apresentada como débito da saída subsequente.
        if st_confirmado and cls._eh_venda_interna_mg(consulta):
            if situacao == cls.ST_RETIDO_ENTRADA:
                codigo = cls._codigo_saida_st_retida(consulta)
                resumo = (
                    "SAÍDA SUBSEQUENTE COM ICMS-ST JÁ RETIDO — sem destaque do ICMS | "
                    f"{codigo} | alíquota nominal não aplicada como débito nesta saída"
                )
                return DiagnosticoRoboTributario(
                    "ICMS",
                    cls.STATUS_CONFIRMADO,
                    100.0,
                    resumo,
                    FUNDAMENTO_SAIDA_ST_RETIDA,
                )

            if situacao == cls.ST_NAO_INFORMADO:
                resumo = (
                    "PRODUTO SUJEITO A ICMS-ST — informe a situação da retenção antes de concluir o ICMS da saída | "
                    f"alíquota nominal de referência: {aliquota:.2f}%"
                )
                return DiagnosticoRoboTributario(
                    "ICMS", cls.STATUS_REVISAR, min(confianca or 70.0, 70.0), resumo,
                    "A definição entre operação própria e saída subsequente depende da responsabilidade pela ST."
                )

            if situacao == cls.ST_SEM_RETENCAO:
                resumo = (
                    "PRODUTO ENQUADRADO EM ICMS-ST, MAS OPERAÇÃO MARCADA SEM RETENÇÃO — "
                    "confirmar exceção/dispensa antes de destacar ICMS"
                )
                return DiagnosticoRoboTributario(
                    "ICMS", cls.STATUS_REVISAR, 50.0, resumo,
                    "O enquadramento do produto em ST foi confirmado; a não retenção exige fundamento específico."
                )

            # Quando o usuário informa que é o responsável pela retenção nesta
            # saída, o ICMS próprio continua sendo analisado pela regra nominal.

        if confirmado:
            status = cls.STATUS_CONFIRMADO
        elif status_motor:
            status = cls.STATUS_REVISAR
        else:
            status = cls.STATUS_PENDENTE

        resumo = f"{status_motor or 'Sem conclusão do motor'} | Alíquota: {aliquota:.2f}%"
        if st_confirmado and situacao == cls.ST_RETER_SAIDA:
            resumo += " | ICMS-ST informado para retenção nesta saída"
        beneficio = str(getattr(ficha, "icms_mg_beneficio_status", "") or "").strip()
        if beneficio:
            resumo += f" | Benefício: {beneficio}"
        fundamento = str(getattr(ficha, "icms_mg_fundamento", "") or "")
        return DiagnosticoRoboTributario("ICMS", status, confianca, resumo, fundamento)

    @classmethod
    def _diagnostico_st(
        cls,
        consulta: ConsultaTributaria,
        ficha: object,
    ) -> DiagnosticoRoboTributario:
        status_motor = str(getattr(ficha, "icms_mg_st_status", "") or "").strip()
        confirmado = bool(getattr(ficha, "icms_mg_st_confirmado", False))
        status_upper = cls._normalizar_texto(status_motor)
        situacao = cls._situacao_st(consulta)
        cest = str(getattr(ficha, "icms_mg_cest", "") or getattr(ficha, "cest", "") or "-")
        mva = float(getattr(ficha, "icms_mg_mva", 0.0) or 0.0)

        if confirmado and cls._eh_venda_interna_mg(consulta):
            if situacao == cls.ST_RETIDO_ENTRADA:
                resumo = (
                    f"PRODUTO SUJEITO AO ICMS-ST | CEST: {cest} | MVA: {mva:.2f}% | "
                    "nesta saída: imposto já retido anteriormente; não há nova retenção"
                )
                return DiagnosticoRoboTributario(
                    "ICMS-ST", cls.STATUS_CONFIRMADO, 100.0, resumo,
                    FUNDAMENTO_SAIDA_ST_RETIDA,
                )
            if situacao == cls.ST_RETER_SAIDA:
                resumo = (
                    f"PRODUTO SUJEITO AO ICMS-ST | CEST: {cest} | MVA original: {mva:.2f}% | "
                    "responsabilidade de retenção informada para esta saída; valor do ST não é calculado por este parecer"
                )
                return DiagnosticoRoboTributario(
                    "ICMS-ST", cls.STATUS_CONFIRMADO, 100.0, resumo,
                    "Enquadramento confirmado pelo Anexo VII; cálculo da retenção depende dos valores da operação."
                )
            if situacao == cls.ST_SEM_RETENCAO:
                resumo = (
                    f"PRODUTO SUJEITO AO ICMS-ST | CEST: {cest} | MVA: {mva:.2f}% | "
                    "operação marcada sem retenção: revisar exceção/dispensa"
                )
                return DiagnosticoRoboTributario(
                    "ICMS-ST", cls.STATUS_REVISAR, 50.0, resumo,
                    "O produto está enquadrado na ST; a ausência de retenção não é presumida automaticamente."
                )

            resumo = (
                f"PRODUTO SUJEITO AO ICMS-ST | CEST: {cest} | MVA: {mva:.2f}% | "
                "responsabilidade pela retenção ainda não informada"
            )
            return DiagnosticoRoboTributario(
                "ICMS-ST", cls.STATUS_REVISAR, 70.0, resumo,
                "Informe se o imposto já foi retido na entrada ou se deverá ser retido nesta saída."
            )

        if confirmado or status_upper.startswith("NAO APLICAVEL"):
            status = cls.STATUS_CONFIRMADO
            confianca = 100.0 if confirmado else 85.0
        elif "NAO LOCALIZADO" in status_upper or not status_motor:
            status = cls.STATUS_PENDENTE
            confianca = 0.0
        else:
            status = cls.STATUS_REVISAR
            confianca = 70.0

        resumo = f"{status_motor or 'ST não confirmada'} | CEST: {cest} | MVA: {mva:.2f}%"
        return DiagnosticoRoboTributario("ICMS-ST", status, confianca, resumo, "")

    @classmethod
    def _diagnostico_difal(
        cls,
        decisao: DecisaoOperacaoTributaria,
    ) -> DiagnosticoRoboTributario:
        componente = decisao.difal
        resultado = decisao.difal_resultado or {}
        fundamento = str(resultado.get("fundamento") or "")
        if resultado.get("responsavel"):
            fundamento = (fundamento + " | Responsável: " + str(resultado.get("responsavel"))).strip(" |")
        return DiagnosticoRoboTributario(
            "DIFAL/FCP",
            componente.status,
            componente.confiabilidade,
            f"{componente.valor} | {componente.motivo}",
            fundamento,
        )

    @classmethod
    def _diagnostico_ipi(cls, ficha: object) -> DiagnosticoRoboTributario:
        ipi = float(getattr(ficha, "ipi", 0.0) or 0.0)
        cst = str(getattr(ficha, "cst_ipi", "") or "-")
        fontes = " | ".join(str(x) for x in (getattr(ficha, "fontes", []) or []) if x)
        resumo = f"IPI da base: {ipi:.2f}% | CST: {cst}. Conferir EX TIPI quando aplicável."
        return DiagnosticoRoboTributario("IPI", cls.STATUS_INFORMATIVO, 0.0, resumo, fontes)

    @classmethod
    def _diagnostico_reforma(cls, ficha: object) -> DiagnosticoRoboTributario:
        status_motor = str(getattr(ficha, "reforma_status", "") or "").strip()
        if status_motor == "CADASTRO ESPECÍFICO":
            status = cls.STATUS_CONFIRMADO
            confianca = 90.0
        elif status_motor:
            status = cls.STATUS_REVISAR
            confianca = 50.0
        else:
            status = cls.STATUS_PENDENTE
            confianca = 0.0

        ibs = float(getattr(ficha, "aliquota_ibs", 0.0) or 0.0)
        cbs = float(getattr(ficha, "aliquota_cbs", 0.0) or 0.0)
        resumo = (
            f"{status_motor or 'Sem enquadramento específico'} | "
            f"CST IBS {getattr(ficha, 'cst_ibs', '') or '-'} | "
            f"CST CBS {getattr(ficha, 'cst_cbs', '') or '-'} | IBS {ibs:.2f}% | CBS {cbs:.2f}%"
        )
        fundamento = str(getattr(ficha, "reforma_observacoes", "") or "")
        return DiagnosticoRoboTributario("Reforma 2026", status, confianca, resumo, fundamento)

    @classmethod
    def _status_geral(cls, diagnosticos: Iterable[DiagnosticoRoboTributario]) -> str:
        decisivos = [d for d in diagnosticos if d.status != cls.STATUS_INFORMATIVO]
        if any(d.status == cls.STATUS_PENDENTE for d in decisivos):
            return "PENDENTE"
        if any(d.status == cls.STATUS_REVISAR for d in decisivos):
            return "REVISAR"
        return "CONSISTENTE"

    @classmethod
    def _confiabilidade_geral(cls, diagnosticos: Iterable[DiagnosticoRoboTributario]) -> float:
        valores = [
            float(d.confiabilidade)
            for d in diagnosticos
            if d.status != cls.STATUS_INFORMATIVO and float(d.confiabilidade) > 0
        ]
        if not valores:
            return 0.0
        # Conservador: a segurança global não pode ser maior que o elo decisivo mais fraco.
        return min(valores)

    @classmethod
    def _texto_destinatario_contribuinte(cls, consulta: ConsultaTributaria) -> str:
        valor = getattr(consulta, "destinatario_contribuinte", None)
        if valor is True:
            return "SIM"
        if valor is False:
            return "NÃO"
        return "NÃO INFORMADO"

    @classmethod
    def _montar_relatorio(cls, resultado: ResultadoRoboTributario) -> str:
        c = resultado.consulta
        ficha = resultado.ficha
        linhas = [
            "FISCALPRO — ROBÔ TRIBUTÁRIO INTELIGENTE",
            "=" * 72,
            f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            f"Status geral: {resultado.status}",
            f"Segurança conservadora: {resultado.confiabilidade:.0f}%",
            "",
            "CONTEXTO DA OPERAÇÃO",
            "-" * 72,
            f"NCM: {''.join(ch for ch in str(c.ncm) if ch.isdigit())}",
            f"Descrição informada: {getattr(c, 'descricao_produto', '') or '-'}",
            f"Empresa: {getattr(c, 'empresa', '') or '-'}",
            f"UF origem → destino: {c.uf_origem.upper()} → {c.uf_destino.upper()}",
            f"Regime: {c.regime}",
            f"Operação: {c.operacao}",
            f"Finalidade: {getattr(c, 'finalidade', '') or '-'}",
            f"Perfil remetente: {getattr(c, 'perfil_remetente', '') or '-'}",
            f"Situação ICMS-ST: {getattr(c, 'situacao_icms_st', '') or 'Não informado'}",
            f"Destinatário contribuinte ICMS: {cls._texto_destinatario_contribuinte(c)}",
            f"Consumidor final: {'SIM' if bool(getattr(c, 'consumidor_final', False)) else 'NÃO'}",
            f"Mercadoria importada: {'SIM' if bool(getattr(c, 'mercadoria_importada', False)) else 'NÃO'}",
            f"Exceção à alíquota interestadual de 4%: {'SIM' if bool(getattr(c, 'excecao_aliquota_importacao', False)) else 'NÃO'}",
        ]

        if ficha is not None:
            linhas += [
                f"Descrição da base: {getattr(ficha, 'descricao', '') or '-'}",
                f"CEST: {getattr(ficha, 'cest', '') or '-'}",
                f"Origem da ficha: {getattr(ficha, 'status', '') or '-'}",
            ]

        decisao = resultado.decisao_operacao
        if decisao is not None:
            linhas += [
                "",
                "DECISÃO DA OPERAÇÃO — SPRINT 17.5.2",
                "-" * 72,
                f"Status da decisão: {decisao.status} | segurança {decisao.confiabilidade:.0f}%",
                f"CFOP provável: {decisao.cfop.valor or '-'} [{decisao.cfop.status}]",
                f"  {decisao.cfop.motivo}",
                f"ICMS: {decisao.icms.valor or '-'} [{decisao.icms.status}]",
                f"Destaque do ICMS: {decisao.destaque_icms.valor or '-'} [{decisao.destaque_icms.status}]",
                f"ICMS-ST na operação: {decisao.icms_st.valor or '-'} [{decisao.icms_st.status}]",
                f"PIS: {decisao.pis.valor or '-'} [{decisao.pis.status}]",
                f"COFINS: {decisao.cofins.valor or '-'} [{decisao.cofins.status}]",
                f"DIFAL/FCP: {decisao.difal.valor or '-'} [{decisao.difal.status}]",
                f"Fonte CFOP: {FONTE_CFOP}",
            ]

        linhas += ["", "DIAGNÓSTICO POR TRIBUTO", "-" * 72]
        if not resultado.diagnosticos:
            linhas.append("Nenhum diagnóstico tributário pôde ser confirmado.")
        for diagnostico in resultado.diagnosticos:
            linhas.append(
                f"[{diagnostico.status}] {diagnostico.tributo} — "
                f"segurança {diagnostico.confiabilidade:.0f}%"
            )
            linhas.append(f"  {diagnostico.resumo}")
            if diagnostico.fundamento:
                linhas.append(f"  Base/fundamento: {diagnostico.fundamento}")

        linhas += ["", "ALERTAS", "-" * 72]
        if resultado.alertas:
            for alerta in resultado.alertas:
                linhas.append(f"• {alerta}")
        else:
            linhas.append("Nenhum alerta adicional criado pelo robô.")

        fontes = []
        if ficha is not None:
            fontes.extend(str(x) for x in (getattr(ficha, "fontes", []) or []) if x)
            fontes.extend(str(x) for x in (getattr(ficha, "base_legal", []) or []) if x)
        if fontes:
            linhas += ["", "FONTES / BASE LEGAL REGISTRADAS", "-" * 72]
            for fonte in dict.fromkeys(fontes):
                linhas.append(f"• {fonte}")

        linhas += [
            "",
            "SEGURANÇA DA SPRINT 17.5.2",
            "-" * 72,
            "O Robô Tributário é assistivo e não aplica correções automaticamente.",
            "A decisão operacional é recomendação conservadora; CFOP/CST só são confirmados quando o contexto é suficiente.",
            "Produto sujeito à ST não significa, sozinho, que haverá nova retenção nesta saída.",
            "DIFAL interestadual com ICMS-ST permanece em revisão conjunta antes do recolhimento.",
            "Resultado PENDENTE ou REVISAR deve ser conferido antes da escrituração/emissão.",
            "O FiscalPro não trata ausência de informação na base como ausência de tributação.",
            "Base preservada: SEGURANÇA DO HOTFIX 17.5.1.",
        ]
        return "\n".join(linhas)
