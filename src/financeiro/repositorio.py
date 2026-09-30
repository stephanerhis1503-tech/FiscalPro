"""Persistência do módulo Contas a Pagar.

Os dados financeiros ficam em um banco separado dos dados fiscais para facilitar
backup, restauração e futuras integrações com o Robô FiscalPro.
"""

from __future__ import annotations

import sqlite3
import re
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

from src.core.caminhos import BANCO_FINANCEIRO
from src.services.empresas_regimes_service import EmpresasRegimesService

EMPRESAS_PADRAO = (
    "Mega Motos Trilha",
    "Mega Motos Comércio",
    "Mega Mix E-commerce",
    "Mega T.O. E-commerce",
    "Mega Serviços",
    "Mega Profissional",
)

CATEGORIAS_PADRAO = (
    "PRODUTOS REVENDA",
    "IMPOSTOS E GUIAS",
    "CONTABILIDADE",
    "FOLHA E ENCARGOS",
    "ALUGUEL",
    "ENERGIA",
    "ÁGUA",
    "INTERNET E TELEFONIA",
    "SERVIÇOS",
    "MANUTENÇÃO",
    "FRETES",
    "OUTROS",
)


class ContasPagarRepositorio:
    def __init__(self, banco: Path = BANCO_FINANCEIRO):
        self.banco = Path(banco)
        self.preparar_banco()

    @contextmanager
    def _conectar(self) -> Iterator[sqlite3.Connection]:
        self.banco.parent.mkdir(parents=True, exist_ok=True)
        conexao = sqlite3.connect(self.banco, timeout=30)
        conexao.row_factory = sqlite3.Row
        conexao.execute("PRAGMA foreign_keys = ON")
        try:
            yield conexao
            conexao.commit()
        except Exception:
            conexao.rollback()
            raise
        finally:
            conexao.close()

    def preparar_banco(self) -> None:
        agora = datetime.now().isoformat(timespec="seconds")
        with self._conectar() as conexao:
            conexao.executescript(
                """
                CREATE TABLE IF NOT EXISTS empresas_financeiras (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL UNIQUE,
                    cnpj TEXT NOT NULL DEFAULT '',
                    ativa INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS categorias_financeiras (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL UNIQUE,
                    ativa INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS fornecedores_financeiros (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    cnpj TEXT NOT NULL DEFAULT '',
                    ativa INTEGER NOT NULL DEFAULT 1,
                    criado_em TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS fornecedor_cnpjs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fornecedor_id INTEGER NOT NULL,
                    cnpj TEXT NOT NULL,
                    ativo INTEGER NOT NULL DEFAULT 1,
                    criado_em TEXT NOT NULL DEFAULT '',
                    UNIQUE(fornecedor_id, cnpj),
                    FOREIGN KEY(fornecedor_id) REFERENCES fornecedores_financeiros(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_fornecedor_cnpjs_fornecedor
                    ON fornecedor_cnpjs(fornecedor_id, ativo);

                CREATE TABLE IF NOT EXISTS contas_pagar (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empresa TEXT NOT NULL,
                    fornecedor TEXT NOT NULL,
                    fornecedor_cnpj TEXT NOT NULL DEFAULT '',
                    descricao TEXT NOT NULL DEFAULT '',
                    categoria TEXT NOT NULL DEFAULT 'OUTROS',
                    valor REAL NOT NULL,
                    vencimento TEXT NOT NULL,
                    data_pagamento TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'A VENCER',
                    numero_documento TEXT NOT NULL DEFAULT '',
                    competencia TEXT NOT NULL DEFAULT '',
                    origem TEXT NOT NULL DEFAULT 'MANUAL',
                    caminho_documento TEXT NOT NULL DEFAULT '',
                    robo_documento_id INTEGER,
                    observacoes TEXT NOT NULL DEFAULT '',
                    chave_duplicidade TEXT NOT NULL DEFAULT '',
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_contas_empresa_vencimento
                    ON contas_pagar(empresa, vencimento);
                CREATE INDEX IF NOT EXISTS idx_contas_status
                    ON contas_pagar(status);
                CREATE INDEX IF NOT EXISTS idx_contas_competencia
                    ON contas_pagar(competencia);
                CREATE INDEX IF NOT EXISTS idx_contas_chave_duplicidade
                    ON contas_pagar(chave_duplicidade);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_contas_robo_documento
                    ON contas_pagar(robo_documento_id)
                    WHERE robo_documento_id IS NOT NULL;

                CREATE TABLE IF NOT EXISTS fila_financeira (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    robo_documento_id INTEGER NOT NULL UNIQUE,
                    empresa TEXT NOT NULL DEFAULT '',
                    fornecedor TEXT NOT NULL DEFAULT '',
                    tipo_documento TEXT NOT NULL DEFAULT '',
                    numero_documento TEXT NOT NULL DEFAULT '',
                    vencimento TEXT NOT NULL DEFAULT '',
                    valor REAL,
                    competencia TEXT NOT NULL DEFAULT '',
                    caminho_documento TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'NOVO',
                    motivo TEXT NOT NULL DEFAULT '',
                    chave_duplicidade TEXT NOT NULL DEFAULT '',
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_fila_status
                    ON fila_financeira(status);

                CREATE TABLE IF NOT EXISTS historico_contas_pagar (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conta_id INTEGER,
                    acao TEXT NOT NULL,
                    detalhe TEXT NOT NULL DEFAULT '',
                    realizado_em TEXT NOT NULL,
                    FOREIGN KEY(conta_id) REFERENCES contas_pagar(id) ON DELETE SET NULL
                );
                """
            )
            conexao.executemany(
                "INSERT OR IGNORE INTO empresas_financeiras(nome, ativa) VALUES (?, 1)",
                [(nome,) for nome in EMPRESAS_PADRAO],
            )
            conexao.executemany(
                "INSERT OR IGNORE INTO categorias_financeiras(nome, ativa) VALUES (?, 1)",
                [(nome,) for nome in CATEGORIAS_PADRAO],
            )
            # Migra automaticamente fornecedores já usados em contas e na fila do robô.
            conexao.execute(
                """
                INSERT OR IGNORE INTO fornecedores_financeiros(nome, ativa, criado_em)
                SELECT DISTINCT TRIM(fornecedor), 1, ?
                FROM contas_pagar
                WHERE TRIM(fornecedor) <> ''
                """,
                (agora,),
            )
            conexao.execute(
                """
                INSERT OR IGNORE INTO fornecedores_financeiros(nome, ativa, criado_em)
                SELECT DISTINCT TRIM(fornecedor), 1, ?
                FROM fila_financeira
                WHERE TRIM(fornecedor) <> ''
                """,
                (agora,),
            )
            # Garante que bases antigas recebam campos das versões seguintes.
            self._garantir_coluna(
                conexao, "contas_pagar", "robo_documento_id", "INTEGER"
            )
            self._garantir_coluna(
                conexao, "contas_pagar", "chave_duplicidade", "TEXT NOT NULL DEFAULT ''"
            )
            self._garantir_coluna(
                conexao, "fornecedores_financeiros", "cnpj", "TEXT NOT NULL DEFAULT ''"
            )
            self._garantir_coluna(
                conexao, "contas_pagar", "fornecedor_cnpj", "TEXT NOT NULL DEFAULT ''"
            )

            # 17.8.114: um mesmo fornecedor pode possuir vários CNPJs.
            # Migra o CNPJ único das versões anteriores para a nova tabela sem perder dados.
            conexao.execute(
                """
                INSERT OR IGNORE INTO fornecedor_cnpjs(fornecedor_id, cnpj, ativo, criado_em)
                SELECT id, TRIM(cnpj), 1, ?
                FROM fornecedores_financeiros
                WHERE TRIM(COALESCE(cnpj, '')) <> ''
                """,
                (agora,),
            )
            # Contas antigas recebem o CNPJ legado somente quando ainda não possuem CNPJ próprio.
            conexao.execute(
                """
                UPDATE contas_pagar
                SET fornecedor_cnpj = COALESCE((
                    SELECT fc.cnpj
                    FROM fornecedor_cnpjs AS fc
                    JOIN fornecedores_financeiros AS f ON f.id = fc.fornecedor_id
                    WHERE f.nome = contas_pagar.fornecedor COLLATE NOCASE
                      AND fc.ativo = 1
                    LIMIT 1
                ), '')
                WHERE TRIM(COALESCE(fornecedor_cnpj, '')) = ''
                  AND (
                      SELECT COUNT(*)
                      FROM fornecedor_cnpjs AS fc2
                      JOIN fornecedores_financeiros AS f2 ON f2.id = fc2.fornecedor_id
                      WHERE f2.nome = contas_pagar.fornecedor COLLATE NOCASE
                        AND fc2.ativo = 1
                  ) = 1
                """
            )
            conexao.execute(
                "UPDATE contas_pagar SET atualizado_em = ? WHERE atualizado_em = ''",
                (agora,),
            )
            self._sincronizar_empresas_centralizadas_conexao(conexao)

    def _sincronizar_empresas_centralizadas_conexao(self, conexao: sqlite3.Connection) -> None:
        cadastros = EmpresasRegimesService.listar_cadastros(incluir_pessoas_fisicas=True)
        if not cadastros:
            return

        nomes_centrais: list[str] = []
        for empresa in cadastros:
            nome = " ".join(str(empresa.get("nome") or "").split())
            cnpj = self._somente_digitos(empresa.get("cnpj"))
            if not nome:
                continue
            nomes_centrais.append(nome)

            existente = None
            if len(cnpj) == 14:
                existente = conexao.execute(
                    "SELECT id, nome FROM empresas_financeiras WHERE cnpj = ? LIMIT 1",
                    (cnpj,),
                ).fetchone()
            if existente is None:
                existente = conexao.execute(
                    "SELECT id, nome FROM empresas_financeiras WHERE nome = ? COLLATE NOCASE LIMIT 1",
                    (nome,),
                ).fetchone()

            if existente is None:
                conexao.execute(
                    "INSERT INTO empresas_financeiras(nome, cnpj, ativa) VALUES (?, ?, 1)",
                    (nome, cnpj),
                )
                continue

            antigo = str(existente["nome"] or "")
            # Se a empresa manual foi renomeada no cadastro central, o CNPJ
            # permite transportar também o histórico financeiro para o novo nome.
            if antigo.casefold() != nome.casefold():
                conflito = conexao.execute(
                    "SELECT id FROM empresas_financeiras WHERE nome = ? COLLATE NOCASE AND id <> ?",
                    (nome, int(existente["id"])),
                ).fetchone()
                if conflito is None:
                    conexao.execute(
                        "UPDATE contas_pagar SET empresa = ? WHERE empresa = ? COLLATE NOCASE",
                        (nome, antigo),
                    )
                    conexao.execute(
                        "UPDATE fila_financeira SET empresa = ? WHERE empresa = ? COLLATE NOCASE",
                        (nome, antigo),
                    )
                    conexao.execute(
                        "UPDATE empresas_financeiras SET nome = ? WHERE id = ?",
                        (nome, int(existente["id"])),
                    )
            conexao.execute(
                "UPDATE empresas_financeiras SET cnpj = CASE WHEN ? <> '' THEN ? ELSE cnpj END, ativa = 1 WHERE id = ?",
                (cnpj, cnpj, int(existente["id"])),
            )

        # Cadastros antigos sem vínculo são escondidos, mas qualquer empresa já
        # usada em contas/fila permanece disponível para consulta histórica.
        if nomes_centrais:
            marcadores = ",".join("?" for _ in nomes_centrais)
            conexao.execute(
                f"""
                UPDATE empresas_financeiras
                   SET ativa = 0
                 WHERE nome COLLATE NOCASE NOT IN ({marcadores})
                   AND nome COLLATE NOCASE NOT IN (SELECT DISTINCT empresa FROM contas_pagar WHERE TRIM(empresa) <> '')
                   AND nome COLLATE NOCASE NOT IN (SELECT DISTINCT empresa FROM fila_financeira WHERE TRIM(empresa) <> '')
                """,
                nomes_centrais,
            )

    def sincronizar_empresas_centralizadas(self) -> None:
        with self._conectar() as conexao:
            self._sincronizar_empresas_centralizadas_conexao(conexao)

    @staticmethod
    def _garantir_coluna(
        conexao: sqlite3.Connection,
        tabela: str,
        coluna: str,
        definicao: str,
    ) -> None:
        colunas = {
            linha["name"]
            for linha in conexao.execute(f"PRAGMA table_info({tabela})").fetchall()
        }
        if coluna not in colunas:
            conexao.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")

    def listar_empresas(self) -> list[str]:
        with self._conectar() as conexao:
            self._sincronizar_empresas_centralizadas_conexao(conexao)
            linhas = conexao.execute(
                "SELECT nome FROM empresas_financeiras WHERE ativa = 1 ORDER BY nome"
            ).fetchall()
        return [str(linha["nome"]) for linha in linhas]

    def listar_categorias(self) -> list[str]:
        with self._conectar() as conexao:
            linhas = conexao.execute(
                "SELECT nome FROM categorias_financeiras WHERE ativa = 1 ORDER BY nome"
            ).fetchall()
        return [str(linha["nome"]) for linha in linhas]

    def salvar_categoria(self, nome: str) -> str:
        nome = " ".join((nome or "").strip().upper().split())
        if not nome:
            raise ValueError("Informe o nome da categoria.")
        with self._conectar() as conexao:
            conexao.execute(
                "INSERT INTO categorias_financeiras(nome, ativa) VALUES (?, 1) "
                "ON CONFLICT(nome) DO UPDATE SET ativa = 1",
                (nome,),
            )
        return nome

    def listar_fornecedores(self, busca: str = "") -> list[str]:
        parametros: list[object] = []
        filtro = ""
        if busca.strip():
            filtro = "AND nome LIKE ?"
            parametros.append(f"%{busca.strip()}%")
        with self._conectar() as conexao:
            linhas = conexao.execute(
                f"SELECT nome FROM fornecedores_financeiros "
                f"WHERE ativa = 1 {filtro} ORDER BY nome",
                parametros,
            ).fetchall()
        return [str(linha["nome"]) for linha in linhas]

    def salvar_fornecedor(self, nome: str) -> str:
        nome = " ".join((nome or "").strip().split())
        if not nome:
            raise ValueError("Informe o fornecedor ou beneficiário.")
        agora = datetime.now().isoformat(timespec="seconds")
        with self._conectar() as conexao:
            existente = conexao.execute(
                "SELECT nome FROM fornecedores_financeiros "
                "WHERE nome = ? COLLATE NOCASE LIMIT 1",
                (nome,),
            ).fetchone()
            if existente:
                nome_salvo = str(existente["nome"])
                conexao.execute(
                    "UPDATE fornecedores_financeiros SET ativa = 1 WHERE nome = ? COLLATE NOCASE",
                    (nome_salvo,),
                )
                return nome_salvo
            conexao.execute(
                "INSERT INTO fornecedores_financeiros(nome, ativa, criado_em) VALUES (?, 1, ?)",
                (nome, agora),
            )
        return nome

    @staticmethod
    def _somente_digitos(valor: object) -> str:
        return "".join(ch for ch in str(valor or "") if ch.isdigit())

    @classmethod
    def validar_cnpj(cls, valor: object) -> str:
        """Valida CNPJ e devolve somente os 14 dígitos. Vazio é permitido."""
        cnpj = cls._somente_digitos(valor)
        if not cnpj:
            return ""
        if len(cnpj) != 14:
            raise ValueError("CNPJ deve ter 14 dígitos.")
        if len(set(cnpj)) == 1:
            raise ValueError("CNPJ inválido.")

        def digito(base: str, pesos: tuple[int, ...]) -> str:
            total = sum(int(n) * p for n, p in zip(base, pesos))
            resto = total % 11
            return "0" if resto < 2 else str(11 - resto)

        d1 = digito(cnpj[:12], (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
        d2 = digito(cnpj[:12] + d1, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
        if cnpj[-2:] != d1 + d2:
            raise ValueError("CNPJ inválido. Confira os números digitados.")
        return cnpj

    def listar_cnpjs_fornecedor(self, nome: str) -> list[str]:
        nome = str(nome or "").strip()
        if not nome:
            return []
        with self._conectar() as conexao:
            linhas = conexao.execute(
                """
                SELECT fc.cnpj
                FROM fornecedor_cnpjs AS fc
                JOIN fornecedores_financeiros AS f ON f.id = fc.fornecedor_id
                WHERE f.nome = ? COLLATE NOCASE AND fc.ativo = 1
                ORDER BY fc.id
                """,
                (nome,),
            ).fetchall()
        return [str(linha["cnpj"] or "") for linha in linhas if str(linha["cnpj"] or "").strip()]

    def listar_fornecedores_cnpj(self, busca: str = "") -> list[sqlite3.Row]:
        parametros: list[object] = []
        filtro = ""
        termo = str(busca or "").strip()
        if termo:
            digitos = self._somente_digitos(termo)
            if digitos:
                filtro = (
                    "AND (f.nome LIKE ? OR EXISTS ("
                    "SELECT 1 FROM fornecedor_cnpjs AS fx "
                    "WHERE fx.fornecedor_id = f.id AND fx.ativo = 1 AND fx.cnpj LIKE ?))"
                )
                parametros.extend([f"%{termo}%", f"%{digitos}%"])
            else:
                filtro = "AND f.nome LIKE ?"
                parametros.append(f"%{termo}%")
        with self._conectar() as conexao:
            return conexao.execute(
                f"""
                SELECT f.id, f.nome,
                       COALESCE((
                           SELECT GROUP_CONCAT(fc.cnpj, ' | ')
                           FROM fornecedor_cnpjs AS fc
                           WHERE fc.fornecedor_id = f.id AND fc.ativo = 1
                       ), '') AS cnpj,
                       COALESCE((
                           SELECT COUNT(*)
                           FROM fornecedor_cnpjs AS fc2
                           WHERE fc2.fornecedor_id = f.id AND fc2.ativo = 1
                       ), 0) AS quantidade_cnpjs
                FROM fornecedores_financeiros AS f
                WHERE f.ativa = 1 {filtro}
                ORDER BY f.nome
                """,
                parametros,
            ).fetchall()

    def obter_cnpj_fornecedor(self, nome: str) -> str:
        cnpjs = self.listar_cnpjs_fornecedor(nome)
        return cnpjs[0] if len(cnpjs) == 1 else ""

    def salvar_cnpj_fornecedor(self, nome: str, cnpj: object) -> str:
        nome_salvo = self.salvar_fornecedor(nome)
        cnpj_digitos = self.validar_cnpj(cnpj)
        if not cnpj_digitos:
            raise ValueError("Informe o CNPJ que deseja adicionar ao fornecedor.")
        agora = datetime.now().isoformat(timespec="seconds")
        with self._conectar() as conexao:
            fornecedor = conexao.execute(
                "SELECT id, COALESCE(cnpj, '') AS cnpj FROM fornecedores_financeiros "
                "WHERE nome = ? COLLATE NOCASE LIMIT 1",
                (nome_salvo,),
            ).fetchone()
            if fornecedor is None:
                raise ValueError("Fornecedor não encontrado no cadastro.")
            fornecedor_id = int(fornecedor["id"])
            conexao.execute(
                "INSERT INTO fornecedor_cnpjs(fornecedor_id, cnpj, ativo, criado_em) "
                "VALUES (?, ?, 1, ?) "
                "ON CONFLICT(fornecedor_id, cnpj) DO UPDATE SET ativo = 1",
                (fornecedor_id, cnpj_digitos, agora),
            )
            # Mantém o campo legado preenchido para compatibilidade com módulos antigos,
            # mas o CNPJ correto de cada pagamento passa a ficar na própria conta.
            if not str(fornecedor["cnpj"] or "").strip():
                conexao.execute(
                    "UPDATE fornecedores_financeiros SET cnpj = ? WHERE id = ?",
                    (cnpj_digitos, fornecedor_id),
                )
        return cnpj_digitos

    @staticmethod
    def _normalizar_texto_chave(texto: object) -> str:
        valor = unicodedata.normalize("NFKD", str(texto or ""))
        valor = "".join(letra for letra in valor if not unicodedata.combining(letra))
        return re.sub(r"\s+", " ", valor).strip().upper()

    @staticmethod
    def _tabela_existe(conexao: sqlite3.Connection, tabela: str) -> bool:
        return conexao.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
            (tabela,),
        ).fetchone() is not None

    def _recalcular_chaves_fornecedor(
        self, conexao: sqlite3.Connection, fornecedor: str
    ) -> None:
        """Mantém a chave de duplicidade coerente depois de renomear fornecedor."""
        for tabela in ("contas_pagar", "fila_financeira"):
            if not self._tabela_existe(conexao, tabela):
                continue
            tem_cnpj = tabela == "contas_pagar"
            coluna_cnpj = ", fornecedor_cnpj" if tem_cnpj else ""
            linhas = conexao.execute(
                f"SELECT id, empresa, fornecedor, vencimento, valor, numero_documento{coluna_cnpj} "
                f"FROM {tabela} WHERE fornecedor = ? COLLATE NOCASE",
                (fornecedor,),
            ).fetchall()
            for linha in linhas:
                try:
                    valor = f"{float(linha['valor'] or 0):.2f}"
                except (TypeError, ValueError):
                    valor = "0.00"
                chave = "|".join(
                    (
                        self._normalizar_texto_chave(linha["empresa"]),
                        self._normalizar_texto_chave(linha["fornecedor"]),
                        str(linha["vencimento"] or ""),
                        valor,
                        self._normalizar_texto_chave(linha["numero_documento"]),
                        self._normalizar_texto_chave(linha["fornecedor_cnpj"] if tem_cnpj else ""),
                    )
                )
                conexao.execute(
                    f"UPDATE {tabela} SET chave_duplicidade = ? WHERE id = ?",
                    (chave, int(linha["id"])),
                )

    def resumo_uso_fornecedor(self, nome: str) -> dict[str, int]:
        """Conta referências antes de ocultar/excluir um fornecedor."""
        nome = str(nome or "").strip()
        if not nome:
            return {"contas": 0, "fila": 0, "agenda": 0, "total": 0}
        with self._conectar() as conexao:
            contas = int(conexao.execute(
                "SELECT COUNT(*) FROM contas_pagar WHERE fornecedor = ? COLLATE NOCASE",
                (nome,),
            ).fetchone()[0])
            fila = 0
            if self._tabela_existe(conexao, "fila_financeira"):
                fila = int(conexao.execute(
                    "SELECT COUNT(*) FROM fila_financeira WHERE fornecedor = ? COLLATE NOCASE",
                    (nome,),
                ).fetchone()[0])
            agenda = 0
            if self._tabela_existe(conexao, "agenda_faturas"):
                agenda = int(conexao.execute(
                    "SELECT COUNT(*) FROM agenda_faturas WHERE fornecedor = ? COLLATE NOCASE",
                    (nome,),
                ).fetchone()[0])
        return {"contas": contas, "fila": fila, "agenda": agenda, "total": contas + fila + agenda}

    def renomear_fornecedor(self, nome_atual: str, novo_nome: str) -> dict[str, object]:
        """Renomeia fornecedor e sincroniza contas, fila e agenda sem perder CNPJ."""
        nome_atual = " ".join(str(nome_atual or "").strip().split())
        novo_nome = " ".join(str(novo_nome or "").strip().split())
        if not nome_atual:
            raise ValueError("Selecione o fornecedor que deseja renomear.")
        if not novo_nome:
            raise ValueError("Informe o novo nome do fornecedor.")

        with self._conectar() as conexao:
            atual = conexao.execute(
                "SELECT id, nome, COALESCE(cnpj, '') AS cnpj FROM fornecedores_financeiros "
                "WHERE nome = ? COLLATE NOCASE LIMIT 1",
                (nome_atual,),
            ).fetchone()
            if atual is None:
                raise ValueError("Fornecedor não encontrado no cadastro.")
            nome_atual_real = str(atual["nome"] or nome_atual)

            # Alteração apenas de maiúsculas/minúsculas ou espaçamento: mantém o mesmo cadastro.
            if nome_atual_real.casefold() == novo_nome.casefold():
                conexao.execute(
                    "UPDATE fornecedores_financeiros SET nome = ?, ativa = 1 WHERE id = ?",
                    (novo_nome, int(atual["id"])),
                )
                nome_destino = novo_nome
                mesclado = False
            else:
                destino = conexao.execute(
                    "SELECT id, nome, COALESCE(cnpj, '') AS cnpj FROM fornecedores_financeiros "
                    "WHERE nome = ? COLLATE NOCASE LIMIT 1",
                    (novo_nome,),
                ).fetchone()
                if destino is not None:
                    cnpj_atual = str(atual["cnpj"] or "")
                    cnpj_destino = str(destino["cnpj"] or "")
                    nome_destino = str(destino["nome"] or novo_nome)
                    conexao.execute(
                        "UPDATE fornecedores_financeiros SET cnpj = ?, ativa = 1 WHERE id = ?",
                        (cnpj_destino or cnpj_atual, int(destino["id"])),
                    )
                    # Vários CNPJs são válidos para o mesmo fornecedor. Ao unir nomes,
                    # transfere todos os CNPJs cadastrados para o cadastro de destino.
                    conexao.execute(
                        "INSERT OR IGNORE INTO fornecedor_cnpjs(fornecedor_id, cnpj, ativo, criado_em) "
                        "SELECT ?, cnpj, ativo, criado_em FROM fornecedor_cnpjs WHERE fornecedor_id = ?",
                        (int(destino["id"]), int(atual["id"])),
                    )
                    mesclado = True
                else:
                    nome_destino = novo_nome
                    conexao.execute(
                        "UPDATE fornecedores_financeiros SET nome = ?, ativa = 1 WHERE id = ?",
                        (nome_destino, int(atual["id"])),
                    )
                    mesclado = False

            contas = conexao.execute(
                "UPDATE contas_pagar SET fornecedor = ?, atualizado_em = ? "
                "WHERE fornecedor = ? COLLATE NOCASE",
                (nome_destino, datetime.now().isoformat(timespec="seconds"), nome_atual_real),
            ).rowcount
            fila = 0
            if self._tabela_existe(conexao, "fila_financeira"):
                fila = conexao.execute(
                    "UPDATE fila_financeira SET fornecedor = ?, atualizado_em = ? "
                    "WHERE fornecedor = ? COLLATE NOCASE",
                    (nome_destino, datetime.now().isoformat(timespec="seconds"), nome_atual_real),
                ).rowcount
            agenda = 0
            if self._tabela_existe(conexao, "agenda_faturas"):
                agenda = conexao.execute(
                    "UPDATE agenda_faturas SET fornecedor = ? WHERE fornecedor = ? COLLATE NOCASE",
                    (nome_destino, nome_atual_real),
                ).rowcount

            if mesclado:
                conexao.execute(
                    "DELETE FROM fornecedores_financeiros WHERE id = ?",
                    (int(atual["id"]),),
                )

            self._recalcular_chaves_fornecedor(conexao, nome_destino)

        return {
            "nome": nome_destino,
            "mesclado": mesclado,
            "contas": int(contas or 0),
            "fila": int(fila or 0),
            "agenda": int(agenda or 0),
        }

    def excluir_fornecedor(self, nome: str) -> dict[str, object]:
        """Exclui cadastro sem uso; com histórico, apenas oculta para preservar lançamentos."""
        nome = str(nome or "").strip()
        if not nome:
            raise ValueError("Selecione o fornecedor que deseja excluir.")
        uso = self.resumo_uso_fornecedor(nome)
        with self._conectar() as conexao:
            linha = conexao.execute(
                "SELECT id, nome FROM fornecedores_financeiros "
                "WHERE nome = ? COLLATE NOCASE LIMIT 1",
                (nome,),
            ).fetchone()
            if linha is None:
                raise ValueError("Fornecedor não encontrado no cadastro.")
            if int(uso["total"]) > 0:
                conexao.execute(
                    "UPDATE fornecedores_financeiros SET ativa = 0 WHERE id = ?",
                    (int(linha["id"]),),
                )
                acao = "ocultado"
            else:
                conexao.execute(
                    "DELETE FROM fornecedores_financeiros WHERE id = ?",
                    (int(linha["id"]),),
                )
                acao = "excluido"
        return {"acao": acao, **uso}

    def listar_competencias(self) -> list[str]:
        with self._conectar() as conexao:
            linhas = conexao.execute(
                "SELECT DISTINCT competencia FROM contas_pagar "
                "WHERE competencia GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]' "
                "ORDER BY competencia"
            ).fetchall()
        return [str(linha["competencia"]) for linha in linhas]

    def inserir_conta(self, dados: dict[str, object]) -> int:
        agora = datetime.now().isoformat(timespec="seconds")
        campos = (
            "empresa", "fornecedor", "fornecedor_cnpj", "descricao", "categoria", "valor",
            "vencimento", "data_pagamento", "status", "numero_documento",
            "competencia", "origem", "caminho_documento", "robo_documento_id",
            "observacoes", "chave_duplicidade",
        )
        valores = [dados.get(campo) for campo in campos]
        with self._conectar() as conexao:
            cursor = conexao.execute(
                f"INSERT INTO contas_pagar({', '.join(campos)}, criado_em, atualizado_em) "
                f"VALUES ({', '.join('?' for _ in campos)}, ?, ?)",
                valores + [agora, agora],
            )
            conta_id = int(cursor.lastrowid)
            conexao.execute(
                "INSERT INTO historico_contas_pagar(conta_id, acao, detalhe, realizado_em) "
                "VALUES (?, 'CRIADA', ?, ?)",
                (conta_id, str(dados.get("origem") or "MANUAL"), agora),
            )
        return conta_id

    def atualizar_conta(self, conta_id: int, dados: dict[str, object]) -> None:
        campos = (
            "empresa", "fornecedor", "fornecedor_cnpj", "descricao", "categoria", "valor",
            "vencimento", "data_pagamento", "status", "numero_documento",
            "competencia", "origem", "caminho_documento", "robo_documento_id",
            "observacoes", "chave_duplicidade",
        )
        agora = datetime.now().isoformat(timespec="seconds")
        with self._conectar() as conexao:
            conexao.execute(
                f"UPDATE contas_pagar SET {', '.join(f'{campo} = ?' for campo in campos)}, "
                "atualizado_em = ? WHERE id = ?",
                [dados.get(campo) for campo in campos] + [agora, int(conta_id)],
            )
            conexao.execute(
                "INSERT INTO historico_contas_pagar(conta_id, acao, detalhe, realizado_em) "
                "VALUES (?, 'ALTERADA', '', ?)",
                (int(conta_id), agora),
            )

    def obter_conta(self, conta_id: int) -> sqlite3.Row | None:
        with self._conectar() as conexao:
            return conexao.execute(
                "SELECT * FROM contas_pagar WHERE id = ?", (int(conta_id),)
            ).fetchone()

    def excluir_conta(self, conta_id: int) -> None:
        agora = datetime.now().isoformat(timespec="seconds")
        with self._conectar() as conexao:
            # Se a conta veio da Agenda de Faturas, devolve o lembrete ao fluxo
            # operacional antes da exclusão. Bases antigas sem a tabela continuam
            # compatíveis.
            tabela_agenda = conexao.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'agenda_faturas_itens'"
            ).fetchone()
            if tabela_agenda:
                conexao.execute(
                    """
                    UPDATE agenda_faturas_itens
                    SET conta_id = NULL,
                        status = CASE WHEN TRIM(caminho_documento) <> ''
                                      THEN 'FATURA BAIXADA'
                                      ELSE 'AGUARDANDO FATURA' END,
                        lancada_em = '', concluida_em = '', atualizado_em = ?
                    WHERE conta_id = ?
                    """,
                    (agora, int(conta_id)),
                )
            conexao.execute("DELETE FROM contas_pagar WHERE id = ?", (int(conta_id),))

    def listar_contas(
        self,
        *,
        empresa: str = "",
        status: str = "",
        competencia: str = "",
        busca: str = "",
        limite: int = 10000,
    ) -> list[sqlite3.Row]:
        filtros: list[str] = []
        parametros: list[object] = []
        if empresa:
            filtros.append("empresa = ?")
            parametros.append(empresa)
        if status:
            filtros.append("status = ?")
            parametros.append(status)
        if competencia:
            filtros.append("competencia = ?")
            parametros.append(competencia)
        if busca:
            termo = f"%{busca.strip()}%"
            filtros.append(
                "(fornecedor LIKE ? OR descricao LIKE ? OR numero_documento LIKE ? "
                "OR observacoes LIKE ?)"
            )
            parametros.extend([termo, termo, termo, termo])
        where = "WHERE " + " AND ".join(filtros) if filtros else ""
        parametros.append(int(limite))
        with self._conectar() as conexao:
            return conexao.execute(
                f"""
                SELECT * FROM contas_pagar
                {where}
                ORDER BY CASE status WHEN 'VENCIDO' THEN 0 WHEN 'A VENCER' THEN 1 ELSE 2 END,
                         vencimento, empresa, fornecedor
                LIMIT ?
                """,
                parametros,
            ).fetchall()

    def listar_contas_periodo(
        self,
        inicio_iso: str,
        fim_iso: str,
        *,
        empresa: str = "",
        incluir_vencidas: bool = False,
    ) -> list[sqlite3.Row]:
        """Lista contas não pagas para um relatório de vencimentos.

        Quando ``incluir_vencidas`` estiver desmarcado, entram apenas as contas
        cujo vencimento está dentro do intervalo informado. Quando estiver
        marcado, também entram todas as contas não pagas anteriores à data
        inicial, até o fim do período selecionado.
        """

        filtros = ["data_pagamento = ''"]
        parametros: list[object] = []
        if incluir_vencidas:
            filtros.append("vencimento <= ?")
            parametros.append(fim_iso)
        else:
            filtros.append("vencimento BETWEEN ? AND ?")
            parametros.extend([inicio_iso, fim_iso])
        if empresa:
            filtros.append("empresa = ?")
            parametros.append(empresa)

        with self._conectar() as conexao:
            return conexao.execute(
                f"""
                SELECT * FROM contas_pagar
                WHERE {' AND '.join(filtros)}
                ORDER BY empresa, vencimento, fornecedor, id
                """,
                parametros,
            ).fetchall()

    def listar_contas_pagas_periodo(
        self,
        inicio_iso: str,
        fim_iso: str,
        *,
        empresas: tuple[str, ...] = (),
    ) -> list[sqlite3.Row]:
        """Lista contas pela data efetiva da baixa, incluindo o CNPJ do fornecedor."""

        filtros = ["TRIM(c.data_pagamento) <> ''", "c.data_pagamento BETWEEN ? AND ?"]
        parametros: list[object] = [inicio_iso, fim_iso]
        selecionadas = tuple(dict.fromkeys(str(nome).strip() for nome in empresas if str(nome).strip()))
        if selecionadas:
            filtros.append("c.empresa IN (" + ",".join("?" for _ in selecionadas) + ")")
            parametros.extend(selecionadas)

        with self._conectar() as conexao:
            return conexao.execute(
                f"""
                SELECT c.*,
                       CASE
                           WHEN TRIM(COALESCE(c.fornecedor_cnpj, '')) <> ''
                               THEN c.fornecedor_cnpj
                           WHEN (
                               SELECT COUNT(*)
                               FROM fornecedor_cnpjs AS fc
                               JOIN fornecedores_financeiros AS ff ON ff.id = fc.fornecedor_id
                               WHERE ff.nome = c.fornecedor COLLATE NOCASE AND fc.ativo = 1
                           ) = 1
                               THEN COALESCE((
                                   SELECT fc2.cnpj
                                   FROM fornecedor_cnpjs AS fc2
                                   JOIN fornecedores_financeiros AS ff2 ON ff2.id = fc2.fornecedor_id
                                   WHERE ff2.nome = c.fornecedor COLLATE NOCASE AND fc2.ativo = 1
                                   LIMIT 1
                               ), '')
                           ELSE ''
                       END AS fornecedor_cnpj_relatorio
                FROM contas_pagar AS c
                WHERE {' AND '.join(filtros)}
                ORDER BY c.data_pagamento, c.empresa, c.fornecedor, c.id
                """,
                parametros,
            ).fetchall()

    def atualizar_status_em_lote(self, hoje_iso: str) -> None:
        with self._conectar() as conexao:
            conexao.execute(
                "UPDATE contas_pagar SET status = 'PAGO' WHERE data_pagamento <> ''"
            )
            conexao.execute(
                "UPDATE contas_pagar SET status = 'VENCIDO' "
                "WHERE data_pagamento = '' AND vencimento < ?",
                (hoje_iso,),
            )
            conexao.execute(
                "UPDATE contas_pagar SET status = 'A VENCER' "
                "WHERE data_pagamento = '' AND vencimento >= ?",
                (hoje_iso,),
            )

    def localizar_duplicidades(
        self,
        chave: str,
        *,
        ignorar_id: int | None = None,
    ) -> list[sqlite3.Row]:
        if not chave:
            return []
        parametros: list[object] = [chave]
        complemento = ""
        if ignorar_id is not None:
            complemento = "AND id <> ?"
            parametros.append(int(ignorar_id))
        with self._conectar() as conexao:
            return conexao.execute(
                f"SELECT * FROM contas_pagar WHERE chave_duplicidade = ? {complemento} "
                "ORDER BY id",
                parametros,
            ).fetchall()

    def resumo(self, *, empresa: str = "", competencia: str = "") -> dict[str, float | int]:
        filtros: list[str] = []
        parametros: list[object] = []
        if empresa:
            filtros.append("empresa = ?")
            parametros.append(empresa)
        if competencia:
            filtros.append("competencia = ?")
            parametros.append(competencia)
        where = "WHERE " + " AND ".join(filtros) if filtros else ""
        with self._conectar() as conexao:
            linha = conexao.execute(
                f"""
                SELECT
                    COALESCE(SUM(valor), 0) AS total,
                    COALESCE(SUM(CASE WHEN status = 'PAGO' THEN valor ELSE 0 END), 0) AS pago,
                    COALESCE(SUM(CASE WHEN status = 'A VENCER' THEN valor ELSE 0 END), 0) AS a_vencer,
                    COALESCE(SUM(CASE WHEN status = 'VENCIDO' THEN valor ELSE 0 END), 0) AS vencido,
                    COUNT(*) AS quantidade
                FROM contas_pagar {where}
                """,
                parametros,
            ).fetchone()
        return {
            "total": float(linha["total"] or 0),
            "pago": float(linha["pago"] or 0),
            "a_vencer": float(linha["a_vencer"] or 0),
            "vencido": float(linha["vencido"] or 0),
            "quantidade": int(linha["quantidade"] or 0),
        }

    def resumo_proximos_dias(self, inicio_iso: str, fim_iso: str, empresa: str = "") -> float:
        filtros = ["status = 'A VENCER'", "vencimento BETWEEN ? AND ?"]
        parametros: list[object] = [inicio_iso, fim_iso]
        if empresa:
            filtros.append("empresa = ?")
            parametros.append(empresa)
        with self._conectar() as conexao:
            linha = conexao.execute(
                "SELECT COALESCE(SUM(valor), 0) AS total FROM contas_pagar WHERE "
                + " AND ".join(filtros),
                parametros,
            ).fetchone()
        return float(linha["total"] or 0)

    def inserir_ou_atualizar_fila(self, dados: dict[str, object]) -> int:
        agora = datetime.now().isoformat(timespec="seconds")
        campos = (
            "robo_documento_id", "empresa", "fornecedor", "tipo_documento",
            "numero_documento", "vencimento", "valor", "competencia",
            "caminho_documento", "status", "motivo", "chave_duplicidade",
        )
        valores = [dados.get(campo) for campo in campos]
        with self._conectar() as conexao:
            conexao.execute(
                f"INSERT INTO fila_financeira({', '.join(campos)}, criado_em, atualizado_em) "
                f"VALUES ({', '.join('?' for _ in campos)}, ?, ?) "
                "ON CONFLICT(robo_documento_id) DO UPDATE SET "
                "empresa = excluded.empresa, fornecedor = excluded.fornecedor, "
                "tipo_documento = excluded.tipo_documento, numero_documento = excluded.numero_documento, "
                "vencimento = excluded.vencimento, valor = excluded.valor, "
                "competencia = excluded.competencia, caminho_documento = excluded.caminho_documento, "
                "motivo = excluded.motivo, chave_duplicidade = excluded.chave_duplicidade, "
                "status = CASE WHEN fila_financeira.status IN ('IMPORTADO','IGNORADO','DUPLICADO') "
                "THEN fila_financeira.status ELSE excluded.status END, atualizado_em = excluded.atualizado_em",
                valores + [agora, agora],
            )
            linha = conexao.execute(
                "SELECT id FROM fila_financeira WHERE robo_documento_id = ?",
                (int(dados["robo_documento_id"]),),
            ).fetchone()
        return int(linha["id"])

    def listar_fila(
        self,
        statuses: Iterable[str] | None = None,
        limite: int = 2000,
    ) -> list[sqlite3.Row]:
        parametros: list[object] = []
        where = ""
        if statuses:
            lista = list(statuses)
            where = "WHERE status IN (" + ",".join("?" for _ in lista) + ")"
            parametros.extend(lista)
        parametros.append(int(limite))
        with self._conectar() as conexao:
            return conexao.execute(
                f"SELECT * FROM fila_financeira {where} "
                "ORDER BY CASE status WHEN 'REVISAR' THEN 0 WHEN 'NOVO' THEN 1 ELSE 2 END, "
                "vencimento, id DESC LIMIT ?",
                parametros,
            ).fetchall()

    def obter_fila(self, fila_id: int) -> sqlite3.Row | None:
        with self._conectar() as conexao:
            return conexao.execute(
                "SELECT * FROM fila_financeira WHERE id = ?", (int(fila_id),)
            ).fetchone()

    def atualizar_status_fila(self, fila_id: int, status: str, motivo: str = "") -> None:
        with self._conectar() as conexao:
            conexao.execute(
                "UPDATE fila_financeira SET status = ?, motivo = ?, atualizado_em = ? WHERE id = ?",
                (
                    status,
                    motivo,
                    datetime.now().isoformat(timespec="seconds"),
                    int(fila_id),
                ),
            )
