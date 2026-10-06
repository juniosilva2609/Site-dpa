"""Conector Banco Inter PJ — API oficial (OAuth2 client_credentials + mTLS).

Credenciais vêm só de variáveis de ambiente (nunca hardcoded, nunca logadas):
  DPA_INTER_CLIENT_ID, DPA_INTER_CLIENT_SECRET,
  DPA_INTER_CERT_CRT (caminho do arquivo .crt),
  DPA_INTER_CERT_KEY (caminho do arquivo .key)

Contrato confirmado por teste real em produção (16/09/2026 e 06/10/2026):
  - Token: POST /oauth/v2/token (client_id + client_secret +
    grant_type=client_credentials + scope=extrato.read, mTLS).
  - Extrato (JSON): GET /banking/v2/extrato?dataInicio=AAAA-MM-DD&dataFim=...
    — `{"transacoes": [...]}` com o texto que o banco exibe no PDF
    (`descricao` = "PIX ENVIADO - Cp :...").
  - Extrato completo (JSON, paginado): GET /banking/v2/extrato/completo
    (mesmas datas + pagina/tamanhoPagina) — mesmos lançamentos com
    `dataInclusao` e na ordem do PDF oficial (mais recente primeiro dentro
    do dia); boletos trazem `detalhes.nossoNumero`.
  - Saldo: GET /banking/v2/saldo — sem data devolve o saldo atual
    (disponível + bloqueios); com `dataSaldo=AAAA-MM-DD` devolve o saldo
    disponível ao fim daquele dia (conferido contra o PDF oficial).
  - PDF nativo: GET /banking/v2/extrato/exportar — embute fontes grandes
    demais para o limite de upload da integração com o Google Drive, então
    não é usado; `inter_pdf.gerar_pdf` remonta o mesmo layout a partir dos
    dados acima.
  - Não existe exportação nativa de OFX nem Excel nessa API — este
    conector gera os dois a partir do `/extrato`.
"""

import hashlib
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from . import inter_pdf
from .base import BankConnector, Extrato

BASE_URL = "https://cdpj.partners.bancointer.com.br"


class InterConnector(BankConnector):
    nome = "Inter"

    def __init__(self, agencia: str, razao_social: str, credenciais_env: dict, cnpj: str = ""):
        self.agencia = agencia
        self.razao_social = razao_social
        self.cnpj = cnpj
        self.client_id = os.environ[credenciais_env["client_id"]]
        self.client_secret = os.environ[credenciais_env["client_secret"]]
        self.cert = (
            os.environ[credenciais_env["certificado"]],
            os.environ[credenciais_env["chave_privada"]],
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

    def _get(self, caminho: str, **params) -> dict:
        resp = requests.get(
            f"{BASE_URL}{caminho}", headers=self._headers(), params=params, cert=self.cert, timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def _extrato_completo(self, inicio: date, fim: date) -> list[dict]:
        transacoes, pagina = [], 0
        while True:
            dados = self._get(
                "/banking/v2/extrato/completo",
                dataInicio=inicio.isoformat(),
                dataFim=fim.isoformat(),
                pagina=pagina,
                tamanhoPagina=1000,
            )
            transacoes += dados.get("transacoes", [])
            if dados.get("ultimaPagina", True):
                return transacoes
            pagina += 1

    def baixar_extrato(self, conta: str, inicio: date, fim: date) -> Extrato:
        datas = {"dataInicio": inicio.isoformat(), "dataFim": fim.isoformat()}
        transacoes = self._get("/banking/v2/extrato", **datas).get("transacoes", [])
        completo = self._extrato_completo(inicio, fim)
        saldo_inicial = float(
            self._get("/banking/v2/saldo", dataSaldo=(inicio - timedelta(days=1)).isoformat())["disponivel"]
        )
        saldo_final = float(self._get("/banking/v2/saldo", dataSaldo=fim.isoformat())["disponivel"])
        saldo_atual = self._get("/banking/v2/saldo")

        lancamentos = inter_pdf.montar_lancamentos(transacoes, completo)
        calculado = round(saldo_inicial + sum(lanc["valor"] for lanc in lancamentos), 2)
        if abs(calculado - saldo_final) > 0.005:
            raise inter_pdf.ExtratoInconsistente(
                f"saldo final calculado ({calculado:.2f}) difere do saldo do banco em {fim} ({saldo_final:.2f})"
            )

        pdf = inter_pdf.gerar_pdf(
            lancamentos,
            saldo_inicial=saldo_inicial,
            saldo_atual=saldo_atual,
            conta=conta,
            agencia=self.agencia,
            razao_social=self.razao_social,
            cnpj=self.cnpj,
            inicio=inicio,
            fim=fim,
            solicitado_em=datetime.now(ZoneInfo("America/Sao_Paulo")),
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
