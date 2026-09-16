"""Conector Sicoob PJ — API oficial (OAuth2 client_credentials + mTLS).

Credenciais vêm só de variáveis de ambiente:
  DPA_SICOOB_CLIENT_ID
  DPA_SICOOB_CERT_PEM (caminho do certificado convertido para .pem)
  DPA_SICOOB_CERT_KEY (caminho da chave privada convertida para .pem)

O Sicoob emite o certificado em .pfx (com senha). A biblioteca `requests`
usa cert/key separados em PEM; certificados e-CNPJ mais antigos usam
criptografia RC2, que exige a flag `-legacy` do OpenSSL 3.x na conversão
(ver docs/setup-bancos.md).

Contrato confirmado por teste real em produção (16/09/2026):
  - Token: POST /auth/realms/cooperado/protocol/openid-connect/token
    (client_id + grant_type=client_credentials + scope=cco_consulta,
    mTLS, SEM client_secret).
  - Extrato: GET /conta-corrente/v4/extrato/{mes}/{ano}
    (atenção: mês vem ANTES do ano na URL) com query
    diaInicial, diaFinal, numeroContaCorrente (conta + dígito, sem
    pontuação/hífen, ex: "685348" para a conta 68.534-8) e apenas o
    header Authorization (client_id como header não é necessário aqui).
  - A resposta é só JSON (saldoAtual, saldoAnterior, transacoes[...]).
    O Sicoob não oferece exportação nativa em PDF/OFX nesse endpoint —
    por isso este conector gera o OFX e a planilha localmente a partir
    do JSON; PDF ainda não está implementado (ver TODO abaixo).
"""

import os
from datetime import date, datetime

import requests

from .base import BankConnector, Extrato

TOKEN_URL = "https://auth.sicoob.com.br/auth/realms/cooperado/protocol/openid-connect/token"
API_BASE_URL = os.environ.get(
    "DPA_SICOOB_API_BASE_URL", "https://api.sicoob.com.br/conta-corrente/v4"
)


def _numero_conta_sem_pontuacao(conta: str) -> str:
    """"68.534-8" -> "685348" (conta + dígito, só números)."""
    return "".join(ch for ch in conta if ch.isdigit())


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
                "scope": "cco_consulta",
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
        resp = requests.get(
            f"{API_BASE_URL}/extrato/{inicio.month:02d}/{inicio.year}",
            headers=self._headers(),
            params={
                "diaInicial": inicio.day,
                "diaFinal": fim.day,
                "numeroContaCorrente": _numero_conta_sem_pontuacao(conta),
            },
            cert=self.cert,
            timeout=30,
        )
        resp.raise_for_status()
        dados = resp.json().get("resultado", {})
        transacoes = dados.get("transacoes", [])

        ofx = _gerar_ofx(transacoes, conta, inicio, fim).encode("utf-8")
        xlsx = _gerar_xlsx(transacoes)

        # TODO: gerar PDF (layout próprio) a partir do mesmo JSON —
        # o Sicoob não oferece exportação nativa em PDF nesse endpoint.
        indisponiveis = ["PDF"]

        return Extrato(pdf=None, ofx=ofx, xlsx=xlsx, indisponiveis=indisponiveis)


def _gerar_ofx(transacoes: list[dict], conta: str, inicio: date, fim: date) -> str:
    def fmt_data(iso: str) -> str:
        return datetime.fromisoformat(iso).strftime("%Y%m%d%H%M%S")

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
        f"<BANKACCTFROM><BANKID>756</BANKID><ACCTID>{conta}</ACCTID><ACCTTYPE>CHECKING</ACCTTYPE></BANKACCTFROM>",
        "<BANKTRANLIST>",
        f"<DTSTART>{inicio.strftime('%Y%m%d')}",
        f"<DTEND>{fim.strftime('%Y%m%d')}",
    ]
    for t in transacoes:
        sinal = "-" if t.get("tipo") == "DEBITO" else ""
        linhas += [
            "<STMTTRN>",
            f"<TRNTYPE>{'DEBIT' if t.get('tipo') == 'DEBITO' else 'CREDIT'}",
            f"<DTPOSTED>{fmt_data(t['data'])}",
            f"<TRNAMT>{sinal}{t.get('valor', '0')}",
            f"<FITID>{t.get('transactionId', '')}",
            f"<MEMO>{t.get('descricao', '')} {t.get('descInfComplementar', '')}".strip(),
            "</STMTTRN>",
        ]
    linhas += ["</BANKTRANLIST>", "</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"]
    return "\n".join(linhas)


def _gerar_xlsx(transacoes: list[dict]) -> bytes:
    from io import BytesIO

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Data", "Tipo", "Valor", "Descrição", "Complemento", "Documento"])
    for t in transacoes:
        ws.append(
            [
                t.get("data", ""),
                t.get("tipo", ""),
                float(t.get("valor", 0)),
                t.get("descricao", ""),
                t.get("descInfComplementar", ""),
                t.get("numeroDocumento", ""),
            ]
        )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
