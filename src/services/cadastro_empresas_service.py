"""Cadastro central de empresas e pessoas do FiscalPro — versão 18.2.20.

A tabela histórica ``empresas_entregas`` é mantida como armazenamento para
preservar instalações existentes. Pessoas jurídicas alimentam os módulos
fiscais; pessoas físicas ficam disponíveis para usos administrativos, em
especial Contas a Pagar.
"""

from __future__ import annotations

import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

from src.core.caminhos import BANCO_FINANCEIRO, PASTA_DADOS_INTERNOS
from src.entregas.servico import EntregasServico


class CadastroEmpresasService:
    REGIMES = EntregasServico.REGIMES
    EMPRESAS_BASE = EntregasServico.EMPRESAS_ATUAIS
    TIPOS_PESSOA = ("PJ", "PF")

    def __init__(self, entregas: EntregasServico | None = None):
        self.entregas = entregas or EntregasServico()
        # Garante a estrutura/base já aprovada sem apagar cadastros manuais.
        self.entregas.sincronizar_estrutura_atual()
        # Consolida CNPJs que já tenham sido cadastrados em módulos antigos.
        self.migrar_dados_legados()

    @property
    def repositorio(self):
        return self.entregas.repositorio

    def listar(self, incluir_inativas: bool = True) -> list[dict[str, Any]]:
        return [
            dict(linha)
            for linha in self.repositorio.listar_empresas(
                incluir_inativas=incluir_inativas,
                incluir_pessoas_fisicas=True,
            )
        ]

    def obter(self, empresa_id: int) -> dict[str, Any] | None:
        linha = self.repositorio.obter_empresa_por_id(int(empresa_id))
        return dict(linha) if linha is not None else None

    @staticmethod
    def _somente_digitos(valor: object) -> str:
        return "".join(ch for ch in str(valor or "") if ch.isdigit())

    @staticmethod
    def _normalizar_nome(valor: object) -> str:
        texto = " ".join(str(valor or "").strip().split()).casefold()
        return "".join(
            c
            for c in unicodedata.normalize("NFD", texto)
            if unicodedata.category(c) != "Mn"
        )

    @classmethod
    def _normalizar_tipo(cls, tipo_pessoa: object) -> str:
        tipo = str(tipo_pessoa or "PJ").strip().upper()
        if tipo not in cls.TIPOS_PESSOA:
            raise ValueError("Selecione Pessoa Jurídica ou Pessoa Física.")
        return tipo

    @classmethod
    def _validar_documento(cls, documento: object, tipo_pessoa: str) -> str:
        documento_limpo = cls._somente_digitos(documento)
        esperado = 11 if tipo_pessoa == "PF" else 14
        nome = "CPF" if tipo_pessoa == "PF" else "CNPJ"
        if len(documento_limpo) != esperado:
            raise ValueError(f"Informe um {nome} válido com {esperado} dígitos.")
        return documento_limpo

    def _validar_duplicidade(
        self,
        nome: str,
        documento: str,
        *,
        excluir_id: int | None = None,
    ) -> None:
        chave_nome = self._normalizar_nome(nome)
        for cadastro in self.listar(incluir_inativas=True):
            cadastro_id = int(cadastro.get("id") or 0)
            if excluir_id is not None and cadastro_id == int(excluir_id):
                continue
            if self._normalizar_nome(cadastro.get("nome")) == chave_nome:
                situacao = "ativo" if int(cadastro.get("ativa") or 0) else "inativo"
                raise ValueError(
                    f"Já existe um cadastro {situacao} com esse nome: {cadastro.get('nome')}."
                )

        por_documento = self.repositorio.obter_empresa_por_documento(
            documento, excluir_id=excluir_id
        )
        if por_documento is not None:
            tipo = str(por_documento["tipo_pessoa"] or "PJ").upper()
            rotulo = "CPF" if tipo == "PF" else "CNPJ"
            raise ValueError(
                f"Este {rotulo} já está cadastrado para {por_documento['nome']}. "
                "Edite ou reative o cadastro existente."
            )

    def cadastrar(
        self,
        nome: str,
        documento: str,
        regime: str,
        tipo_pessoa: str = "PJ",
    ) -> int:
        nome = " ".join(str(nome or "").strip().split())
        if not nome:
            raise ValueError("Informe o nome/razão social.")
        tipo = self._normalizar_tipo(tipo_pessoa)
        documento_limpo = self._validar_documento(documento, tipo)
        self._validar_duplicidade(nome, documento_limpo)

        if tipo == "PF":
            empresa_id = self.repositorio.salvar_empresa(
                nome,
                cnpj=documento_limpo,
                regime="NÃO SE APLICA",
                tipo_pessoa="PF",
                manual=True,
            )
        else:
            empresa_id = self.entregas.cadastrar_empresa(nome, documento_limpo, regime)
        self.sincronizar_integracoes()
        return empresa_id

    def editar(
        self,
        empresa_id: int,
        nome: str,
        documento: str,
        regime: str,
        tipo_pessoa: str = "PJ",
    ) -> None:
        empresa = self.repositorio.obter_empresa_por_id(int(empresa_id))
        if empresa is None:
            raise ValueError("Cadastro não localizado.")

        tipo_atual = str(empresa["tipo_pessoa"] or "PJ").upper()
        tipo = self._normalizar_tipo(tipo_pessoa)
        if tipo != tipo_atual:
            raise ValueError(
                "O tipo Pessoa Física/Pessoa Jurídica não pode ser alterado depois do cadastro. "
                "Exclua este cadastro e crie outro com o tipo correto."
            )

        nome = " ".join(str(nome or "").strip().split())
        if not nome:
            raise ValueError("Informe o nome/razão social.")
        documento_limpo = self._validar_documento(documento, tipo)
        self._validar_duplicidade(
            nome,
            documento_limpo,
            excluir_id=int(empresa_id),
        )

        if tipo == "PF":
            self.repositorio.atualizar_empresa(
                int(empresa_id),
                nome=nome,
                cnpj=documento_limpo,
                regime="NÃO SE APLICA",
                tipo_pessoa="PF",
            )
        else:
            self.entregas.editar_empresa(int(empresa_id), nome, documento_limpo, regime)
        self.sincronizar_integracoes()

    def _eh_empresa_base_protegida(self, empresa: sqlite3.Row | dict[str, Any]) -> bool:
        if int(empresa["manual"] or 0):
            return False
        nomes_base = {self._normalizar_nome(nome) for nome, _ in self.EMPRESAS_BASE}
        return self._normalizar_nome(empresa["nome"]) in nomes_base

    def desativar(self, empresa_id: int) -> None:
        empresa = self.repositorio.obter_empresa_por_id(int(empresa_id))
        if empresa is None:
            raise ValueError("Cadastro não localizado.")
        if self._eh_empresa_base_protegida(empresa):
            raise ValueError(
                "As empresas-base do grupo permanecem ativas no cadastro. "
                "Se precisar substituir uma delas, edite CNPJ e regime."
            )
        self.repositorio.desativar_empresa(int(empresa_id))
        self.sincronizar_integracoes()

    def reativar(self, empresa_id: int) -> None:
        empresa = self.repositorio.obter_empresa_por_id(int(empresa_id))
        if empresa is None:
            raise ValueError("Cadastro não localizado.")
        tipo = str(empresa["tipo_pessoa"] or "PJ").upper()
        documento = self._somente_digitos(empresa["cnpj"])
        self._validar_duplicidade(
            str(empresa["nome"]), documento, excluir_id=int(empresa_id)
        )
        self.repositorio.salvar_empresa(
            str(empresa["nome"]),
            cnpj=documento,
            regime=str(empresa["regime"] or ("NÃO SE APLICA" if tipo == "PF" else "A DEFINIR")),
            tipo_pessoa=tipo,
            manual=bool(int(empresa["manual"] or 0)),
        )
        if tipo == "PJ":
            self.entregas._garantir_modelos_empresa(int(empresa_id))
        self.sincronizar_integracoes()

    def excluir(self, empresa_id: int) -> None:
        empresa = self.repositorio.obter_empresa_por_id(int(empresa_id))
        if empresa is None:
            raise ValueError("Cadastro não localizado.")
        if self._eh_empresa_base_protegida(empresa):
            raise ValueError(
                "Esta é uma empresa-base do FiscalPro e não pode ser excluída. "
                "Cadastros duplicados/manuais podem ser excluídos normalmente."
            )
        self.repositorio.excluir_empresa(int(empresa_id))
        self.sincronizar_integracoes()

    def _absorver_empresa_legada(self, nome: str, cnpj: str) -> bool:
        nome = " ".join(str(nome or "").split())
        cnpj = self._somente_digitos(cnpj)
        if not nome or len(cnpj) != 14:
            return False

        existente = self.repositorio.obter_empresa_por_nome(nome)
        if existente is not None:
            cnpj_atual = self._somente_digitos(existente["cnpj"])
            if not cnpj_atual:
                outro = self.repositorio.obter_empresa_por_documento(
                    cnpj, excluir_id=int(existente["id"])
                )
                if outro is not None:
                    return False
                self.repositorio.atualizar_empresa(
                    int(existente["id"]),
                    nome=str(existente["nome"]),
                    cnpj=cnpj,
                    regime=str(existente["regime"] or "A DEFINIR"),
                    tipo_pessoa="PJ",
                )
                return True
            return False

        if self.repositorio.obter_empresa_por_documento(cnpj) is not None:
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
        existe um CNPJ de 14 dígitos. Nunca sobrescreve um documento central já salvo.
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
        """Propaga a identidade central sem tocar em documentos/lançamentos."""
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
