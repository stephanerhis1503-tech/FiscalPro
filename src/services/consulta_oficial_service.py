"""Consulta resumida às bases oficiais já sincronizadas no FiscalPro.

Este serviço não transforma cadastro operacional em regra legal. Ele identifica
somente o que possui evidência oficial estruturada e sinaliza os pontos que ainda
precisam de validação fiscal.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Dict, List

from src.inteligencia.base_oficial.repositorio import BaseOficialRepository
from src.repositorios.ficha_tributaria_repository import FichaTributariaRepository
from src.services.atualizador_fontes_oficiais import AtualizadorFontesOficiais
from src.services.piscofins_monofasico_service import PISCOFINSMonofasicoService
from src.services.piscofins_nacional_service import PISCOFINSNacionalService
from src.services.icms_st_mg_service import ICMSSTMGService
from src.services.icms_mg_nacional_service import ICMSMGNacionalService
from src.services.icms_uf_service import ICMSUFService, UFS_COBERTURA
from src.services.empresas_regimes_service import EmpresasRegimesService


class ConsultaOficialService:
    @staticmethod
    def _normalizar_ncm(ncm: Any) -> str:
        codigo = "".join(c for c in str(ncm or "") if c.isdigit())
        if len(codigo) != 8:
            raise ValueError("O NCM deve possuir 8 dígitos.")
        return codigo

    @staticmethod
    def consultar(
        ncm: Any,
        contexto: Dict[str, Any] | None = None,
        descricao: str = "",
        ex_tipi: str = "",
    ) -> Dict[str, Any]:
        codigo = ConsultaOficialService._normalizar_ncm(ncm)
        contexto = EmpresasRegimesService.aplicar_contexto(contexto)

        # Registra o catálogo sem acessar a internet. A sincronização só ocorre
        # quando o usuário escolhe Atualizar bases oficiais.
        AtualizadorFontesOficiais.registrar_catalogo()

        cadastro = BaseOficialRepository.buscar_ncm_oficial(codigo)
        tipi = BaseOficialRepository.buscar_tipi(codigo)
        fontes = BaseOficialRepository.listar_fontes()
        evidencias = BaseOficialRepository.listar_evidencias(codigo)
        base_legal = FichaTributariaRepository.buscar_base_legal(codigo)
        piscofins_monofasico = PISCOFINSMonofasicoService.analisar(
            codigo, contexto=contexto, descricao=descricao, ex_tipi=ex_tipi
        )
        piscofins_nacional = PISCOFINSNacionalService.analisar(
            codigo, contexto=contexto, descricao=descricao, ex_tipi=ex_tipi
        )
        icms_st_mg = ICMSSTMGService.analisar(
            codigo, contexto=contexto, descricao=descricao
        )
        icms_mg = ICMSMGNacionalService.analisar(
            codigo, contexto=contexto, descricao=descricao
        )
        icms_uf: Dict[str, Any] = {}
        uf_destino = str(contexto.get("uf_destino") or "").strip().upper()
        if uf_destino in UFS_COBERTURA:
            try:
                icms_uf = ICMSUFService.analisar(codigo, contexto=contexto, descricao=descricao)
            except (ValueError, TypeError):
                icms_uf = {}

        ncm_confirmado = bool(cadastro and str(cadastro.get("status") or "").upper() == "ATIVO")
        normas_oficiais = [item for item in base_legal if int(item.get("origem_oficial") or 0)]

        ipi_principal = next((item for item in tipi if not str(item.get("ex_tipi") or "").strip()), None)
        if ipi_principal is None and len(tipi) == 1:
            ipi_principal = tipi[0]

        return {
            "ncm": codigo,
            "consultado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "ncm_confirmado": ncm_confirmado,
            "descricao_oficial": str(cadastro.get("descricao") or "") if cadastro else "",
            "status_ncm": str(cadastro.get("status") or "") if cadastro else "NÃO LOCALIZADO",
            "tipi": tipi,
            "ipi_principal": ipi_principal,
            "ipi_confirmado": bool(tipi),
            "base_legal": base_legal,
            "normas_oficiais": normas_oficiais,
            "evidencias": evidencias,
            "fontes": fontes,
            "icms_st_confirmado": bool(
                icms_uf.get("st_confirmado")
                if icms_uf and str(icms_uf.get("uf_destino") or "").upper() != "MG"
                else icms_st_mg.get("confirmado")
            ),
            "fontes_por_codigo": {item["codigo"]: item for item in fontes},
            "piscofins_monofasico": piscofins_monofasico,
            "piscofins_nacional": piscofins_nacional,
            "icms_st_mg": icms_st_mg,
            "icms_mg": icms_mg,
            "icms_uf": icms_uf,
        }


    @staticmethod
    def st_contextual(resultado: Dict[str, Any]) -> Dict[str, Any]:
        """Retorna o enquadramento ST da UF de destino quando houver motor estadual instalado."""
        resultado = dict(resultado or {})
        uf = dict(resultado.get("icms_uf") or {})
        destino = str(uf.get("uf_destino") or "").strip().upper()
        if uf and destino and destino != "MG":
            segmento = str(uf.get("segmento_st") or "").upper()
            modelo = str(uf.get("st_modelo_calculo") or "").upper()
            status_st = str(uf.get("st_status") or "").upper()
            fonte_codigo = ""
            fonte_nome = ""
            regra_aplicada = ""
            if destino == "RN":
                if "PNEUM" in segmento:
                    fonte_codigo = "SEFAZ_RN_ANEXO_007"
                    fonte_nome = "SEFAZ/RN — RICMS/RN, Anexo 007"
                    regra_aplicada = "ICMS-ST/RN — PNEUMÁTICOS — ANEXO 007"
                elif "ANEXO 005" in modelo or "ANTECIPA" in status_st:
                    fonte_codigo = "SEFAZ_RN_ANEXO_005"
                    fonte_nome = "SEFAZ/RN — RICMS/RN, Anexo 005"
                    regra_aplicada = "ANTECIPAÇÃO ICMS/RN — ANEXO 005"
            if destino == "MA":
                if "PNEUM" in segmento:
                    fonte_codigo = "SEFAZ_MA_RICMS"
                    fonte_nome = "SEFAZ/MA — RICMS/MA / Convênio ICMS 102/17"
                    regra_aplicada = "ICMS-ST/MA — PNEUMÁTICOS — CONVÊNIO 102/17"
                elif "AUTOPE" in segmento:
                    fonte_codigo = "SEFAZ_MA_RICMS"
                    fonte_nome = "SEFAZ/MA — RICMS/MA, Anexo 4.41"
                    regra_aplicada = "ICMS-ST/MA — AUTOPEÇAS — PROTOCOLO 41/08"
            if destino == "PI":
                if "PNEUM" in segmento:
                    fonte_codigo = "SEFAZ_PI_RICMS"
                    fonte_nome = "SEFAZ/PI — RICMS/PI, Anexo X, arts. 75-76"
                    regra_aplicada = "ICMS-ST/PI — PNEUMÁTICOS — CONVÊNIO 102/17"
                elif "AUTOPE" in segmento:
                    fonte_codigo = "SEFAZ_PI_RICMS"
                    fonte_nome = "SEFAZ/PI — RICMS/PI, Anexo X, arts. 93-94"
                    regra_aplicada = "ICMS-ST/PI — AUTOPEÇAS — PROTOCOLO 41/08"
            if destino == "TO":
                if "PNEUM" in segmento:
                    fonte_codigo = "SEFAZ_TO_ANEXO_XXI"
                    fonte_nome = "SEFAZ/TO — RICMS/TO, Anexo XXI / Convênio ICMS 102/17"
                    regra_aplicada = "ICMS-ST/TO — PNEUMÁTICOS — CONVÊNIO 102/17"
                elif "AUTOPE" in segmento:
                    fonte_codigo = "SEFAZ_TO_ANEXO_XXI"
                    fonte_nome = "SEFAZ/TO — RICMS/TO, Anexo XXI / Protocolo 97/10"
                    regra_aplicada = "ICMS-ST/TO — AUTOPEÇAS — PROTOCOLO 97/10"
            if destino == "AC":
                if "PNEUM" in segmento:
                    fonte_codigo = "SEFAZ_AC_IN_DIAT_01_2023"
                    fonte_nome = "SEFAZ/AC — IN DIAT 01/2023, Anexo I, segmento 16"
                    regra_aplicada = "ICMS-ST/AC — PNEUMÁTICOS — CONVÊNIO 102/17"
                elif "AUTOPE" in segmento:
                    fonte_codigo = "SEFAZ_AC_IN_DIAT_01_2023"
                    fonte_nome = "SEFAZ/AC — IN DIAT 01/2023, Anexo I, segmento 1"
                    regra_aplicada = "ICMS-ST/AC — AUTOPEÇAS — PROTOCOLO 41/08"
            if destino == "AM":
                if "PNEUM" in segmento:
                    fonte_codigo = "SEFAZ_AM_LEI_6108"
                    fonte_nome = "SEFAZ/AM — Lei 6.108/2022, Anexo XVI"
                    regra_aplicada = "ICMS-ST/AM — PNEUMÁTICOS — CONVÊNIO 102/17"
                elif "AUTOPE" in segmento:
                    fonte_codigo = "SEFAZ_AM_LEI_6108"
                    fonte_nome = "SEFAZ/AM — Lei 6.108/2022, Anexo III"
                    regra_aplicada = "ICMS-ST/AM — AUTOPEÇAS — PROTOCOLO 41/08"
            if destino == "AP":
                if "PNEUM" in segmento:
                    fonte_codigo = "SEFAZ_AP_RICMS"
                    fonte_nome = "SEFAZ/AP — RICMS/AP / Convênio ICMS 102/17"
                    regra_aplicada = "ICMS-ST/AP — PNEUMÁTICOS — CONVÊNIO 102/17"
                elif "AUTOPE" in segmento:
                    fonte_codigo = "SEFAZ_AP_RICMS"
                    fonte_nome = "SEFAZ/AP — RICMS/AP, art. 272-B"
                    regra_aplicada = "ICMS-ST/AP — AUTOPEÇAS — PROTOCOLO 41/08"
            if destino == "RO":
                fonte_codigo = "SEFIN_RO_DEC_29048"
                if "PNEUM" in segmento:
                    fonte_nome = "SEFIN/RO — Decreto 29.048/2024, Tabela XVI"
                    regra_aplicada = "ICMS-ST/RO — PNEUMÁTICOS — CONVÊNIO 102/17"
                elif "AUTOPE" in segmento:
                    fonte_nome = "SEFIN/RO — Decreto 29.048/2024, Tabela II"
                    regra_aplicada = "ICMS-ST/RO — AUTOPEÇAS — RESPONSABILIDADE LOCAL"
            if destino == "SE":
                if "PNEUM" in segmento:
                    fonte_codigo = "SEFAZ_SE_RICMS"
                    fonte_nome = "SEFAZ/SE — RICMS/SE, arts. 681 e 684"
                    regra_aplicada = "ICMS-ST/SE — PNEUMÁTICOS — CONVÊNIO 102/17"
                elif "AUTOPE" in segmento:
                    fonte_codigo = "SEFAZ_SE_RICMS"
                    fonte_nome = "SEFAZ/SE — RICMS/SE, arts. 681, 684 e 784 / Anexo IX"
                    if "ANTECIPA" in modelo or "ANTECIPA" in status_st:
                        regra_aplicada = "ANTECIPAÇÃO ICMS/SE — ART. 784, II, d"
                    else:
                        regra_aplicada = "ICMS-ST/SE — AUTOPEÇAS — PROTOCOLO 97/10"
            return {
                "encontrado": bool(uf.get("st_potencial")),
                "confirmado": bool(uf.get("st_confirmado")),
                "decisao_confirmada": bool(uf.get("st_decisao_confirmada")),
                "status": str(uf.get("st_status") or ""),
                "cest": str(uf.get("cest") or ""),
                "segmento": str(uf.get("segmento_st") or ""),
                "descricao_legal": str(uf.get("descricao_legal_st") or ""),
                "mva_original": uf.get("mva_original"),
                "mva_ajustada": uf.get("mva_ajustada"),
                "mva_aplicada": uf.get("mva_aplicada"),
                "mva_tipo": str(uf.get("mva_tipo") or ""),
                "st_modelo_calculo": str(uf.get("st_modelo_calculo") or ""),
                "carga_liquida_st": uf.get("carga_liquida_st"),
                "carga_liquida_status": str(uf.get("carga_liquida_status") or ""),
                "antecipacao_percentual": uf.get("antecipacao_percentual"),
                "antecipacao_status": str(uf.get("antecipacao_status") or ""),
                "responsabilidade": str(uf.get("st_responsabilidade") or ""),
                "acordo_status": str(uf.get("st_acordo_status") or ""),
                "fundamento_legal": str(uf.get("fundamento_st") or ""),
                "fonte_url": str(uf.get("fonte_st") or ""),
                "fonte_codigo": fonte_codigo,
                "fonte_nome": fonte_nome,
                "regra_aplicada": regra_aplicada,
                "observacao": str(uf.get("observacao") or ""),
                "uf": destino,
            }
        base = dict(resultado.get("icms_st_mg") or {})
        base.setdefault("uf", "MG")

        # 17.8.75 — em operação interna de MG com ST confirmado, a MVA
        # original estruturada é a margem efetivamente aplicável quando não
        # existe MVA ajustada separada para a operação.
        origem = str(base.get("uf_origem") or "").strip().upper()
        destino_mg = str(base.get("uf_destino") or "MG").strip().upper()
        if (
            bool(base.get("confirmado"))
            and origem == destino_mg == "MG"
            and base.get("mva_aplicada") is None
            and base.get("mva_original") is not None
        ):
            base["mva_aplicada"] = base.get("mva_original")
            base["mva_tipo"] = "MVA original — operação interna"

        return base

    @staticmethod
    def icms_contextual(resultado: Dict[str, Any]) -> Dict[str, Any]:
        """Normaliza o ICMS da operação para a UF efetivamente consultada."""
        resultado = dict(resultado or {})
        uf = dict(resultado.get("icms_uf") or {})
        destino = str(uf.get("uf_destino") or "").strip().upper()
        if uf and destino and destino != "MG":
            return {
                "aliquota_nominal": uf.get("aliquota_operacao"),
                "aliquota_status": str(uf.get("aliquota_operacao_status") or ""),
                "aliquota_confirmada": bool(uf.get("aliquota_operacao_confirmada")),
                "aliquota_interna_destino": uf.get("aliquota_interna_destino"),
                "aliquota_interna_status": str(uf.get("aliquota_interna_status") or ""),
                "st_confirmado": bool(uf.get("st_confirmado")),
                "confiabilidade_aliquota": float(uf.get("confiabilidade_aliquota") or 0.0),
                "fundamento_aliquota": str(uf.get("fundamento_aliquota") or ""),
                "fonte_aliquota": str(uf.get("fonte_aliquota") or ""),
                "uf": destino,
            }
        base = dict(resultado.get("icms_mg") or {})
        base.setdefault("uf", "MG")
        return base



    @staticmethod
    def _normalizar_texto(valor: Any) -> str:
        texto = str(valor or "").strip().upper()
        import unicodedata
        texto = "".join(
            c for c in unicodedata.normalize("NFD", texto)
            if unicodedata.category(c) != "Mn"
        )
        return " ".join(texto.split())

    @staticmethod
    def _valor_informado(valor: Any) -> bool:
        texto = ConsultaOficialService._normalizar_texto(valor)
        return texto not in {
            "", "-", "NONE", "NAO INFORMADO", "NAO DEFINIDO", "NAO LOCALIZADO"
        }

    @staticmethod
    def cfop_para_exibicao(
        resultado: Dict[str, Any],
        contexto: Dict[str, Any] | None = None,
        tributacao_atual: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Sugere CFOP sem transformar contexto incompleto em conclusão definitiva.

        O cadastro local prevalece quando contém CFOP real. Sem cadastro, a função
        usa apenas fatos já conhecidos na Ficha: tipo de operação, finalidade, UFs e
        enquadramento oficial em ICMS-ST. Quando a posição da empresa na ST ou a
        condição do destinatário ainda é necessária, exibe alternativas condicionais
        em vez de escolher silenciosamente um código.
        """
        contexto = dict(contexto or {})
        tributacao_atual = dict(tributacao_atual or {})

        cfop_local = str(tributacao_atual.get("CFOP") or "").strip()
        if ConsultaOficialService._valor_informado(cfop_local):
            return {
                "valor": cfop_local,
                "status": "CADASTRO LOCAL",
                "confiabilidade": 80.0,
                "observacao": "CFOP exibido conforme a regra/cadastro local mais aderente à operação.",
            }

        operacao = ConsultaOficialService._normalizar_texto(contexto.get("operacao"))
        finalidade = ConsultaOficialService._normalizar_texto(contexto.get("finalidade"))
        origem = ConsultaOficialService._normalizar_texto(contexto.get("uf_origem"))
        destino = ConsultaOficialService._normalizar_texto(contexto.get("uf_destino"))
        contribuinte = ConsultaOficialService._normalizar_texto(contexto.get("contribuinte"))

        eh_saida = any(chave in operacao for chave in ("VENDA", "SAIDA", "REVENDA"))
        if not eh_saida or not origem or not destino:
            return {
                "valor": "Não informado",
                "status": "REVISAR",
                "confiabilidade": 0.0,
                "observacao": "Informe uma operação de saída e as UFs de origem/destino para sugerir o CFOP.",
            }

        revenda = any(chave in finalidade for chave in ("REVENDA", "COMERCIALIZ")) or not finalidade
        if not revenda:
            return {
                "valor": "Não informado",
                "status": "REVISAR",
                "confiabilidade": 0.0,
                "observacao": "A finalidade informada não permite presumir que a mercadoria foi adquirida de terceiros.",
            }

        interna = origem == destino
        st = ConsultaOficialService.st_contextual(resultado)
        st_confirmado = bool(st.get("confirmado"))

        if interna and st_confirmado:
            return {
                "valor": "5405 / 5403 — condicional",
                "status": "CONDICIONAL",
                "confiabilidade": 65.0,
                "observacao": (
                    "Para revenda interna sujeita a ST: use 5405 quando o ICMS-ST já foi retido anteriormente; "
                    "use 5403 quando o estabelecimento for responsável pela retenção nesta saída. "
                    "Confirme a posição da empresa na substituição tributária antes de escriturar."
                ),
            }

        if interna:
            return {
                "valor": "5102",
                "status": "SUGESTÃO FORTE",
                "confiabilidade": 90.0,
                "observacao": "Venda interna de mercadoria adquirida ou recebida de terceiros, sem ST confirmada para a operação.",
            }

        if st_confirmado:
            return {
                "valor": "6403 / 6404 — revisar posição na ST",
                "status": "CONDICIONAL",
                "confiabilidade": 55.0,
                "observacao": (
                    "Na saída interestadual com ST, 6403 alcança venda de mercadoria adquirida de terceiros "
                    "na condição de contribuinte substituto; 6404 é restrito à condição de substituto quando "
                    "o imposto já tiver sido retido anteriormente. Para contribuinte substituído, não escolha "
                    "automaticamente um desses códigos: confirme a regra/protocolo da operação e da UF de destino."
                ),
            }

        if contribuinte in {"SIM", "CONTRIBUINTE"}:
            return {
                "valor": "6102",
                "status": "SUGESTÃO FORTE",
                "confiabilidade": 90.0,
                "observacao": "Venda interestadual de mercadoria adquirida de terceiros para destinatário contribuinte do ICMS.",
            }
        if contribuinte in {"NAO", "NAO CONTRIBUINTE"}:
            return {
                "valor": "6108",
                "status": "SUGESTÃO FORTE",
                "confiabilidade": 90.0,
                "observacao": "Venda interestadual de mercadoria adquirida de terceiros destinada a não contribuinte do ICMS.",
            }
        return {
            "valor": "6102 / 6108 — condicional",
            "status": "CONDICIONAL",
            "confiabilidade": 60.0,
            "observacao": "Confirme se o destinatário é contribuinte do ICMS: 6102 para contribuinte; 6108 para não contribuinte.",
        }

    @staticmethod
    def confianca_oficial_para_exibicao(
        resultado: Dict[str, Any],
        contexto: Dict[str, Any] | None = None,
        tributacao_atual: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Calcula segurança geral da análise oficial sem confundir ausência de regra local com ausência de evidência.

        O índice é de completude/rastreabilidade da análise exibida. Resultados
        condicionais continuam limitados à faixa MÉDIA, mesmo quando NCM, TIPI e ST
        estão confirmados.
        """
        resultado = dict(resultado or {})
        contexto = dict(contexto or {})
        tributacao_atual = dict(tributacao_atual or {})

        pontos = 0.0
        detalhes: list[str] = []

        if bool(resultado.get("ncm_confirmado")):
            pontos += 20.0
            detalhes.append("NCM oficial confirmado")

        if bool(resultado.get("ipi_confirmado")):
            pontos += 10.0
            detalhes.append("TIPI oficial localizada")

        icms = ConsultaOficialService.icms_contextual(resultado)
        confianca_icms = float(icms.get("confiabilidade_aliquota") or 0.0)
        if icms.get("aliquota_nominal") is not None:
            pontos += 20.0 * max(0.0, min(100.0, confianca_icms)) / 100.0
            detalhes.append(f"ICMS/{str(icms.get('uf') or 'MG').upper()} analisado ({confianca_icms:.0f}%)")

        st = ConsultaOficialService.st_contextual(resultado)
        icms_uf_ctx = dict(resultado.get("icms_uf") or {})
        st_nao_aplicavel = bool(st.get("nao_aplicavel")) or str(st.get("decisao_st") or "").strip().upper() == "NAO"
        if st_nao_aplicavel:
            pontos += 20.0
            detalhes.append("ICMS-ST não aplicável confirmado pela descrição legal")
        elif bool(st.get("confirmado")):
            pontos += 20.0
            detalhes.append("ICMS-ST/CEST/MVA confirmados")
        elif bool(st.get("encontrado")):
            pontos += 12.0
            detalhes.append("ICMS-ST localizado com revisão")

        pisco = dict(resultado.get("piscofins_nacional") or {})
        confianca_pisco = float(pisco.get("confiabilidade") or 0.0)
        if pisco:
            pontos += 20.0 * max(0.0, min(100.0, confianca_pisco)) / 100.0
            detalhes.append(f"PIS/COFINS analisado ({confianca_pisco:.0f}%)")

        cfop = ConsultaOficialService.cfop_para_exibicao(resultado, contexto, tributacao_atual)
        confianca_cfop = float(cfop.get("confiabilidade") or 0.0)
        pontos += 10.0 * max(0.0, min(100.0, confianca_cfop)) / 100.0
        if confianca_cfop > 0:
            detalhes.append(f"CFOP {cfop.get('status', '').lower()}")

        fcp_pendente = bool(
            icms_uf_ctx
            and str(icms_uf_ctx.get("uf_destino") or "").upper() != "MG"
            and not bool(icms_uf_ctx.get("fcp_confirmado"))
        )
        if fcp_pendente:
            detalhes.append("FCP/fundo estadual requer revisão")
        condicionais = (
            not bool(icms.get("aliquota_confirmada"))
            or not bool(pisco.get("confirmado"))
            or fcp_pendente
            or str(cfop.get("status") or "").upper() in {"CONDICIONAL", "REVISAR"}
        )
        if condicionais:
            pontos = min(pontos, 84.0)
        if not bool(resultado.get("ncm_confirmado")):
            pontos = min(pontos, 49.0)

        pontos = round(max(0.0, min(100.0, pontos)), 1)
        nivel = "ALTA" if pontos >= 85.0 else "MÉDIA" if pontos >= 65.0 else "BAIXA"
        return {
            "confiabilidade": pontos,
            "nivel": nivel,
            "detalhes": detalhes,
            "cfop": cfop,
            "condicional": condicionais,
        }

    @staticmethod
    def aplicar_confianca_oficial_ao_parecer(
        parecer: Any, resultado_consulta: Dict[str, Any]
    ) -> Any:
        if parecer is None:
            return parecer
        contexto = dict(getattr(parecer, "contexto", {}) or {})
        tributacao = dict(getattr(parecer, "tributacao_atual", {}) or {})
        seguranca = ConsultaOficialService.confianca_oficial_para_exibicao(
            resultado_consulta, contexto, tributacao
        )
        oficial = float(seguranca.get("confiabilidade") or 0.0)
        atual = float(getattr(parecer, "confiabilidade", 0.0) or 0.0)
        if oficial > atual:
            parecer.confiabilidade = oficial
            parecer.nivel_confiabilidade = str(seguranca.get("nivel") or "BAIXA")

        parecer.regras_aplicadas["seguranca_oficial_17_8_6"] = dict(seguranca)
        parecer.versao_motor = "17.8.6"

        confirmados: list[str] = []
        if resultado_consulta.get("ncm_confirmado"):
            confirmados.append("NCM")
        if resultado_consulta.get("ipi_confirmado"):
            confirmados.append("TIPI")
        icms = ConsultaOficialService.icms_contextual(resultado_consulta)
        if icms.get("aliquota_nominal") is not None:
            confirmados.append(f"ICMS/{str(icms.get('uf') or 'MG').upper()}")
        st = ConsultaOficialService.st_contextual(resultado_consulta)
        if bool(st.get("nao_aplicavel")) or str(st.get("decisao_st") or "").strip().upper() == "NAO":
            confirmados.append("ICMS-ST não aplicável pela descrição legal")
        elif st.get("confirmado"):
            confirmados.append("ICMS-ST/CEST/MVA")

        pisco = dict(resultado_consulta.get("piscofins_nacional") or {})
        mono = dict(resultado_consulta.get("piscofins_monofasico") or {})
        if bool(mono.get("exclusao_confirmada")):
            destinacao = str(mono.get("destinacao_identificada") or "aplicação informada")
            confirmados.append(f"monofásico excluído para {destinacao}")
        cfop = dict(seguranca.get("cfop") or {})
        pendentes: list[str] = []
        if pisco and not pisco.get("confirmado"):
            pendentes.append("PIS/COFINS permanece como sugestão condicional")
        if str(cfop.get("status") or "").upper() == "CONDICIONAL":
            pendentes.append("CFOP depende do contexto operacional")
        if not bool(icms.get("aliquota_confirmada")) and icms.get("aliquota_nominal") is not None:
            pendentes.append("alíquota/CST de ICMS requer conferência das exceções")

        trecho_confirmados = ", ".join(confirmados) if confirmados else "parte das bases oficiais"
        trecho_pendentes = (
            " Permanecem pontos condicionais: " + "; ".join(pendentes) + "."
            if pendentes else ""
        )
        if bool(tributacao.get("Revisão manual")):
            parecer.resumo_executivo = (
                f"Para o NCM {getattr(parecer, 'ncm', '')}, existe uma regra manual salva e preservada para o contexto. "
                f"O FiscalPro também confirmou {trecho_confirmados} nas bases sincronizadas para comparação."
                f"{trecho_pendentes} Segurança geral da análise: "
                f"{str(getattr(parecer, 'nivel_confiabilidade', 'BAIXA')).lower()} "
                f"({float(getattr(parecer, 'confiabilidade', 0.0)):.0f}%)."
            )
        else:
            parecer.resumo_executivo = (
                f"Para o NCM {getattr(parecer, 'ncm', '')}, o FiscalPro confirmou {trecho_confirmados} "
                f"nas bases sincronizadas, mesmo sem uma regra local completa para todo o contexto."
                f"{trecho_pendentes} Segurança geral da análise: "
                f"{str(getattr(parecer, 'nivel_confiabilidade', 'BAIXA')).lower()} "
                f"({float(getattr(parecer, 'confiabilidade', 0.0)):.0f}%)."
            )
        return parecer

    @staticmethod
    def aplicar_piscofins_ao_parecer(parecer: Any, resultado_consulta: Dict[str, Any]) -> Any:
        # Mantém o enriquecimento histórico do motor monofásico e, em seguida,
        # aplica a camada nacional. A segunda camada é a responsável por continuar
        # a análise no regime normal quando o código não pertence à Lei 10.485/2002.
        parecer = PISCOFINSMonofasicoService.aplicar_ao_parecer(
            parecer, dict(resultado_consulta.get("piscofins_monofasico") or {})
        )
        return PISCOFINSNacionalService.aplicar_ao_parecer(
            parecer, dict(resultado_consulta.get("piscofins_nacional") or {})
        )

    @staticmethod
    def aplicar_icms_st_mg_ao_parecer(parecer: Any, resultado_consulta: Dict[str, Any]) -> Any:
        uf = dict(resultado_consulta.get("icms_uf") or {})
        destino = str(uf.get("uf_destino") or "").strip().upper()
        if uf and destino and destino != "MG":
            if parecer is None:
                return parecer
            st = ConsultaOficialService.st_contextual(resultado_consulta)
            tributacao = dict(getattr(parecer, "tributacao_atual", {}) or {})
            revisao_manual = bool(tributacao.get("Revisão manual"))

            # A Ficha nasceu com a cobertura de MG como base local. Em uma consulta
            # para outra UF, conclusões e campos automáticos de MG não podem permanecer
            # como se fossem parte da decisão da operação. Regras manuais do usuário
            # continuam preservadas; removemos apenas o enriquecimento oficial de MG.
            if hasattr(parecer, "conclusoes"):
                parecer.conclusoes = [
                    item for item in list(parecer.conclusoes or [])
                    if "ICMS-ST DE MINAS GERAIS" not in str(item).upper()
                    and "ICMS-ST/MG" not in str(item).upper()
                ]
            if hasattr(parecer, "alertas"):
                parecer.alertas = [
                    item for item in list(parecer.alertas or [])
                    if "ICMS-ST/MG" not in str(item).upper()
                    and "MINAS GERAIS" not in str(item).upper()
                ]
            for chave in (
                "ICMS-ST oficial MG — comparação",
                "MVA ST oficial MG",
                "Âmbito ST MG",
                "Segmento ST MG",
            ):
                parecer.tributacao_atual.pop(chave, None)
            if st.get("encontrado"):
                cest = str(st.get("cest") or "").strip()
                cest_digitos = "".join(c for c in cest if c.isdigit())
                if cest_digitos and (not revisao_manual or not str(tributacao.get("CEST") or "").strip()):
                    parecer.dados_gerais["CEST"] = cest_digitos
                if not revisao_manual:
                    parecer.tributacao_atual["ICMS-ST"] = (
                        "SIM" if st.get("confirmado") else "REVISAR"
                    )
                parecer.tributacao_atual[f"CEST oficial {destino}"] = cest
                mva = st.get("mva_aplicada")
                if mva is not None:
                    parecer.tributacao_atual[f"MVA ST oficial {destino}"] = float(mva)
                parecer.tributacao_atual[f"Segmento ST {destino}"] = str(st.get("segmento") or "")
                fundamento = str(st.get("fundamento_legal") or "").strip()
                fonte = str(st.get("fonte_url") or "").strip()
                if fundamento and fundamento not in parecer.base_legal:
                    parecer.base_legal.append(fundamento)
                if fonte and fonte not in parecer.fontes:
                    parecer.fontes.append(fonte)
                conclusao = (
                    f"NCM analisado na cobertura ICMS-ST/{destino}: CEST {cest or 'não informado'}, "
                    f"status {str(st.get('status') or 'revisar')}."
                )
                if conclusao not in parecer.conclusoes:
                    parecer.conclusoes.insert(0, conclusao)
            parecer.regras_aplicadas["icms_uf_oficial"] = dict(uf)
            return parecer
        return ICMSSTMGService.aplicar_ao_parecer(
            parecer, dict(resultado_consulta.get("icms_st_mg") or {})
        )

    @staticmethod
    def aplicar_fontes_ao_parecer(parecer: Any, resultado_consulta: Dict[str, Any]) -> Any:
        parecer = ConsultaOficialService.aplicar_piscofins_ao_parecer(parecer, resultado_consulta)
        parecer = ConsultaOficialService.aplicar_icms_st_mg_ao_parecer(parecer, resultado_consulta)
        return ConsultaOficialService.aplicar_confianca_oficial_ao_parecer(parecer, resultado_consulta)

    @staticmethod
    def piscofins_para_exibicao(
        resultado: Dict[str, Any], tributacao_atual: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Escolhe o melhor resultado visível sem confundir ausência de monofásico com NCM inválido."""
        tributacao_atual = dict(tributacao_atual or {})
        nacional = dict(resultado.get("piscofins_nacional") or {})
        monofasico = dict(resultado.get("piscofins_monofasico") or {})

        def informado(valor: Any) -> bool:
            texto = str(valor or "").strip().upper()
            return texto not in {"", "-", "NONE", "NÃO INFORMADO", "NAO INFORMADO"}

        cst_pis_local = tributacao_atual.get("CST PIS")
        cst_cofins_local = tributacao_atual.get("CST COFINS")
        local_informado = informado(cst_pis_local) or informado(cst_cofins_local)

        if local_informado:
            return {
                "origem": "CADASTRO LOCAL",
                "sugerido": False,
                "confirmado": False,
                "cst_pis": str(cst_pis_local or ""),
                "aliquota_pis": tributacao_atual.get("PIS"),
                "cst_cofins": str(cst_cofins_local or ""),
                "aliquota_cofins": tributacao_atual.get("COFINS"),
                "status": str(nacional.get("status") or "Cadastro local"),
                "observacao": str(nacional.get("observacao") or "Tributação cadastrada localmente."),
                "fonte_url": str(nacional.get("fonte_url") or ""),
            }

        # 17.8.75 — quando o enquadramento depende de EX TIPI, a ficha deve
        # mostrar a condição em vez de PIS/COFINS simplesmente "não informado".
        enquadramento_mono = str(monofasico.get("enquadramento") or "").upper()
        if "EX TIPI" in enquadramento_mono and not bool(monofasico.get("confirmado")):
            descricao_legal = str(monofasico.get("descricao_legal") or "")
            ex_validos = re.findall(r"EX\s*(\d{1,2})", descricao_legal.upper())
            ex_validos = [str(int(x)).zfill(2) for x in ex_validos if x.isdigit()]
            ex_texto = ", ".join(ex_validos) or "indicado na legislação"
            return {
                "origem": "LEI 10.485/2002 — CONDICIONAL POR EX TIPI",
                "sugerido": False,
                "confirmado": False,
                "condicional_ex_tipi": True,
                "ex_tipi_validos": ex_validos,
                "cst_pis": "",
                "aliquota_pis": None,
                "cst_cofins": "",
                "aliquota_cofins": None,
                "status": "CONDICIONAL — CONFIRMAR EX TIPI",
                "observacao": (
                    f"Este NCM só entra no regime monofásico da Lei nº 10.485/2002 no EX {ex_texto}. "
                    "Se o EX aplicável for confirmado e a operação for revenda por comerciante, "
                    "PIS e COFINS ficam com CST 04 e alíquota 0%. Sem confirmação do EX, "
                    "não aplicar alíquota zero automaticamente; revisar a regra normal do regime."
                ),
                "fonte_url": str(monofasico.get("fonte_url") or nacional.get("fonte_url") or ""),
            }

        if bool(nacional.get("confirmado")):
            return {
                "origem": "MOTOR NACIONAL — CONFIRMADO",
                "sugerido": False,
                "confirmado": True,
                "cst_pis": str(nacional.get("cst_pis") or ""),
                "aliquota_pis": nacional.get("aliquota_pis"),
                "cst_cofins": str(nacional.get("cst_cofins") or ""),
                "aliquota_cofins": nacional.get("aliquota_cofins"),
                "status": str(nacional.get("status") or "CONFIRMADO"),
                "observacao": str(nacional.get("observacao") or ""),
                "fonte_url": str(nacional.get("fonte_url") or ""),
            }

        sugestao_pis = str(nacional.get("sugestao_cst_pis") or "").strip()
        sugestao_cofins = str(nacional.get("sugestao_cst_cofins") or "").strip()
        if sugestao_pis or sugestao_cofins:
            ncm_valido = bool(resultado.get("ncm_confirmado"))
            prefixo = (
                "NCM válido e localizado. " if ncm_valido
                else "Código analisado pelo motor. "
            )
            if bool(monofasico.get("exclusao_confirmada")):
                observacao = (
                    prefixo
                    + "O regime monofásico da Lei nº 10.485/2002 foi excluído para a aplicação informada. "
                    + str(monofasico.get("observacao") or "")
                    + " A tributação abaixo é a regra padrão do regime e continua sujeita às demais exceções: "
                    + str(nacional.get("observacao") or "")
                ).strip()
            else:
                observacao = (
                    prefixo
                    + "Não houve enquadramento automático no regime monofásico da Lei nº 10.485/2002. "
                    + str(nacional.get("observacao") or "")
                ).strip()
            return {
                "origem": "MOTOR NACIONAL — SUGESTÃO CONDICIONAL",
                "sugerido": True,
                "confirmado": False,
                "cst_pis": sugestao_pis,
                "aliquota_pis": nacional.get("sugestao_aliquota_pis"),
                "cst_cofins": sugestao_cofins,
                "aliquota_cofins": nacional.get("sugestao_aliquota_cofins"),
                "status": str(nacional.get("status") or "SUGESTÃO CONDICIONAL"),
                "observacao": observacao,
                "monofasico_excluido": bool(monofasico.get("exclusao_confirmada")),
                "destinacao_identificada": str(monofasico.get("destinacao_identificada") or ""),
                "fonte_url": str(nacional.get("fonte_url") or ""),
            }

        return {
            "origem": "REVISAR",
            "sugerido": False,
            "confirmado": False,
            "cst_pis": "",
            "aliquota_pis": None,
            "cst_cofins": "",
            "aliquota_cofins": None,
            "status": str(nacional.get("status") or monofasico.get("status") or "REVISÃO NECESSÁRIA"),
            "observacao": str(
                nacional.get("observacao")
                or monofasico.get("observacao")
                or "Revisar o enquadramento do produto e da operação."
            ),
            "fonte_url": str(nacional.get("fonte_url") or monofasico.get("fonte_url") or ""),
        }

    @staticmethod
    def icms_para_exibicao(
        resultado: Dict[str, Any], tributacao_atual: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Combina cadastro local e motor oficial sem inventar CST/CSOSN.

        O cadastro local continua prevalecendo quando possui CST/CSOSN real. Quando
        ele está vazio, mas o motor de MG já encontrou uma alíquota nominal, a tela
        passa a exibir essa alíquota e deixa o CST explicitamente pendente conforme
        a operação. Isso evita o falso ``CST Não informado • 0,00%`` ao lado de uma
        alíquota oficial já conhecida.
        """
        tributacao_atual = dict(tributacao_atual or {})
        oficial = ConsultaOficialService.icms_contextual(resultado)
        st = ConsultaOficialService.st_contextual(resultado)

        def texto_informado(valor: Any) -> bool:
            texto = str(valor or "").strip().upper()
            return texto not in {
                "", "-", "NONE", "NÃO INFORMADO", "NAO INFORMADO",
                "NÃO DEFINIDO", "NAO DEFINIDO",
            }

        def numero(valor: Any) -> Any:
            if valor in (None, "", "Não informado", "Nao informado"):
                return None
            try:
                texto = str(valor).strip().replace("%", "")
                if "," in texto:
                    texto = texto.replace(".", "").replace(",", ".")
                return float(texto)
            except (TypeError, ValueError):
                return None

        cst_local = tributacao_atual.get("CST/CSOSN ICMS")
        aliquota_local = numero(tributacao_atual.get("ICMS"))
        cst_local_informado = texto_informado(cst_local)

        if cst_local_informado:
            return {
                "origem": "CADASTRO LOCAL",
                "cst": str(cst_local).strip(),
                "cst_definido": True,
                "aliquota": aliquota_local,
                "aliquota_confirmada": False,
                "status": "CADASTRO LOCAL",
                "observacao": "CST/CSOSN e alíquota exibidos conforme o cadastro local.",
            }

        aliquota_oficial = numero(oficial.get("aliquota_nominal"))
        if aliquota_oficial is not None:
            status = str(oficial.get("aliquota_status") or "ALÍQUOTA NOMINAL ANALISADA")
            st_confirmado = bool(st.get("confirmado") or oficial.get("st_confirmado"))
            if st_confirmado:
                complemento = (
                    "Há enquadramento em ICMS-ST; o CST/CSOSN depende da posição da empresa "
                    "na operação (substituto ou substituído), da origem da mercadoria e do regime tributário."
                )
            else:
                complemento = (
                    "O CST/CSOSN depende do regime tributário, da origem da mercadoria, "
                    "do benefício/redução e da situação efetiva da operação."
                )
            return {
                "origem": f"ICMS/{oficial.get('uf') or 'MG'} OFICIAL",
                "cst": "",
                "cst_definido": False,
                "aliquota": aliquota_oficial,
                "aliquota_confirmada": bool(oficial.get("aliquota_confirmada")),
                "status": status,
                "observacao": (
                    f"Alíquota da operação para {oficial.get('uf') or 'MG'}: {status}. {complemento} "
                    "O FiscalPro não presume o CST automaticamente sem esse contexto."
                ),
            }

        if aliquota_local is not None and abs(aliquota_local) > 0.000001:
            return {
                "origem": "CADASTRO LOCAL — CST PENDENTE",
                "cst": "",
                "cst_definido": False,
                "aliquota": aliquota_local,
                "aliquota_confirmada": False,
                "status": "CST/CSOSN PENDENTE",
                "observacao": (
                    "Existe alíquota no cadastro local, mas o CST/CSOSN ainda não foi definido. "
                    "Revise o contexto da operação antes de aplicar."
                ),
            }

        return {
            "origem": "REVISAR",
            "cst": "",
            "cst_definido": False,
            "aliquota": None,
            "aliquota_confirmada": False,
            "status": str(oficial.get("aliquota_status") or "ICMS NÃO DETERMINADO"),
            "observacao": "O motor ainda não determinou alíquota e CST/CSOSN para esta operação.",
        }

    @staticmethod
    def texto_ipi(resultado: Dict[str, Any]) -> str:
        item = resultado.get("ipi_principal") or {}
        if not item:
            return "Não sincronizado"
        texto = str(item.get("aliquota_texto") or "").strip()
        if texto:
            return texto if "%" in texto or texto.upper() == "NT" else f"{texto}%"
        valor = item.get("aliquota")
        if valor is None:
            return "Não informado"
        return f"{float(valor):.2f}%".replace(".", ",")


    @staticmethod
    def ipi_para_exibicao(
        resultado: Dict[str, Any],
        tributacao_atual: Dict[str, Any] | None = None,
        contexto: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Separa a alíquota TIPI de referência do tratamento de IPI da operação."""
        resultado = dict(resultado or {})
        tributacao_atual = dict(tributacao_atual or {})
        contexto = dict(contexto or {})

        tipi_referencia = ConsultaOficialService.texto_ipi(resultado)
        cst = str(tributacao_atual.get("CST IPI") or "").strip()
        aliquota_bruta = tributacao_atual.get("IPI")

        aliquota_numero = None
        if aliquota_bruta not in (None, "", "Não informado"):
            try:
                aliquota_numero = float(str(aliquota_bruta).replace("%", "").replace(",", "."))
            except (TypeError, ValueError):
                aliquota_numero = None

        cst_exibicao = cst if ConsultaOficialService._valor_informado(cst) else "não informado"
        if aliquota_numero is None:
            aliquota_exibicao = "não informada"
        else:
            aliquota_exibicao = f"{aliquota_numero:.2f}%".replace(".", ",")

        tratamento_operacao = f"CST {cst_exibicao} • {aliquota_exibicao}"

        tipi_itens = list(resultado.get("tipi") or [])
        tem_ex_tipi = any(str(item.get("ex_tipi") or "").strip() for item in tipi_itens)
        observacao_tipi = (
            "Alíquota de referência da TIPI para o NCM. Não significa, sozinha, IPI devido ou destacado "
            "nesta operação."
        )
        if tem_ex_tipi or len(tipi_itens) > 1:
            observacao_tipi += " Há enquadramentos/EX TIPI; confira a descrição e o EX aplicável."

        operacao = ConsultaOficialService._normalizar_texto(contexto.get("operacao"))
        empresa = str(contexto.get("empresa") or "").strip()
        complemento_contexto = ""
        if empresa:
            complemento_contexto = f" Empresa: {empresa}."
        if operacao:
            complemento_contexto += f" Operação: {operacao.title()}."

        revisar_operacao = not ConsultaOficialService._valor_informado(cst) or aliquota_numero is None
        observacao_operacao = (
            "Tratamento informado pela regra/cadastro da operação. Não confundir com a alíquota TIPI de referência. "
            "Confirme a condição do estabelecimento (industrial, importador/equiparado, quando aplicável) e o "
            "enquadramento real da operação antes de escriturar."
            + complemento_contexto
        )

        diferenca = ConsultaOficialService.divergencia_ipi(resultado, aliquota_bruta)
        if diferenca:
            observacao_operacao += " " + diferenca

        return {
            "tipi_referencia": tipi_referencia,
            "tratamento_operacao": tratamento_operacao,
            "observacao_tipi": observacao_tipi,
            "observacao_operacao": observacao_operacao,
            "revisar_operacao": revisar_operacao,
            "cst": cst,
            "aliquota": aliquota_numero,
        }

    @staticmethod
    def revisao_para_exibicao(
        resultado: Dict[str, Any],
        parecer: Any,
        tributacao_atual: Dict[str, Any] | None = None,
        contexto: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Retorna motivos objetivos para o status de revisão da ficha."""
        resultado = dict(resultado or {})
        tributacao_atual = dict(tributacao_atual or {})
        contexto = dict(contexto or {})

        motivos: list[str] = []
        detalhes: list[str] = []

        def adicionar(rotulo: str, detalhe: str) -> None:
            if rotulo not in motivos:
                motivos.append(rotulo)
                detalhes.append(detalhe)

        if not bool(resultado.get("ncm_confirmado")):
            adicionar("NCM", "NCM não confirmado na base oficial sincronizada.")

        pisco = dict(resultado.get("piscofins_nacional") or {})
        icms = ConsultaOficialService.icms_contextual(resultado)
        st = ConsultaOficialService.st_contextual(resultado)
        tem_evidencia_oficial = any(
            (
                bool(resultado.get("ncm_confirmado")),
                bool(resultado.get("ipi_confirmado")),
                bool(pisco.get("confirmado")),
                icms.get("aliquota_nominal") is not None,
                bool(st.get("confirmado") or st.get("encontrado")),
            )
        )
        if not bool(resultado.get("normas_oficiais")) and not tem_evidencia_oficial:
            adicionar("BASE LEGAL", "Não há evidência oficial suficiente vinculada para fechar o contexto.")

        if pisco and not bool(pisco.get("confirmado")):
            mono = dict(resultado.get("piscofins_monofasico") or {})
            detalhe_pisco = str(pisco.get("observacao") or "PIS/COFINS permanece como sugestão condicional.")
            if bool(mono.get("exclusao_confirmada")):
                detalhe_pisco = (
                    f"Monofásico excluído para {mono.get('destinacao_identificada') or 'a aplicação informada'}: "
                    f"{mono.get('observacao') or ''} Tributação padrão ainda condicional: {detalhe_pisco}"
                ).strip()
            adicionar("PIS/COFINS", detalhe_pisco)

        if icms.get("aliquota_nominal") is not None and not bool(icms.get("aliquota_confirmada")):
            adicionar(
                "ICMS",
                str(
                    icms.get("aliquota_status")
                    or "Alíquota/CST de ICMS depende das exceções e do contexto da operação."
                ),
            )

        icms_uf_ctx = dict(resultado.get("icms_uf") or {})
        if (
            icms_uf_ctx
            and str(icms_uf_ctx.get("uf_destino") or "").upper() != "MG"
            and not bool(icms_uf_ctx.get("fcp_confirmado"))
        ):
            adicionar(
                "FCP/FUNDO",
                str(icms_uf_ctx.get("fcp_status") or "FCP/fundo estadual ainda não automatizado para esta UF."),
            )

        cfop = ConsultaOficialService.cfop_para_exibicao(resultado, contexto, tributacao_atual)
        if str(cfop.get("status") or "").upper() in {"CONDICIONAL", "REVISAR"}:
            adicionar(
                "CFOP",
                str(cfop.get("observacao") or "CFOP depende do contexto operacional."),
            )

        ipi = ConsultaOficialService.ipi_para_exibicao(resultado, tributacao_atual, contexto)
        if bool(ipi.get("revisar_operacao")):
            adicionar(
                "IPI OPERAÇÃO",
                "A TIPI foi consultada, mas o CST/alíquota do IPI da operação ainda não está completamente definido.",
            )

        regra = ConsultaOficialService._normalizar_texto(tributacao_atual.get("Regra aplicada"))
        regra_estadual_estruturada = bool(
            st.get("decisao_confirmada")
            and (
                str(st.get("fundamento_legal") or "").strip()
                or str(st.get("st_modelo_calculo") or "").strip()
                or str(st.get("regra_aplicada") or "").strip()
            )
        )
        if regra in {"", "NAO LOCALIZADA"} and not regra_estadual_estruturada:
            adicionar(
                "REGRA LOCAL",
                "Não há regra local completa aderente ao contexto; o resultado usa bases oficiais e sugestões condicionais.",
            )

        pendencias = list(getattr(parecer, "pendencias", []) or [])
        if pendencias and not motivos:
            adicionar("PENDÊNCIAS", str(pendencias[0]))

        confiabilidade = float(getattr(parecer, "confiabilidade", 0.0) or 0.0)
        if confiabilidade < 70 and "NCM" not in motivos:
            adicionar(
                "SEGURANÇA",
                f"Segurança geral da análise em {confiabilidade:.0f}%; confira os pontos indicados.",
            )

        return {
            "precisa_revisar": bool(motivos),
            "motivos": motivos,
            "detalhes": detalhes,
            "texto_curto": " • ".join(motivos[:4]),
        }

    @staticmethod
    def divergencia_ipi(resultado: Dict[str, Any], aliquota_local: Any) -> str:
        item = resultado.get("ipi_principal") or {}
        oficial = item.get("aliquota")
        if oficial is None or aliquota_local in (None, "", "Não informado"):
            return ""
        try:
            local = float(str(aliquota_local).replace("%", "").replace(",", "."))
        except (TypeError, ValueError):
            return ""
        if abs(float(oficial) - local) > 0.005:
            return (
                f"TIPI de referência: {float(oficial):.2f}%; regra da operação: {local:.2f}%. "
                "Essa diferença não é, por si só, erro: confirme EX TIPI, a condição do estabelecimento "
                "e o enquadramento da operação."
            ).replace(".", ",", 2)
        return ""
