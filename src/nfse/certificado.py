"""Utilidades para certificado digital A1 (PKCS#12/PFX)."""

from __future__ import annotations

import os
import ssl
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12


@dataclass(frozen=True)
class InfoCertificado:
    titular: str
    emissor: str
    serial: str
    valido_de: str
    valido_ate: str


def _carregar_pfx(caminho: str | Path, senha: str):
    path = Path(caminho)
    if not path.is_file():
        raise FileNotFoundError(f"Certificado não encontrado: {path}")
    conteudo = path.read_bytes()
    try:
        chave, certificado, cadeia = pkcs12.load_key_and_certificates(
            conteudo,
            senha.encode("utf-8") if senha else None,
        )
    except Exception as exc:
        raise ValueError("Não foi possível abrir o certificado A1. Confira o arquivo e a senha.") from exc
    if chave is None or certificado is None:
        raise ValueError("O arquivo informado não contém certificado e chave privada utilizáveis.")
    return chave, certificado, cadeia or []


def ler_info_certificado(caminho: str | Path, senha: str) -> InfoCertificado:
    _chave, certificado, _cadeia = _carregar_pfx(caminho, senha)

    def nome_legivel(nome: x509.Name) -> str:
        partes = []
        for oid in (x509.NameOID.COMMON_NAME, x509.NameOID.ORGANIZATION_NAME):
            valores = nome.get_attributes_for_oid(oid)
            if valores:
                partes.append(valores[0].value)
        return " • ".join(partes) or nome.rfc4514_string()

    inicio = certificado.not_valid_before_utc if hasattr(certificado, "not_valid_before_utc") else certificado.not_valid_before
    fim = certificado.not_valid_after_utc if hasattr(certificado, "not_valid_after_utc") else certificado.not_valid_after
    return InfoCertificado(
        titular=nome_legivel(certificado.subject),
        emissor=nome_legivel(certificado.issuer),
        serial=f"{certificado.serial_number:X}",
        valido_de=inicio.strftime("%d/%m/%Y %H:%M"),
        valido_ate=fim.strftime("%d/%m/%Y %H:%M"),
    )


@contextmanager
def contexto_ssl_a1(caminho: str | Path, senha: str):
    """Cria SSLContext mTLS a partir de .pfx/.p12 e remove PEMs temporários."""

    chave, certificado, cadeia = _carregar_pfx(caminho, senha)
    temp_dir = tempfile.TemporaryDirectory(prefix="fiscalpro_nfse_")
    try:
        pasta = Path(temp_dir.name)
        chave_path = pasta / "key.pem"
        cert_path = pasta / "cert.pem"

        chave_path.write_bytes(
            chave.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        blocos = [certificado.public_bytes(serialization.Encoding.PEM)]
        blocos.extend(c.public_bytes(serialization.Encoding.PEM) for c in cadeia)
        cert_path.write_bytes(b"".join(blocos))

        if os.name != "nt":
            os.chmod(chave_path, 0o600)
            os.chmod(cert_path, 0o600)

        contexto = ssl.create_default_context()
        contexto.minimum_version = ssl.TLSVersion.TLSv1_2
        contexto.load_cert_chain(certfile=str(cert_path), keyfile=str(chave_path))
        yield contexto
    finally:
        temp_dir.cleanup()
