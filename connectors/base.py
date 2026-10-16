"""Interface comum que todo conector de banco deve implementar.

Cada conector cuida apenas de: autenticar e baixar o extrato (PDF/OFX/Excel)
de um período. Nomear o arquivo, checar duplicidade e organizar no Drive é
responsabilidade do orquestrador (fora deste módulo), não do conector.
"""

import base64
import binascii
import hashlib
import os
import tempfile
from dataclasses import dataclass
from datetime import date


def arquivo_de_credencial(nome_env: str) -> str:
    """Devolve o caminho de um certificado/chave guardado na variável `nome_env`.

    A variável pode conter o caminho do arquivo (modelo antigo, com
    ~/.dpa-secrets) ou o próprio conteúdo — PEM ou PEM em base64 numa linha só,
    como dá para cadastrar nas variáveis de ambiente do ambiente cloud. No
    segundo caso o conteúdo é gravado num arquivo temporário com permissão 600,
    porque o `requests` só aceita caminho no parâmetro `cert`.
    """
    valor = os.environ[nome_env].strip()
    if valor.startswith("-----BEGIN"):
        pem = valor.replace("\\n", "\n").encode()
    else:
        try:
            pem = base64.b64decode(valor, validate=True)
        except (binascii.Error, ValueError):
            return valor
        if not pem.lstrip().startswith(b"-----BEGIN"):
            return valor
    pasta = os.path.join(tempfile.gettempdir(), "dpa-certs")
    os.makedirs(pasta, mode=0o700, exist_ok=True)
    caminho = os.path.join(pasta, nome_env + "-" + hashlib.sha256(pem).hexdigest()[:12] + ".pem")
    if not os.path.exists(caminho):
        fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(pem)
    return caminho


@dataclass
class Extrato:
    pdf: bytes | None = None
    ofx: bytes | None = None
    xlsx: bytes | None = None
    indisponiveis: list[str] | None = None  # formatos que o banco não devolveu


class BankConnector:
    """Contrato que cada banco (inter.py, sicoob.py, santander.py, ...) implementa."""

    nome: str

    def autenticar(self) -> None:
        """Obtém o token de acesso (OAuth2 client_credentials + mTLS)."""
        raise NotImplementedError

    def baixar_extrato(self, conta: str, inicio: date, fim: date) -> Extrato:
        """Consulta e baixa o extrato do período [inicio, fim] (inclusive)."""
        raise NotImplementedError


class ConectorNaoConfigurado(BankConnector):
    """Placeholder para bancos com integracao.status != ativo em empresas.yaml.

    Mantém o processo de fechamento rodando para os outros bancos: este
    apenas devolve "indisponível/pendente" no relatório, sem lançar erro.
    """

    def __init__(self, nome: str, motivo: str):
        self.nome = nome
        self.motivo = motivo

    def autenticar(self) -> None:
        pass

    def baixar_extrato(self, conta: str, inicio: date, fim: date) -> Extrato:
        return Extrato(indisponiveis=[f"pendente de configuração: {self.motivo}"])
