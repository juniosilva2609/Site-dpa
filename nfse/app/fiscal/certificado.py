# -*- coding: utf-8 -*-
"""Certificado digital e-CNPJ A1 (.pfx/.p12): assinatura da DPS e mTLS com a Sefin Nacional.

O arquivo fica em `NFSE_CERT_PATH` (ou em `<dados>/certificado.pfx`, onde o upload da
tela de Configuração grava). A SENHA só existe na variável de ambiente `NFSE_CERT_SENHA`
-- nunca em banco, tela, log ou argumento de função."""

import contextlib
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .. import config


class CertificadoIndisponivel(Exception):
    pass


def caminho_certificado() -> Path | None:
    caminho = Path(os.environ.get("NFSE_CERT_PATH") or config.caminho_certificado_padrao())
    return caminho if caminho.is_file() else None


def disponivel() -> bool:
    return caminho_certificado() is not None and bool(os.environ.get("NFSE_CERT_SENHA"))


def carregar() -> tuple[bytes, bytes]:
    """Devolve (certificado_pem, chave_privada_pem)."""
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, pkcs12

    caminho = caminho_certificado()
    senha = os.environ.get("NFSE_CERT_SENHA")
    if not caminho or not senha:
        raise CertificadoIndisponivel(
            "Certificado digital não configurado: envie o arquivo .pfx em Configuração e defina a "
            "senha na variável de ambiente NFSE_CERT_SENHA.")
    try:
        chave, cert, _cadeia = pkcs12.load_key_and_certificates(caminho.read_bytes(), senha.encode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise CertificadoIndisponivel(
            "Não consegui abrir o certificado com a senha configurada -- confira o arquivo e a senha.") from e
    if not chave or not cert:
        raise CertificadoIndisponivel("Certificado ou chave privada ausente no arquivo .pfx/.p12.")
    return (cert.public_bytes(Encoding.PEM),
            chave.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))


def validade() -> tuple[datetime, datetime]:
    """(nao_antes, nao_depois) em UTC, lidos do X.509 (nunca a chave privada)."""
    from cryptography import x509

    cert_pem, _ = carregar()
    cert = x509.load_pem_x509_certificate(cert_pem)
    return cert.not_valid_before_utc, cert.not_valid_after_utc


def dias_para_vencer() -> int | None:
    """Dias inteiros até vencer (negativo = vencido); None se o certificado não abre."""
    try:
        _, fim = validade()
    except CertificadoIndisponivel:
        return None
    return (fim - datetime.now(timezone.utc)).days


def cnpj_do_certificado() -> str | None:
    """CNPJ (14 dígitos) do titular, quando presente no certificado ICP-Brasil (OID 2.16.76.1.3.3
    nas otherName do SAN, ou no fim do CN "NOME:CNPJ")."""
    import re

    from cryptography import x509
    from cryptography.x509.oid import NameOID

    try:
        cert_pem, _ = carregar()
    except CertificadoIndisponivel:
        return None
    cert = x509.load_pem_x509_certificate(cert_pem)
    try:
        cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    except IndexError:
        return None
    m = re.search(r":(\d{14})\b", cn)
    return m.group(1) if m else None


@contextlib.contextmanager
def arquivos_temporarios_para_requests():
    """`requests` exige caminhos para `cert=(cert, key)`: grava os PEM num diretório temporário
    (chave com chmod 600) só durante o `with` e apaga tudo ao sair, mesmo em caso de erro."""
    cert_pem, chave_pem = carregar()
    dir_tmp = tempfile.mkdtemp(prefix="nfse_cert_")
    try:
        caminho_cert = os.path.join(dir_tmp, "cert.pem")
        caminho_chave = os.path.join(dir_tmp, "key.pem")
        with open(caminho_cert, "wb") as f:
            f.write(cert_pem)
        fd = os.open(caminho_chave, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(chave_pem)
        yield caminho_cert, caminho_chave
    finally:
        shutil.rmtree(dir_tmp, ignore_errors=True)
