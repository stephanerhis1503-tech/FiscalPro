"""Consultas fiscais referenciais para a Auditoria Tributaria do SPED.

Somente leitura dos motores existentes de NCM/TIPI, PIS/Cofins e ICMS/MG.
Esta camada NAO cria regras na Ficha, NAO valida direito a credito, NAO
calcula imposto a recolher e NAO gera propostas de correcao de SPED.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from src.inteligencia.base_oficial.repositorio import BaseOficialRepository
from src.services.icms_mg_lote_integracao_service import ICMSMGLoteIntegracaoService
from src.services.piscofins_nacional_service import PISCOFINSNacionalService


def _texto(valor: Any) -> str:
    return str(valor if valor is not None else "").strip()


def _digitos(valor: Any) -> str:
    return "".join(c for c in _texto(valor) if c.isdigit())


class ReferenciasAuditoriaSPEDService:
    """Cacheia consultas iguais e preserva a origem de cada referencia."""

    def __init__(self) -> None:
        self._cache_ncm: dict[str, dict[str, Any]] = {}
        self._cache_pis: dict[tuple, dict[str, Any]] = {}
        self._cache_icms: dict[tuple, dict[str, Any]] = {}

    def consultar_item(
        self, ncm: str, descricao: str, contexto: dict[str, Any],
        ex_tipi: str = "",
    ) -> dict[str, Any]:
        codigo = _digitos(ncm)
        descricao = _texto(descricao)
        ex_tipi = _texto(ex_tipi)
        empresa = _texto(contexto.get("empresa"))
        regime = _texto(contexto.get("regime")).upper()
        operacao = _texto(contexto.get("operacao")).upper()
        finalidade = _texto(contexto.get("finalidade")).upper()
        origem = _texto(contexto.get("uf_origem")).upper()
        destino = _texto(contexto.get("uf_destino")).upper()
        data_op = _texto(contexto.get("data_operacao"))
        referencia: dict[str, Any] = {
            "ncm": codigo, "descricao": descricao, "ex_tipi": ex_tipi,
            "regime": regime, "operacao": operacao, "finalidade": finalidade,
            "uf_origem": origem, "uf_destino": destino,
            "data_operacao": data_op, "ncm_status": "NAO CONSULTADO",
            "ncm_descricao_oficial": "", "ncm_fonte": "",
            "tipi_status": "NAO CONSULTADA",
            "pis_status": "NAO CONSULTADO", "pis_confirmado": False,
            "pis_fundamento": "", "pis_fonte": "",
            "icms_status": "NAO CONSULTADO", "icms_confirmado": False,
            "st_status": "NAO CONSULTADO", "st_decisao_confirmada": False,
            "st_cest": "", "icms_fonte": "",
            "falha_tecnica": False,
            "restricao_uso": (
                "Consulta meramente referencial. Nao equivale a regra "
                "da Ficha nem confirma CST, base, credito, MVA ou imposto "
                "devido. Verificar finalidade, operacao e vigencia."
            ),
        }
        if len(codigo) != 8:
            referencia["ncm_status"] = "NCM INVALIDO PARA CONSULTA"
            return referencia

        if codigo not in self._cache_ncm:
            try:
                registro = BaseOficialRepository.buscar_ncm_oficial(codigo)
                tipi = BaseOficialRepository.buscar_tipi(codigo)
                self._cache_ncm[codigo] = {
                    "ncm_status": (
                        _texto(registro.get("status")) or "CADASTRO OFICIAL"
                        if registro else "NAO LOCALIZADO NA BASE INSTALADA"
                    ),
                    "ncm_descricao_oficial": (
                        _texto(registro.get("descricao_completa")
                               or registro.get("descricao")) if registro else ""
                    ),
                    "ncm_fonte": (
                        _texto(registro.get("fonte_codigo")) if registro else ""
                    ),
                    "tipi_status": (
                        "CONSULTA DISPONIVEL; EX/INCIDENCIA A CONFERIR"
                        if tipi else "NAO LOCALIZADA NA BASE INSTALADA"
                    ),
                    "falha_tecnica": False,
                }
            except Exception:
                self._cache_ncm[codigo] = {
                    "ncm_status": "FALHA NA CONSULTA DA BASE NCM",
                    "ncm_descricao_oficial": "",
                    "ncm_fonte": "",
                    "tipi_status": "BASE NAO DISPONIVEL",
                    "falha_tecnica": True,
                }
        referencia.update(self._cache_ncm[codigo])
        try:
            data_valida = bool(data_op and date.fromisoformat(data_op))
        except ValueError:
            data_valida = False

        if operacao == "ENTRADA" and not finalidade:
            # CFOP sem natureza confirmavel: consultar apenas NCM/TIPI.
            # Sem finalidade não se conclui PIS/COFINS, ICMS nem ST.
            referencia["pis_status"] = "REVISAR FINALIDADE ANTES DE PIS/COFINS"
            referencia["icms_status"] = "REVISAR FINALIDADE ANTES DE ICMS"
            referencia["st_status"] = "REVISAR FINALIDADE ANTES DE ICMS-ST"
            referencia["restricao_uso"] = (
                "Finalidade de entrada nao classificada pelo CFOP. "
                "Sem decisao de CST, credito ou ST; exige revisao documental."
            )
            return referencia
        if not regime or not operacao or not data_valida:
            referencia["pis_status"] = "REVISAR: INFORME REGIME/OPERACAO/DATA"
        else:
            contexto_pis = {
                "empresa": empresa, "regime": regime, "operacao": operacao,
                "finalidade": finalidade, "data_operacao": data_op,
            }
            chave = (codigo, descricao.upper(), ex_tipi, tuple(sorted(contexto_pis.items())))
            if chave not in self._cache_pis:
                try:
                    r = PISCOFINSNacionalService.analisar(
                        codigo, contexto=contexto_pis, descricao=descricao,
                        ex_tipi=ex_tipi,
                    )
                    self._cache_pis[chave] = {
                        "pis_status": _texto(r.get("status")) or "REVISAR",
                        "pis_confirmado": bool(r.get("confirmado")),
                        "pis_fundamento": _texto(r.get("fundamento")),
                        "pis_fonte": _texto(r.get("fonte_url")),
                        "falha_tecnica": False,
                    }
                except Exception:
                    self._cache_pis[chave] = {
                        "pis_status": "FALHA NA CONSULTA PIS/COFINS",
                        "pis_confirmado": False,
                        "pis_fundamento": "", "pis_fonte": "",
                        "falha_tecnica": True,
                    }
            falha_anterior = bool(referencia.get("falha_tecnica"))
            referencia.update(self._cache_pis[chave])
            referencia["falha_tecnica"] = (
                falha_anterior or bool(self._cache_pis[chave].get("falha_tecnica"))
            )
            # Mesmo quando o enquadramento legal e confirmado, nenhum credito
            # ou CST da entrada pode ser inferido por esta consulta isolada.

        if destino != "MG":
            referencia["icms_status"] = "ICMS/MG NAO CONSULTADO (DESTINO OUTRA UF)"
            referencia["st_status"] = "ST/MG NAO CONSULTADA (DESTINO OUTRA UF)"
        elif not origem or not data_valida:
            referencia["icms_status"] = "REVISAR: INFORME UF ORIGEM/DATA"
            referencia["st_status"] = "REVISAR: INFORME UF ORIGEM/DATA"
        else:
            ctx_icms = {
                "empresa": empresa, "regime": regime, "operacao": operacao,
                "finalidade": finalidade, "uf_origem": origem, "uf_destino": destino,
                "data_operacao": data_op,
            }
            chave_icms = (codigo, descricao.upper(), tuple(sorted(ctx_icms.items())))
            if chave_icms not in self._cache_icms:
                try:
                    r = ICMSMGLoteIntegracaoService.analisar(
                        codigo, contexto=ctx_icms, descricao=descricao,
                    )
                    self._cache_icms[chave_icms] = {
                        "icms_status": (
                            _texto(r.get("aliquota_operacao_status"))
                            or _texto(r.get("status")) or "REVISAR ICMS"
                        ),
                        "icms_confirmado": bool(r.get("aliquota_operacao_confirmada")),
                        "st_status": _texto(r.get("st_status")) or "REVISAR ST",
                        "st_decisao_confirmada": bool(r.get("st_decisao_confirmada")),
                        "st_cest": _digitos(r.get("cest")),
                        "icms_fonte": (
                            _texto(r.get("fonte_st")) or _texto(r.get("fonte_aliquota"))
                        ),
                        "falha_tecnica": False,
                    }
                except Exception:
                    self._cache_icms[chave_icms] = {
                        "icms_status": "FALHA NA CONSULTA ICMS/MG",
                        "icms_confirmado": False,
                        "st_status": "FALHA NA CONSULTA ST/MG",
                        "st_decisao_confirmada": False,
                        "st_cest": "", "icms_fonte": "", "falha_tecnica": True,
                    }
            falha_anterior = bool(referencia.get("falha_tecnica"))
            referencia.update(self._cache_icms[chave_icms])
            referencia["falha_tecnica"] = (
                falha_anterior or bool(self._cache_icms[chave_icms].get("falha_tecnica"))
            )
        return referencia
