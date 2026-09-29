"""Configurador tributário de venda para o Olist — base cumulativa 17.8.54.

Esta camada não cria uma nova regra fiscal. Ela organiza, em uma única resposta,
os motores já existentes do FiscalPro para responder à pergunta operacional:
"como esta venda deve ser configurada no Olist?".

A análise cruza produto/NCM, empresa/regime, origem/destino, condição do
destinatário, ICMS-ST, DIFAL/FCP, PIS/COFINS e referência de IPI. O resultado
separa campos confirmados de pontos que ainda exigem revisão antes da emissão.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from src.inteligencia.consulta_tributaria import ConsultaTributaria
from src.services.difal_fcp_nacional_service import DIFALFCPNacionalService
from src.services.empresas_regimes_service import EmpresasRegimesService
from src.services.icms_uf_service import ICMSUFService
from src.services.robo_tributario_service import ResultadoRoboTributario, RoboTributarioService


@dataclass(frozen=True, slots=True)
class CampoConfiguracaoOlist:
    grupo: str
    campo: str
    valor: str
    status: str
    observacao: str = ""


@dataclass(slots=True)
class ResultadoConfiguradorOlist:
    consulta: ConsultaTributaria
    robo: ResultadoRoboTributario
    icms_uf: dict[str, Any]
    difal: dict[str, Any]
    campos_olist: list[CampoConfiguracaoOlist] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)
    status: str = "REVISAR"
    confiabilidade: float = 0.0
    relatorio: str = ""

    @property
    def pronto_para_configurar(self) -> bool:
        return self.status == "CONFIRMADO"


class ConfiguradorOlistService:
    """Consolida os motores tributários e traduz o resultado para o Olist."""

    STATUS_CONFIRMADO = "CONFIRMADO"
    STATUS_REVISAR = "REVISAR"
    STATUS_PENDENTE = "PENDENTE"

    @staticmethod
    def _texto(valor: Any, padrao: str = "-") -> str:
        texto = str(valor or "").strip()
        return texto or padrao

    @staticmethod
    def _percentual(valor: Any) -> str:
        if valor is None or valor == "":
            return "-"
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return str(valor)
        return f"{numero:.2f}%".replace(".", ",")

    @staticmethod
    def _moeda(valor: Any) -> str:
        if valor is None or valor == "":
            return "-"
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return str(valor)
        texto = f"{numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {texto}"

    @staticmethod
    def _destinatario_texto(valor: bool | None) -> str:
        if valor is True:
            return "Contribuinte do ICMS"
        if valor is False:
            return "Não contribuinte do ICMS"
        return "Não informado"

    @staticmethod
    def _natureza_sugerida(cfop: str) -> str:
        codigo = "".join(c for c in str(cfop or "") if c.isdigit())
        mapa = {
            "5101": "Venda de produção do estabelecimento",
            "6101": "Venda interestadual de produção do estabelecimento",
            "5102": "Venda de mercadoria adquirida ou recebida de terceiros",
            "6102": "Venda interestadual de mercadoria adquirida ou recebida de terceiros",
            "5401": "Venda de produção do estabelecimento com ICMS-ST",
            "6401": "Venda interestadual de produção do estabelecimento com ICMS-ST",
            "5403": "Venda de mercadoria adquirida de terceiros com ICMS-ST — substituto",
            "6403": "Venda interestadual de mercadoria adquirida de terceiros com ICMS-ST — substituto",
            "5405": "Venda de mercadoria adquirida de terceiros com ICMS-ST já retido",
            "6404": "Venda interestadual de mercadoria com ICMS-ST já retido anteriormente",
        }
        return mapa.get(codigo, "Revisar a natureza conforme o CFOP da operação")

    @classmethod
    def _status_campo(cls, confirmado: bool, pendente: bool = False) -> str:
        if pendente:
            return cls.STATUS_PENDENTE
        return cls.STATUS_CONFIRMADO if confirmado else cls.STATUS_REVISAR

    @classmethod
    def analisar(
        cls,
        *,
        ncm: str,
        descricao_produto: str,
        empresa: str,
        regime: str,
        uf_origem: str,
        uf_destino: str,
        destinatario_contribuinte: bool | None,
        consumidor_final: bool = True,
        valor_operacao: Any = None,
        perfil_remetente: str = "Comerciante",
        situacao_icms_st: str = "Não informado",
        mercadoria_importada: bool = False,
        excecao_aliquota_importacao: bool = False,
        finalidade: str = "Revenda",
        operacao: str = "Venda",
        data_operacao: str = "",
        contrato_fidelidade: bool = False,
    ) -> ResultadoConfiguradorOlist:
        codigo = "".join(c for c in str(ncm or "") if c.isdigit())
        if len(codigo) != 8:
            raise ValueError("Informe ou selecione um NCM com 8 dígitos para o produto.")

        empresa = str(empresa or "").strip()
        regime_resolvido = EmpresasRegimesService.resolver_regime(empresa, regime)
        if not regime_resolvido:
            raise ValueError("Informe o regime tributário da empresa.")

        consulta = ConsultaTributaria(
            ncm=codigo,
            descricao_produto=str(descricao_produto or "").strip(),
            empresa=empresa,
            regime=regime_resolvido,
            uf_origem=str(uf_origem or "").strip().upper(),
            uf_destino=str(uf_destino or "").strip().upper(),
            operacao=operacao,
            finalidade=finalidade,
            perfil_remetente=perfil_remetente,
            situacao_icms_st=situacao_icms_st,
            destinatario_contribuinte=destinatario_contribuinte,
            consumidor_final=bool(consumidor_final),
            mercadoria_importada=bool(mercadoria_importada),
            excecao_aliquota_importacao=bool(excecao_aliquota_importacao),
            data_operacao=str(data_operacao or "").strip(),
        )

        robo = RoboTributarioService.analisar(consulta)

        contexto_icms = {
            "uf_origem": consulta.uf_origem,
            "uf_destino": consulta.uf_destino,
            "regime": consulta.regime,
            "operacao": consulta.operacao,
            "finalidade": consulta.finalidade,
            "consumidor_final": consulta.consumidor_final,
            "mercadoria_importada": consulta.mercadoria_importada,
            "excecao_aliquota_importacao": consulta.excecao_aliquota_importacao,
            "data_operacao": consulta.data_operacao,
            "perfil_remetente": consulta.perfil_remetente,
            "contrato_fidelidade": bool(contrato_fidelidade),
        }
        icms_uf = ICMSUFService.analisar(
            codigo,
            contexto=contexto_icms,
            descricao=consulta.descricao_produto,
        )

        contexto_difal = {
            **contexto_icms,
            "destinatario_contribuinte": destinatario_contribuinte,
            "usar_motor_icms_uf": True,
            "valor_operacao": valor_operacao,
            "valor_inclui_icms": True,
            "modalidade_calculo": "AUTO",
        }
        difal = DIFALFCPNacionalService.analisar(
            codigo,
            contexto=contexto_difal,
            descricao=consulta.descricao_produto,
        )

        resultado = ResultadoConfiguradorOlist(
            consulta=consulta,
            robo=robo,
            icms_uf=icms_uf,
            difal=difal,
        )
        cls._montar_campos(resultado)
        cls._consolidar_status(resultado)
        resultado.relatorio = cls._montar_relatorio(resultado)
        return resultado

    @classmethod
    def _montar_campos(cls, resultado: ResultadoConfiguradorOlist) -> None:
        consulta = resultado.consulta
        robo = resultado.robo
        decisao = robo.decisao_operacao
        ficha = robo.ficha
        icms_uf = resultado.icms_uf
        difal = resultado.difal

        if decisao is None:
            resultado.alertas.append(
                "O Robô Tributário não conseguiu formar a decisão operacional completa para este NCM."
            )
            return

        cfop = cls._texto(decisao.cfop.valor, "REVISAR")
        natureza = cls._natureza_sugerida(cfop)
        difal_nao_contrib = bool(
            difal.get("aplicavel")
            and consulta.consumidor_final
            and consulta.destinatario_contribuinte is False
        )
        difal_config_confirmada = bool(
            (not difal_nao_contrib and difal.get("confirmado"))
            or (difal_nao_contrib and difal.get("confirmado"))
        )

        pis_aliq = getattr(ficha, "aliquota_pis", None) if ficha is not None else None
        cofins_aliq = getattr(ficha, "aliquota_cofins", None) if ficha is not None else None
        ipi = getattr(ficha, "ipi", None) if ficha is not None else None
        cst_ipi = getattr(ficha, "cst_ipi", "") if ficha is not None else ""

        campos = [
            CampoConfiguracaoOlist(
                "Operação",
                "Natureza de operação sugerida",
                natureza,
                cls._status_campo(decisao.cfop.status == cls.STATUS_CONFIRMADO),
                f"CFOP provável: {cfop}. Use o nome da natureza que corresponda a este tratamento no cadastro do Olist.",
            ),
            CampoConfiguracaoOlist(
                "Operação",
                "CFOP",
                cfop,
                decisao.cfop.status,
                decisao.cfop.motivo,
            ),
            CampoConfiguracaoOlist(
                "ICMS",
                "CST / CSOSN",
                cls._texto(decisao.icms.valor, "REVISAR"),
                decisao.icms.status,
                decisao.icms.motivo,
            ),
            CampoConfiguracaoOlist(
                "ICMS",
                "Destaque do ICMS próprio",
                cls._texto(decisao.destaque_icms.valor, "REVISAR"),
                decisao.destaque_icms.status,
                decisao.destaque_icms.motivo,
            ),
            CampoConfiguracaoOlist(
                "ICMS",
                "Alíquota da operação",
                cls._percentual(icms_uf.get("aliquota_operacao")),
                cls._status_campo(bool(icms_uf.get("aliquota_operacao_confirmada"))),
                cls._texto(icms_uf.get("aliquota_operacao_status")),
            ),
            CampoConfiguracaoOlist(
                "ICMS-ST",
                "Tratamento ICMS-ST",
                cls._texto(decisao.icms_st.valor, "REVISAR"),
                decisao.icms_st.status,
                decisao.icms_st.motivo,
            ),
            CampoConfiguracaoOlist(
                "ICMS-ST",
                "CEST",
                cls._texto(icms_uf.get("cest")),
                cls._status_campo(bool(icms_uf.get("st_decisao_confirmada"))),
                cls._texto(icms_uf.get("st_status")),
            ),
            CampoConfiguracaoOlist(
                "ICMS-ST",
                "Modelo de cálculo ST",
                cls._texto(icms_uf.get("st_modelo_calculo"), "MVA / regra estadual"),
                cls._status_campo(bool(icms_uf.get("st_decisao_confirmada"))),
                cls._texto(icms_uf.get("st_status")),
            ),
            CampoConfiguracaoOlist(
                "ICMS-ST",
                "Antecipação / percentual de agregação",
                cls._percentual(icms_uf.get("antecipacao_percentual")),
                cls._status_campo(bool(icms_uf.get("st_decisao_confirmada"))),
                cls._texto(icms_uf.get("antecipacao_status"), "Não se aplica antecipação estruturada à regra selecionada."),
            ),
            CampoConfiguracaoOlist(
                "ICMS-ST",
                "Carga líquida ST / entrada",
                cls._percentual(icms_uf.get("carga_liquida_st")),
                cls._status_campo(bool(icms_uf.get("st_decisao_confirmada"))),
                cls._texto(icms_uf.get("carga_liquida_status"), "Não se aplica carga líquida à regra estadual selecionada."),
            ),
            CampoConfiguracaoOlist(
                "ICMS-ST",
                "MVA aplicável",
                cls._percentual(icms_uf.get("mva_aplicada")),
                cls._status_campo(bool(icms_uf.get("st_decisao_confirmada"))),
                cls._texto(icms_uf.get("mva_tipo") or icms_uf.get("st_status")),
            ),
            CampoConfiguracaoOlist(
                "DIFAL",
                "ICMS DIFAL para não contribuinte",
                "SIM" if difal_nao_contrib else "NÃO",
                cls._status_campo(difal_config_confirmada),
                cls._texto(difal.get("motivo")),
            ),
            CampoConfiguracaoOlist(
                "DIFAL",
                "Alíquota interestadual",
                cls._percentual(difal.get("aliquota_interestadual")),
                cls._status_campo(bool(difal.get("aliquota_interestadual_confirmada"))),
                cls._texto(difal.get("aliquota_interestadual_status")),
            ),
            CampoConfiguracaoOlist(
                "DIFAL",
                "Alíquota interna da UF destino",
                cls._percentual(difal.get("aliquota_interna_destino")),
                cls._status_campo(bool(difal.get("aliquota_interna_confirmada"))),
                cls._texto(difal.get("aliquota_interna_status")),
            ),
            CampoConfiguracaoOlist(
                "DIFAL",
                "Diferencial percentual",
                cls._percentual(difal.get("diferencial_percentual")),
                cls._status_campo(bool(difal.get("confirmado"))),
                "Diferença entre a carga interna de destino e a alíquota interestadual, conforme o motor instalado.",
            ),
            CampoConfiguracaoOlist(
                "DIFAL",
                "FCP / fundo de combate à pobreza",
                cls._percentual(difal.get("aliquota_fcp")),
                cls._status_campo(bool(difal.get("fcp_confirmado"))),
                cls._texto(difal.get("fcp_status")),
            ),
            CampoConfiguracaoOlist(
                "DIFAL",
                "Responsável pelo DIFAL",
                cls._texto(difal.get("responsavel")),
                cls._status_campo(bool(difal.get("confirmado"))),
                "A responsabilidade depende da condição do destinatário informada na operação.",
            ),
            CampoConfiguracaoOlist(
                "PIS/COFINS",
                "PIS",
                f"{cls._texto(decisao.pis.valor, 'REVISAR')} • {cls._percentual(pis_aliq)}",
                decisao.pis.status,
                decisao.pis.motivo,
            ),
            CampoConfiguracaoOlist(
                "PIS/COFINS",
                "COFINS",
                f"{cls._texto(decisao.cofins.valor, 'REVISAR')} • {cls._percentual(cofins_aliq)}",
                decisao.cofins.status,
                decisao.cofins.motivo,
            ),
            CampoConfiguracaoOlist(
                "IPI",
                "IPI / TIPI de referência",
                f"{cls._percentual(ipi)} • CST {cls._texto(cst_ipi)}",
                "INFORMATIVO",
                "A alíquota TIPI é referência do NCM; confirme o tratamento do IPI na operação concreta antes de configurar a nota.",
            ),
            CampoConfiguracaoOlist(
                "Olist",
                "Cálculo automático de impostos",
                "HABILITADO",
                cls.STATUS_CONFIRMADO,
                "O Olist precisa recalcular o grupo de ICMS depois que a natureza e o DIFAL forem configurados.",
            ),
            CampoConfiguracaoOlist(
                "Olist",
                "Recarregar natureza na nota",
                "SIM",
                cls.STATUS_CONFIRMADO,
                "Depois de salvar a configuração, selecione novamente a Natureza da Operação na nota para recarregar as regras.",
            ),
        ]

        if difal.get("valor_operacao") is not None:
            campos.extend(
                [
                    CampoConfiguracaoOlist(
                        "DIFAL",
                        "Valor da operação analisado",
                        cls._moeda(difal.get("valor_operacao")),
                        "INFORMATIVO",
                    ),
                    CampoConfiguracaoOlist(
                        "DIFAL",
                        "Valor DIFAL esperado",
                        cls._moeda(difal.get("valor_difal")),
                        cls._status_campo(bool(difal.get("confirmado"))),
                    ),
                    CampoConfiguracaoOlist(
                        "DIFAL",
                        "Valor FCP esperado",
                        cls._moeda(difal.get("valor_fcp")),
                        cls._status_campo(bool(difal.get("fcp_confirmado"))),
                    ),
                ]
            )

        resultado.campos_olist = campos

        resultado.alertas.extend(str(a) for a in robo.alertas if str(a).strip())
        if consulta.destinatario_contribuinte is None and consulta.uf_origem != consulta.uf_destino:
            resultado.alertas.append(
                "Informe se o destinatário é contribuinte do ICMS. Sem isso o FiscalPro não deve confirmar a configuração de DIFAL."
            )
        if not consulta.descricao_produto:
            resultado.alertas.append(
                "Informe a descrição real do produto para aumentar a segurança dos enquadramentos NCM/CEST."
            )
        if icms_uf.get("exige_revisao"):
            resultado.alertas.append(
                "O motor estadual marcou pontos de ICMS/FCP/ST para revisão antes da emissão."
            )

    @classmethod
    def _consolidar_status(cls, resultado: ResultadoConfiguradorOlist) -> None:
        statuses = {campo.status for campo in resultado.campos_olist if campo.status != "INFORMATIVO"}
        if cls.STATUS_PENDENTE in statuses or resultado.robo.status == cls.STATUS_PENDENTE:
            resultado.status = cls.STATUS_PENDENTE
        elif cls.STATUS_REVISAR in statuses or resultado.robo.status == cls.STATUS_REVISAR:
            resultado.status = cls.STATUS_REVISAR
        else:
            resultado.status = cls.STATUS_CONFIRMADO

        confiancas: list[float] = []
        for valor in (
            resultado.robo.confiabilidade,
            resultado.icms_uf.get("confiabilidade_aliquota"),
            resultado.icms_uf.get("confiabilidade_fcp"),
            resultado.icms_uf.get("confiabilidade_st"),
            resultado.difal.get("confiabilidade"),
        ):
            try:
                numero = float(valor or 0.0)
            except (TypeError, ValueError):
                continue
            if numero > 0:
                confiancas.append(numero)
        resultado.confiabilidade = min(confiancas) if confiancas else 0.0

    @classmethod
    def _linhas_campos(cls, campos: Iterable[CampoConfiguracaoOlist]) -> list[str]:
        linhas: list[str] = []
        grupo_atual = ""
        for campo in campos:
            if campo.grupo != grupo_atual:
                if linhas:
                    linhas.append("")
                grupo_atual = campo.grupo
                linhas.append(grupo_atual.upper())
                linhas.append("-" * 72)
            linhas.append(f"{campo.campo}: {campo.valor}  [{campo.status}]")
            if campo.observacao:
                linhas.append(f"  ↳ {campo.observacao}")
        return linhas

    @classmethod
    def _montar_relatorio(cls, resultado: ResultadoConfiguradorOlist) -> str:
        c = resultado.consulta
        linhas = [
            "FISCALPRO — CONFIGURADOR TRIBUTÁRIO PARA OLIST",
            "=" * 72,
            f"Status: {resultado.status}",
            f"Segurança conservadora: {resultado.confiabilidade:.0f}%" if resultado.confiabilidade else "Segurança conservadora: -",
            "",
            "OPERAÇÃO ANALISADA",
            "-" * 72,
            f"Produto: {c.descricao_produto or '-'}",
            f"NCM: {c.ncm}",
            f"Empresa: {c.empresa or 'Empresa nova / não cadastrada'}",
            f"Regime: {c.regime}",
            f"UF origem → destino: {c.uf_origem} → {c.uf_destino}",
            f"Destinatário: {cls._destinatario_texto(c.destinatario_contribuinte)}",
            f"Consumidor final: {'SIM' if c.consumidor_final else 'NÃO'}",
            f"Perfil remetente: {c.perfil_remetente or '-'}",
            f"Situação ICMS-ST: {c.situacao_icms_st or '-'}",
            "",
            "CONFIGURAÇÃO / CONFERÊNCIA",
            "=" * 72,
        ]
        linhas.extend(cls._linhas_campos(resultado.campos_olist))
        linhas.extend(
            [
                "",
                "PASSOS NO OLIST PARA DIFAL NÃO CONTRIBUINTE",
                "=" * 72,
                "1. Configurações > Notas Fiscais > ICMS DIFAL para não contribuinte: confira a UF de destino e as alíquotas.",
                "2. Configurações > Notas Fiscais > Naturezas de operação de saída (tributação): abra a natureza usada na venda.",
                "3. No campo 'ICMS DIFAL para não contribuinte', use o resultado indicado pelo FiscalPro.",
                "4. Salve e, na edição da nota, selecione novamente a Natureza da Operação para recarregar as configurações.",
                "5. Mantenha o cálculo automático de impostos habilitado para o sistema gerar o grupo de ICMS.",
            ]
        )
        if resultado.alertas:
            linhas.extend(["", "PONTOS PARA REVISAR", "=" * 72])
            linhas.extend(f"• {texto}" for texto in dict.fromkeys(resultado.alertas))
        linhas.extend(
            [
                "",
                "SEGURANÇA",
                "=" * 72,
                "O FiscalPro não substitui a legislação vigente nem a validação fiscal. Campos marcados como REVISAR/PENDENTE não devem ser aplicados automaticamente.",
            ]
        )
        return "\n".join(linhas).rstrip() + "\n"


__all__ = [
    "CampoConfiguracaoOlist",
    "ResultadoConfiguradorOlist",
    "ConfiguradorOlistService",
]
