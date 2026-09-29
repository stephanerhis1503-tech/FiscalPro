"""Base nacional offline de NCM e TIPI da Sprint 16.4.

O pacote embarcado é derivado da planilha oficial da TIPI publicada pela
Receita Federal. Ele garante consulta sem internet e enriquece a descrição curta
do Classif com a hierarquia do produto, sem apagar códigos oficiais mais recentes
que já existam no banco do usuário.
"""

from __future__ import annotations

import gzip
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from src.core.caminhos import pasta_recursos
from src.inteligencia.base_oficial.repositorio import BaseOficialRepository


ARQUIVO_BASE_NACIONAL = (
    pasta_recursos()
    / "dados"
    / "bases_oficiais"
    / "base_ncm_tipi_2026_02_13.json.gz"
)


@dataclass(frozen=True)
class ResultadoBaseNacional:
    status: str
    versao: str = ""
    total_ncm: int = 0
    total_tipi: int = 0
    referencia: str = ""
    data_publicacao: str = ""
    mensagem: str = ""


class BaseNCMNacionalService:
    _lock = threading.Lock()
    _resultado_sessao: ResultadoBaseNacional | None = None

    @classmethod
    def garantir_instalada(cls, forcar: bool = False) -> ResultadoBaseNacional:
        """Instala ou enriquece a base uma única vez por sessão do FiscalPro."""
        if cls._resultado_sessao is not None and not forcar:
            return cls._resultado_sessao

        with cls._lock:
            if cls._resultado_sessao is not None and not forcar:
                return cls._resultado_sessao

            try:
                metadata = cls._ler_metadata()
                resumo = BaseOficialRepository.resumo_base_nacional()
                mesma_versao = str(resumo.get("versao") or "") == str(
                    metadata.get("versao") or ""
                )
                base_completa = (
                    int(resumo.get("total_ncm") or 0)
                    >= int(metadata.get("total_ncm") or 0)
                    and int(resumo.get("total_tipi") or 0)
                    >= int(metadata.get("total_tipi") or 0)
                )

                if mesma_versao and base_completa and not forcar:
                    cls._resultado_sessao = cls._resultado_do_resumo(
                        resumo, metadata, "Base nacional pronta para consulta offline."
                    )
                    return cls._resultado_sessao

                payload = cls._ler_payload()
                resultado = BaseOficialRepository.instalar_base_nacional(
                    payload["metadata"], payload["ncm"], payload["tipi"]
                )
                cls._resultado_sessao = ResultadoBaseNacional(
                    status="SUCESSO",
                    versao=str(resultado.get("versao") or ""),
                    total_ncm=int(resultado.get("total_ncm") or 0),
                    total_tipi=int(resultado.get("total_tipi") or 0),
                    referencia=str(metadata.get("referencia") or ""),
                    data_publicacao=str(metadata.get("data_publicacao") or ""),
                    mensagem=(
                        "Base nacional instalada e enriquecida sem alterar "
                        "cadastros tributários do usuário."
                    ),
                )
            except Exception as exc:
                resumo = BaseOficialRepository.resumo_base_nacional()
                possui_base = int(resumo.get("total_ncm") or 0) > 0
                cls._resultado_sessao = ResultadoBaseNacional(
                    status="PARCIAL" if possui_base else "ERRO",
                    versao=str(resumo.get("versao") or ""),
                    total_ncm=int(resumo.get("total_ncm") or 0),
                    total_tipi=int(resumo.get("total_tipi") or 0),
                    referencia=str(resumo.get("referencia") or ""),
                    data_publicacao=str(resumo.get("data_publicacao") or ""),
                    mensagem=f"Não foi possível preparar o pacote offline: {exc}",
                )
            return cls._resultado_sessao

    @staticmethod
    def _ler_payload() -> Dict[str, Any]:
        if not ARQUIVO_BASE_NACIONAL.is_file():
            raise FileNotFoundError(
                f"Pacote nacional não encontrado: {ARQUIVO_BASE_NACIONAL}"
            )
        with gzip.open(ARQUIVO_BASE_NACIONAL, "rt", encoding="utf-8") as arquivo:
            payload = json.load(arquivo)
        if not isinstance(payload, dict):
            raise ValueError("O pacote nacional possui formato inválido.")
        if not isinstance(payload.get("ncm"), list) or not isinstance(
            payload.get("tipi"), list
        ):
            raise ValueError("O pacote nacional não contém as tabelas NCM e TIPI.")
        return payload

    @staticmethod
    def _ler_metadata() -> Dict[str, Any]:
        if not ARQUIVO_BASE_NACIONAL.is_file():
            raise FileNotFoundError(
                f"Pacote nacional não encontrado: {ARQUIVO_BASE_NACIONAL}"
            )
        # O arquivo tem menos de 500 KB compactado; a leitura integral mantém a
        # implementação simples e ocorre somente uma vez por sessão.
        with gzip.open(ARQUIVO_BASE_NACIONAL, "rt", encoding="utf-8") as arquivo:
            payload = json.load(arquivo)
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("Metadados da base nacional não encontrados.")
        return metadata

    @staticmethod
    def _resultado_do_resumo(
        resumo: Dict[str, Any], metadata: Dict[str, Any], mensagem: str
    ) -> ResultadoBaseNacional:
        return ResultadoBaseNacional(
            status="SUCESSO",
            versao=str(resumo.get("versao") or metadata.get("versao") or ""),
            total_ncm=int(resumo.get("total_ncm") or 0),
            total_tipi=int(resumo.get("total_tipi") or 0),
            referencia=str(
                resumo.get("referencia") or metadata.get("referencia") or ""
            ),
            data_publicacao=str(
                resumo.get("data_publicacao")
                or metadata.get("data_publicacao")
                or ""
            ),
            mensagem=mensagem,
        )
