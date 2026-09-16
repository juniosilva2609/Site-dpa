"""Conector Sicoob PJ — API oficial (OAuth2 client_credentials + mTLS).

Credenciais vêm só de variáveis de ambiente:
  DPA_SICOOB_CLIENT_ID
  DPA_SICOOB_CERT_PEM (caminho do certificado convertido para .pem)
  DPA_SICOOB_CERT_KEY (caminho da chave privada convertida para .pem)

O Sicoob emite o certificado em .pfx (com senha). A biblioteca `requests`
usa cert/key separados em PEM, então o .pfx precisa ser convertido uma
única vez, por exemplo:

    openssl pkcs12 -in certificado.pfx -clcerts -nokeys -out sicoob_cert.pem
    openssl pkcs12 -in certificado.pfx -nocerts -nodes -out sicoob_key.pem

Baseado na documentação pública do portal developers.sicoob.com.br. A URL
de produção do endpoint de conta corrente deve ser confirmada no portal no
momento da ativação (o sandbox público é
https://sandbox.sicoob.com.br/sicoob/sandbox/conta-corrente/v4) — o que já
está confiável hoje é o fluxo OAuth2 client_credentials + mTLS via Keycloak.
"""

import os
from datetime import date

import requests

from .base import BankConnector, Extrato

TOKEN_URL = "https://auth.sicoob.com.br/auth/realms/cooperado/protocol/openid-connect/token"
API_BASE_URL = os.environ.get(
    "DPA_SICOOB_API_BASE_URL", "https://api.sicoob.com.br/conta-corrente/v4"
)


class SicoobConnector(BankConnector):
    nome = "Sicoob"

    def __init__(self):
        self.client_id = os.environ["DPA_SICOOB_CLIENT_ID"]
        self.cert = (
            os.environ["DPA_SICOOB_CERT_PEM"],
            os.environ["DPA_SICOOB_CERT_KEY"],
        )
        self._token: str | None = None

    def autenticar(self) -> None:
        resp = requests.post(
            TOKEN_URL,
            cert=self.cert,
            data={
                "client_id": self.client_id,
                "grant_type": "client_credentials",
                "scope": "cco_consulta",  # confirmar nome exato do escopo no portal
            },
            timeout=30,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]

    def _headers(self) -> dict:
        if not self._token:
            self.autenticar()
        return {
            "Authorization": f"Bearer {self._token}",
            "client_id": self.client_id,
        }

    def baixar_extrato(self, conta: str, inicio: date, fim: date) -> Extrato:
        resp = requests.get(
            f"{API_BASE_URL}/extrato/{inicio.year}/{inicio.month:02d}",
            headers=self._headers(),
            params={
                "diaInicial": inicio.day,
                "diaFinal": fim.day,
                "numeroContaCorrente": conta,
            },
            cert=self.cert,
            timeout=30,
        )
        resp.raise_for_status()
        dados = resp.json()

        # A API do Sicoob devolve os lançamentos em JSON; PDF/OFX nativos
        # não costumam vir desse mesmo endpoint — confirmar no portal se
        # há exportação direta. Sem isso, o extrato em JSON precisa ser
        # convertido para OFX localmente (fora deste conector).
        indisponiveis = ["PDF", "EXCEL"]

        return Extrato(pdf=None, ofx=None, xlsx=None, indisponiveis=indisponiveis)
