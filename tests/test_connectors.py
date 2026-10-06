from datetime import date
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
import requests
from pypdf import PdfReader

from connectors import inter_pdf
from connectors.inter import InterConnector
from connectors.santander import SantanderConnector
from connectors.sicoob import SicoobConnector


INTER_ENV = {
    "client_id": "DPA_INTER_CLIENT_ID",
    "client_secret": "DPA_INTER_CLIENT_SECRET",
    "certificado": "DPA_INTER_CERT_CRT",
    "chave_privada": "DPA_INTER_CERT_KEY",
}

INTER_SIMPLES = [
    {"dataEntrada": "2026-09-01", "tipoTransacao": "PIX", "tipoOperacao": "C", "valor": "100.0",
     "titulo": "Pix recebido", "descricao": "PIX RECEBIDO - Cp :1234-Cliente X"},
    {"dataEntrada": "2026-09-01", "tipoTransacao": "PIX", "tipoOperacao": "D", "valor": "30.0",
     "titulo": "Pix enviado ", "descricao": "PIX ENVIADO - Cp :5678-Fornecedor Y"},
]
INTER_COMPLETO = [
    {"dataTransacao": "2026-09-01", "dataInclusao": "2026-09-01 15:00:00.000", "tipoOperacao": "D",
     "valor": "30.00", "titulo": "Pix enviado ", "descricao": "Fornecedor Y"},
    {"dataTransacao": "2026-09-01", "dataInclusao": "2026-09-01 09:00:00.000", "tipoOperacao": "C",
     "valor": "100.00", "titulo": "Pix recebido", "descricao": "Cliente X"},
]


def _resp(corpo):
    resp = MagicMock(status_code=200)
    resp.raise_for_status.return_value = None
    resp.json.return_value = corpo
    return resp


def _fake_inter_get(saldo_fim=1070.0):
    def fake_get(url, headers, params, cert, timeout):
        if url.endswith("/banking/v2/extrato"):
            return _resp({"transacoes": INTER_SIMPLES})
        if url.endswith("/banking/v2/extrato/completo"):
            return _resp({"transacoes": INTER_COMPLETO, "ultimaPagina": True})
        if url.endswith("/banking/v2/saldo"):
            por_data = {"2026-08-31": 1000.0, "2026-09-15": saldo_fim}
            if "dataSaldo" in params:
                return _resp({"disponivel": por_data[params["dataSaldo"]]})
            return _resp({"disponivel": 900.0, "bloqueadoCheque": 0.0})
        raise AssertionError(url)

    return fake_get


def _inter_conector(monkeypatch, tmp_path):
    monkeypatch.setenv("DPA_INTER_CLIENT_ID", "id")
    monkeypatch.setenv("DPA_INTER_CLIENT_SECRET", "secret")
    monkeypatch.setenv("DPA_INTER_CERT_CRT", str(tmp_path / "c.crt"))
    monkeypatch.setenv("DPA_INTER_CERT_KEY", str(tmp_path / "c.key"))
    return InterConnector(agencia="0001-9", razao_social="Teste Ltda", credenciais_env=INTER_ENV,
                          cnpj="00.000.000/0001-00")


def test_inter_autentica_e_baixa_extrato_com_saldos(monkeypatch, tmp_path):
    conector = _inter_conector(monkeypatch, tmp_path)
    with patch("connectors.inter.requests.post", return_value=_resp({"access_token": "tok123"})) as post, patch(
        "connectors.inter.requests.get", side_effect=_fake_inter_get()
    ):
        extrato = conector.baixar_extrato("123456", date(2026, 9, 1), date(2026, 9, 15))

    post.assert_called_once()
    assert conector._token == "tok123"
    texto_pdf = "".join(pagina.extract_text() for pagina in PdfReader(BytesIO(extrato.pdf)).pages)
    assert "Saldo do dia: R$ 1.070,00" in texto_pdf
    assert 'Pix enviado: "Cp :5678-Fornecedor Y"' in texto_pdf
    assert "R$ 900,00" in texto_pdf
    assert extrato.ofx is not None and b"<STMTTRN>" in extrato.ofx
    assert extrato.xlsx is not None


def test_inter_saldo_que_nao_fecha_com_o_banco_falha(monkeypatch, tmp_path):
    conector = _inter_conector(monkeypatch, tmp_path)
    with patch("connectors.inter.requests.post", return_value=_resp({"access_token": "t"})), patch(
        "connectors.inter.requests.get", side_effect=_fake_inter_get(saldo_fim=999.0)
    ):
        with pytest.raises(inter_pdf.ExtratoInconsistente, match="saldo final"):
            conector.baixar_extrato("123456", date(2026, 9, 1), date(2026, 9, 15))


def test_inter_lancamentos_seguem_ordem_do_completo_com_saldo_acumulado():
    lancamentos = inter_pdf.com_saldos(inter_pdf.montar_lancamentos(INTER_SIMPLES, INTER_COMPLETO), 1000.0)
    assert [(lanc["texto"], lanc["valor"], lanc["saldo"]) for lanc in lancamentos] == [
        ('Pix enviado: "Cp :5678-Fornecedor Y"', -30.0, 970.0),
        ('Pix recebido: "Cp :1234-Cliente X"', 100.0, 1070.0),
    ]


def test_inter_boletos_de_mesmo_valor_casam_pelo_nosso_numero():
    simples = [
        {"dataEntrada": "2026-09-10", "tipoOperacao": "C", "valor": "574.0",
         "titulo": "Boleto de cobrança recebido", "descricao": f"RECEBIMENTO TITULO - 112/{n}"}
        for n in ("111", "222")
    ]
    completo = [
        {"dataTransacao": "2026-09-10", "tipoOperacao": "C", "valor": "574.00",
         "titulo": "Boleto de cobrança recebido", "descricao": "X", "detalhes": {"nossoNumero": n}}
        for n in ("222", "111")
    ]
    textos = [lanc["texto"] for lanc in inter_pdf.montar_lancamentos(simples, completo)]
    assert textos == ['Boleto de cobranca recebido: "112/222"', 'Boleto de cobranca recebido: "112/111"']


@pytest.mark.parametrize(
    "titulo, descricao, descricao_completo, esperado",
    [
        ("Pagamento efetuado", "PAGAMENTO DARF - ", "DARF - Metalúrgica Amapá SA",
         "Pagamento efetuado DARF - Metalurgica Amapa SA"),
        ("Pagamento Simples Nacional", "PAGAMENTO SIMPLES NACIONAL - SIMPLES NACIONAL", "", "SIMPLES NACIONAL"),
        ("Pagamento efetuado", "PAGAMENTO DE TITULO - ENERGIA E ÁGUA", "", 'Pagamento efetuado: "ENERGIA E AGUA"'),
        ("Pix enviado ", "PIX ENVIADO - Cp :08561701-OAB  SP", "", 'Pix enviado: "Cp :08561701-OAB SP"'),
    ],
)
def test_inter_texto_igual_ao_pdf_do_banco(titulo, descricao, descricao_completo, esperado):
    simples = {"titulo": titulo, "descricao": descricao}
    assert inter_pdf.texto_lancamento(simples, {"descricao": descricao_completo}) == esperado


def test_inter_erro_401_propaga(monkeypatch, tmp_path):
    monkeypatch.setenv("DPA_INTER_CLIENT_ID", "id")
    monkeypatch.setenv("DPA_INTER_CLIENT_SECRET", "secret")
    monkeypatch.setenv("DPA_INTER_CERT_CRT", str(tmp_path / "c.crt"))
    monkeypatch.setenv("DPA_INTER_CERT_KEY", str(tmp_path / "c.key"))
    conector = InterConnector(
        agencia="0001",
        razao_social="Teste",
        credenciais_env={
            "client_id": "DPA_INTER_CLIENT_ID",
            "client_secret": "DPA_INTER_CLIENT_SECRET",
            "certificado": "DPA_INTER_CERT_CRT",
            "chave_privada": "DPA_INTER_CERT_KEY",
        },
    )

    resp = MagicMock(status_code=401)
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=resp)

    with patch("connectors.inter.requests.post", return_value=resp):
        with pytest.raises(requests.exceptions.HTTPError):
            conector.autenticar()


def test_sicoob_autentica_e_baixa_extrato(monkeypatch, tmp_path):
    monkeypatch.setenv("DPA_SICOOB_CLIENT_ID", "id")
    monkeypatch.setenv("DPA_SICOOB_CERT_PEM", str(tmp_path / "c.pem"))
    monkeypatch.setenv("DPA_SICOOB_CERT_KEY", str(tmp_path / "c.key"))

    token_resp = MagicMock(status_code=200)
    token_resp.raise_for_status.return_value = None
    token_resp.json.return_value = {"access_token": "tok456"}

    extrato_resp = MagicMock(status_code=200)
    extrato_resp.raise_for_status.return_value = None
    extrato_resp.json.return_value = {
        "resultado": {
            "saldoAtual": "1000.00",
            "saldoAnterior": "900.00",
            "saldoLimite": "0",
            "saldoBloqueado": "0",
            "saldoBloqueioJudicial": "0",
            "transacoes": [
                {
                    "data": "2026-09-01T10:00:00",
                    "tipo": "CREDITO",
                    "valor": "100.00",
                    "descricao": "Deposito",
                    "descInfComplementar": "",
                    "numeroDocumento": "1",
                    "transactionId": "tx1",
                }
            ],
        }
    }

    conector = SicoobConnector(
        cooperativa="4030-4",
        cooperativa_nome="SICOOB DIVICRED",
        razao_social="Teste Ltda",
        credenciais_env={
            "client_id": "DPA_SICOOB_CLIENT_ID",
            "certificado_pem": "DPA_SICOOB_CERT_PEM",
            "chave_privada": "DPA_SICOOB_CERT_KEY",
        },
    )

    with patch("connectors.sicoob.requests.post", return_value=token_resp), patch(
        "connectors.sicoob.requests.get", return_value=extrato_resp
    ):
        extrato = conector.baixar_extrato("68.534-8", date(2026, 9, 1), date(2026, 9, 15))

    assert extrato.pdf is not None
    assert extrato.ofx is not None
    assert extrato.xlsx is not None


def test_santander_autentica(monkeypatch, tmp_path):
    monkeypatch.setenv("DPA_SANTANDER_CLIENT_ID", "id")
    monkeypatch.setenv("DPA_SANTANDER_CLIENT_SECRET", "secret")
    monkeypatch.setenv("DPA_SANTANDER_CERT_CRT", str(tmp_path / "c.crt"))
    monkeypatch.setenv("DPA_SANTANDER_CERT_KEY", str(tmp_path / "c.key"))

    token_resp = MagicMock(status_code=200)
    token_resp.raise_for_status.return_value = None
    token_resp.json.return_value = {"access_token": "tok789"}

    conector = SantanderConnector(
        agencia="4177",
        razao_social="Teste Ltda",
        credenciais_env={
            "client_id": "DPA_SANTANDER_CLIENT_ID",
            "client_secret": "DPA_SANTANDER_CLIENT_SECRET",
            "certificado": "DPA_SANTANDER_CERT_CRT",
            "chave_privada": "DPA_SANTANDER_CERT_KEY",
        },
    )

    with patch("connectors.santander.requests.post", return_value=token_resp) as post:
        conector.autenticar()

    post.assert_called_once()
    assert conector._token == "tok789"


def test_santander_baixa_extrato_efetivos_e_provisionados(monkeypatch, tmp_path):
    monkeypatch.setenv("DPA_SANTANDER_CLIENT_ID", "id")
    monkeypatch.setenv("DPA_SANTANDER_CLIENT_SECRET", "secret")
    monkeypatch.setenv("DPA_SANTANDER_CERT_CRT", str(tmp_path / "c.crt"))
    monkeypatch.setenv("DPA_SANTANDER_CERT_KEY", str(tmp_path / "c.key"))

    token_resp = MagicMock(status_code=200)
    token_resp.raise_for_status.return_value = None
    token_resp.json.return_value = {"access_token": "tok789"}

    efetivos_resp = MagicMock(status_code=200)
    efetivos_resp.raise_for_status.return_value = None
    efetivos_resp.json.return_value = {
        "_content": [
            {
                "creditDebitType": "CREDITO",
                "transactionName": "TED RECEBIDA",
                "historicComplement": "18715615000160",
                "amount": "636.27",
                "transactionDate": "30/09/2026",
                "documentNumber": "000000",
            }
        ],
        "_pageable": {"totalRecords": "1"},
    }

    provisionados_resp = MagicMock(status_code=200)
    provisionados_resp.raise_for_status.return_value = None
    provisionados_resp.json.return_value = {"_pageable": {"totalRecords": "0"}}

    conector = SantanderConnector(
        agencia="4177",
        razao_social="Teste Ltda",
        credenciais_env={
            "client_id": "DPA_SANTANDER_CLIENT_ID",
            "client_secret": "DPA_SANTANDER_CLIENT_SECRET",
            "certificado": "DPA_SANTANDER_CERT_CRT",
            "chave_privada": "DPA_SANTANDER_CERT_KEY",
        },
    )

    def fake_get(url, **kwargs):
        return efetivos_resp if "/transactions/" in url else provisionados_resp

    with patch("connectors.santander.requests.post", return_value=token_resp), patch(
        "connectors.santander.requests.get", side_effect=fake_get
    ):
        extrato = conector.baixar_extrato("13000821-0", date(2026, 9, 1), date(2026, 9, 30))

    assert extrato.pdf is not None and extrato.pdf.startswith(b"%PDF")
    assert extrato.ofx is not None and b"<TRNAMT>636.27" in extrato.ofx
    assert extrato.xlsx is not None
    assert extrato.indisponiveis is None


def test_santander_pagina_ate_esgotar_nextpage(monkeypatch, tmp_path):
    monkeypatch.setenv("DPA_SANTANDER_CLIENT_ID", "id")
    monkeypatch.setenv("DPA_SANTANDER_CLIENT_SECRET", "secret")
    monkeypatch.setenv("DPA_SANTANDER_CERT_CRT", str(tmp_path / "c.crt"))
    monkeypatch.setenv("DPA_SANTANDER_CERT_KEY", str(tmp_path / "c.key"))

    token_resp = MagicMock(status_code=200)
    token_resp.raise_for_status.return_value = None
    token_resp.json.return_value = {"access_token": "tok789"}

    pagina_1 = MagicMock(status_code=200)
    pagina_1.raise_for_status.return_value = None
    pagina_1.json.return_value = {
        "_content": [{"creditDebitType": "DEBITO", "transactionName": "A", "amount": "1.00", "transactionDate": "01/09/2026", "documentNumber": "1"}],
        "_pageable": {"totalRecords": "2", "paging": "abc123"},
    }
    pagina_2 = MagicMock(status_code=200)
    pagina_2.raise_for_status.return_value = None
    pagina_2.json.return_value = {
        "_content": [{"creditDebitType": "DEBITO", "transactionName": "B", "amount": "2.00", "transactionDate": "02/09/2026", "documentNumber": "2"}],
        "_pageable": {"totalRecords": "2"},
    }
    vazio = MagicMock(status_code=200)
    vazio.raise_for_status.return_value = None
    vazio.json.return_value = {"_pageable": {"totalRecords": "0"}}

    conector = SantanderConnector(
        agencia="4177",
        razao_social="Teste Ltda",
        credenciais_env={
            "client_id": "DPA_SANTANDER_CLIENT_ID",
            "client_secret": "DPA_SANTANDER_CLIENT_SECRET",
            "certificado": "DPA_SANTANDER_CERT_CRT",
            "chave_privada": "DPA_SANTANDER_CERT_KEY",
        },
    )
    chamadas = {"n": 0}

    def fake_get(url, **kwargs):
        if "/provisioneds/" in url:
            return vazio
        chamadas["n"] += 1
        return pagina_1 if chamadas["n"] == 1 else pagina_2

    with patch("connectors.santander.requests.post", return_value=token_resp), patch(
        "connectors.santander.requests.get", side_effect=fake_get
    ):
        itens = conector._buscar_paginado("/transactions", "4177.000130008210", date(2026, 9, 1), date(2026, 9, 30))

    assert len(itens) == 2
    assert chamadas["n"] == 2


def test_sicoob_erro_500_propaga(monkeypatch, tmp_path):
    monkeypatch.setenv("DPA_SICOOB_CLIENT_ID", "id")
    monkeypatch.setenv("DPA_SICOOB_CERT_PEM", str(tmp_path / "c.pem"))
    monkeypatch.setenv("DPA_SICOOB_CERT_KEY", str(tmp_path / "c.key"))
    conector = SicoobConnector(
        cooperativa="4030-4",
        cooperativa_nome="X",
        razao_social="Teste",
        credenciais_env={
            "client_id": "DPA_SICOOB_CLIENT_ID",
            "certificado_pem": "DPA_SICOOB_CERT_PEM",
            "chave_privada": "DPA_SICOOB_CERT_KEY",
        },
    )

    resp = MagicMock(status_code=500)
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=resp)

    with patch("connectors.sicoob.requests.post", return_value=resp):
        with pytest.raises(requests.exceptions.HTTPError):
            conector.autenticar()
