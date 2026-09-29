"""Comparação de cenários tributários — FiscalPro 17.8.36.

Reaproveita exatamente os motores já usados pela Ficha Inteligente para montar
um resumo comparável do mesmo NCM em dois contextos, sem criar uma segunda
lógica fiscal paralela.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List

from src.parecer.motor_parecer import MotorParecer
from src.repositorios.ficha_tributaria_repository import FichaTributariaRepository
from src.services.consulta_oficial_service import ConsultaOficialService
from src.services.empresas_regimes_service import EmpresasRegimesService
from src.services.indicador_seguranca_tributaria import IndicadorSegurancaTributaria


@dataclass(frozen=True, slots=True)
class LinhaComparacaoTributaria:
    chave: str
    campo: str
    valor_a: str
    valor_b: str
    diferente: bool


class ComparadorCenariosTributariosService:
    """Analisa e compara dois contextos usando os motores oficiais do FiscalPro."""

    CAMPOS_COMPARACAO = (
        ("regime", "Regime tributário"),
        ("piscofins", "PIS / COFINS"),
        ("icms_st", "ICMS-ST / MVA"),
        ("cest", "CEST"),
        ("icms", "ICMS próprio"),
        ("cfop", "CFOP sugerido"),
        ("tipi", "TIPI de referência"),
        ("ipi_operacao", "IPI na operação"),
        ("seguranca", "Segurança da análise"),
        ("revisoes", "Pontos a revisar"),
    )

    @staticmethod
    def _texto(valor: Any) -> str:
        return " ".join(str(valor or "").strip().split())

    @staticmethod
    def _percentual(valor: Any) -> str:
        if valor in (None, ""):
            return "Não informado"
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return str(valor)
        return f"{numero:.2f}%".replace(".", ",")

    @staticmethod
    def _numero(valor: Any) -> float | None:
        """Converte percentuais/valores simples em número sem inferir regra fiscal."""
        if valor in (None, ""):
            return None
        if isinstance(valor, (int, float)):
            return float(valor)
        texto = str(valor).strip().replace("%", "").replace(" ", "")
        if not texto:
            return None
        if "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", ".")
        try:
            return float(texto)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _formatar_par_percentuais(cls, pis: float | None, cofins: float | None) -> str:
        return f"PIS {cls._percentual(pis)} • COFINS {cls._percentual(cofins)}"

    @classmethod
    def _resumo_inteligente(
        cls,
        cenario_a: Dict[str, Any],
        cenario_b: Dict[str, Any],
        linhas: List[LinhaComparacaoTributaria],
    ) -> Dict[str, Any]:
        """Produz leitura orientativa sem eleger automaticamente um cenário fiscal."""
        mapa = {linha.chave: linha for linha in linhas}
        ma = dict(cenario_a.get("metricas") or {})
        mb = dict(cenario_b.get("metricas") or {})
        itens: List[str] = []

        pis_a, cof_a = ma.get("pis"), ma.get("cofins")
        pis_b, cof_b = mb.get("pis"), mb.get("cofins")
        linha_pisco = mapa.get("piscofins")
        if linha_pisco and linha_pisco.diferente:
            lado_menor = None
            if None not in (pis_a, cof_a, pis_b, cof_b):
                if pis_a <= pis_b and cof_a <= cof_b and (pis_a < pis_b or cof_a < cof_b):
                    lado_menor = "A"
                elif pis_b <= pis_a and cof_b <= cof_a and (pis_b < pis_a or cof_b < cof_a):
                    lado_menor = "B"
            if lado_menor:
                menor = ma if lado_menor == "A" else mb
                maior = mb if lado_menor == "A" else ma
                itens.append(
                    f"PIS/COFINS: o Cenário {lado_menor} apresenta alíquotas nominais menores "
                    f"({cls._formatar_par_percentuais(menor.get('pis'), menor.get('cofins'))}) "
                    f"que o outro cenário ({cls._formatar_par_percentuais(maior.get('pis'), maior.get('cofins'))}). "
                    "Isso não significa, por si só, menor carga efetiva: cumulatividade, créditos e a operação real precisam ser considerados."
                )
            else:
                itens.append(
                    "PIS/COFINS: o tratamento muda entre os cenários. Compare regime, CST, possíveis créditos e exceções antes de concluir o efeito efetivo."
                )
        else:
            itens.append(
                f"PIS/COFINS: sem diferença principal nos valores exibidos ({cenario_a['valores'].get('piscofins', 'Não informado')})."
            )

        icms_a, icms_b = ma.get("icms"), mb.get("icms")
        linha_icms = mapa.get("icms")
        if linha_icms and linha_icms.diferente:
            if icms_a is not None and icms_b is not None:
                itens.append(
                    f"ICMS próprio: as alíquotas nominais mudam — A {cls._percentual(icms_a)} × B {cls._percentual(icms_b)}. "
                    "Valide base de cálculo, benefícios, origem/destino e exceções da operação antes de comparar impacto."
                )
            else:
                itens.append("ICMS próprio: o tratamento muda entre os cenários e requer leitura da regra da operação.")
        else:
            valor = cenario_a["valores"].get("icms") or "Não informado"
            itens.append(f"ICMS próprio: sem diferença principal entre os cenários ({valor}).")

        mva_a, mva_b = ma.get("mva"), mb.get("mva")
        linha_st = mapa.get("icms_st")
        if linha_st and linha_st.diferente:
            if mva_a is not None and mva_b is not None:
                itens.append(
                    f"ICMS-ST/MVA: o enquadramento muda — MVA A {cls._percentual(mva_a)} × B {cls._percentual(mva_b)}. "
                    "MVA isolada não define a melhor opção; recalcule a ST no contexto real."
                )
            else:
                itens.append("ICMS-ST: o enquadramento difere e deve ser conferido no contexto real de cada cenário.")
        else:
            itens.append(
                f"ICMS-ST: sem diferença principal nos dados exibidos ({cenario_a['valores'].get('icms_st', 'Não informado')})."
            )

        linha_cfop = mapa.get("cfop")
        if linha_cfop and linha_cfop.diferente:
            itens.append(
                f"CFOP: a sugestão muda entre os cenários (A {linha_cfop.valor_a} × B {linha_cfop.valor_b}); confirme a natureza efetiva da operação."
            )

        seg_a, seg_b = ma.get("seguranca"), mb.get("seguranca")
        linha_seg = mapa.get("seguranca")
        if linha_seg and linha_seg.diferente and seg_a is not None and seg_b is not None:
            lado = "A" if seg_a > seg_b else "B"
            itens.append(
                f"Segurança: o Cenário {lado} possui maior nível de confirmação ({cls._percentual(max(seg_a, seg_b))} × {cls._percentual(min(seg_a, seg_b))}). "
                "Maior segurança significa mais confirmação das regras, não menor imposto."
            )

        revisoes_a = list(cenario_a.get("detalhes", {}).get("motivos_revisao") or [])
        revisoes_b = list(cenario_b.get("detalhes", {}).get("motivos_revisao") or [])
        uniao = []
        for item in revisoes_a + revisoes_b:
            if item and item not in uniao:
                uniao.append(item)
        if uniao:
            itens.append("Atenção antes de aplicar: " + " • ".join(uniao) + ".")

        diferentes = [linha for linha in linhas if linha.diferente]
        if not diferentes:
            conclusao = (
                "Os cenários são equivalentes nos campos principais comparados. Isso não substitui a conferência da documentação, "
                "da operação real e das regras marcadas para revisão."
            )
        else:
            conclusao = (
                "Não existe vencedor automático. O FiscalPro destaca diferenças nominais e de enquadramento; a decisão deve considerar "
                "créditos aplicáveis, operação real, documentos, exceções e todos os pontos marcados para revisão."
            )

        return {
            "badge": "SEM VENCEDOR AUTOMÁTICO",
            "titulo": "Leitura orientativa da comparação",
            "itens": itens[:6],
            "conclusao": conclusao,
        }

    @classmethod
    def _normalizar_contexto(cls, contexto: Dict[str, Any] | None) -> Dict[str, Any]:
        saida = dict(contexto or {})
        empresa = cls._texto(saida.get("empresa"))
        if not empresa or empresa == "Todas as empresas":
            raise ValueError("Selecione uma empresa específica para cada cenário.")
        saida["empresa"] = empresa
        saida["regime"] = EmpresasRegimesService.resolver_regime(
            empresa, saida.get("regime") or ""
        )
        if not saida.get("regime"):
            raise ValueError(f"Não foi possível definir o regime tributário de {empresa}.")
        saida["operacao"] = cls._texto(saida.get("operacao")) or "SAÍDA"
        saida["finalidade"] = cls._texto(saida.get("finalidade")) or "REVENDA"
        saida["uf_origem"] = cls._texto(saida.get("uf_origem")).upper() or "MG"
        saida["uf_destino"] = cls._texto(saida.get("uf_destino")).upper() or "MG"
        saida["contribuinte"] = cls._texto(saida.get("contribuinte")) or "TODOS"
        saida["origem_mercadoria"] = (
            cls._texto(saida.get("origem_mercadoria")) or "NÃO INFORMADA"
        )
        saida["data_operacao"] = cls._texto(saida.get("data_operacao")) or date.today().isoformat()
        return EmpresasRegimesService.aplicar_contexto(saida)

    @classmethod
    def analisar_cenario(cls, ncm: str, contexto: Dict[str, Any]) -> Dict[str, Any]:
        ncm = "".join(c for c in str(ncm or "") if c.isdigit())
        if len(ncm) != 8:
            raise ValueError("Informe um NCM válido com 8 dígitos para comparar.")

        contexto = cls._normalizar_contexto(contexto)
        empresa = contexto["empresa"]
        dados_ficha = FichaTributariaRepository.carregar_ficha(ncm, empresa=empresa)
        dados_gerais_consulta = dict(dados_ficha.get("dados_gerais") or {})
        consulta_oficial = ConsultaOficialService.consultar(
            ncm,
            contexto=contexto,
            descricao=str(dados_gerais_consulta.get("descricao") or ""),
            ex_tipi=str(dados_gerais_consulta.get("ex_tipi") or ""),
        )
        parecer = MotorParecer.gerar(dados_ficha, contexto)
        parecer = ConsultaOficialService.aplicar_fontes_ao_parecer(
            parecer, consulta_oficial
        )
        tributacao = dict(parecer.tributacao_atual or {})

        pisco = ConsultaOficialService.piscofins_para_exibicao(consulta_oficial, tributacao)
        icms = ConsultaOficialService.icms_para_exibicao(consulta_oficial, tributacao)
        cfop = ConsultaOficialService.cfop_para_exibicao(consulta_oficial, contexto, tributacao)
        ipi = ConsultaOficialService.ipi_para_exibicao(consulta_oficial, tributacao, contexto)
        revisao = ConsultaOficialService.revisao_para_exibicao(
            consulta_oficial, parecer, tributacao, contexto
        )
        st = ConsultaOficialService.st_contextual(consulta_oficial)
        indicador_geral = IndicadorSegurancaTributaria.geral(parecer)

        status_pisco = cls._texto(pisco.get("status"))
        pisco_confirmado = bool(pisco.get("confirmado"))
        if "MONOFÁSICO" in status_pisco.upper():
            texto_pisco = "Monofásico • PIS 0,00% • COFINS 0,00%"
        else:
            texto_pisco = (
                f"PIS {cls._percentual(pisco.get('aliquota_pis'))} • "
                f"COFINS {cls._percentual(pisco.get('aliquota_cofins'))}"
            )
        cst_pis = cls._texto(pisco.get("cst_pis"))
        cst_cofins = cls._texto(pisco.get("cst_cofins"))
        if cst_pis or cst_cofins:
            texto_pisco += f" • CST {cst_pis or '-'} / {cst_cofins or '-'}"
        if status_pisco:
            texto_pisco += f" • {status_pisco}"

        st_confirmado = bool(st.get("confirmado"))
        mva = st.get("mva_aplicada")
        if mva is None:
            mva = st.get("mva_original")
        if st_confirmado:
            texto_st = f"SIM • MVA {cls._percentual(mva)}"
        else:
            texto_st = cls._texto(st.get("status")) or "Revisar enquadramento"
        cest = cls._texto(st.get("cest")) or cls._texto(tributacao.get("CEST")) or "Não informado"

        cst_icms = cls._texto(icms.get("cst"))
        texto_icms = cls._percentual(icms.get("aliquota"))
        if cst_icms:
            texto_icms += f" • CST {cst_icms}"
        status_icms = cls._texto(icms.get("status"))
        if status_icms:
            texto_icms += f" • {status_icms}"

        texto_cfop = cls._texto(cfop.get("valor")) or "Não informado"
        status_cfop = cls._texto(cfop.get("status"))
        if status_cfop and status_cfop.upper() not in texto_cfop.upper():
            texto_cfop += f" • {status_cfop}"

        motivos = [cls._texto(x) for x in (revisao.get("motivos") or []) if cls._texto(x)]
        texto_revisoes = " • ".join(motivos) if motivos else "Nenhum ponto crítico indicado"

        descricao = cls._texto(getattr(parecer, "descricao", "")) or cls._texto(
            dados_gerais_consulta.get("descricao")
        )
        regime = contexto["regime"]
        perfil = EmpresasRegimesService.obter_perfil(empresa)
        regime_pisco = perfil.regime_piscofins if perfil is not None else ""
        texto_regime = regime + (f" • {regime_pisco}" if regime_pisco and regime_pisco != regime else "")

        return {
            "ncm": ncm,
            "descricao": descricao,
            "contexto": contexto,
            "empresa": empresa,
            "regime": regime,
            "rota": f"{contexto['uf_origem']}→{contexto['uf_destino']}",
            "operacao": contexto["operacao"],
            "valores": {
                "regime": texto_regime,
                "piscofins": texto_pisco,
                "icms_st": texto_st,
                "cest": cest,
                "icms": texto_icms,
                "cfop": texto_cfop,
                "tipi": cls._texto(ipi.get("tipi_referencia")) or "Não informado",
                "ipi_operacao": cls._texto(ipi.get("tratamento_operacao")) or "Não informado",
                "seguranca": indicador_geral.resultado,
                "revisoes": texto_revisoes,
            },
            "metricas": {
                "pis": cls._numero(pisco.get("aliquota_pis")),
                "cofins": cls._numero(pisco.get("aliquota_cofins")),
                "icms": cls._numero(icms.get("aliquota")),
                "mva": cls._numero(mva),
                "seguranca": cls._numero(getattr(parecer, "confiabilidade", None)),
            },
            "detalhes": {
                "piscofins_confirmado": pisco_confirmado,
                "icms_st_confirmado": st_confirmado,
                "revisar": bool(revisao.get("precisa_revisar")),
                "motivos_revisao": motivos,
                "revisao_detalhes": list(revisao.get("detalhes") or []),
                "consulta_oficial": consulta_oficial,
            },
        }

    @classmethod
    def comparar(
        cls,
        ncm: str,
        contexto_a: Dict[str, Any],
        contexto_b: Dict[str, Any],
    ) -> Dict[str, Any]:
        cenario_a = cls.analisar_cenario(ncm, contexto_a)
        cenario_b = cls.analisar_cenario(ncm, contexto_b)
        linhas: List[LinhaComparacaoTributaria] = []
        for chave, campo in cls.CAMPOS_COMPARACAO:
            valor_a = cls._texto(cenario_a["valores"].get(chave))
            valor_b = cls._texto(cenario_b["valores"].get(chave))
            linhas.append(
                LinhaComparacaoTributaria(
                    chave=chave,
                    campo=campo,
                    valor_a=valor_a,
                    valor_b=valor_b,
                    diferente=valor_a.casefold() != valor_b.casefold(),
                )
            )
        diferentes = [linha for linha in linhas if linha.diferente]
        resumo_inteligente = cls._resumo_inteligente(cenario_a, cenario_b, linhas)
        return {
            "ncm": cenario_a["ncm"],
            "descricao": cenario_a["descricao"] or cenario_b["descricao"],
            "cenario_a": cenario_a,
            "cenario_b": cenario_b,
            "linhas": linhas,
            "total_diferencas": len(diferentes),
            "campos_diferentes": [linha.campo for linha in diferentes],
            "resumo_inteligente": resumo_inteligente,
        }
