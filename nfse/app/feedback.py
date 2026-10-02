# -*- coding: utf-8 -*-
"""Sugestões e inconsistências: o usuário escreve no sistema, fica registrado e chega por e-mail ao responsável.
Se o e-mail falhar (SMTP fora do ar/não configurado) o registro permanece e o envio é repetido pela manutenção."""

import sqlite3

from . import config, db, saida

TIPOS = {"sugestao": "Sugestão", "inconsistencia": "Inconsistência / erro"}
MAX_MENSAGEM = 4000
LIMITE_POR_HORA = 10


def _linha(texto: str, limite: int = 200) -> str:
    return " ".join((texto or "").split())[:limite]


def registrar(con: sqlite3.Connection, usuario: str, tipo: str, mensagem: str, origem: str = "",
              nota_id: int | None = None, contexto: str = "") -> int:
    """Grava o relato e tenta enviar o e-mail. Levanta ValueError para entrada inválida/excesso de envios."""
    mensagem = (mensagem or "").strip()
    if tipo not in TIPOS:
        raise ValueError("Escolha se é uma sugestão ou uma inconsistência.")
    if len(mensagem) < 10:
        raise ValueError("Descreva com um pouco mais de detalhe (mínimo de 10 caracteres).")
    if len(mensagem) > MAX_MENSAGEM:
        raise ValueError(f"Mensagem muito longa (máximo de {MAX_MENSAGEM} caracteres).")
    recentes = con.execute("SELECT COUNT(*) FROM feedback WHERE usuario = ? AND em > datetime('now','localtime','-1 hour')",
                           (usuario,)).fetchone()[0]
    if recentes >= LIMITE_POR_HORA:
        raise ValueError("Muitos envios seguidos. Aguarde um pouco e tente de novo.")
    if nota_id is not None and not con.execute("SELECT 1 FROM nota WHERE id = ?", (nota_id,)).fetchone():
        nota_id = None
    origem = _linha(origem, 120) if (origem or "").startswith("/") else ""
    cur = con.execute("INSERT INTO feedback (usuario, tipo, mensagem, origem, nota_id, contexto) VALUES (?,?,?,?,?,?)",
                      (usuario, tipo, mensagem, origem, nota_id, _linha(contexto, 400)))
    enviar(con, cur.lastrowid)
    return cur.lastrowid


def enviar(con: sqlite3.Connection, feedback_id: int) -> bool:
    f = con.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
    if f is None or f["enviado_em"]:
        return False
    cfg = db.obter_config(con)
    corpo = (f"{TIPOS[f['tipo']]} #{f['id']} enviada por {f['usuario']} em {f['em']}\n"
             f"Tela: {f['origem'] or '-'}"
             + (f"\nNota: #{f['nota_id']}" if f["nota_id"] else "")
             + f"\nAmbiente: {cfg['ambiente']} | Prestador: {cfg['razao_social']}\n"
             f"Contexto: {f['contexto'] or '-'}\n\n{f['mensagem']}\n")
    try:
        saida.enviar_email([config.email_suporte()], f"[NFS-e] {TIPOS[f['tipo']]} #{f['id']} de {_linha(f['usuario'], 40)}", corpo, [])
    except Exception as e:  # noqa: BLE001 -- fica pendente e a manutenção tenta de novo
        con.execute("UPDATE feedback SET envio_erro = ? WHERE id = ?", (str(e)[:300], feedback_id))
        return False
    con.execute("UPDATE feedback SET enviado_em = datetime('now','localtime'), envio_erro = NULL WHERE id = ?", (feedback_id,))
    return True


def enviar_pendentes(con: sqlite3.Connection) -> int:
    n = 0
    for f in con.execute("SELECT id FROM feedback WHERE enviado_em IS NULL ORDER BY id LIMIT 20").fetchall():
        n += enviar(con, f["id"])
    return n
