"""Classificação de empresa, tipo de arquivo e nomes seguros."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .config import EMPRESAS_POR_ALIAS


VARIANTES_EMPRESAS: dict[str, tuple[str, ...]] = {
    "Mega Motos Trilha": ("mega motos trilha", "mega trilha"),
    "Mega Motos Comércio": ("mega motos comercio", "mega motos comércio", "mega comercio"),
    "Mega Mix E-commerce": ("mega mix e-commerce", "mega mix ecommerce", "mega mix"),
    "Mega T.O. E-commerce": ("mega t.o. e-commerce", "mega to ecommerce", "mega t.o", "mega to"),
    "Mega Serviços": ("mega servicos", "mega serviços"),
    "Mega Profissional": ("mega profissional",),
}

PALAVRAS_GUIA = {
    "darf", "das", "dae", "gnre", "guia", "boleto", "tributo", "imposto",
    "icms", "inss", "fgts", "irpj", "csll", "pis", "cofins", "gps",
}


def normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(letra for letra in texto if not unicodedata.combining(letra))
    return texto.casefold()


def identificar_empresa(destinatarios: str, assunto: str = "", snippet: str = "") -> str | None:
    destinatarios_norm = normalizar_texto(destinatarios)
    for alias, empresa in EMPRESAS_POR_ALIAS.items():
        padrao = rf"\+{re.escape(alias)}@gmail\.com"
        if re.search(padrao, destinatarios_norm):
            return empresa

    contexto = normalizar_texto(f"{assunto} {snippet}")
    for empresa, variantes in VARIANTES_EMPRESAS.items():
        if any(normalizar_texto(variante) in contexto for variante in variantes):
            return empresa
    return None


def classificar_arquivo(nome: str, mime_type: str = "") -> str:
    extensao = Path(nome).suffix.lower()
    nome_norm = normalizar_texto(nome)

    if extensao == ".xml" or "xml" in mime_type.lower():
        return "XML"
    if extensao == ".zip" or "zip" in mime_type.lower():
        return "ZIP"
    if extensao == ".pdf" or "pdf" in mime_type.lower():
        if any(re.search(rf"\b{re.escape(palavra)}\b", nome_norm) for palavra in PALAVRAS_GUIA):
            return "Guias"
        return "PDF"
    return "Outros"


def nome_seguro(nome: str, padrao: str = "anexo") -> str:
    nome = Path(nome or padrao).name.strip()
    nome = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", nome)
    nome = re.sub(r"\s+", " ", nome).strip(" .")
    if not nome:
        nome = padrao
    return nome[:180]


def pasta_empresa_segura(empresa: str | None) -> str:
    if not empresa:
        return "_Nao_Identificada"
    return nome_seguro(empresa.replace(".", ""), "_Nao_Identificada")
