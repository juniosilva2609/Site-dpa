"""Conector Santander PJ — API oficial "Balance and Extract" (saldo e
extrato, somente leitura), OAuth2 client_credentials + mTLS.

Credenciais só de variáveis de ambiente (nunca hardcoded, nunca logadas):
  DPA_SANTANDER_CLIENT_ID, DPA_SANTANDER_CLIENT_SECRET,
  DPA_SANTANDER_CERT_CRT (caminho do certificado do e-CNPJ da DPA),
  DPA_SANTANDER_CERT_KEY (caminho da chave privada extraída do .pfx do e-CNPJ)

Status em 30/09/2026: **autenticação confirmada por chamada real** —
`autenticar()` foi testado em produção com client_id/client_secret/
certificado/chave reais da DPA e devolveu um token válido. O endpoint de
extrato/saldo do produto "Balance and Extract" AINDA NÃO foi confirmado:
três caminhos plausíveis (`/balances_extracts/v1/bank_accounts/{agencia.
conta}/...`) foram testados e o gateway do Santander devolveu "Unable to
identify proxy for host" — ou seja, esse proxy/produto não existe nesse
caminho para esta aplicação. O caminho certo só aparece na documentação da
aplicação "Plataforma ERP-DPA API SANTAND" depois de logar no Portal
Santander Developers (developer.santander.com.br → Minhas Aplicações → essa
aplicação → documentação/Swagger do produto Balance and Extract).
`baixar_extrato` levanta `NotImplementedError` até esse caminho ser
confirmado (ver TODO abaixo). Enquanto isso, `config/empresas.yaml` mantém
`integracao.status: pendente_cadastro` — este conector não é chamado pelo
orquestrador (`connectors/runner.py`) até que esse status mude para `ativo`,
depois de um teste de ponta a ponta bem-sucedido (mesmo critério usado para
Inter e Sicoob).
"""

import os
from datetime import date

import requests

from .base import BankConnector, Extrato

BASE_URL = "https://trust-open.api.santander.com.br"
TOKEN_URL = f"{BASE_URL}/auth/oauth/v2/token"


def _numero_conta_sem_pontuacao(conta: str) -> str:
    """"13000821-0" -> "130008210" (conta + dígito, só números)."""
    return "".join(ch for ch in conta if ch.isdigit())


class SantanderConnector(BankConnector):
    nome = "Santander"

    def __init__(self, agencia: str, razao_social: str):
        self.agencia = agencia
        self.razao_social = razao_social
        self.client_id = os.environ["DPA_SANTANDER_CLIENT_ID"]
        self.client_secret = os.environ["DPA_SANTANDER_CLIENT_SECRET"]
        self.cert = (
            os.environ["DPA_SANTANDER_CERT_CRT"],
            os.environ["DPA_SANTANDER_CERT_KEY"],
        )
        self._token: str | None = None

    def autenticar(self) -> None:
        resp = requests.post(
            TOKEN_URL,
            cert=self.cert,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=30,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]

    def _headers(self) -> dict:
        if not self._token:
            self.autenticar()
        return {"Authorization": f"Bearer {self._token}"}

    def baixar_extrato(self, conta: str, inicio: date, fim: date) -> Extrato:
        # TODO (bloqueado): confirmar no Portal Santander Developers
        # (developer.santander.com.br → Minhas Aplicações → "Plataforma
        # ERP-DPA API SANTAND" → documentação/Swagger do produto Balance and
        # Extract) o caminho exato do endpoint e o formato da resposta (nome
        # dos campos de transação). Caminhos já testados e descartados em
        # 30/09/2026 (gateway devolveu "Unable to identify proxy for host"):
        #   /balances_extracts/v1/bank_accounts/{agencia}.{conta}/balances
        #   /balances_extracts/v1/bank_accounts/{agencia}.{conta}/extracts
        #   /balances_extracts/v1/bank_accounts/{agencia}.{conta}
        # Depois de confirmado, implementar aqui no mesmo padrão de
        # connectors/inter.py e connectors/sicoob.py (GET com headers de
        # auth + mTLS, gerar PDF/OFX/Excel localmente a partir do JSON de
        # transações).
        raise NotImplementedError(
            "endpoint de extrato do Santander ainda não confirmado — "
            "autenticação já validada, falta o caminho certo do Portal "
            "(ver TODO em connectors/santander.py)"
        )
