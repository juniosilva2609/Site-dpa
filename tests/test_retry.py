import pytest
import requests

from connectors.retry import com_retry


def _http_error(status_code):
    resp = requests.Response()
    resp.status_code = status_code
    return requests.exceptions.HTTPError(response=resp)


def test_sucesso_de_primeira():
    assert com_retry(lambda: 42) == 42


def test_repescagem_em_timeout(monkeypatch):
    monkeypatch.setattr("connectors.retry.time.sleep", lambda s: None)
    chamadas = {"n": 0}

    def func():
        chamadas["n"] += 1
        if chamadas["n"] < 3:
            raise requests.exceptions.Timeout()
        return "ok"

    assert com_retry(func, tentativas=3, espera_inicial=0.01) == "ok"
    assert chamadas["n"] == 3


def test_repescagem_em_erro_5xx(monkeypatch):
    monkeypatch.setattr("connectors.retry.time.sleep", lambda s: None)
    chamadas = {"n": 0}

    def func():
        chamadas["n"] += 1
        if chamadas["n"] < 2:
            raise _http_error(503)
        return "ok"

    assert com_retry(func, tentativas=3) == "ok"


def test_erro_4xx_nao_reprocessa(monkeypatch):
    def sleep_nao_deveria_ser_chamado(s):
        raise AssertionError("não deveria esperar para reprocessar erro de cliente")

    monkeypatch.setattr("connectors.retry.time.sleep", sleep_nao_deveria_ser_chamado)
    chamadas = {"n": 0}

    def func():
        chamadas["n"] += 1
        raise _http_error(401)

    with pytest.raises(requests.exceptions.HTTPError):
        com_retry(func, tentativas=3)
    assert chamadas["n"] == 1


def test_esgota_tentativas_e_repassa_erro(monkeypatch):
    monkeypatch.setattr("connectors.retry.time.sleep", lambda s: None)

    def func():
        raise requests.exceptions.ConnectionError()

    with pytest.raises(requests.exceptions.ConnectionError):
        com_retry(func, tentativas=3, espera_inicial=0.01)
