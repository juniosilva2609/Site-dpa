"""Conector Banco Inter PJ — API oficial (OAuth2 client_credentials + mTLS).

Credenciais vêm só de variáveis de ambiente (nunca hardcoded, nunca logadas):
  DPA_INTER_CLIENT_ID, DPA_INTER_CLIENT_SECRET,
  DPA_INTER_CERT_CRT (caminho do arquivo .crt),
  DPA_INTER_CERT_KEY (caminho do arquivo .key)

Contrato confirmado por teste real em produção (16/09/2026):
  - Token: POST /oauth/v2/token (client_id + client_secret +
    grant_type=client_credentials + scope=extrato.read, mTLS).
  - Extrato (lista de lançamentos, JSON): GET /banking/v2/extrato
    ?dataInicio=AAAA-MM-DD&dataFim=AAAA-MM-DD — devolve só
    `{"transacoes": [...]}`, sem saldo.
  - Extrato em PDF nativo: GET /banking/v2/extrato/exportar
    (mesmos parâmetros de data) — devolve `{"pdf": "<base64>"}`.
    Confirmado que parâmetros de formato (`tipoArquivo`, `formato`) são
    ignorados: esse endpoint só devolve PDF, nunca OFX/Excel.
  - Não existe exportação nativa de OFX nem Excel nessa API — por isso
    este conector gera os dois localmente a partir do JSON de transações
    (mesmo padrão usado no conector do Sicoob).

Sobre o PDF: o endpoint nativo devolve um PDF com fontes customizadas
embutidas, grande demais para o limite de upload por chamada da
integração com o Google Drive usada por este projeto. Por isso o PDF
salvo no Drive é gerado localmente (`inter_pdf.gerar_pdf`, via
reportlab, fontes padrão sem embutimento) a partir do mesmo JSON de
transações — não é o extrato oficial do banco (isso é explicitado no
próprio rodapé do PDF gerado). O PDF nativo do banco pode ser obtido
diretamente pelo app/site do Inter quando o documento oficial for
necessário.
"""

import hashlib
import os
from datetime import date, datetime

import requests

from . import inter_pdf
from .base import BankConnector, Extrato

BASE_URL = "https://cdpj.partners.bancointer.com.br"


class InterConnector(BankConnector):
    nome = "Inter"

    def __init__(self, agencia: str, razao_social: str):
        self.agencia = agencia
        self.razao_social = razao_social
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
        params = {"dataInicio": inicio.isoformat(), "dataFim": fim.isoformat()}

        resp = requests.get(
            f"{BASE_URL}/banking/v2/extrato",
            headers=self._headers(),
            params=params,
            cert=self.cert,
            timeout=30,
        )
        resp.raise_for_status()
        transacoes = resp.json().get("transacoes", [])

        pdf = inter_pdf.gerar_pdf(
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


def _fitid(t: dict) -> str:
    base = f"{t.get('dataEntrada')}|{t.get('valor')}|{t.get('titulo')}|{t.get('descricao')}"
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
        f"<BANKACCTFROM><BANKID>077</BANKID><ACCTID>{conta}</ACCTID><ACCTTYPE>CHECKING</ACCTTYPE></BANKACCTFROM>",
        "<BANKTRANLIST>",
        f"<DTSTART>{inicio.strftime('%Y%m%d')}",
        f"<DTEND>{fim.strftime('%Y%m%d')}",
    ]
    for t in transacoes:
        credito = t.get("tipoOperacao") == "C"
        valor = float(t.get("valor", 0))
        data_iso = datetime.strptime(t["dataEntrada"], "%Y-%m-%d").strftime("%Y%m%d")
        memo = f"{t.get('titulo', '')} {t.get('descricao', '')}".strip()
        linhas += [
            "<STMTTRN>",
            f"<TRNTYPE>{'CREDIT' if credito else 'DEBIT'}",
            f"<DTPOSTED>{data_iso}",
            f"<TRNAMT>{valor if credito else -valor}",
            f"<FITID>{_fitid(t)}",
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
    ws.append(["Data", "Tipo", "Operação", "Valor", "Título", "Descrição"])
    for t in transacoes:
        ws.append(
            [
                t.get("dataEntrada", ""),
                t.get("tipoTransacao", ""),
                "CREDITO" if t.get("tipoOperacao") == "C" else "DEBITO",
                float(t.get("valor", 0)),
                t.get("titulo", ""),
                t.get("descricao", ""),
            ]
        )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
