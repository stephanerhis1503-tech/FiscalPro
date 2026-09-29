"""Integração do motor estadual de Minas Gerais com a análise em lote.

Hotfix 17.2.2
--------------
Esta camada não altera XML ou SPED. Ela enriquece o resultado nacional de ICMS
quando a UF de destino é Minas Gerais, usando o enquadramento detalhado de
ICMS-ST/MG já instalado, a fórmula de MVA ajustada e a regra objetiva do
adicional FEM/FCP vigente entre 2024 e 2026.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional
import re
import unicodedata

from src.inteligencia.base_oficial.repositorio import BaseOficialRepository
from src.services.calculadora_icms_st_mg_service import CalculadoraICMSSTMGService
from src.services.icms_uf_service import ICMSUFService


URL_DECRETO_FEM_MG = (
    "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/"
    "decretos/2023/d48736_2023.html"
)
URL_ANEXO_VII_MG = (
    "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/"
    "ricms_2023_seco/anexovii2023seco.pdf"
)


class ICMSMGLoteIntegracaoService:
    """Enriquece o ICMS/MG no lote sem substituir o motor nacional."""

    @staticmethod
    def _texto(valor: Any) -> str:
        texto = str(valor or "").strip().upper()
        texto = "".join(
            caractere
            for caractere in unicodedata.normalize("NFD", texto)
            if unicodedata.category(caractere) != "Mn"
        )
        return " ".join(texto.split())

    @staticmethod
    def _limpar_observacao_legada(texto: Any) -> str:
        """Remove avisos antigos que ficaram incompatíveis após a integração MG."""
        observacao = str(texto or "").strip()
        padroes = (
            r"\s*O FCP/MG ainda não está automatizado nesta camada nacional\.?",
            r"\s*FCP/MG ainda não está automatizado nesta camada nacional\.?",
        )
        for padrao in padroes:
            observacao = re.sub(padrao, "", observacao, flags=re.IGNORECASE)
        return " ".join(observacao.split())

    @staticmethod
    def _formatar_percentual(valor: Any) -> str:
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return "-"
        return f"{numero:.2f}%".replace(".", ",")

    @classmethod
    def _mensagem_fcp_integrado(cls, resultado: Dict[str, Any]) -> str:
        status = str(resultado.get("fcp_status") or "").strip()
        aliquota = resultado.get("fcp")
        confirmado = bool(resultado.get("fcp_confirmado"))
        status_normalizado = cls._texto(status)

        if confirmado and aliquota is not None:
            percentual = cls._formatar_percentual(aliquota)
            if float(aliquota) == 0.0:
                if "FORA DA LISTA OBJETIVA" in status_normalizado:
                    conclusao = "não aplicável à mercadoria consultada"
                else:
                    conclusao = "não aplicável ao contexto informado"
            else:
                conclusao = "confirmado para a mercadoria e a operação consultadas"
            return (
                f"FCP/FEM analisado pelo motor estadual de MG: "
                f"{percentual} — {conclusao}."
            )

        detalhe = status.rstrip(".") if status else "revisão necessária"
        return f"FCP/FEM analisado pelo motor estadual de MG: {detalhe}."

    @staticmethod
    def _booleano(valor: Any) -> bool:
        if isinstance(valor, bool):
            return valor
        return str(valor or "").strip().upper() in {
            "1", "S", "SIM", "TRUE", "VERDADEIRO", "YES",
        }

    @staticmethod
    def _data(valor: Any) -> date:
        texto = str(valor or "").strip()
        for formato in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(texto[:10], formato).date()
            except ValueError:
                continue
        return date.today()

    @classmethod
    def _categoria_fem_mg(cls, ncm: str, descricao: str) -> Optional[str]:
        """Retorna a categoria objetiva do Decreto 48.736/2023, quando reconhecida.

        A lista é deliberadamente conservadora. Mercadorias que dependem de
        composição, apresentação comercial ou finalidade permanecem condicionais.
        """
        texto = cls._texto(descricao)

        # Bebidas e tabaco.
        if ncm.startswith(("220291", "2203", "2204", "2205", "2206", "2208")):
            if "AGUARDENTE DE CANA" in texto or "AGUARDENTE DE MELACO" in texto:
                return None
            return "BEBIDAS ALCANÇADAS PELO FEM/MG"
        if ncm.startswith("24"):
            return "PRODUTOS DE TABACARIA"
        if ncm.startswith(("2202",)) and any(
            termo in texto for termo in ("REFRIGERANTE", "ISOTONIC", "ENERGETIC")
        ):
            return "REFRIGERANTES, ISOTÔNICOS E ENERGÉTICOS"

        # Armas expressamente listadas.
        if ncm.startswith(("9302", "9303", "9304", "9307")):
            return "ARMAS ALCANÇADAS PELO FEM/MG"

        # Perfumaria, cosméticos e toucador, com exclusões descritivas do decreto.
        if ncm.startswith(("3303", "3304", "3305", "3306", "3307")):
            exclusoes = (
                "XAMPU", "SHAMPOO", "ANTISSOLAR", "PROTETOR SOLAR",
                "SABAO DE TOUCADOR", "HIGIENE BUCAL", "HIGIENE DENTARIA",
                "FIO DENTAL",
            )
            if any(termo in texto for termo in exclusoes):
                return None
            return "PERFUMARIA, COSMÉTICOS E PRODUTOS DE TOUCADOR"

        # Hipóteses reconhecíveis por NCM/descrição.
        if ncm == "85171300" or (ncm.startswith("8517") and any(
            termo in texto for termo in ("CELULAR", "SMARTPHONE", "TELEFONE MOVEL")
        )):
            return "TELEFONES CELULARES E SMARTPHONES"
        if ncm.startswith("8525") and any(
            termo in texto for termo in ("CAMERA", "FILMADORA", "FOTOGRAF")
        ):
            return "CÂMERAS E ACESSÓRIOS"
        if ncm.startswith("9507"):
            return "ARTIGOS PARA PESCA ESPORTIVA"
        if any(termo in texto for termo in (
            "SUPLEMENTO ENERGETICO", "SUPLEMENTO PROTEICO", "CREATINA",
            "SUPLEMENTO DE CAFEINA", "ALIMENTO PARA ATLETA",
        )):
            return "ALIMENTOS PARA ATLETAS"
        if any(termo in texto for termo in (
            "SOM AUTOMOTIVO", "VIDEO AUTOMOTIVO", "ALTO-FALANTE AUTOMOTIVO",
            "AMPLIFICADOR AUTOMOTIVO", "TRANSFORMADOR AUTOMOTIVO",
        )):
            return "SOM OU VÍDEO PARA USO AUTOMOTIVO"
        return None

    @classmethod
    def _fem_mg(
        cls,
        *,
        ncm: str,
        descricao: str,
        data_operacao: date,
        consumidor_final: bool,
        st_confirmado: bool,
    ) -> Dict[str, Any]:
        if data_operacao < date(2024, 1, 1) or data_operacao > date(2026, 12, 31):
            return {
                "aliquota": None,
                "status": "REVISAR VIGÊNCIA DO FEM/MG FORA DO PERÍODO 2024–2026",
                "confirmado": False,
                "confiabilidade": 0.0,
                "fundamento": "Decreto MG nº 48.736/2023, arts. 2º e 11.",
                "fonte": URL_DECRETO_FEM_MG,
            }

        categoria = cls._categoria_fem_mg(ncm, descricao)
        if categoria is None:
            return {
                "aliquota": 0.0,
                "status": "NÃO APLICÁVEL — MERCADORIA FORA DA LISTA OBJETIVA DO FEM/MG",
                "confirmado": True,
                "confiabilidade": 100.0,
                "fundamento": "Decreto MG nº 48.736/2023, art. 2º.",
                "fonte": URL_DECRETO_FEM_MG,
            }

        if st_confirmado or consumidor_final:
            alcance = "ICMS-ST" if st_confirmado else "OPERAÇÃO A CONSUMIDOR FINAL"
            return {
                "aliquota": 2.0,
                "status": f"CONFIRMADO — FEM/MG 2% ({categoria}; {alcance})",
                "confirmado": True,
                "confiabilidade": 100.0,
                "fundamento": "Decreto MG nº 48.736/2023, arts. 2º e 3º.",
                "fonte": URL_DECRETO_FEM_MG,
            }

        return {
            "aliquota": 0.0,
            "status": (
                f"NÃO APLICÁVEL AO CONTEXTO INFORMADO — {categoria}; "
                "SEM CONSUMIDOR FINAL E SEM ST CONFIRMADA"
            ),
            "confirmado": True,
            "confiabilidade": 100.0,
            "fundamento": "Decreto MG nº 48.736/2023, arts. 2º e 3º.",
            "fonte": URL_DECRETO_FEM_MG,
        }

    @staticmethod
    def _referencia_st(ncm: str, cest: str) -> Dict[str, str]:
        candidatos = BaseOficialRepository.buscar_st_mg_por_ncm(ncm)
        cest_digitos = "".join(c for c in str(cest or "") if c.isdigit())
        escolhido = None
        for item in candidatos:
            item_cest = "".join(c for c in str(item.get("cest") or "") if c.isdigit())
            if cest_digitos and item_cest == cest_digitos:
                escolhido = item
                break
        if escolhido is None and candidatos:
            escolhido = candidatos[0]
        if not escolhido:
            return {"referencia": "", "atualizado_em": ""}
        return {
            "referencia": str(escolhido.get("vigencia_referencia") or ""),
            "atualizado_em": str(escolhido.get("atualizado_em") or ""),
        }

    @classmethod
    def analisar(
        cls,
        ncm: Any,
        contexto: Optional[Dict[str, Any]] = None,
        descricao: str = "",
    ) -> Dict[str, Any]:
        contexto = dict(contexto or {})
        resultado = ICMSUFService.analisar(ncm, contexto=contexto, descricao=descricao)
        destino = str(contexto.get("uf_destino") or "").strip().upper()
        if destino != "MG":
            return resultado

        codigo = "".join(c for c in str(ncm or "") if c.isdigit())
        data_operacao = cls._data(contexto.get("data_operacao"))
        origem = str(contexto.get("uf_origem") or "").strip().upper()
        consumidor_final = cls._booleano(contexto.get("consumidor_final"))

        # Vigência/rastreabilidade da cópia oficial instalada.
        referencia = cls._referencia_st(codigo, str(resultado.get("cest") or ""))
        resultado["st_vigencia_referencia"] = referencia["referencia"]
        resultado["st_atualizado_em"] = referencia["atualizado_em"]

        # Se a mercadoria consta da tabela mineira, a incidência estadual da ST
        # pode ser confirmada mesmo quando a UF de origem não integra o acordo.
        # Nesse caso, o ponto pendente é quem recolhe (remetente, destinatário ou
        # responsável por regime especial), e não o enquadramento do produto.
        st_enquadrado_mg = bool(resultado.get("cest") and resultado.get("mva_original") is not None)
        responsabilidade_confirmada = bool(resultado.get("st_confirmado"))
        if st_enquadrado_mg and not bool(resultado.get("st_confirmado")):
            resultado["st_confirmado"] = True
            resultado["st_decisao_confirmada"] = True
            resultado["st_responsabilidade_confirmada"] = False
            resultado["st_responsabilidade_status"] = (
                "ICMS-ST/MG APLICÁVEL; RESPONSABILIDADE PELO RECOLHIMENTO A REVISAR "
                "CONFORME ÂMBITO, INSCRIÇÃO DO REMETENTE E REGIME ESPECIAL"
            )
            resultado["st_responsabilidade"] = resultado["st_responsabilidade_status"]
            resultado["confiabilidade_st"] = 85.0
        else:
            sem_st_confirmado = bool(
                resultado.get("st_decisao_confirmada")
                and not resultado.get("st_confirmado")
            )
            resultado["st_responsabilidade_confirmada"] = bool(
                responsabilidade_confirmada or sem_st_confirmado
            )
            resultado["st_responsabilidade_status"] = (
                "SEM RESPONSABILIDADE DE ST — NÃO INCIDE NA REGRA ESTADUAL ANALISADA"
                if sem_st_confirmado
                else (
                    "RESPONSABILIDADE CONFIRMADA PELO MOTOR ESTADUAL"
                    if responsabilidade_confirmada
                    else str(resultado.get("st_responsabilidade") or "")
                )
            )

        # FEM/FCP objetivo de MG.
        fcp = cls._fem_mg(
            ncm=codigo,
            descricao=descricao,
            data_operacao=data_operacao,
            consumidor_final=consumidor_final,
            st_confirmado=bool(resultado.get("st_confirmado")),
        )
        resultado.update({
            "fcp": fcp.get("aliquota"),
            "fcp_status": fcp.get("status"),
            "fcp_confirmado": bool(fcp.get("confirmado")),
            "confiabilidade_fcp": float(fcp.get("confiabilidade") or 0.0),
            "fundamento_fcp": str(fcp.get("fundamento") or ""),
            "fonte_fcp": str(fcp.get("fonte") or ""),
        })

        # MVA ajustada para entradas interestaduais destinadas a MG.
        original = resultado.get("mva_original")
        inter = resultado.get("aliquota_operacao")
        interna = resultado.get("aliquota_interna_destino")
        st_confirmado = bool(resultado.get("st_confirmado"))
        operacao_interestadual = bool(origem and origem != "MG")
        if st_confirmado and original is not None:
            resultado["mva_aplicada"] = float(original)
            resultado["mva_tipo"] = "MVA ORIGINAL MG"
            if operacao_interestadual and inter is not None and interna is not None:
                ajustada = float(
                    CalculadoraICMSSTMGService.calcular_mva_ajustada(
                        original, inter, interna
                    )
                )
                resultado["mva_ajustada"] = ajustada
                resultado["mva_aplicada"] = ajustada
                resultado["mva_tipo"] = "MVA AJUSTADA MG"
                responsabilidade_ok = bool(resultado.get("st_responsabilidade_confirmada"))
                if bool(resultado.get("aliquota_interna_confirmada")) and responsabilidade_ok:
                    resultado["st_status"] = (
                        "ICMS-ST/MG CONFIRMADO — MVA AJUSTADA CALCULADA"
                    )
                elif responsabilidade_ok:
                    resultado["st_status"] = (
                        "ICMS-ST/MG CONFIRMADO — MVA AJUSTADA CALCULADA COM "
                        "ALÍQUOTA INTERNA CONDICIONAL"
                    )
                else:
                    resultado["st_status"] = (
                        "ICMS-ST/MG APLICÁVEL — MVA AJUSTADA CALCULADA; "
                        "RESPONSABILIDADE PELO RECOLHIMENTO A REVISAR"
                    )
            elif origem == "MG":
                resultado["st_status"] = "ICMS-ST/MG CONFIRMADO — MVA ORIGINAL APLICADA"

        # Recalcula a decisão geral sem transformar alíquota condicional em confirmação.
        resultado["confirmado"] = bool(
            resultado.get("aliquota_operacao_confirmada")
            and resultado.get("aliquota_interna_confirmada")
            and resultado.get("fcp_confirmado")
            and resultado.get("st_decisao_confirmada")
            and resultado.get("st_responsabilidade_confirmada")
        )
        resultado["exige_revisao"] = not bool(resultado["confirmado"])
        if resultado["confirmado"]:
            resultado["status"] = "ICMS/MG CONFIRMADO PELO MOTOR ESTADUAL INTEGRADO"
        else:
            resultado["status"] = "ICMS/MG INTEGRADO — REVISAR SOMENTE PONTOS CONDICIONAIS"

        observacoes = [
            cls._limpar_observacao_legada(resultado.get("observacao")),
            cls._mensagem_fcp_integrado(resultado),
        ]
        if referencia["referencia"]:
            observacoes.append(f"Referência ST instalada: {referencia['referencia']}.")
        if referencia["atualizado_em"]:
            observacoes.append(f"Base ST/MG atualizada em {referencia['atualizado_em']}.")
        observacoes.append(
            "A MVA ajustada segue a fórmula geral do Anexo VII; benefícios ou regimes especiais individuais permanecem fora do cálculo automático."
        )
        resultado["observacao"] = " ".join(item for item in observacoes if item)
        if st_enquadrado_mg:
            resultado["fundamento_st"] = (
                f"{resultado.get('fundamento_st') or ''} | "
                "RICMS/MG/2023, Anexo VII — enquadramento e MVA ajustada"
            ).strip(" |")
            resultado["fonte_st"] = (
                f"{resultado.get('fonte_st') or ''} | {URL_ANEXO_VII_MG}"
            ).strip(" |")
        return resultado


__all__ = ["ICMSMGLoteIntegracaoService"]
