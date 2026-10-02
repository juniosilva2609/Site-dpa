# -*- coding: utf-8 -*-
"""Alertas: aparecem no painel e (se o e-mail estiver configurado) são enviados uma única vez."""

import os
import sqlite3

from . import config, db, saida


def abrir(con: sqlite3.Connection, chave: str, mensagem: str, nivel: str = "aviso", nota_id: int | None = None) -> None:
    """Abre o alerta `chave`. Se já existir e estiver aberto, não repete; se estava resolvido, reabre."""
    existente = con.execute("SELECT id, resolvido_em, mensagem FROM alerta WHERE chave = ?", (chave,)).fetchone()
    if existente is None:
        con.execute("INSERT INTO alerta (chave, nivel, mensagem, nota_id) VALUES (?,?,?,?)",
                    (chave, nivel, mensagem, nota_id))
    elif existente["resolvido_em"] is not None:
        con.execute("UPDATE alerta SET resolvido_em = NULL, email_enviado_em = NULL, mensagem = ?, nivel = ?, "
                    "criado_em = datetime('now','localtime') WHERE id = ?", (mensagem, nivel, existente["id"]))
    elif existente["mensagem"] != mensagem:
        con.execute("UPDATE alerta SET mensagem = ? WHERE id = ?", (mensagem, existente["id"]))


def resolver(con: sqlite3.Connection, chave: str) -> None:
    con.execute("UPDATE alerta SET resolvido_em = datetime('now','localtime') WHERE chave = ? AND resolvido_em IS NULL",
                (chave,))


def resolver_da_nota(con: sqlite3.Connection, nota_id: int) -> None:
    con.execute("UPDATE alerta SET resolvido_em = datetime('now','localtime') WHERE nota_id = ? "
                "AND resolvido_em IS NULL", (nota_id,))


def abertos(con: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in con.execute(
        "SELECT * FROM alerta WHERE resolvido_em IS NULL ORDER BY CASE nivel WHEN 'erro' THEN 0 WHEN 'aviso' THEN 1 "
        "ELSE 2 END, criado_em DESC")]


def enviar_pendentes(con: sqlite3.Connection) -> int:
    """Manda por e-mail (um só e-mail resumo) os alertas ainda não enviados. Devolve quantos foram."""
    cfg = db.obter_config(con)
    destinos = saida.lista_emails(cfg["email_alertas"]) or saida.lista_emails(cfg["emails_destino"])
    if os.environ.get("NFSE_SUPORTE_COPIA_ALERTAS") == "1" and config.email_suporte() not in destinos:
        destinos = destinos + [config.email_suporte()]   # opt-in: o responsável pelo sistema também é avisado
    pendentes = con.execute("SELECT * FROM alerta WHERE resolvido_em IS NULL AND email_enviado_em IS NULL "
                            "AND nivel IN ('aviso','erro') ORDER BY id").fetchall()
    if not pendentes or not destinos:
        return 0
    corpo = "Atenção no sistema de NFS-e:\n\n" + "\n".join(f"- [{a['nivel'].upper()}] {a['mensagem']}" for a in pendentes)
    corpo += "\n\nAbra o sistema para ver os detalhes e resolver."
    try:
        saida.enviar_email(destinos, "NFS-e: atenção necessária", corpo, [])
    except Exception:  # noqa: BLE001 -- sem SMTP/rede: tenta de novo no próximo ciclo
        return 0
    con.executemany("UPDATE alerta SET email_enviado_em = datetime('now','localtime') WHERE id = ?",
                    [(a["id"],) for a in pendentes])
    return len(pendentes)
