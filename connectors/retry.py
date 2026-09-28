"""Retry com backoff exponencial para chamadas às APIs bancárias.

Só reprocessa falha transitória de rede (timeout, conexão) ou erro de
servidor (5xx) do banco. Erro de cliente (4xx — ex: credencial inválida,
escopo errado) nunca é reprocessado: tentar de novo não resolve um 401,
só atrasa o relatório de erro.
"""

from __future__ import annotations

import time
from typing import Callable, TypeVar

import requests

T = TypeVar("T")

_ERROS_DE_REDE = (requests.exceptions.Timeout, requests.exceptions.ConnectionError)


def _repescavel(exc: BaseException) -> bool:
    if isinstance(exc, _ERROS_DE_REDE):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        return exc.response is not None and exc.response.status_code >= 500
    return False


def com_retry(func: Callable[[], T], tentativas: int = 3, espera_inicial: float = 1.0) -> T:
    """Executa func(), tentando de novo em erro transitório de rede/servidor.

    Backoff exponencial entre tentativas: espera_inicial, espera_inicial*2,
    espera_inicial*4... Repassa a exceção original se a última tentativa
    também falhar, ou imediatamente se o erro não for repescável.
    """
    ultima_excecao: BaseException | None = None
    for tentativa in range(1, tentativas + 1):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001 - decide reprocessar ou não abaixo
            if not _repescavel(exc):
                raise
            ultima_excecao = exc
            if tentativa < tentativas:
                time.sleep(espera_inicial * (2 ** (tentativa - 1)))

    assert ultima_excecao is not None
    raise ultima_excecao
