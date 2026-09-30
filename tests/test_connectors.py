from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import requests

from connectors.inter import InterConnector
from connectors.santander import SantanderConnector
from connectors.sicoob import SicoobConnector


def test_inter_autentica_e_baixa_extrato(monkeypatch, tmp_path):
    monkeypatch.setenv("DPA_INTER_CLIENT_ID", "id")
    monkeypatch.setenv("DPA_INTER_CLIENT_SECRET", "secret")
    monkeypatch.setenv("DPA_INTER_CERT_CRT", str(tmp_path / "c.crt"))
    monkeypatch.setenv("DPA_INTER_CERT_KEY", str(tmp_path / "c.key"))

    token_resp = MagicMock(status_code=200)
    token_resp.raise_for_status.return_value = None
    token_resp.json.return_value = {"access_token": "tok123"}

    extrato_resp = MagicMock(status_code=200)
    extrato_resp.raise_for_status.return_value = None
    extrato_resp.json.return_value = {
        "transacoes": [
            {
                "dataEntrada": "2026-09-01",
                "tipoTransacao": "PIX",
                "tipoOperacao": "C",
                "valor": "100.00",
                "titulo": "Recebimento",
                "descricao": "Cliente X",
            }
        ]
    }

    conector = InterConnector(agencia="0001", razao_social="Teste Ltda")

    with patch("connectors.inter.requests.post", return_value=token_resp) as post, patch(
        "connectors.inter.requests.get", return_value=extrato_resp
    ) as get:
        extrato = conector.baixar_extrato("123456", date(2026, 9, 1), date(2026, 9, 15))

    post.assert_called_once()
    get.assert_called_once()
    assert conector._token == "tok123"
    assert extrato.pdf is not None
    assert extrato.ofx is not None and b"<STMTTRN>" in extrato.ofx
    assert extrato.xlsx is not None


def test_inter_erro_401_propaga(monkeypatch, tmp_path):
    monkeypatch.setenv("DPA_INTER_CLIENT_ID", "id")
    monkeypatch.setenv("DPA_INTER_CLIENT_SECRET", "secret")
    monkeypatch.setenv("DPA_INTER_CERT_CRT", str(tmp_path / "c.crt"))
    monkeypatch.setenv("DPA_INTER_CERT_KEY", str(tmp_path / "c.key"))
    conector = InterConnector(agencia="0001", razao_social="Teste")

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
        cooperativa="4030-4", cooperativa_nome="SICOOB DIVICRED", razao_social="Teste Ltda"
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

    conector = SantanderConnector(agencia="4177", razao_social="Teste Ltda")

    with patch("connectors.santander.requests.post", return_value=token_resp) as post:
        conector.autenticar()

    post.assert_called_once()
    assert conector._token == "tok789"


def test_santander_baixar_extrato_ainda_nao_implementado(monkeypatch, tmp_path):
    monkeypatch.setenv("DPA_SANTANDER_CLIENT_ID", "id")
    monkeypatch.setenv("DPA_SANTANDER_CLIENT_SECRET", "secret")
    monkeypatch.setenv("DPA_SANTANDER_CERT_CRT", str(tmp_path / "c.crt"))
    monkeypatch.setenv("DPA_SANTANDER_CERT_KEY", str(tmp_path / "c.key"))
    conector = SantanderConnector(agencia="4177", razao_social="Teste Ltda")

    with pytest.raises(NotImplementedError):
        conector.baixar_extrato("13000821-0", date(2026, 9, 1), date(2026, 9, 15))


def test_sicoob_erro_500_propaga(monkeypatch, tmp_path):
    monkeypatch.setenv("DPA_SICOOB_CLIENT_ID", "id")
    monkeypatch.setenv("DPA_SICOOB_CERT_PEM", str(tmp_path / "c.pem"))
    monkeypatch.setenv("DPA_SICOOB_CERT_KEY", str(tmp_path / "c.key"))
    conector = SicoobConnector(cooperativa="4030-4", cooperativa_nome="X", razao_social="Teste")

    resp = MagicMock(status_code=500)
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=resp)

    with patch("connectors.sicoob.requests.post", return_value=resp):
        with pytest.raises(requests.exceptions.HTTPError):
            conector.autenticar()
