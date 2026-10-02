# -*- coding: utf-8 -*-
"""Configuração do processo (variáveis de ambiente). Segredos NUNCA ficam em banco/tela/log."""

import os
import secrets
import time
from pathlib import Path

# Todo horário do sistema é o de Brasília (o container do Render roda em UTC); o SQLite
# "localtime" e o `datetime.now()` seguem esta variável.
os.environ["TZ"] = "America/Sao_Paulo"
if hasattr(time, "tzset"):
    time.tzset()

_RAIZ = Path(__file__).resolve().parent.parent  # .../nfse


def pasta_dados() -> Path:
    pasta = Path(os.environ.get("NFSE_DATA_DIR") or _RAIZ / "data")
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def caminho_banco() -> Path:
    return Path(os.environ.get("NFSE_DB_PATH") or pasta_dados() / "nfse.db")


def caminho_certificado_padrao() -> Path:
    return pasta_dados() / "certificado.pfx"


def pasta_saida_padrao() -> Path:
    return Path(os.environ.get("NFSE_SAIDA_DIR") or _RAIZ / "saida")


def secret_key() -> str:
    """SECRET_KEY do ambiente; sem ela, gera uma e guarda em <dados>/secret_key (chmod 600)."""
    chave = os.environ.get("SECRET_KEY")
    if chave:
        return chave
    arq = pasta_dados() / "secret_key"
    if arq.exists():
        return arq.read_text().strip()
    chave = secrets.token_hex(32)
    arq.write_text(chave)
    try:
        os.chmod(arq, 0o600)
    except OSError:
        pass
    return chave


def smtp() -> dict | None:
    """Servidor de e-mail das variáveis SMTP_*; None se não configurado."""
    host = os.environ.get("SMTP_HOST")
    usuario = os.environ.get("SMTP_USER")
    if not host or not usuario:
        return None
    return {"host": host, "porta": int(os.environ.get("SMTP_PORT", "587")), "usuario": usuario,
            "senha": os.environ.get("SMTP_SENHA", ""), "remetente": os.environ.get("SMTP_FROM") or usuario,
            "ssl": os.environ.get("SMTP_SSL", "0") == "1"}
