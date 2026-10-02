# -*- coding: utf-8 -*-
"""SQLite: conexão, migrações (migrations/NNN_*.sql, aplicadas uma vez, em ordem) e utilitários."""

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from . import config

_MIGRACOES = Path(__file__).parent / "migrations"


def conectar(caminho: str | Path | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(str(caminho or config.caminho_banco()), timeout=15, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 15000")
    if str(caminho or config.caminho_banco()) != ":memory:":
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA synchronous = NORMAL")
    return con


def migrar(con: sqlite3.Connection) -> list[str]:
    con.execute("CREATE TABLE IF NOT EXISTS schema_versao (arquivo TEXT PRIMARY KEY, aplicada_em TEXT)")
    feitas = {r["arquivo"] for r in con.execute("SELECT arquivo FROM schema_versao")}
    aplicadas = []
    for arq in sorted(_MIGRACOES.glob("*.sql")):
        if arq.name in feitas:
            continue
        # executescript faz COMMIT implícito; registramos a versão logo depois.
        con.executescript(arq.read_text(encoding="utf-8"))
        con.execute("INSERT INTO schema_versao VALUES (?, datetime('now','localtime'))", (arq.name,))
        aplicadas.append(arq.name)
    return aplicadas


@contextmanager
def transacao(con: sqlite3.Connection):
    """BEGIN IMMEDIATE ... COMMIT (ROLLBACK em erro): toma o lock de escrita já no início."""
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


def obter_config(con: sqlite3.Connection) -> dict:
    return dict(con.execute("SELECT * FROM configuracao WHERE id = 1").fetchone())


def adquirir_trava(con: sqlite3.Connection, nome: str, segundos: int = 300) -> bool:
    """Lease atômico: True se esta conexão conseguiu a trava `nome` por `segundos`."""
    agora = time.time()
    with transacao(con):
        atual = con.execute("SELECT ate FROM trava WHERE nome = ?", (nome,)).fetchone()
        if atual and atual["ate"] > agora:
            return False
        con.execute("INSERT INTO trava (nome, ate) VALUES (?, ?) "
                    "ON CONFLICT(nome) DO UPDATE SET ate = excluded.ate", (nome, agora + segundos))
    return True


def liberar_trava(con: sqlite3.Connection, nome: str) -> None:
    con.execute("DELETE FROM trava WHERE nome = ?", (nome,))


def registrar_historico(con: sqlite3.Connection, usuario: str | None, nota_id: int | None, acao: str,
                        detalhe: str | None = None) -> None:
    con.execute("INSERT INTO historico (usuario, nota_id, acao, detalhe) VALUES (?,?,?,?)",
                (usuario or "sistema", nota_id, acao, (detalhe or "")[:2000]))
