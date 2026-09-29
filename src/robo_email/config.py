"""Configuração persistente do Robô FiscalPro."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.core.caminhos import PASTA_ROBO_EMAIL, pasta_recursos

BASE_DIR = pasta_recursos()
DADOS_ROBO_DIR = PASTA_ROBO_EMAIL
CONFIG_PATH = DADOS_ROBO_DIR / "config.json"
TOKEN_PATH = DADOS_ROBO_DIR / "token_gmail.json"
BANCO_PATH = DADOS_ROBO_DIR / "robo_email.db"
INSTRUCOES_PATH = BASE_DIR / "CONFIGURAR_GMAIL_ROBO.txt"

EMAIL_PRINCIPAL = "grupomegamotos.fiscal@gmail.com"

EMPRESAS_POR_ALIAS: dict[str, str] = {
    "megatrilha": "Mega Motos Trilha",
    "megacomercio": "Mega Motos Comércio",
    "megamix": "Mega Mix E-commerce",
    "megato": "Mega T.O. E-commerce",
    "megaservicos": "Mega Serviços",
    "megaprofissional": "Mega Profissional",
}

ENDERECOS_EMPRESAS: dict[str, str] = {
    alias: f"grupomegamotos.fiscal+{alias}@gmail.com"
    for alias in EMPRESAS_POR_ALIAS
}

# Categorias que podem ser marcadas como obrigatórias no controle mensal.
# "Links" não entra nessa lista porque é uma forma de recebimento, não um
# documento esperado. Quando o link é baixado, o arquivo entra na categoria real.
CATEGORIAS_DOCUMENTOS_ESPERADOS = ("XML", "Guias", "PDF", "ZIP", "Outros")


def documentos_esperados_padrao() -> dict[str, list[str]]:
    """Padrão conservador: somente guias são esperadas mensalmente.

    As demais categorias podem ser ativadas por empresa na tela do painel mensal.
    Isso evita criar falsas pendências para empresas que não recebem XML/PDF todo mês.
    """

    return {empresa: ["Guias"] for empresa in EMPRESAS_POR_ALIAS.values()}


# Domínios oficiais iniciais. O domínio do portal da contabilidade deve ser
# cadastrado pela usuária após conferir o endereço correto.
DOMINIOS_CONFIAVEIS_PADRAO = ["gov.br"]

# Rastreadores de abertura nunca devem ser autorizados para download.
DOMINIOS_RASTREADORES = {
    "mailtrack.email",
    "mailtrack.io",
    "mailtrack.com",
}


@dataclass(slots=True)
class ConfiguracaoRoboEmail:
    """Preferências locais do robô. Senhas nunca são armazenadas."""

    caminho_credenciais: str = ""
    pasta_destino: str = str(Path.home() / "Documents" / "FiscalPro" / "Documentos Fiscais")
    dias_retroativos: int = 30
    somente_nao_lidos: bool = False
    revisao_busca: int = 2
    limite_mensagens: int = 500
    registrar_links: bool = True
    baixar_links_automaticamente: bool = False
    dominios_confiaveis: list[str] = field(
        default_factory=lambda: list(DOMINIOS_CONFIAVEIS_PADRAO)
    )
    tamanho_maximo_link_mb: int = 25
    documentos_esperados: dict[str, list[str]] = field(
        default_factory=documentos_esperados_padrao
    )
    cnpjs_empresas: dict[str, str] = field(
        default_factory=lambda: {empresa: "" for empresa in EMPRESAS_POR_ALIAS.values()}
    )

    @classmethod
    def carregar(cls) -> "ConfiguracaoRoboEmail":
        DADOS_ROBO_DIR.mkdir(parents=True, exist_ok=True)
        if not CONFIG_PATH.exists():
            return cls()

        try:
            dados: dict[str, Any] = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            permitidos = {campo for campo in cls.__dataclass_fields__}
            filtrados = {chave: valor for chave, valor in dados.items() if chave in permitidos}

            # Migração Hotfix 17.6.7: versões antigas buscavam somente mensagens
            # não lidas por padrão. Como Gmail/Outlook/celular podem marcar uma
            # mensagem como lida antes de o FiscalPro rodar, documentos legítimos
            # deixavam de ser encontrados. O repositório já controla IDs concluídos,
            # portanto a busca segura passa a considerar toda a caixa de entrada
            # recente e pula o que já foi processado.
            revisao_anterior = int(dados.get("revisao_busca", 0) or 0)
            if revisao_anterior < 2:
                filtrados["somente_nao_lidos"] = False
                filtrados["revisao_busca"] = 2

            if "dominios_confiaveis" in filtrados:
                filtrados["dominios_confiaveis"] = cls.normalizar_dominios(
                    filtrados.get("dominios_confiaveis", [])
                )
            if "documentos_esperados" in filtrados:
                filtrados["documentos_esperados"] = cls.normalizar_documentos_esperados(
                    filtrados.get("documentos_esperados", {})
                )
            if "cnpjs_empresas" in filtrados:
                filtrados["cnpjs_empresas"] = cls.normalizar_cnpjs_empresas(
                    filtrados.get("cnpjs_empresas", {})
                )
            return cls(**filtrados)
        except (OSError, ValueError, TypeError):
            return cls()

    def salvar(self) -> None:
        DADOS_ROBO_DIR.mkdir(parents=True, exist_ok=True)
        self.dominios_confiaveis = self.normalizar_dominios(self.dominios_confiaveis)
        self.documentos_esperados = self.normalizar_documentos_esperados(
            self.documentos_esperados
        )
        self.cnpjs_empresas = self.normalizar_cnpjs_empresas(self.cnpjs_empresas)
        CONFIG_PATH.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @property
    def credenciais(self) -> Path:
        return Path(self.caminho_credenciais).expanduser()

    @property
    def destino(self) -> Path:
        return Path(self.pasta_destino).expanduser()

    def validar(self) -> list[str]:
        erros: list[str] = []
        if not self.caminho_credenciais:
            erros.append("Selecione o arquivo JSON de credenciais do Google.")
        elif not self.credenciais.is_file():
            erros.append("O arquivo JSON de credenciais não foi encontrado.")

        if not self.pasta_destino:
            erros.append("Selecione a pasta onde os documentos serão salvos.")
        if not 1 <= int(self.dias_retroativos) <= 3650:
            erros.append("O período deve ficar entre 1 e 3650 dias.")
        if not 1 <= int(self.limite_mensagens) <= 5000:
            erros.append("O limite deve ficar entre 1 e 5000 mensagens.")
        if not 1 <= int(self.tamanho_maximo_link_mb) <= 200:
            erros.append("O limite de download por link deve ficar entre 1 e 200 MB.")

        invalidos = [
            dominio
            for dominio in self.dominios_confiaveis
            if not self.dominio_valido(dominio)
        ]
        if invalidos:
            erros.append(
                "Domínio(s) inválido(s) na lista segura: " + ", ".join(invalidos)
            )
        cnpjs_invalidos = [
            empresa
            for empresa, cnpj in self.cnpjs_empresas.items()
            if cnpj and len(re.sub(r"\D", "", cnpj)) != 14
        ]
        if cnpjs_invalidos:
            erros.append(
                "CNPJ inválido para: " + ", ".join(cnpjs_invalidos)
            )
        return erros

    @staticmethod
    def dominio_valido(dominio: str) -> bool:
        dominio = (dominio or "").strip().lower().rstrip(".")
        if not dominio or "/" in dominio or ":" in dominio or "@" in dominio:
            return False
        return bool(
            re.fullmatch(
                r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
                dominio,
            )
        )

    @classmethod
    def normalizar_dominios(cls, dominios: Any) -> list[str]:
        if isinstance(dominios, str):
            itens = re.split(r"[,;\n\r\t ]+", dominios)
        elif isinstance(dominios, (list, tuple, set)):
            itens = [str(item) for item in dominios]
        else:
            itens = []

        resultado: list[str] = []
        for item in itens:
            dominio = item.strip().lower().rstrip(".")
            dominio = re.sub(r"^https?://", "", dominio)
            dominio = dominio.split("/", 1)[0]
            if dominio.startswith("www."):
                dominio = dominio[4:]
            if dominio in DOMINIOS_RASTREADORES:
                continue
            if cls.dominio_valido(dominio) and dominio not in resultado:
                resultado.append(dominio)
        return resultado


    @classmethod
    def normalizar_cnpjs_empresas(cls, dados: Any) -> dict[str, str]:
        """Mantém um CNPJ opcional por empresa para conferência documental."""

        resultado = {empresa: "" for empresa in EMPRESAS_POR_ALIAS.values()}
        if not isinstance(dados, dict):
            return resultado
        for empresa in resultado:
            digitos = re.sub(r"\D", "", str(dados.get(empresa, "") or ""))
            resultado[empresa] = digitos if len(digitos) == 14 else ""
        return resultado

    @classmethod
    def normalizar_documentos_esperados(cls, dados: Any) -> dict[str, list[str]]:
        """Normaliza o checklist mensal, preservando empresas sem exigências."""

        padrao = documentos_esperados_padrao()
        if not isinstance(dados, dict):
            return padrao

        resultado: dict[str, list[str]] = {}
        categorias_validas = set(CATEGORIAS_DOCUMENTOS_ESPERADOS)
        for empresa in EMPRESAS_POR_ALIAS.values():
            if empresa not in dados:
                resultado[empresa] = list(padrao[empresa])
                continue

            valor = dados.get(empresa)
            if isinstance(valor, str):
                itens = re.split(r"[,;\n\r\t]+", valor)
            elif isinstance(valor, (list, tuple, set)):
                itens = [str(item) for item in valor]
            else:
                itens = []

            normalizados: list[str] = []
            for categoria in CATEGORIAS_DOCUMENTOS_ESPERADOS:
                if any(str(item).strip().casefold() == categoria.casefold() for item in itens):
                    if categoria in categorias_validas and categoria not in normalizados:
                        normalizados.append(categoria)
            resultado[empresa] = normalizados
        return resultado
