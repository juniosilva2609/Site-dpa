"""Conector Santander PJ — API oficial "Balance and Extract" (saldo e
extrato, somente leitura), OAuth2 client_credentials + mTLS.

Credenciais só de variáveis de ambiente (nunca hardcoded, nunca logadas):
  DPA_SANTANDER_CLIENT_ID, DPA_SANTANDER_CLIENT_SECRET,
  DPA_SANTANDER_CERT_CRT (caminho do certificado do e-CNPJ da DPA),
  DPA_SANTANDER_CERT_KEY (caminho da chave privada extraída do .pfx do e-CNPJ)

Diferente do Inter e do Sicoob, este conector AINDA NÃO foi validado por uma
chamada real em produção — falta a chave privada (protegida dentro do .pfx
do e-CNPJ, com senha, ainda não extraída). O host/endpoint de token abaixo é
o publicamente documentado para integrações Santander Developers Brasil
(client_credentials + mTLS); o endpoint de extrato do produto
"Balance and Extract" não está confirmado, por isso `baixar_extrato` levanta
`NotImplementedError` até o primeiro teste real definir o caminho e o
formato de resposta certos (ver TODO abaixo). Enquanto isso,
`config/empresas.yaml` mantém `integracao.status: pendente_cadastro` — este
conector não é chamado pelo orquestrador (`connectors/runner.py`) até que
esse status mude para `ativo`, depois de um teste de ponta a ponta
bem-sucedido (mesmo critério usado para Inter e Sicoob).
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
        # TODO (bloqueado até o primeiro teste real): confirmar no Portal
        # Santander Developers (aplicação "Plataforma ERP-DPA API SANTAND")
        # o caminho exato do produto "Balance and Extract" e o formato da
        # resposta (nome dos campos de transação), e então implementar aqui
        # no mesmo padrão de connectors/inter.py e connectors/sicoob.py
        # (GET com headers de auth + mTLS, gerar PDF/OFX/Excel localmente a
        # partir do JSON de transações).
        raise NotImplementedError(
            "endpoint de extrato do Santander ainda não confirmado por teste real "
            "— ver TODO em connectors/santander.py"
        )
