"""Serviço seguro de backup e restauração do FiscalPro.

Os arquivos persistentes são armazenados em um ZIP com manifesto e hashes
SHA-256. Bancos SQLite são copiados pela API de backup do próprio SQLite,
permitindo criar uma cópia consistente mesmo com o FiscalPro aberto.
"""

from __future__ import annotations

import gc
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import zipfile
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable

from src.core.app_info import NOME_APP, VERSAO_APP
from src.core.caminhos import (
    RAIZ_DADOS,
    esta_empacotado,
    localizar_melhor_banco_financeiro_legacy,
)

FORMATO_BACKUP = 1
ARQUIVO_MANIFESTO = "manifesto.json"
PREFIXO_DADOS = "dados_app"
PREFIXO_DOCUMENTOS = "documentos_robo"
CORRECAO_WINDOWS_15_5_6 = True
CAMINHO_BANCO_FINANCEIRO = f"{PREFIXO_DADOS}/dados/financeiro/contas_pagar.db"


class BackupInvalidoError(ValueError):
    """Indica que o arquivo selecionado não é um backup íntegro do FiscalPro."""


@dataclass(frozen=True, slots=True)
class ResultadoBackup:
    caminho: Path
    quantidade_arquivos: int
    tamanho_bytes: int
    inclui_documentos: bool
    tipo: str
    contas_pagar: int | None = None


class ServicoBackup:
    """Cria, valida e restaura backups do FiscalPro."""

    def __init__(
        self,
        raiz_dados: str | Path | None = None,
        pasta_backups: str | Path | None = None,
        pasta_documentos: str | Path | None = None,
    ) -> None:
        self.raiz_dados = Path(raiz_dados or RAIZ_DADOS).expanduser().resolve()
        self.pasta_backups = Path(
            pasta_backups or (self.raiz_dados / "backups")
        ).expanduser().resolve()
        self._pasta_documentos_informada = (
            Path(pasta_documentos).expanduser().resolve() if pasta_documentos else None
        )
        self.banco_financeiro = (
            self.raiz_dados / "dados" / "financeiro" / "contas_pagar.db"
        )

    @property
    def pasta_manuais(self) -> Path:
        return self.pasta_backups / "manuais"

    @property
    def pasta_automaticos(self) -> Path:
        return self.pasta_backups / "automaticos"

    @property
    def pasta_seguranca(self) -> Path:
        return self.pasta_backups / "seguranca"

    def preparar(self) -> None:
        for pasta in (
            self.pasta_backups,
            self.pasta_manuais,
            self.pasta_automaticos,
            self.pasta_seguranca,
        ):
            pasta.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _perfil_usuario_atual() -> Path:
        """Retorna o perfil do Windows atual sem depender de caminhos do PC antigo."""
        valor = str(os.environ.get("USERPROFILE", "")).strip()
        if valor:
            return Path(valor).expanduser()
        return Path.home()

    @classmethod
    def _remapear_caminho_de_outro_perfil(cls, caminho: str | Path) -> Path:
        r"""Migra C:\Users\usuario_antigo\... para o usuário Windows atual.

        Backups são portáteis entre computadores. Caminhos absolutos guardados em
        configurações não podem obrigar a restauração a acessar o perfil antigo.
        """
        texto = str(caminho or "").strip()
        if not texto:
            return cls._perfil_usuario_atual()

        # PureWindowsPath entende corretamente caminhos C:\\Users\... mesmo
        # quando este método é exercitado por testes fora do Windows.
        try:
            win = PureWindowsPath(texto)
            partes = win.parts
            if (
                len(partes) >= 3
                and partes[1].casefold() == "users"
                and str(partes[0]).endswith("\\")
            ):
                perfil = cls._perfil_usuario_atual()
                perfil_texto = str(perfil)
                perfil_win = PureWindowsPath(perfil_texto)
                nome_perfil = (
                    perfil_win.name if perfil_win.drive else perfil.name
                )
                if partes[2].casefold() != nome_perfil.casefold():
                    if perfil_win.drive:
                        return Path(str(perfil_win.joinpath(*partes[3:])))
                    return perfil.joinpath(*partes[3:])
        except (OSError, ValueError, TypeError):
            pass

        return Path(texto).expanduser()

    def obter_pasta_documentos(self) -> Path:
        if self._pasta_documentos_informada is not None:
            return self._remapear_caminho_de_outro_perfil(
                self._pasta_documentos_informada
            )

        config = self.raiz_dados / "dados" / "robo_email" / "config.json"
        try:
            dados = json.loads(config.read_text(encoding="utf-8"))
            caminho = str(dados.get("pasta_destino", "")).strip()
            if caminho:
                # Não chama resolve() no caminho antigo: no Windows isso pode
                # gerar WinError 5 ao tentar tocar C:\Users\usuario_antigo.
                return self._remapear_caminho_de_outro_perfil(caminho)
        except (OSError, ValueError, TypeError):
            pass

        return self._perfil_usuario_atual() / "Documents" / "FiscalPro" / "Documentos Fiscais"

    def criar_backup(
        self,
        *,
        tipo: str = "manual",
        incluir_documentos: bool = False,
        destino: str | Path | None = None,
    ) -> ResultadoBackup:
        tipo = tipo.strip().lower()
        if tipo not in {"manual", "automatico", "seguranca"}:
            raise ValueError("Tipo de backup inválido.")

        self.preparar()
        destino_final = self._resolver_destino(tipo, destino)
        destino_final.parent.mkdir(parents=True, exist_ok=True)

        if tipo != "seguranca":
            self._validar_fonte_financeira_antes_backup()
        arquivos_app = list(self._iterar_arquivos_app())
        # Não toca em pasta_documentos quando o backup não inclui documentos.
        # Isso é essencial no backup de segurança criado antes da restauração:
        # um caminho antigo de outro PC não pode bloquear a operação.
        arquivos_documentos: list[tuple[Path, str]] = []
        if incluir_documentos:
            pasta_documentos = self.obter_pasta_documentos()
            arquivos_documentos = list(self._iterar_documentos(pasta_documentos))

        criado_em = datetime.now().astimezone()
        manifesto: dict[str, object] = {
            "formato": FORMATO_BACKUP,
            "aplicativo": NOME_APP,
            "versao_aplicativo": VERSAO_APP,
            "criado_em": criado_em.isoformat(timespec="seconds"),
            "tipo": tipo,
            "inclui_documentos": bool(incluir_documentos),
            "arquivos": [],
            "modulos": {},
        }

        total_bytes = 0
        arquivo_temporario = destino_final.with_suffix(destino_final.suffix + ".tmp")
        if arquivo_temporario.exists():
            arquivo_temporario.unlink()

        try:
            with self._pasta_temporaria(prefix="fiscalpro_backup_") as pasta_tmp:
                with zipfile.ZipFile(
                    arquivo_temporario,
                    mode="w",
                    compression=zipfile.ZIP_DEFLATED,
                    compresslevel=6,
                ) as pacote:
                    for origem, nome_pacote, categoria in (
                        *[(p, n, "dados") for p, n in arquivos_app],
                        *[(p, n, "documentos") for p, n in arquivos_documentos],
                    ):
                        caminho_leitura = self._preparar_arquivo_para_leitura(origem, pasta_tmp)
                        tamanho = caminho_leitura.stat().st_size
                        resumo = self._sha256(caminho_leitura)
                        if nome_pacote == CAMINHO_BANCO_FINANCEIRO:
                            resumo_financeiro = self._resumo_contas_pagar(caminho_leitura)
                            if resumo_financeiro is not None:
                                manifesto["modulos"]["contas_pagar"] = resumo_financeiro
                        pacote.write(caminho_leitura, arcname=nome_pacote)
                        total_bytes += tamanho
                        manifesto["arquivos"].append(
                            {
                                "caminho": nome_pacote,
                                "categoria": categoria,
                                "tamanho": tamanho,
                                "sha256": resumo,
                            }
                        )

                    pacote.writestr(
                        ARQUIVO_MANIFESTO,
                        json.dumps(manifesto, ensure_ascii=False, indent=2),
                    )

            self._substituir_arquivo_com_tentativas(arquivo_temporario, destino_final)
        except Exception:
            arquivo_temporario.unlink(missing_ok=True)
            raise

        if tipo == "automatico":
            self._aplicar_retencao(self.pasta_automaticos, limite=7)
        elif tipo == "seguranca":
            self._aplicar_retencao(self.pasta_seguranca, limite=5)

        resumo_contas = self._resumo_contas_manifesto(manifesto)
        return ResultadoBackup(
            caminho=destino_final,
            quantidade_arquivos=len(manifesto["arquivos"]),
            tamanho_bytes=total_bytes,
            inclui_documentos=bool(incluir_documentos),
            tipo=tipo,
            contas_pagar=(
                int(resumo_contas["registros"]) if resumo_contas is not None else None
            ),
        )

    def criar_backup_automatico_se_necessario(self) -> ResultadoBackup | None:
        """Cria no máximo um backup automático por dia, sem documentos externos."""

        self.preparar()
        hoje = datetime.now().strftime("%Y-%m-%d")
        for arquivo in self.pasta_automaticos.glob("FiscalPro_Automatico_*.zip"):
            if hoje in arquivo.name:
                return None
        return self.criar_backup(tipo="automatico", incluir_documentos=False)

    def validar_backup(self, arquivo: str | Path) -> dict[str, object]:
        caminho = Path(arquivo).expanduser().resolve()
        if not caminho.is_file():
            raise BackupInvalidoError("O arquivo de backup não foi encontrado.")

        try:
            with zipfile.ZipFile(caminho, "r") as pacote:
                if ARQUIVO_MANIFESTO not in pacote.namelist():
                    raise BackupInvalidoError("O manifesto do backup não foi encontrado.")
                manifesto = json.loads(pacote.read(ARQUIVO_MANIFESTO).decode("utf-8"))
                self._validar_manifesto(manifesto)

                nomes = set(pacote.namelist())
                for item in manifesto["arquivos"]:
                    nome = str(item["caminho"])
                    self._validar_nome_pacote(nome)
                    if nome not in nomes:
                        raise BackupInvalidoError(f"Arquivo ausente no backup: {nome}")
                    dados = pacote.read(nome)
                    if len(dados) != int(item["tamanho"]):
                        raise BackupInvalidoError(f"Tamanho divergente no arquivo: {nome}")
                    if hashlib.sha256(dados).hexdigest() != str(item["sha256"]):
                        raise BackupInvalidoError(f"Integridade inválida no arquivo: {nome}")

                # Backups anteriores ao 17.8.3 não tinham o resumo financeiro
                # no manifesto. A validação o calcula sem alterar o ZIP, para
                # que a restauração continue protegida contra uma base vazia.
                if self._resumo_contas_manifesto(manifesto) is None:
                    resumo_financeiro = self._resumo_contas_no_pacote(pacote)
                    if resumo_financeiro is not None:
                        modulos = manifesto.setdefault("modulos", {})
                        if isinstance(modulos, dict):
                            modulos["contas_pagar"] = resumo_financeiro
                return manifesto
        except zipfile.BadZipFile as erro:
            raise BackupInvalidoError("O arquivo ZIP está inválido ou corrompido.") from erro
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as erro:
            raise BackupInvalidoError("O manifesto do backup está inválido.") from erro

    def restaurar_backup(
        self,
        arquivo: str | Path,
        *,
        criar_backup_seguranca: bool = True,
    ) -> dict[str, object]:
        caminho = Path(arquivo).expanduser().resolve()
        manifesto = self.validar_backup(caminho)
        self._validar_restauracao_financeira(manifesto)

        backup_seguranca: ResultadoBackup | None = None
        if criar_backup_seguranca:
            backup_seguranca = self.criar_backup(
                tipo="seguranca",
                incluir_documentos=False,
            )

        restaurados = 0
        documentos_restaurados = 0
        pasta_documentos = self.obter_pasta_documentos()

        with self._pasta_temporaria(prefix="fiscalpro_restauracao_") as pasta_tmp:
            with zipfile.ZipFile(caminho, "r") as pacote:
                for item in manifesto["arquivos"]:
                    nome = str(item["caminho"])
                    destino = self._destino_restauracao(nome, pasta_documentos)
                    temporario = pasta_tmp / PurePosixPath(nome)
                    temporario.parent.mkdir(parents=True, exist_ok=True)
                    temporario.write_bytes(pacote.read(nome))
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    self._restaurar_arquivo(temporario, destino)
                    restaurados += 1
                    if nome.startswith(PREFIXO_DOCUMENTOS + "/"):
                        documentos_restaurados += 1

        self._conferir_restauracao_financeira(manifesto)
        self._migrar_caminhos_do_pc_anterior()

        # Força a coleta de objetos sqlite/cursors antes de devolver o
        # controle. Isso evita que o Windows mantenha o arquivo restaurado
        # bloqueado por alguns milissegundos após o término da operação.
        gc.collect()
        time.sleep(0.05)

        return {
            "manifesto": manifesto,
            "arquivos_restaurados": restaurados,
            "documentos_restaurados": documentos_restaurados,
            "backup_seguranca": str(backup_seguranca.caminho) if backup_seguranca else "",
        }

    def _migrar_caminhos_do_pc_anterior(self) -> None:
        """Atualiza referências absolutas do perfil antigo após a restauração.

        A migração é deliberadamente restrita aos campos que o próprio
        FiscalPro usa como caminhos. Nenhum valor financeiro é alterado.
        """
        # Robô de e-mail: pasta de destino dos documentos fiscais.
        config = self.raiz_dados / "dados" / "robo_email" / "config.json"
        try:
            dados = json.loads(config.read_text(encoding="utf-8"))
            atual = str(dados.get("pasta_destino", "")).strip()
            if atual:
                novo = str(self._remapear_caminho_de_outro_perfil(atual))
                if novo != atual:
                    dados["pasta_destino"] = novo
                    config.write_text(
                        json.dumps(dados, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

        # Scanner/Contas a Pagar: última pasta escolhida para recebimento.
        pasta_scan = self.raiz_dados / "dados" / "financeiro" / "pasta_download_scans.txt"
        try:
            atual = pasta_scan.read_text(encoding="utf-8").strip()
            if atual:
                novo = str(self._remapear_caminho_de_outro_perfil(atual))
                if novo != atual:
                    pasta_scan.write_text(novo, encoding="utf-8")
        except OSError:
            pass

        # Anexos das contas: troca apenas caminhos absolutos de perfil antigo.
        banco = self.raiz_dados / "dados" / "financeiro" / "contas_pagar.db"
        if not banco.is_file() or not self._eh_banco_sqlite(banco):
            return
        conexao: sqlite3.Connection | None = None
        try:
            conexao = sqlite3.connect(banco, timeout=30, cached_statements=0)
            existe = conexao.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='contas_pagar'"
            ).fetchone()
            if not existe:
                return
            colunas = {
                str(linha[1])
                for linha in conexao.execute("PRAGMA table_info(contas_pagar)").fetchall()
            }
            if "id" not in colunas or "caminho_documento" not in colunas:
                return
            linhas = conexao.execute(
                "SELECT id, caminho_documento FROM contas_pagar "
                "WHERE COALESCE(caminho_documento, '') <> ''"
            ).fetchall()
            alteracoes: list[tuple[str, int]] = []
            for identificador, caminho in linhas:
                atual = str(caminho or "").strip()
                if not atual:
                    continue
                novo = str(self._remapear_caminho_de_outro_perfil(atual))
                if novo != atual:
                    alteracoes.append((novo, int(identificador)))
            if alteracoes:
                conexao.executemany(
                    "UPDATE contas_pagar SET caminho_documento = ? WHERE id = ?",
                    alteracoes,
                )
                conexao.commit()
        except sqlite3.DatabaseError:
            if conexao is not None:
                conexao.rollback()
        finally:
            if conexao is not None:
                conexao.close()

    @staticmethod
    def _resumo_contas_pagar(caminho: Path) -> dict[str, object] | None:
        if not caminho.is_file() or not ServicoBackup._eh_banco_sqlite(caminho):
            return None
        conexao: sqlite3.Connection | None = None
        try:
            uri = caminho.resolve().as_uri() + "?mode=ro"
            conexao = sqlite3.connect(uri, uri=True, timeout=10, cached_statements=0)
            existe = conexao.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='contas_pagar'"
            ).fetchone()
            if not existe:
                return None
            integridade = str(conexao.execute("PRAGMA quick_check").fetchone()[0])
            if integridade.casefold() != "ok":
                raise BackupInvalidoError(
                    f"Integridade inválida no banco de Contas a Pagar: {integridade}"
                )
            registros = int(conexao.execute("SELECT COUNT(*) FROM contas_pagar").fetchone()[0])
            colunas = {
                str(linha[1])
                for linha in conexao.execute("PRAGMA table_info(contas_pagar)").fetchall()
            }

            def maximo(coluna: str) -> str:
                if coluna not in colunas:
                    return ""
                valor = conexao.execute(
                    f"""SELECT COALESCE(MAX(\"{coluna}\"), '') FROM contas_pagar"""
                ).fetchone()[0]
                return str(valor or "")

            return {
                "caminho": "dados/financeiro/contas_pagar.db",
                "presente": True,
                "registros": registros,
                "integridade_sqlite": integridade,
                "ultimo_lancamento": maximo("criado_em"),
                "ultima_atualizacao": maximo("atualizado_em"),
                "ultimo_pagamento": maximo("data_pagamento"),
            }
        except sqlite3.Error as erro:
            raise BackupInvalidoError(
                f"Não foi possível validar o banco de Contas a Pagar: {erro}"
            ) from erro
        finally:
            if conexao is not None:
                conexao.close()

    @staticmethod
    def _resumo_contas_manifesto(manifesto: dict[str, object]) -> dict[str, object] | None:
        modulos = manifesto.get("modulos")
        if not isinstance(modulos, dict):
            return None
        resumo = modulos.get("contas_pagar")
        return resumo if isinstance(resumo, dict) else None

    def _resumo_contas_no_pacote(
        self, pacote: zipfile.ZipFile
    ) -> dict[str, object] | None:
        if CAMINHO_BANCO_FINANCEIRO not in pacote.namelist():
            return None
        with self._pasta_temporaria(prefix="fiscalpro_validacao_financeiro_") as pasta:
            temporario = pasta / "contas_pagar.db"
            temporario.write_bytes(pacote.read(CAMINHO_BANCO_FINANCEIRO))
            return self._resumo_contas_pagar(temporario)

    def _validar_fonte_financeira_antes_backup(self) -> None:
        resumo_atual = self._resumo_contas_pagar(self.banco_financeiro)
        if resumo_atual is not None and int(resumo_atual["registros"]) > 0:
            return
        # A busca em instalações antigas só faz sentido na execução instalada.
        # Em testes/raízes customizadas não devemos inspecionar o computador.
        if self.raiz_dados != Path(RAIZ_DADOS).resolve() or not esta_empacotado():
            return
        legado = localizar_melhor_banco_financeiro_legacy()
        if legado is None:
            return
        caminho_legado, quantidade = legado
        if quantidade > 0:
            raise RuntimeError(
                "Backup cancelado para proteger suas Contas a Pagar. "
                f"O banco atual está vazio, mas foi encontrada uma base antiga com "
                f"{quantidade} conta(s) em:\n{caminho_legado}\n\n"
                "Feche e abra o FiscalPro novamente para concluir a migração segura "
                "antes de criar outro backup."
            )

    def _validar_restauracao_financeira(self, manifesto: dict[str, object]) -> None:
        atual = self._resumo_contas_pagar(self.banco_financeiro)
        backup = self._resumo_contas_manifesto(manifesto)
        if atual is None or backup is None:
            return
        quantidade_atual = int(atual.get("registros", 0))
        quantidade_backup = int(backup.get("registros", 0))
        if quantidade_atual > 0 and quantidade_backup == 0:
            raise BackupInvalidoError(
                "Restauração bloqueada por segurança. O FiscalPro atual possui "
                f"{quantidade_atual} conta(s) a pagar, mas o backup selecionado "
                "contém 0. Nenhum dado foi substituído. Escolha outro backup."
            )

    def _conferir_restauracao_financeira(self, manifesto: dict[str, object]) -> None:
        esperado = self._resumo_contas_manifesto(manifesto)
        if esperado is None:
            return
        quantidade_esperada = int(esperado.get("registros", 0))
        atual = self._resumo_contas_pagar(self.banco_financeiro)
        if atual is None:
            raise BackupInvalidoError(
                "A restauração terminou, mas o banco de Contas a Pagar não pôde ser validado."
            )
        quantidade_atual = int(atual.get("registros", 0))
        if quantidade_atual != quantidade_esperada:
            raise BackupInvalidoError(
                "A conferência após a restauração encontrou divergência nas Contas a Pagar: "
                f"esperado {quantidade_esperada}, encontrado {quantidade_atual}. "
                "O backup de segurança criado antes da operação foi preservado."
            )

    def listar_backups(self, limite: int = 20) -> list[Path]:
        self.preparar()
        arquivos = [
            arquivo
            for pasta in (self.pasta_manuais, self.pasta_automaticos, self.pasta_seguranca)
            for arquivo in pasta.glob("*.zip")
            if arquivo.is_file()
        ]
        arquivos.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        return arquivos[: max(1, int(limite))]

    def _resolver_destino(self, tipo: str, destino: str | Path | None) -> Path:
        agora = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")[:-3]
        prefixos = {
            "manual": "FiscalPro_Backup",
            "automatico": "FiscalPro_Automatico",
            "seguranca": "FiscalPro_Antes_Restauracao",
        }
        nome = f"{prefixos[tipo]}_{agora}.zip"
        if destino is None:
            pasta = {
                "manual": self.pasta_manuais,
                "automatico": self.pasta_automaticos,
                "seguranca": self.pasta_seguranca,
            }[tipo]
            return pasta / nome

        caminho = Path(destino).expanduser()
        if caminho.suffix.lower() == ".zip":
            return caminho.resolve()
        return caminho.resolve() / nome

    def _iterar_arquivos_app(self) -> Iterable[tuple[Path, str]]:
        # Hotfix 17.8.2: o backup deixa de manter uma lista fechada de módulos.
        # Tudo que é dado persistente do FiscalPro dentro de ``dados/`` entra
        # automaticamente no pacote. Assim Contas a Pagar, Controle de Entregas
        # e módulos futuros não ficam de fora quando a usuária troca de máquina.
        fontes: list[Path] = [
            self.raiz_dados / "fiscalpro.db",
            self.raiz_dados / "dados",
        ]
        vistos: set[Path] = set()
        for fonte in fontes:
            if fonte.is_file():
                candidatos = [fonte]
            elif fonte.is_dir():
                candidatos = sorted(item for item in fonte.rglob("*") if item.is_file())
            else:
                candidatos = []

            for arquivo in candidatos:
                resolvido = arquivo.resolve()
                if resolvido in vistos or self._deve_ignorar(arquivo):
                    continue
                vistos.add(resolvido)
                relativo = arquivo.relative_to(self.raiz_dados).as_posix()
                yield arquivo, f"{PREFIXO_DADOS}/{relativo}"

    def _iterar_documentos(self, pasta: Path) -> Iterable[tuple[Path, str]]:
        if not pasta.is_dir():
            return
        for arquivo in sorted(item for item in pasta.rglob("*") if item.is_file()):
            if self._deve_ignorar(arquivo):
                continue
            try:
                arquivo.resolve().relative_to(self.pasta_backups)
                continue
            except ValueError:
                pass
            relativo = arquivo.relative_to(pasta).as_posix()
            yield arquivo, f"{PREFIXO_DOCUMENTOS}/{relativo}"

    @staticmethod
    def _deve_ignorar(arquivo: Path) -> bool:
        partes = {parte.casefold() for parte in arquivo.parts}
        if "__pycache__" in partes or ".git" in partes:
            return True
        nome = arquivo.name.casefold()
        return nome.endswith((".tmp", ".lock", "-wal", "-shm", ".restaurando"))

    def _preparar_arquivo_para_leitura(self, origem: Path, pasta_tmp: Path) -> Path:
        if origem.suffix.casefold() != ".db":
            return origem

        snapshot = pasta_tmp / f"sqlite_{len(list(pasta_tmp.glob('sqlite_*'))):04d}.db"
        fonte: sqlite3.Connection | None = None
        destino: sqlite3.Connection | None = None
        try:
            uri = origem.resolve().as_uri() + "?mode=ro"
            # cached_statements=0 evita que statements preparados permaneçam
            # associados ao arquivo após o fechamento, algo que pode atrasar a
            # liberação do handle no Windows/Python 3.13.
            fonte = sqlite3.connect(
                uri, uri=True, timeout=10, cached_statements=0
            )
            destino = sqlite3.connect(
                snapshot, timeout=10, cached_statements=0
            )
            fonte.backup(destino)
            destino.commit()
            return snapshot
        except sqlite3.DatabaseError:
            # Alguns arquivos podem usar a extensão .db sem serem SQLite.
            return origem
        finally:
            if destino is not None:
                destino.close()
            if fonte is not None:
                fonte.close()
            destino = None
            fonte = None
            gc.collect()


    def _restaurar_arquivo(self, origem: Path, destino: Path) -> None:
        """Restaura um arquivo sem substituir fisicamente bancos SQLite abertos.

        No Windows, ``os.replace`` falha quando qualquer conexão mantém o banco
        aberto. Para arquivos SQLite, a restauração usa a API oficial de backup
        do SQLite, que copia as páginas para o banco de destino com segurança.
        """

        if origem.suffix.casefold() == ".db" and self._eh_banco_sqlite(origem):
            self._restaurar_banco_sqlite(origem, destino)
            return

        alvo_tmp = destino.with_name(destino.name + ".restaurando")
        alvo_tmp.unlink(missing_ok=True)
        shutil.copy2(origem, alvo_tmp)
        try:
            self._substituir_arquivo_com_tentativas(alvo_tmp, destino)
        finally:
            alvo_tmp.unlink(missing_ok=True)

    @staticmethod
    def _eh_banco_sqlite(caminho: Path) -> bool:
        try:
            with caminho.open("rb") as arquivo:
                return arquivo.read(16) == b"SQLite format 3\x00"
        except OSError:
            return False

    @staticmethod
    def _restaurar_banco_sqlite(origem: Path, destino: Path) -> None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        uri_origem = origem.resolve().as_uri() + "?mode=ro"
        ultimo_erro: Exception | None = None

        for tentativa in range(6):
            fonte: sqlite3.Connection | None = None
            alvo: sqlite3.Connection | None = None
            try:
                fonte = sqlite3.connect(
                    uri_origem, uri=True, timeout=30, cached_statements=0
                )
                alvo = sqlite3.connect(
                    destino, timeout=30, cached_statements=0
                )
                cursor = alvo.execute("PRAGMA busy_timeout = 30000")
                cursor.close()
                fonte.backup(alvo, pages=256, sleep=0.05)
                alvo.commit()
                return
            except sqlite3.OperationalError as erro:
                ultimo_erro = erro
            finally:
                if alvo is not None:
                    alvo.close()
                if fonte is not None:
                    fonte.close()
                alvo = None
                fonte = None
                gc.collect()

            time.sleep(0.25 * (tentativa + 1))

        raise PermissionError(
            f"Não foi possível restaurar o banco {destino.name}. "
            "Feche outras janelas do FiscalPro e tente novamente."
        ) from ultimo_erro

    @staticmethod
    def _substituir_arquivo_com_tentativas(origem: Path, destino: Path) -> None:
        ultimo_erro: Exception | None = None
        for tentativa in range(6):
            try:
                os.replace(origem, destino)
                return
            except PermissionError as erro:
                ultimo_erro = erro
                gc.collect()
                time.sleep(0.20 * (tentativa + 1))

        raise PermissionError(
            f"O arquivo {destino.name} está em uso por outro processo. "
            "Feche o programa que está usando o arquivo e tente novamente."
        ) from ultimo_erro

    @staticmethod
    @contextmanager
    def _pasta_temporaria(prefix: str):
        pasta = Path(tempfile.mkdtemp(prefix=prefix))
        try:
            yield pasta
        finally:
            for tentativa in range(6):
                try:
                    shutil.rmtree(pasta)
                    break
                except FileNotFoundError:
                    break
                except PermissionError:
                    gc.collect()
                    time.sleep(0.20 * (tentativa + 1))
            else:
                # Uma trava transitória do Windows não deve invalidar um backup
                # já concluído. O sistema operacional removerá os temporários
                # posteriormente; nenhum dado do usuário fica nessa pasta.
                shutil.rmtree(pasta, ignore_errors=True)

    @staticmethod
    def _sha256(caminho: Path) -> str:
        resumo = hashlib.sha256()
        with caminho.open("rb") as arquivo:
            for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
                resumo.update(bloco)
        return resumo.hexdigest()

    @staticmethod
    def _validar_manifesto(manifesto: object) -> None:
        if not isinstance(manifesto, dict):
            raise BackupInvalidoError("Manifesto inválido.")
        if manifesto.get("formato") != FORMATO_BACKUP:
            raise BackupInvalidoError("Versão de backup não suportada.")
        if manifesto.get("aplicativo") != NOME_APP:
            raise BackupInvalidoError("Este arquivo não pertence ao FiscalPro.")
        if not isinstance(manifesto.get("arquivos"), list):
            raise BackupInvalidoError("Lista de arquivos inválida.")

    @staticmethod
    def _validar_nome_pacote(nome: str) -> None:
        caminho = PurePosixPath(nome)
        if caminho.is_absolute() or ".." in caminho.parts:
            raise BackupInvalidoError("O backup contém um caminho inseguro.")
        if not caminho.parts or caminho.parts[0] not in {PREFIXO_DADOS, PREFIXO_DOCUMENTOS}:
            raise BackupInvalidoError("O backup contém um caminho desconhecido.")

    def _destino_restauracao(self, nome: str, pasta_documentos: Path) -> Path:
        self._validar_nome_pacote(nome)
        partes = PurePosixPath(nome).parts
        if partes[0] == PREFIXO_DADOS:
            destino = self.raiz_dados.joinpath(*partes[1:]).resolve()
            try:
                destino.relative_to(self.raiz_dados)
            except ValueError as erro:
                raise BackupInvalidoError("Destino de restauração inseguro.") from erro
            return destino

        raiz_documentos = pasta_documentos.expanduser().resolve()
        destino = raiz_documentos.joinpath(*partes[1:]).resolve()
        try:
            destino.relative_to(raiz_documentos)
        except ValueError as erro:
            raise BackupInvalidoError("Destino de documentos inseguro.") from erro
        return destino

    @staticmethod
    def _aplicar_retencao(pasta: Path, limite: int) -> None:
        arquivos = sorted(
            (item for item in pasta.glob("*.zip") if item.is_file()),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for antigo in arquivos[limite:]:
            antigo.unlink(missing_ok=True)
