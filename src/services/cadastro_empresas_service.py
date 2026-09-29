"""Cadastro central de empresas do FiscalPro — versão 18.2.18.

A tabela histórica ``empresas_entregas`` é mantida como armazenamento para
preservar instalações existentes, mas passa a ser a fonte única de identidade
da empresa em todo o FiscalPro. Os demais módulos sincronizam seus dados
auxiliares (certificado/NSU, financeiro etc.) a partir deste cadastro.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from src.core.caminhos import BANCO_FINANCEIRO, PASTA_DADOS_INTERNOS
from src.entregas.servico import EntregasServico


class CadastroEmpresasService:
    REGIMES = EntregasServico.REGIMES
    EMPRESAS_BASE = EntregasServico.EMPRESAS_ATUAIS

    def __init__(self, entregas: EntregasServico | None = None):
        self.entregas = entregas or EntregasServico()
        # Garante a estrutura/base já aprovada sem apagar empresas manuais.
        self.entregas.sincronizar_estrutura_atual()
        # Consolida CNPJs que já tenham sido cadastrados em módulos antigos.
        self.migrar_dados_legados()

    @property
    def repositorio(self):
        return self.entregas.repositorio

    def listar(self, incluir_inativas: bool = True) -> list[dict[str, Any]]:
        return [dict(linha) for linha in self.repositorio.listar_empresas(incluir_inativas)]

    def obter(self, empresa_id: int) -> dict[str, Any] | None:
        linha = self.repositorio.obter_empresa_por_id(int(empresa_id))
        return dict(linha) if linha is not None else None

    def cadastrar(self, nome: str, cnpj: str, regime: str) -> int:
        empresa_id = self.entregas.cadastrar_empresa(nome, cnpj, regime)
        self.sincronizar_integracoes()
        return empresa_id

    def editar(self, empresa_id: int, nome: str, cnpj: str, regime: str) -> None:
        self.entregas.editar_empresa(empresa_id, nome, cnpj, regime)
        self.sincronizar_integracoes()

    def desativar(self, empresa_id: int) -> None:
        empresa = self.repositorio.obter_empresa_por_id(int(empresa_id))
        if empresa is None:
            raise ValueError("Empresa não localizada.")
        nomes_base = {nome.casefold() for nome, _ in self.EMPRESAS_BASE}
        if str(empresa["nome"]).casefold() in nomes_base:
            raise ValueError(
                "As empresas-base do grupo permanecem ativas no cadastro. "
                "Se precisar substituir uma delas, edite CNPJ e regime."
            )
        self.repositorio.desativar_empresa(int(empresa_id))
        self.sincronizar_integracoes()

    def reativar(self, empresa_id: int) -> None:
        empresa = self.repositorio.obter_empresa_por_id(int(empresa_id))
        if empresa is None:
            raise ValueError("Empresa não localizada.")
        self.repositorio.salvar_empresa(
            str(empresa["nome"]),
            cnpj=str(empresa["cnpj"] or ""),
            regime=str(empresa["regime"] or "A DEFINIR"),
            manual=bool(int(empresa["manual"] or 0)),
        )
        self.entregas._garantir_modelos_empresa(int(empresa_id))
        self.sincronizar_integracoes()

    @staticmethod
    def _somente_digitos(valor: object) -> str:
        return "".join(ch for ch in str(valor or "") if ch.isdigit())

    def _absorver_empresa_legada(self, nome: str, cnpj: str) -> bool:
        nome = " ".join(str(nome or "").split())
        cnpj = self._somente_digitos(cnpj)
        if not nome or len(cnpj) != 14:
            return False

        existente = self.repositorio.obter_empresa_por_nome(nome)
        if existente is not None:
            cnpj_atual = self._somente_digitos(existente["cnpj"])
            if not cnpj_atual:
                self.repositorio.atualizar_empresa(
                    int(existente["id"]),
                    nome=str(existente["nome"]),
                    cnpj=cnpj,
                    regime=str(existente["regime"] or "A DEFINIR"),
                )
                return True
            return False

        try:
            self.entregas.cadastrar_empresa(nome, cnpj, "A DEFINIR")
            return True
        except ValueError:
            return False

    @staticmethod
    def _linhas_sqlite(caminho: Path, sql: str) -> list[sqlite3.Row]:
        if not caminho.is_file():
            return []
        conexao: sqlite3.Connection | None = None
        try:
            conexao = sqlite3.connect(caminho, timeout=5)
            conexao.row_factory = sqlite3.Row
            return list(conexao.execute(sql).fetchall())
        except sqlite3.Error:
            return []
        finally:
            if conexao is not None:
                conexao.close()

    def migrar_dados_legados(self) -> int:
        """Traz CNPJs já existentes em NFS-e/Financeiro para o cadastro central.

        A migração é conservadora: só preenche CNPJ vazio ou cria empresa quando
        existe um CNPJ de 14 dígitos. Nunca sobrescreve um CNPJ central já salvo.
        """
        total = 0
        banco_nfse = PASTA_DADOS_INTERNOS / "nfse" / "nfse_nacional.db"
        for linha in self._linhas_sqlite(
            banco_nfse,
            "SELECT nome, cnpj FROM empresas_nfse ORDER BY id",
        ):
            total += int(self._absorver_empresa_legada(linha["nome"], linha["cnpj"]))

        for linha in self._linhas_sqlite(
            BANCO_FINANCEIRO,
            "SELECT nome, cnpj FROM empresas_financeiras WHERE ativa = 1 ORDER BY id",
        ):
            total += int(self._absorver_empresa_legada(linha["nome"], linha["cnpj"]))
        return total

    def sincronizar_integracoes(self) -> None:
        """Propaga identidade central sem tocar em documentos/lançamentos."""
        try:
            from src.financeiro.repositorio import ContasPagarRepositorio

            ContasPagarRepositorio().sincronizar_empresas_centralizadas()
        except Exception:
            # Uma integração indisponível não pode impedir o cadastro central.
            pass
        try:
            from src.nfse.repositorio import RepositorioNFSe

            RepositorioNFSe().sincronizar_empresas_centralizadas()
        except Exception:
            pass
