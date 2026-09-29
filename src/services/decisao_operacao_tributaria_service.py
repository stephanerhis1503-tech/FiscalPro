"""Decisão Tributária da Operação — Sprint 17.5.2.

Transforma os diagnósticos já produzidos pelos motores do FiscalPro em uma
recomendação operacional conservadora: CFOP provável, CST/CSOSN de ICMS,
CST de PIS/COFINS, destaque do ICMS e indicação de DIFAL/FCP.

A camada não substitui a legislação da UF nem aplica alterações em documentos.
Quando o contexto não é suficiente, devolve REVISAR/PENDENTE em vez de presumir.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any

from src.services.difal_fcp_nacional_service import DIFALFCPNacionalService


FONTE_CFOP = (
    "Receita Federal — Código Fiscal de Operações e de Prestações (CFOP), "
    "página atualizada em 03/06/2026."
)


@dataclass(frozen=True, slots=True)
class ComponenteDecisao:
    valor: str
    status: str
    confiabilidade: float
    motivo: str = ""


@dataclass(slots=True)
class DecisaoOperacaoTributaria:
    status: str
    confiabilidade: float
    cfop: ComponenteDecisao
    icms: ComponenteDecisao
    pis: ComponenteDecisao
    cofins: ComponenteDecisao
    destaque_icms: ComponenteDecisao
    icms_st: ComponenteDecisao
    difal: ComponenteDecisao
    difal_resultado: dict[str, Any] = field(default_factory=dict)
    alertas: list[str] = field(default_factory=list)

    @property
    def resumo(self) -> str:
        return (
            f"CFOP {self.cfop.valor or '-'} | ICMS {self.icms.valor or '-'} | "
            f"PIS {self.pis.valor or '-'} | COFINS {self.cofins.valor or '-'} | "
            f"DIFAL {self.difal.valor or '-'}"
        )


class DecisaoOperacaoTributariaService:
    STATUS_CONFIRMADO = "CONFIRMADO"
    STATUS_REVISAR = "REVISAR"
    STATUS_PENDENTE = "PENDENTE"
    STATUS_INFORMATIVO = "INFORMATIVO"

    ST_NAO_INFORMADO = "NAO INFORMADO"
    ST_RETIDO_ENTRADA = "ICMS-ST JA RETIDO NA ENTRADA"
    ST_RETER_SAIDA = "RESPONSAVEL POR RETER ICMS-ST NESTA SAIDA"
    ST_SEM_RETENCAO = "MERCADORIA SEM RETENCAO DE ICMS-ST"

    @staticmethod
    def _normalizar_texto(valor: Any) -> str:
        texto = str(valor or "").strip().upper()
        texto = "".join(
            c for c in unicodedata.normalize("NFD", texto)
            if unicodedata.category(c) != "Mn"
        )
        return " ".join(texto.split())

    @classmethod
    def _situacao_st(cls, consulta: Any) -> str:
        return cls._normalizar_texto(getattr(consulta, "situacao_icms_st", "")) or cls.ST_NAO_INFORMADO

    @classmethod
    def _perfil(cls, consulta: Any) -> str:
        return cls._normalizar_texto(getattr(consulta, "perfil_remetente", ""))

    @classmethod
    def _regime_simples(cls, consulta: Any) -> bool:
        return "SIMPLES" in cls._normalizar_texto(getattr(consulta, "regime", ""))

    @classmethod
    def _destinatario_contribuinte(cls, consulta: Any) -> bool | None:
        valor = getattr(consulta, "destinatario_contribuinte", None)
        if isinstance(valor, bool) or valor is None:
            return valor
        texto = cls._normalizar_texto(valor)
        if texto in {"SIM", "CONTRIBUINTE", "TRUE", "1"}:
            return True
        if texto in {"NAO", "NAO CONTRIBUINTE", "FALSE", "0"}:
            return False
        return None

    @classmethod
    def _cfop(cls, consulta: Any, ficha: Any) -> ComponenteDecisao:
        operacao = cls._normalizar_texto(getattr(consulta, "operacao", ""))
        if operacao not in {"VENDA", "REVENDA", "SAIDA"}:
            return ComponenteDecisao(
                "",
                cls.STATUS_REVISAR,
                0.0,
                "A Sprint 17.5.2 só confirma CFOP de venda/saída comum; devolução, transferência e remessa exigem contexto próprio.",
            )

        origem = cls._normalizar_texto(getattr(consulta, "uf_origem", ""))
        destino = cls._normalizar_texto(getattr(consulta, "uf_destino", ""))
        interna = origem == destino
        perfil = cls._perfil(consulta)
        comerciante = perfil in {"COMERCIANTE", "REVENDEDOR"}
        fabricante = perfil in {"FABRICANTE", "FABRICANTE/IMPORTADOR"}
        st_confirmado = bool(getattr(ficha, "icms_mg_st_confirmado", False))
        situacao_st = cls._situacao_st(consulta)
        destinatario = cls._destinatario_contribuinte(consulta)

        if st_confirmado and situacao_st == cls.ST_RETIDO_ENTRADA:
            if interna and comerciante:
                return ComponenteDecisao(
                    "5405", cls.STATUS_CONFIRMADO, 100.0,
                    "Venda interna de mercadoria adquirida de terceiros, sujeita à ST, na condição de contribuinte substituído.",
                )
            if not interna:
                return ComponenteDecisao(
                    "6404", cls.STATUS_CONFIRMADO, 100.0,
                    "Venda interestadual de mercadoria sujeita à ST cujo imposto já foi retido anteriormente.",
                )
            return ComponenteDecisao(
                "", cls.STATUS_REVISAR, 55.0,
                "Mercadoria com ST já retido, mas o perfil informado não permite confirmar o CFOP interno 5405.",
            )

        if st_confirmado and situacao_st == cls.ST_RETER_SAIDA:
            if interna and comerciante:
                return ComponenteDecisao(
                    "5403", cls.STATUS_CONFIRMADO, 100.0,
                    "Venda interna de mercadoria adquirida de terceiros com ST, na condição de contribuinte substituto.",
                )
            if interna and fabricante:
                return ComponenteDecisao(
                    "5401", cls.STATUS_CONFIRMADO, 100.0,
                    "Venda interna de produção do estabelecimento com ST, na condição de contribuinte substituto.",
                )
            if not interna and comerciante:
                return ComponenteDecisao(
                    "6403", cls.STATUS_CONFIRMADO, 100.0,
                    "Venda interestadual de mercadoria adquirida de terceiros com ST, na condição de contribuinte substituto.",
                )
            if not interna and fabricante:
                return ComponenteDecisao(
                    "6401", cls.STATUS_CONFIRMADO, 100.0,
                    "Venda interestadual de produção do estabelecimento com ST, na condição de contribuinte substituto.",
                )

        # Se a própria situação informada fala em ST, mas a base não confirmou o
        # enquadramento, não sugerimos um CFOP de ST apenas pela marcação manual.
        if situacao_st in {cls.ST_RETIDO_ENTRADA, cls.ST_RETER_SAIDA} and not st_confirmado:
            return ComponenteDecisao(
                "", cls.STATUS_PENDENTE, 0.0,
                "A situação da operação indica ICMS-ST, porém o enquadramento do produto em ST não foi confirmado pela base instalada.",
            )

        if not (comerciante or fabricante):
            return ComponenteDecisao(
                "", cls.STATUS_REVISAR, 45.0,
                "Informe se a mercadoria é produção própria ou adquirida de terceiros para definir o CFOP de venda.",
            )

        if interna:
            codigo = "5102" if comerciante else "5101"
            motivo = (
                "Venda interna de mercadoria adquirida ou recebida de terceiros."
                if comerciante
                else "Venda interna de produção do estabelecimento."
            )
            return ComponenteDecisao(codigo, cls.STATUS_CONFIRMADO, 100.0, motivo)

        # Nas vendas interestaduais há códigos específicos para não contribuinte.
        if destinatario is None:
            return ComponenteDecisao(
                "", cls.STATUS_REVISAR, 50.0,
                "Informe se o destinatário é contribuinte do ICMS para diferenciar o CFOP interestadual comum do CFOP destinado a não contribuinte.",
            )
        if comerciante:
            codigo = "6102" if destinatario else "6108"
            motivo = (
                "Venda interestadual de mercadoria adquirida de terceiros para contribuinte."
                if destinatario
                else "Venda interestadual de mercadoria adquirida de terceiros destinada a não contribuinte."
            )
        else:
            codigo = "6101" if destinatario else "6107"
            motivo = (
                "Venda interestadual de produção do estabelecimento para contribuinte."
                if destinatario
                else "Venda interestadual de produção do estabelecimento destinada a não contribuinte."
            )
        return ComponenteDecisao(codigo, cls.STATUS_CONFIRMADO, 100.0, motivo)

    @classmethod
    def _icms(cls, consulta: Any, ficha: Any) -> ComponenteDecisao:
        situacao_st = cls._situacao_st(consulta)
        st_confirmado = bool(getattr(ficha, "icms_mg_st_confirmado", False))
        regime_simples = cls._regime_simples(consulta)
        importada = bool(getattr(consulta, "mercadoria_importada", False))
        icms_confirmado = bool(getattr(ficha, "icms_mg_confirmado", False))
        reducao = float(getattr(ficha, "icms_mg_reducao_base", 0.0) or 0.0)
        beneficio = str(getattr(ficha, "icms_mg_beneficio_status", "") or "").strip()

        if st_confirmado and situacao_st == cls.ST_RETIDO_ENTRADA:
            if regime_simples:
                return ComponenteDecisao(
                    "CSOSN 500", cls.STATUS_CONFIRMADO, 100.0,
                    "ICMS cobrado anteriormente por substituição tributária; saída subsequente sem novo destaque do imposto próprio.",
                )
            if importada:
                return ComponenteDecisao(
                    "CST x60 — definir origem", cls.STATUS_REVISAR, 70.0,
                    "A situação tributária 60 está definida, mas a mercadoria foi marcada como importada e o primeiro dígito do CST depende da origem da mercadoria.",
                )
            return ComponenteDecisao(
                "CST 060", cls.STATUS_CONFIRMADO, 100.0,
                "ICMS cobrado anteriormente por substituição tributária; saída subsequente sem novo destaque do imposto próprio.",
            )

        if st_confirmado and situacao_st == cls.ST_RETER_SAIDA:
            if regime_simples:
                return ComponenteDecisao(
                    "CSOSN 201/202/203",
                    cls.STATUS_REVISAR,
                    65.0,
                    "A cobrança de ST foi informada, mas o CSOSN depende de permissão de crédito e eventual isenção por faixa.",
                )
            if icms_confirmado and not beneficio and reducao <= 0:
                if importada:
                    return ComponenteDecisao(
                        "CST x10 — definir origem", cls.STATUS_REVISAR, 70.0,
                        "A situação tributária 10 está definida, mas o primeiro dígito do CST depende da origem da mercadoria importada.",
                    )
                return ComponenteDecisao(
                    "CST 010", cls.STATUS_CONFIRMADO, 95.0,
                    "Operação tributada com responsabilidade pelo ICMS-ST subsequente; não foi identificado benefício/redução na ficha.",
                )
            return ComponenteDecisao(
                "CST 010/030/070 — revisar",
                cls.STATUS_REVISAR,
                55.0,
                "A responsabilidade por ST está definida, mas o CST depende do tratamento do ICMS próprio e de benefício/redução.",
            )

        if regime_simples:
            return ComponenteDecisao(
                "CSOSN — revisar", cls.STATUS_REVISAR, 50.0,
                "Sem ST retido, o CSOSN depende de permissão de crédito, faixa e demais regras do Simples Nacional.",
            )

        if icms_confirmado and not beneficio and reducao <= 0:
            if importada:
                return ComponenteDecisao(
                    "CST x00 — definir origem", cls.STATUS_REVISAR, 70.0,
                    "A situação tributária 00 está definida, mas o primeiro dígito do CST depende da origem da mercadoria importada.",
                )
            return ComponenteDecisao(
                "CST 000", cls.STATUS_CONFIRMADO, 95.0,
                "ICMS próprio confirmado sem redução/benefício específico na ficha; tributação integral.",
            )
        if icms_confirmado:
            return ComponenteDecisao(
                "CST — revisar", cls.STATUS_REVISAR, 65.0,
                "O ICMS foi confirmado, mas há benefício/redução ou contexto que impede presumir tributação integral.",
            )
        return ComponenteDecisao(
            "CST — revisar", cls.STATUS_REVISAR, 45.0,
            "O motor de ICMS ainda não confirmou o tratamento próprio da operação.",
        )

    @classmethod
    def _piscofins(cls, ficha: Any, tributo: str) -> ComponenteDecisao:
        confirmado = bool(getattr(ficha, "piscofins_confirmado", False))
        revisao = bool(getattr(ficha, "piscofins_exige_revisao", True))
        divergencia = bool(getattr(ficha, "piscofins_divergencia", False))
        confianca = float(getattr(ficha, "piscofins_confiabilidade", 0.0) or 0.0)
        atributo = "pis_cst" if tributo == "PIS" else "cofins_cst"
        valor = str(getattr(ficha, atributo, "") or "").strip()

        if confirmado and not revisao and not divergencia and valor:
            return ComponenteDecisao(f"CST {valor}", cls.STATUS_CONFIRMADO, confianca or 100.0, "CST confirmado pelo motor nacional de PIS/COFINS.")
        sugestao_attr = "piscofins_sugestao_cst_pis" if tributo == "PIS" else "piscofins_sugestao_cst_cofins"
        sugestao = str(getattr(ficha, sugestao_attr, "") or "").strip()
        if sugestao:
            return ComponenteDecisao(f"CST {sugestao} — sugestão", cls.STATUS_REVISAR, min(confianca or 65.0, 65.0), "O motor possui apenas sugestão condicional; confirme exceções antes de usar.")
        return ComponenteDecisao("CST — revisar", cls.STATUS_REVISAR, min(confianca or 40.0, 60.0), "O motor ainda não confirmou o CST desta operação.")

    @classmethod
    def _destaque_icms(cls, consulta: Any, ficha: Any) -> ComponenteDecisao:
        st_confirmado = bool(getattr(ficha, "icms_mg_st_confirmado", False))
        situacao_st = cls._situacao_st(consulta)
        if st_confirmado and situacao_st == cls.ST_RETIDO_ENTRADA:
            return ComponenteDecisao("NÃO", cls.STATUS_CONFIRMADO, 100.0, "Saída subsequente com ICMS-ST já retido anteriormente.")
        if st_confirmado and situacao_st == cls.ST_RETER_SAIDA:
            if bool(getattr(ficha, "icms_mg_confirmado", False)):
                return ComponenteDecisao("SIM — ICMS próprio; ST separado", cls.STATUS_CONFIRMADO, 90.0, "A empresa foi informada como responsável pela retenção nesta saída.")
            return ComponenteDecisao("REVISAR", cls.STATUS_REVISAR, 50.0, "A ST deve ser retida nesta saída, mas o ICMS próprio ainda não foi confirmado.")
        if bool(getattr(ficha, "icms_mg_confirmado", False)):
            return ComponenteDecisao("SIM", cls.STATUS_CONFIRMADO, float(getattr(ficha, "icms_mg_confiabilidade", 0.0) or 80.0), "ICMS próprio confirmado pelo motor instalado.")
        return ComponenteDecisao("REVISAR", cls.STATUS_REVISAR, 45.0, "Não há confirmação suficiente para afirmar o destaque do ICMS próprio.")

    @classmethod
    def _icms_st(cls, consulta: Any, ficha: Any) -> ComponenteDecisao:
        confirmado = bool(getattr(ficha, "icms_mg_st_confirmado", False))
        situacao = cls._situacao_st(consulta)
        if confirmado and situacao == cls.ST_RETIDO_ENTRADA:
            return ComponenteDecisao("JÁ RETIDO — sem nova retenção", cls.STATUS_CONFIRMADO, 100.0, "Produto sujeito à ST e imposto informado como retido na entrada.")
        if confirmado and situacao == cls.ST_RETER_SAIDA:
            return ComponenteDecisao("RETER NESTA SAÍDA", cls.STATUS_CONFIRMADO, 100.0, "Produto sujeito à ST e responsabilidade de retenção informada para esta saída.")
        if confirmado and situacao == cls.ST_SEM_RETENCAO:
            return ComponenteDecisao("SEM RETENÇÃO — revisar exceção", cls.STATUS_REVISAR, 50.0, "O produto foi confirmado na ST, mas a operação foi marcada sem retenção.")
        if confirmado:
            return ComponenteDecisao("SUJEITO À ST — informar responsabilidade", cls.STATUS_REVISAR, 70.0, "Falta informar se a ST já foi retida ou será retida nesta saída.")
        status_motor = cls._normalizar_texto(getattr(ficha, "icms_mg_st_status", ""))
        if "NAO APLICAVEL" in status_motor:
            return ComponenteDecisao("NÃO APLICÁVEL", cls.STATUS_CONFIRMADO, 85.0, "Motor registrou ST como não aplicável ao contexto.")
        if "NAO LOCALIZADO" in status_motor or not status_motor:
            return ComponenteDecisao("NÃO CONFIRMADO", cls.STATUS_PENDENTE, 0.0, "Ausência na base não é tratada como ausência de ST.")
        return ComponenteDecisao("REVISAR", cls.STATUS_REVISAR, 60.0, str(getattr(ficha, "icms_mg_st_status", "") or "ST não confirmada."))

    @classmethod
    def _difal(cls, consulta: Any, ficha: Any) -> tuple[ComponenteDecisao, dict[str, Any]]:
        contexto = {
            "uf_origem": getattr(consulta, "uf_origem", ""),
            "uf_destino": getattr(consulta, "uf_destino", ""),
            "regime": getattr(consulta, "regime", ""),
            "operacao": getattr(consulta, "operacao", ""),
            "consumidor_final": bool(getattr(consulta, "consumidor_final", False)),
            "destinatario_contribuinte": getattr(consulta, "destinatario_contribuinte", None),
            "mercadoria_importada": bool(getattr(consulta, "mercadoria_importada", False)),
            "excecao_aliquota_importacao": bool(getattr(consulta, "excecao_aliquota_importacao", False)),
        }
        resultado = DIFALFCPNacionalService.analisar(
            getattr(consulta, "ncm", ""),
            contexto=contexto,
            descricao=str(getattr(consulta, "descricao_produto", "") or getattr(ficha, "descricao", "") or ""),
        )

        status_texto = cls._normalizar_texto(resultado.get("status"))
        aplicavel = bool(resultado.get("aplicavel"))
        confirmado = bool(resultado.get("confirmado"))
        confianca = float(resultado.get("confiabilidade", 0.0) or 0.0)

        # A camada genérica de DIFAL não encerra sozinha operações interestaduais
        # que também envolvam ICMS-ST; nesse caso o robô conserva a conclusão.
        st_confirmado = bool(getattr(ficha, "icms_mg_st_confirmado", False))
        origem = cls._normalizar_texto(getattr(consulta, "uf_origem", ""))
        destino = cls._normalizar_texto(getattr(consulta, "uf_destino", ""))
        if st_confirmado and origem != destino and aplicavel:
            valor = "APLICÁVEL — revisar junto com ICMS-ST"
            return ComponenteDecisao(
                valor, cls.STATUS_REVISAR, min(confianca or 60.0, 60.0),
                "A operação é interestadual para consumidor final e também envolve ST; confirme a disciplina da UF/protocolo antes do recolhimento.",
            ), resultado

        if confirmado and not aplicavel:
            return ComponenteDecisao("NÃO APLICÁVEL", cls.STATUS_CONFIRMADO, confianca or 100.0, str(resultado.get("motivo") or resultado.get("status") or "")), resultado
        if confirmado and aplicavel:
            diferencial = resultado.get("diferencial_percentual")
            detalhe = f"APLICÁVEL ({float(diferencial):.2f} p.p.)" if diferencial is not None else "APLICÁVEL"
            return ComponenteDecisao(detalhe, cls.STATUS_CONFIRMADO, confianca or 90.0, str(resultado.get("responsavel") or resultado.get("motivo") or "")), resultado
        if aplicavel or "DIFAL" in status_texto:
            return ComponenteDecisao("APLICÁVEL — revisar", cls.STATUS_REVISAR, confianca, str(resultado.get("observacao") or resultado.get("motivo") or "")), resultado
        if resultado.get("exige_revisao"):
            return ComponenteDecisao("REVISAR", cls.STATUS_REVISAR, confianca, str(resultado.get("motivo") or resultado.get("observacao") or "")), resultado
        return ComponenteDecisao("NÃO CONFIRMADO", cls.STATUS_PENDENTE, confianca, str(resultado.get("motivo") or "DIFAL não pôde ser concluído.")), resultado

    @classmethod
    def analisar(cls, consulta: Any, ficha: Any) -> DecisaoOperacaoTributaria:
        cfop = cls._cfop(consulta, ficha)
        icms = cls._icms(consulta, ficha)
        pis = cls._piscofins(ficha, "PIS")
        cofins = cls._piscofins(ficha, "COFINS")
        destaque = cls._destaque_icms(consulta, ficha)
        st = cls._icms_st(consulta, ficha)
        difal, difal_resultado = cls._difal(consulta, ficha)

        componentes = [cfop, icms, pis, cofins, destaque, st, difal]
        if any(c.status == cls.STATUS_PENDENTE for c in componentes):
            status = cls.STATUS_PENDENTE
        elif any(c.status == cls.STATUS_REVISAR for c in componentes):
            status = cls.STATUS_REVISAR
        else:
            status = cls.STATUS_CONFIRMADO

        confiancas = [c.confiabilidade for c in componentes if c.confiabilidade > 0]
        confiabilidade = min(confiancas) if confiancas else 0.0

        alertas: list[str] = []
        if cfop.status != cls.STATUS_CONFIRMADO:
            alertas.append(f"CFOP: {cfop.motivo}")
        if icms.status != cls.STATUS_CONFIRMADO:
            alertas.append(f"ICMS: {icms.motivo}")
        if difal.status != cls.STATUS_CONFIRMADO:
            alertas.append(f"DIFAL/FCP: {difal.motivo}")

        return DecisaoOperacaoTributaria(
            status=status,
            confiabilidade=confiabilidade,
            cfop=cfop,
            icms=icms,
            pis=pis,
            cofins=cofins,
            destaque_icms=destaque,
            icms_st=st,
            difal=difal,
            difal_resultado=difal_resultado,
            alertas=alertas,
        )


__all__ = [
    "ComponenteDecisao",
    "DecisaoOperacaoTributaria",
    "DecisaoOperacaoTributariaService",
    "FONTE_CFOP",
]
