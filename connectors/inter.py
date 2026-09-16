"""Conector Banco Inter PJ — API oficial (OAuth2 client_credentials + mTLS).

Credenciais vêm só de variáveis de ambiente (nunca hardcoded, nunca logadas):
  DPA_INTER_CLIENT_ID, DPA_INTER_CLIENT_SECRET,
  DPA_INTER_CERT_CRT (caminho do arquivo .crt),
  DPA_INTER_CERT_KEY (caminho do arquivo .key)

Baseado na documentação pública do portal developers.bancointer.com.br.
Os caminhos de endpoint abaixo devem ser conferidos contra o portal no
momento da ativação (a Inter versiona/ajusta rotas com alguma frequência) —
o que já está confiável hoje é o formato do fluxo (OAuth2 + mTLS + escopo
`extrato.read`).
"""

import base64
import os
from datetime import date

import requests

from .base import BankConnector, Extrato

BASE_URL = "https://cdpj.partners.bancointer.com.br"


class InterConnector(BankConnector):
    nome = "Inter"

    def __init__(self):
        self.client_id = os.environ["DPA_INTER_CLIENT_ID"]
        self.client_secret = os.environ["DPA_INTER_CLIENT_SECRET"]
        self.cert = (
            os.environ["DPA_INTER_CERT_CRT"],
            os.environ["DPA_INTER_CERT_KEY"],
        )
        self._token: str | None = None

    def autenticar(self) -> None:
        resp = requests.post(
            f"{BASE_URL}/oauth/v2/token",
            cert=self.cert,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
                "scope": "extrato.read",
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
        params = {
            "dataInicio": inicio.isoformat(),
            "dataFim": fim.isoformat(),
        }
        resp = requests.get(
            f"{BASE_URL}/banking/v2/extrato",
            headers=self._headers(),
            params=params,
            cert=self.cert,
            timeout=30,
        )
        resp.raise_for_status()
        movimentos = resp.json()

        indisponiveis = []

        # Endpoint de exportação devolve o arquivo já pronto em base64.
        # Confirmar no portal se o parâmetro de formato é `tipoArquivo` ou
        # equivalente vigente no momento da ativação.
        def _exportar(formato: str) -> bytes | None:
            r = requests.get(
                f"{BASE_URL}/banking/v2/extrato/exportar",
                headers=self._headers(),
                params={**params, "tipoArquivo": formato},
                cert=self.cert,
                timeout=30,
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            conteudo_b64 = r.json().get("pdf") or r.json().get("arquivo")
            return base64.b64decode(conteudo_b64) if conteudo_b64 else None

        pdf = _exportar("PDF")
        if pdf is None:
            indisponiveis.append("PDF")

        ofx = _exportar("OFX")
        if ofx is None:
            indisponiveis.append("OFX")

        # A API do Inter não costuma oferecer exportação nativa em Excel;
        # ficará marcado como indisponível a menos que a conta ofereça.
        indisponiveis.append("EXCEL")

        return Extrato(pdf=pdf, ofx=ofx, xlsx=None, indisponiveis=indisponiveis)
