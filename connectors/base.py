"""Interface comum que todo conector de banco deve implementar.

Cada conector cuida apenas de: autenticar e baixar o extrato (PDF/OFX/Excel)
de um período. Nomear o arquivo, checar duplicidade e organizar no Drive é
responsabilidade do orquestrador (fora deste módulo), não do conector.
"""

from dataclasses import dataclass
from datetime import date


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
