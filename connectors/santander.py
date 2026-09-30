"""Conector Santander PJ — API oficial "Saldo e Extrato" / "Bank Account
Information" v1.0.0 (somente leitura), OAuth2 client_credentials + mTLS.

Credenciais só de variáveis de ambiente (nunca hardcoded, nunca logadas):
  DPA_SANTANDER_CLIENT_ID, DPA_SANTANDER_CLIENT_SECRET,
  DPA_SANTANDER_CERT_CRT (caminho do certificado do e-CNPJ da DPA),
  DPA_SANTANDER_CERT_KEY (caminho da chave privada extraída do .pfx do e-CNPJ)

Contrato validado de ponta a ponta em 30/09/2026: autenticação real +
GET /transactions e GET /provisioneds reais (conta 4177.000130008210,
competência 09/2026) devolvendo lançamentos de verdade (TED, PIX etc.) +
OFX/Excel/PDF gerados localmente a partir desse JSON. Lido originalmente na
documentação do Portal Santander Developers (aba "Documentação técnica" +
"Documentação Funcional" do produto associado à aplicação "Plataforma
ERP-DPA API SANTAND"):
  - Token: POST https://trust-open.api.santander.com.br/auth/oauth/v2/token
    (client_id + client_secret + grant_type=client_credentials, mTLS).
  - Extrato de conta Santander própria: combina
    GET /transactions/{agencia.conta} (lançamentos efetivos) e
    GET /provisioneds/{agencia.conta} (lançamentos provisionados) — o
    endpoint genérico /banks/{bank_id}/statements é para Open Finance
    (outras instituições) e não foi usado aqui.
  - `{agencia.conta}`: agência (4 dígitos) + "." + conta com dígito, só
    números, com zeros à esquerda até 12 dígitos (ex.: "4177.000130008210").
  - Cada chamada de API (além do token) exige também o header
    `X-Application-Key: <client_id>`.
  - Paginação: `_limit` (a doc funcional diz até 750, "por página") e
    `_nextPage` (valor de `_pageable.paging` da resposta anterior).
  - Datas de consulta: `initialDate`/`finalDate`, formato `AAAA-MM-DD`.
  - Campos de cada lançamento (efetivos/provisionados): `creditDebitType`
    (CREDITO/DEBITO), `transactionName`, `historicComplement`, `amount`
    (string, SEM sinal — o sinal vem de `creditDebitType`),
    `transactionDate` (formato `DD/MM/AAAA`), `documentNumber`. Não há um ID
    único por lançamento nessas duas rotas (diferente do extrato Open
    Finance, que tem `transactionId`) — o FITID do OFX é sintetizado por
    hash do conteúdo + posição.

Não há exportação nativa de PDF/OFX/Excel nessa API — este conector gera os
três localmente a partir do JSON de transações (`connectors/santander_pdf.py`
para o PDF, mesmo padrão do Inter/Sicoob). Não existe um ID único por
lançamento nas rotas `/transactions`/`/provisioneds` para conta própria (ao
contrário do extrato Open Finance) — o `FITID` do OFX é sintetizado por hash
do conteúdo + posição.
"""

import hashlib
import os
from datetime import date, datetime

import requests

from . import santander_pdf
from .base import BankConnector, Extrato

BASE_URL = "https://trust-open.api.santander.com.br/bank_account_information/v1"
TOKEN_URL = "https://trust-open.api.santander.com.br/auth/oauth/v2/token"


def _conta_padded(conta: str) -> str:
    """"13000821-0" -> "000130008210" (conta+dígito, só números, 12 dígitos)."""
    return "".join(ch for ch in conta if ch.isdigit()).zfill(12)


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
        return {
            "Authorization": f"Bearer {self._token}",
            "X-Application-Key": self.client_id,
        }

    def _buscar_paginado(self, path: str, agencia_conta: str, inicio: date, fim: date) -> list[dict]:
        itens: list[dict] = []
        next_page = None
        for _ in range(20):  # limite de segurança contra paginação mal comportada
            params = {
                "initialDate": inicio.isoformat(),
                "finalDate": fim.isoformat(),
                "_limit": 750,
            }
            if next_page:
                params["_nextPage"] = next_page
            resp = requests.get(
                f"{BASE_URL}{path}/{agencia_conta}",
                headers=self._headers(),
                params=params,
                cert=self.cert,
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
            content = body.get("_content") or []
            itens.extend(content)
            next_page = (body.get("_pageable") or {}).get("paging")
            if not content or not next_page:
                break
        return itens

    def baixar_extrato(self, conta: str, inicio: date, fim: date) -> Extrato:
        agencia_conta = f"{self.agencia}.{_conta_padded(conta)}"

        efetivos = self._buscar_paginado("/transactions", agencia_conta, inicio, fim)
        provisionados = self._buscar_paginado("/provisioneds", agencia_conta, inicio, fim)

        transacoes = [_normalizar(item, provisionado=False) for item in efetivos]
        transacoes += [_normalizar(item, provisionado=True) for item in provisionados]

        pdf = santander_pdf.gerar_pdf(
            transacoes,
            conta=conta,
            agencia=self.agencia,
            razao_social=self.razao_social,
            inicio=inicio,
            fim=fim,
        )
        ofx = _gerar_ofx(transacoes, conta, inicio, fim).encode("utf-8")
        xlsx = _gerar_xlsx(transacoes)

        return Extrato(pdf=pdf, ofx=ofx, xlsx=xlsx, indisponiveis=None)


def _normalizar(item: dict, provisionado: bool) -> dict:
    try:
        valor = abs(float(item.get("amount", 0)))
    except (TypeError, ValueError):
        valor = 0.0
    return {
        "data": item.get("transactionDate", ""),
        "credito": item.get("creditDebitType") == "CREDITO",
        "valor": valor,
        "descricao": item.get("transactionName") or "",
        "complemento": item.get("historicComplement") or "",
        "documento": item.get("documentNumber") or "",
        "provisionado": provisionado,
    }


def _data_iso(data_br: str) -> str:
    """"25/01/2024" -> "20240125". Devolve string vazia se o formato não bater."""
    try:
        return datetime.strptime(data_br, "%d/%m/%Y").strftime("%Y%m%d")
    except (ValueError, TypeError):
        return ""


def _fitid(t: dict, indice: int) -> str:
    base = f"{t['data']}|{t['valor']}|{t['descricao']}|{t['documento']}|{indice}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:20].upper()


def _gerar_ofx(transacoes: list[dict], conta: str, inicio: date, fim: date) -> str:
    linhas = [
        "OFXHEADER:100",
        "DATA:OFXSGML",
        "VERSION:102",
        "SECURITY:NONE",
        "ENCODING:UTF-8",
        "CHARSET:UTF-8",
        "COMPRESSION:NONE",
        "OLDFILEUID:NONE",
        "NEWFILEUID:NONE",
        "",
        "<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS>",
        "<CURDEF>BRL",
        f"<BANKACCTFROM><BANKID>033</BANKID><ACCTID>{conta}</ACCTID><ACCTTYPE>CHECKING</ACCTTYPE></BANKACCTFROM>",
        "<BANKTRANLIST>",
        f"<DTSTART>{inicio.strftime('%Y%m%d')}",
        f"<DTEND>{fim.strftime('%Y%m%d')}",
    ]
    for i, t in enumerate(transacoes, start=1):
        valor = t["valor"] if t["credito"] else -t["valor"]
        memo = f"{t['descricao']} {t['complemento']}".strip()
        if t["provisionado"]:
            memo = f"[PROVISIONADO] {memo}".strip()
        linhas += [
            "<STMTTRN>",
            f"<TRNTYPE>{'CREDIT' if t['credito'] else 'DEBIT'}",
            f"<DTPOSTED>{_data_iso(t['data'])}",
            f"<TRNAMT>{valor}",
            f"<FITID>{_fitid(t, i)}",
            f"<MEMO>{memo}",
            "</STMTTRN>",
        ]
    linhas += ["</BANKTRANLIST>", "</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"]
    return "\n".join(linhas)


def _gerar_xlsx(transacoes: list[dict]) -> bytes:
    from io import BytesIO

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Data", "Tipo", "Valor", "Descrição", "Complemento", "Documento", "Provisionado"])
    for t in transacoes:
        ws.append(
            [
                t["data"],
                "CREDITO" if t["credito"] else "DEBITO",
                t["valor"],
                t["descricao"],
                t["complemento"],
                t["documento"],
                "SIM" if t["provisionado"] else "NAO",
            ]
        )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
