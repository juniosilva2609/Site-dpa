# -*- coding: utf-8 -*-
"""Sistema de emissão automática de NFS-e (Sistema Nacional / Portal Nacional)."""

import os

from flask import Flask

from . import config, db


def create_app(db_path: str | None = None, iniciar_agendador: bool | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = str(db_path or config.caminho_banco())
    app.config["SECRET_KEY"] = config.secret_key()
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("NFSE_DEV") != "1"
    app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 12

    con = db.conectar(app.config["DB_PATH"])
    db.migrar(con)
    _criar_admin_inicial(con)
    con.close()

    from . import web
    web.registrar(app)

    if iniciar_agendador is None:
        iniciar_agendador = os.environ.get("NFSE_AGENDADOR", "1") == "1"
    if iniciar_agendador:
        from . import scheduler
        scheduler.iniciar_thread(app.config["DB_PATH"])
    return app


def _criar_admin_inicial(con) -> None:
    """Se NFSE_ADMIN_SENHA estiver definida e ainda não existir usuário, cria o administrador."""
    senha = os.environ.get("NFSE_ADMIN_SENHA")
    if not senha or con.execute("SELECT 1 FROM usuario LIMIT 1").fetchone():
        return
    from werkzeug.security import generate_password_hash
    con.execute("INSERT INTO usuario (nome, login, senha_hash, admin) VALUES (?,?,?,1)",
                ("Administrador", os.environ.get("NFSE_ADMIN_USER", "admin"), generate_password_hash(senha)))
