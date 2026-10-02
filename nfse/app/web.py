# -*- coding: utf-8 -*-
"""Telas e rotas (Flask). Todas exigem login, exceto /entrar, /primeiro-acesso e /saude. Todo POST exige CSRF."""

import hmac
import io
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request, send_file, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from . import agenda, alertas, conferencia, db, emissor, feedback, municipios, saida, util
from .fiscal import api_nfse, certificado, danfse
from .fiscal.dps import MOTIVOS_CANCELAMENTO

STATUS = {
    "a_conferir": ("A conferir", "amarelo"), "aprovada": ("Aprovada: sai no horário", "azul"),
    "emitindo": ("Emitindo…", "azul"), "emitida": ("Emitida", "verde"), "rejeitada": ("Erro: corrigir", "vermelho"),
    "verificar": ("Verificar", "vermelho"), "atrasada": ("Atrasada", "vermelho"),
    "cancelada": ("Cancelada", "cinza"), "pulada": ("Pulada", "cinza"),
}
EDITAVEIS = ("a_conferir", "aprovada", "atrasada", "rejeitada")
_FALHAS_LOGIN: dict[str, list[float]] = {}


def registrar(app: Flask) -> None:
    app.jinja_env.filters.update(
        valor=util.fmt_valor, dt=util.fmt_data_hora, data=util.fmt_data, doc=util.fmt_documento,
        status_label=lambda s: STATUS.get(s, (s, "cinza"))[0], status_css=lambda s: STATUS.get(s, (s, "cinza"))[1],
        cidade=municipios.rotulo)
    app.jinja_env.globals.update(STATUS=STATUS, csrf_token=_csrf_token, agora=util.agora)

    @app.before_request
    def _antes():
        g.con = db.conectar(app.config["DB_PATH"])
        livres = {"login", "primeiro_acesso", "saude", "static"}
        if request.endpoint in livres or request.endpoint is None:
            return None
        if "uid" not in session:
            if not g.con.execute("SELECT 1 FROM usuario LIMIT 1").fetchone():
                return redirect(url_for("primeiro_acesso"))
            return redirect(url_for("login", proximo=request.path))
        usuario = g.con.execute("SELECT * FROM usuario WHERE id = ? AND ativo = 1", (session["uid"],)).fetchone()
        if usuario is None:
            session.clear()
            return redirect(url_for("login"))
        g.usuario = dict(usuario)
        return None

    @app.before_request
    def _csrf():
        if request.method == "POST" and request.endpoint != "static":
            enviado = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
            if not hmac.compare_digest(enviado, session.get("csrf", "x" * 8)) or "csrf" not in session:
                abort(400, "Sessão expirada ou formulário inválido. Volte e tente de novo.")

    @app.after_request
    def _cabecalhos(resp):
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.teardown_request
    def _fechar(_exc):
        con = g.pop("con", None)
        if con is not None:
            con.close()

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def _erro(e):
        return render_template("erro.html", erro=e), e.code

    app.add_url_rule("/saude", "saude", saude)
    for regra, endpoint, func, metodos in _ROTAS:
        app.add_url_rule(regra, endpoint, func, methods=metodos)


def _csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def admin_requerido(func):
    @wraps(func)
    def interno(*a, **k):
        if not g.usuario["admin"]:
            abort(403, "Somente o administrador pode fazer isso.")
        return func(*a, **k)
    return interno


def saude():
    r = g.con.execute("SELECT valor FROM estado WHERE chave = 'ultimo_tick'").fetchone()
    return jsonify(ok=True, ultimo_ciclo=r["valor"] if r else None)


# ------------------------------------------------------------------------------------- acesso
def login():
    ip = request.remote_addr or "?"
    recentes = [t for t in _FALHAS_LOGIN.get(ip, []) if time.time() - t < 300]
    if request.method == "POST":
        if len(recentes) >= 5:
            flash("Muitas tentativas. Aguarde 5 minutos.", "erro")
        else:
            u = g.con.execute("SELECT * FROM usuario WHERE login = ? AND ativo = 1",
                              (request.form.get("login", "").strip().lower(),)).fetchone()
            if u and check_password_hash(u["senha_hash"], request.form.get("senha", "")):
                session.clear()
                session["uid"] = u["id"]
                session.permanent = True
                _FALHAS_LOGIN.pop(ip, None)
                destino = request.args.get("proximo", "")
                return redirect(destino if destino.startswith("/") and not destino.startswith("//") else url_for("painel"))
            _FALHAS_LOGIN[ip] = recentes + [time.time()]
            flash("Usuário ou senha incorretos.", "erro")
    return render_template("login.html")


def sair():
    session.clear()
    return redirect(url_for("login"))


def primeiro_acesso():
    if g.con.execute("SELECT 1 FROM usuario LIMIT 1").fetchone():
        return redirect(url_for("login"))
    codigo = os.environ.get("NFSE_SETUP_CODE")
    if not codigo and request.remote_addr not in ("127.0.0.1", "::1"):
        # Sem código de instalação, só quem está na própria máquina cria o administrador: evita que o
        # primeiro visitante de um servidor público tome conta do sistema.
        abort(403, "Defina NFSE_SETUP_CODE (ou NFSE_ADMIN_SENHA) no ambiente do servidor para criar o administrador.")
    if request.method == "POST":
        f = request.form
        if codigo and not hmac.compare_digest(f.get("codigo", ""), codigo):
            flash("Código de instalação incorreto.", "erro")
        elif len(f.get("senha", "")) < 8:
            flash("A senha precisa ter pelo menos 8 caracteres.", "erro")
        elif f.get("senha") != f.get("senha2"):
            flash("As senhas não conferem.", "erro")
        elif not f.get("login", "").strip():
            flash("Informe o usuário.", "erro")
        else:
            g.con.execute("INSERT INTO usuario (nome, login, senha_hash, admin) VALUES (?,?,?,1)",
                          (f.get("nome", "").strip() or "Administrador", f["login"].strip().lower(),
                           generate_password_hash(f["senha"])))
            flash("Administrador criado. Entre com o novo usuário.", "ok")
            return redirect(url_for("login"))
    return render_template("primeiro_acesso.html", pede_codigo=bool(codigo))


def conta():
    if request.method == "POST":
        f = request.form
        if not check_password_hash(g.usuario["senha_hash"], f.get("atual", "")):
            flash("Senha atual incorreta.", "erro")
        elif len(f.get("nova", "")) < 8 or f.get("nova") != f.get("nova2"):
            flash("A nova senha precisa ter 8+ caracteres e ser digitada igual duas vezes.", "erro")
        else:
            g.con.execute("UPDATE usuario SET senha_hash = ? WHERE id = ?", (generate_password_hash(f["nova"]), g.usuario["id"]))
            flash("Senha alterada.", "ok")
            return redirect(url_for("painel"))
    return render_template("conta.html")


@admin_requerido
def usuarios():
    if request.method == "POST":
        f = request.form
        acao = f.get("acao")
        if acao == "novo":
            if not f.get("login", "").strip() or len(f.get("senha", "")) < 8:
                flash("Informe o usuário e uma senha de 8+ caracteres.", "erro")
            else:
                try:
                    g.con.execute("INSERT INTO usuario (nome, login, senha_hash, admin) VALUES (?,?,?,?)",
                                  (f.get("nome", "").strip() or f["login"], f["login"].strip().lower(),
                                   generate_password_hash(f["senha"]), 1 if f.get("admin") else 0))
                    flash("Usuário criado.", "ok")
                except sqlite3.IntegrityError:
                    flash("Já existe um usuário com esse login.", "erro")
        elif acao in ("ativar", "desativar", "senha"):
            uid = int(f.get("id", 0))
            if acao == "senha":
                if len(f.get("senha", "")) < 8:
                    flash("A senha precisa ter 8+ caracteres.", "erro")
                else:
                    g.con.execute("UPDATE usuario SET senha_hash = ? WHERE id = ?", (generate_password_hash(f["senha"]), uid))
                    flash("Senha redefinida.", "ok")
            elif uid == g.usuario["id"]:
                flash("Você não pode desativar o próprio usuário.", "erro")
            else:
                g.con.execute("UPDATE usuario SET ativo = ? WHERE id = ?", (1 if acao == "ativar" else 0, uid))
        return redirect(url_for("usuarios"))
    return render_template("usuarios.html", lista=g.con.execute("SELECT * FROM usuario ORDER BY nome").fetchall())


# ------------------------------------------------------------------------------------- painel
def painel():
    con = g.con
    cfg = db.obter_config(con)
    atencao = con.execute(
        "SELECT n.*, c.nome AS cliente FROM nota n JOIN cliente c ON c.id = n.cliente_id WHERE n.status IN "
        "('a_conferir','atrasada','rejeitada','verificar') ORDER BY n.prevista_em").fetchall()
    proximas = con.execute(
        "SELECT n.*, c.nome AS cliente FROM nota n JOIN cliente c ON c.id = n.cliente_id "
        "WHERE n.status IN ('aprovada','emitindo') ORDER BY n.prevista_em").fetchall()
    recentes = con.execute(
        "SELECT n.*, c.nome AS cliente FROM nota n JOIN cliente c ON c.id = n.cliente_id "
        "WHERE n.status IN ('emitida','cancelada') ORDER BY n.emitida_em DESC, n.id DESC LIMIT 10").fetchall()
    tick = con.execute("SELECT valor FROM estado WHERE chave = 'ultimo_tick'").fetchone()
    parado = True
    if tick:
        parado = datetime.now() - datetime.fromisoformat(tick["valor"]) > timedelta(minutes=3)
    dias_cert = certificado.dias_para_vencer() if certificado.disponivel() else None
    return render_template("painel.html", cfg=cfg, atencao=atencao, proximas=proximas, recentes=recentes,
                           alertas=alertas.abertos(con), agendador_parado=parado, dias_cert=dias_cert,
                           cert_ok=certificado.disponivel(), problemas_config=conferencia.conferir_configuracao(cfg),
                           ultimo_ciclo=tick["valor"] if tick else None)


# ------------------------------------------------------------------------------------- clientes
def _ler_cliente(f) -> dict:
    nome = f.get("nome", "").strip()
    doc = util.so_digitos(f.get("documento"))
    if not nome:
        raise ValueError("Informe o nome / razão social do cliente.")
    if not util.documento_valido(doc):
        raise ValueError("CPF/CNPJ inválido. Confira os números.")
    cod = ""
    if f.get("cidade", "").strip():
        cod = municipios.codigo(f["cidade"], f.get("uf", "")) or ""
        if not cod:
            raise ValueError("Não encontrei essa cidade/UF. Confira a grafia (ex.: Belo Horizonte / MG).")
    return {"nome": nome, "documento": doc, "email": f.get("email", "").strip(), "telefone": util.so_digitos(f.get("telefone")),
            "cep": util.so_digitos(f.get("cep")), "logradouro": f.get("logradouro", "").strip(),
            "numero": f.get("numero", "").strip(), "complemento": f.get("complemento", "").strip(),
            "bairro": f.get("bairro", "").strip(), "codigo_municipio": cod,
            "enviar_nota_por_email": 1 if f.get("enviar_nota_por_email") else 0, "ativo": 1 if f.get("ativo", "1") else 0}


def clientes():
    lista = g.con.execute("SELECT * FROM cliente ORDER BY ativo DESC, nome").fetchall()
    return render_template("clientes.html", lista=lista)


def cliente_form(cid=None):
    atual = None
    if cid:
        atual = g.con.execute("SELECT * FROM cliente WHERE id = ?", (cid,)).fetchone()
        if atual is None:
            abort(404)
        atual = dict(atual)
    if request.method == "POST":
        try:
            dados = _ler_cliente(request.form)
            if cid is None:
                dados["ativo"] = 1
                cols = ",".join(dados)
                cur = g.con.execute(f"INSERT INTO cliente ({cols}) VALUES ({','.join('?' * len(dados))})", tuple(dados.values()))
                cid = cur.lastrowid
            else:
                dados["ativo"] = 1 if request.form.get("ativo") else 0
                g.con.execute("UPDATE cliente SET " + ", ".join(f"{k} = ?" for k in dados) + " WHERE id = ?",
                              (*dados.values(), cid))
            flash("Cliente salvo.", "ok")
            return redirect(url_for("clientes"))
        except ValueError as e:
            flash(str(e), "erro")
        except sqlite3.IntegrityError:
            flash("Já existe um cliente com esse CPF/CNPJ.", "erro")
        atual = request.form
    nome_uf = municipios.nome_uf(atual["codigo_municipio"]) if atual is not None and atual.get("codigo_municipio") else None
    return render_template("cliente_form.html", c=atual, cidade=nome_uf[0] if nome_uf else (atual.get("cidade", "") if atual is not None else ""),
                           uf=nome_uf[1] if nome_uf else (atual.get("uf", "MG") if atual is not None else "MG"), ufs=municipios.UFS)


# ------------------------------------------------------------------------------------- notas
def _ler_nota(f) -> dict:
    try:
        quando = datetime.fromisoformat(f"{f['prevista_data']} {f['prevista_hora']}")
    except (KeyError, ValueError) as e:
        raise ValueError("Informe a data e a hora de emissão.") from e
    cliente = g.con.execute("SELECT id FROM cliente WHERE id = ? AND ativo = 1", (f.get("cliente_id", 0),)).fetchone()
    if cliente is None:
        raise ValueError("Escolha o cliente.")
    competencia = f.get("competencia", "").strip() or None
    if competencia:
        try:
            datetime.fromisoformat(competencia)
        except ValueError as e:
            raise ValueError("Competência inválida.") from e
    return {"cliente_id": cliente["id"], "prevista_em": quando.strftime(agenda.FORMATO),
            "descricao": f.get("descricao", "").strip().replace("\r\n", "\n"),
            "valor_centavos": util.parse_valor(f.get("valor", "")), "competencia": competencia}


def notas():
    f = request.args
    where, args = ["1=1"], []
    if f.get("status"):
        where.append("n.status = ?")
        args.append(f["status"])
    if f.get("mes"):
        where.append("substr(n.prevista_em,1,7) = ?")
        args.append(f["mes"])
    if f.get("cliente"):
        where.append("n.cliente_id = ?")
        args.append(f["cliente"])
    lista = g.con.execute(
        f"SELECT n.*, c.nome AS cliente FROM nota n JOIN cliente c ON c.id = n.cliente_id WHERE {' AND '.join(where)} "
        "ORDER BY n.prevista_em DESC, n.id DESC LIMIT 300", args).fetchall()
    return render_template("notas.html", lista=lista, f=f, clientes=g.con.execute("SELECT id, nome FROM cliente ORDER BY nome").fetchall())


def nota_nova():
    clientes_ativos = g.con.execute("SELECT id, nome FROM cliente WHERE ativo = 1 ORDER BY nome").fetchall()
    if request.method == "POST":
        try:
            d = _ler_nota(request.form)
            cur = g.con.execute(
                "INSERT INTO nota (cliente_id, prevista_em, descricao, valor_centavos, competencia, status, criado_por) "
                "VALUES (?,?,?,?,?, 'a_conferir', ?)",
                (d["cliente_id"], d["prevista_em"], d["descricao"], d["valor_centavos"], d["competencia"], g.usuario["login"]))
            db.registrar_historico(g.con, g.usuario["login"], cur.lastrowid, "criada", "Nota avulsa")
            flash("Nota criada. Confira e aprove (ou emita agora).", "ok")
            return redirect(url_for("nota_detalhe", nid=cur.lastrowid))
        except ValueError as e:
            flash(str(e), "erro")
        n = request.form
    else:
        daqui_1h = (util.agora() + timedelta(hours=1)).replace(minute=0)
        n = {"prevista_data": daqui_1h.strftime("%Y-%m-%d"), "prevista_hora": daqui_1h.strftime("%H:%M")}
    return render_template("nota_nova.html", n=n, clientes=clientes_ativos)


def _nota_ou_404(nid) -> dict:
    n = g.con.execute("SELECT n.*, c.nome AS cliente, c.documento AS cliente_doc FROM nota n JOIN cliente c "
                      "ON c.id = n.cliente_id WHERE n.id = ?", (nid,)).fetchone()
    if n is None:
        abort(404)
    return dict(n)


def nota_detalhe(nid):
    n = _nota_ou_404(nid)
    if request.method == "POST" and n["status"] in EDITAVEIS:
        try:
            d = _ler_nota(request.form)
            g.con.execute("UPDATE nota SET cliente_id=?, prevista_em=?, descricao=?, valor_centavos=?, competencia=?, "
                          "status='a_conferir', conferido_por=NULL, conferido_em=NULL, mensagem_erro=NULL WHERE id=?",
                          (d["cliente_id"], d["prevista_em"], d["descricao"], d["valor_centavos"], d["competencia"], nid))
            db.registrar_historico(g.con, g.usuario["login"], nid, "editada", "Dados alterados (volta para conferência)")
            flash("Salvo. A nota voltou para \"A conferir\".", "ok")
        except ValueError as e:
            flash(str(e), "erro")
        return redirect(url_for("nota_detalhe", nid=nid))
    problemas = conferencia.conferir(g.con, nid) if n["status"] in EDITAVEIS else []
    hist = g.con.execute("SELECT * FROM historico WHERE nota_id = ? ORDER BY id DESC LIMIT 30", (nid,)).fetchall()
    return render_template(
        "nota.html", n=n, problemas=problemas, bloqueada=bool(conferencia.erros(problemas)), hist=hist,
        editavel=n["status"] in EDITAVEIS, motivos=MOTIVOS_CANCELAMENTO,
        clientes=g.con.execute("SELECT id, nome FROM cliente WHERE ativo = 1 OR id = ? ORDER BY nome", (n["cliente_id"],)).fetchall(),
        cfg=db.obter_config(g.con), limite=util.LIMITE_DESCRICAO, tamanho=util.tamanho_descricao(n["descricao"]))


def _resultado(r: dict, ok_msg: str):
    if r.get("ok"):
        flash(ok_msg, "ok")
    else:
        flash(r.get("erro") or "Não foi possível concluir.", "erro")


def nota_acao(nid, acao):
    _nota_ou_404(nid)
    login = g.usuario["login"]
    if acao == "aprovar":
        _resultado(emissor.aprovar(g.con, nid, login), "Conferida e aprovada: a nota será emitida no horário previsto.")
    elif acao == "desaprovar":
        emissor.desaprovar(g.con, nid, login)
        flash("A nota voltou para conferência.", "ok")
    elif acao == "pular":
        emissor.pular(g.con, nid, login)
        flash("Esta nota não será emitida.", "ok")
    elif acao == "emitir":
        r = emissor.emitir(g.con, nid, usuario=login, manual=True)
        _resultado(r, f"NFS-e {r.get('numero_nfse', '')} emitida.")
    elif acao == "consultar":
        _resultado(emissor.consultar_na_sefin(g.con, nid, login), "Encontrada na Sefin: nota concluída.")
    elif acao == "anexar-xml":
        arq = request.files.get("xml")
        texto = arq.read().decode("utf-8", errors="replace") if arq else ""
        _resultado(emissor.anexar_xml(g.con, nid, texto, login), "XML anexado: nota concluída.")
    elif acao == "entregar":
        g.con.execute("UPDATE nota SET entrega_tentativas = 0 WHERE id = ?", (nid,))
        r = saida.entregar(g.con, nid)
        erros = [v for v in r.values() if v not in (None, "ok")]
        flash("Arquivos entregues." if not erros else "Entrega com problema: " + "; ".join(erros), "ok" if not erros else "erro")
        alertas.resolver(g.con, f"entrega-{nid}")
    elif acao == "cancelar":
        if not g.usuario["admin"]:
            abort(403, "Somente o administrador pode cancelar uma NFS-e.")
        _resultado(emissor.cancelar(g.con, nid, request.form.get("motivo", ""), request.form.get("texto", ""), login),
                   "NFS-e cancelada.")
    else:
        abort(404)
    return redirect(url_for("nota_detalhe", nid=nid))


def nota_arquivo(nid, tipo):
    n = _nota_ou_404(nid)
    if not n["xml_nfse"]:
        abort(404, "Esta nota ainda não tem XML.")
    nome = saida.nome_arquivo(n, n["cliente"])
    if tipo == "xml":
        return send_file(io.BytesIO(n["xml_nfse"].encode("utf-8")), mimetype="application/xml", as_attachment=True,
                         download_name=f"{nome}.xml")
    try:
        pdf = danfse.gerar_danfse_para_registro(n["xml_nfse"], n["status"])
    except danfse.DanfseIndisponivel as e:
        abort(400, str(e))
    return send_file(io.BytesIO(pdf), mimetype="application/pdf", as_attachment=request.args.get("baixar") == "1",
                     download_name=f"{nome}.pdf")


# ------------------------------------------------------------------------------------- agendamentos
def _ler_agendamento(f) -> dict:
    nome = f.get("nome", "").strip()
    if not nome:
        raise ValueError("Dê um nome ao agendamento.")
    cliente = g.con.execute("SELECT id FROM cliente WHERE id = ?", (f.get("cliente_id", 0),)).fetchone()
    if cliente is None:
        raise ValueError("Escolha o cliente.")
    if not f.get("descricao", "").strip():
        raise ValueError("Escreva a descrição do serviço.")
    freq = f.get("frequencia")
    if freq not in ("mensal", "semanal", "unica"):
        raise ValueError("Escolha a frequência.")
    dados = {"nome": nome, "cliente_id": cliente["id"], "descricao": f["descricao"].strip().replace("\r\n", "\n"),
             "valor_centavos": util.parse_valor(f.get("valor", "")), "frequencia": freq, "dia_mes": None,
             "dia_semana": None, "data_unica": None, "hora": f.get("hora", "09:00") or "09:00",
             "antecedencia_dias": max(1, min(30, int(f.get("antecedencia_dias") or 3))),
             "auto_aprovar": 1 if f.get("auto_aprovar") else 0, "ativo": 1 if f.get("ativo") else 0}
    try:
        datetime.strptime(dados["hora"], "%H:%M")
        if freq == "mensal":
            dados["dia_mes"] = int(f.get("dia_mes", ""))
            if not 1 <= dados["dia_mes"] <= 31:
                raise ValueError
        elif freq == "semanal":
            dados["dia_semana"] = int(f.get("dia_semana", ""))
            if not 0 <= dados["dia_semana"] <= 6:
                raise ValueError
        else:
            dados["data_unica"] = datetime.fromisoformat(f.get("data_unica", "")).date().isoformat()
    except ValueError as e:
        raise ValueError("Confira a data/dia e a hora da frequência escolhida.") from e
    return dados


def agendamentos():
    lista = []
    for a in g.con.execute("SELECT a.*, c.nome AS cliente FROM agendamento a JOIN cliente c ON c.id = a.cliente_id "
                           "ORDER BY a.ativo DESC, a.nome").fetchall():
        a = dict(a)
        a["proxima"] = agenda.proxima(a) if a["ativo"] else None
        lista.append(a)
    return render_template("agendamentos.html", lista=lista)


def agendamento_form(aid=None):
    atual = None
    if aid:
        atual = g.con.execute("SELECT * FROM agendamento WHERE id = ?", (aid,)).fetchone()
        if atual is None:
            abort(404)
        atual = dict(atual)
        atual["valor"] = util.valor_para_campo(atual["valor_centavos"])
    if request.method == "POST":
        try:
            d = _ler_agendamento(request.form)
            if aid is None:
                cur = g.con.execute(f"INSERT INTO agendamento ({','.join(d)}) VALUES ({','.join('?' * len(d))})", tuple(d.values()))
                aid = cur.lastrowid
            else:
                g.con.execute("UPDATE agendamento SET " + ", ".join(f"{k} = ?" for k in d) + " WHERE id = ?", (*d.values(), aid))
            n = len(agenda.gerar_notas(g.con))
            flash("Agendamento salvo." + (f" {n} nota(s) já entraram para conferência." if n else ""), "ok")
            return redirect(url_for("agendamentos"))
        except ValueError as e:
            flash(str(e), "erro")
        atual = request.form
    proxima = agenda.proxima(dict(atual)) if isinstance(atual, dict) and atual.get("ativo") else None
    return render_template("agendamento_form.html", a=atual, proxima=proxima, clientes=g.con.execute(
        "SELECT id, nome FROM cliente WHERE ativo = 1 ORDER BY nome").fetchall())


def agendamentos_gerar():
    n = len(agenda.gerar_notas(g.con))
    flash(f"{n} nota(s) nova(s) gerada(s) para conferência." if n else "Nenhuma nota nova para gerar agora.", "ok")
    return redirect(url_for("agendamentos"))


# ------------------------------------------------------------------------------------- sugestões
def sugestoes():
    if request.method == "POST":
        f = request.form
        if f.get("acao") == "resolver" and g.usuario["admin"]:
            g.con.execute("UPDATE feedback SET resolvido_em = CASE WHEN resolvido_em IS NULL THEN datetime('now','localtime') "
                          "ELSE NULL END WHERE id = ?", (int(f.get("id", 0)),))
            return redirect(url_for("sugestoes"))
        if f.get("acao") == "reenviar" and g.usuario["admin"]:
            ok = feedback.enviar(g.con, int(f.get("id", 0)))
            flash("E-mail enviado." if ok else "Não consegui enviar agora; veja o erro na lista.", "ok" if ok else "erro")
            return redirect(url_for("sugestoes"))
        try:
            nota = f.get("nota_id", "").strip()
            fid = feedback.registrar(
                g.con, g.usuario["login"], f.get("tipo", ""), f.get("mensagem", ""), f.get("origem", ""),
                int(nota) if nota.isdigit() else None,
                f"ambiente={db.obter_config(g.con)['ambiente']}; navegador={request.headers.get('User-Agent', '')[:150]}")
            enviado = g.con.execute("SELECT enviado_em FROM feedback WHERE id = ?", (fid,)).fetchone()[0]
            flash("Obrigado! Sua mensagem foi enviada ao responsável pelo sistema." if enviado else
                  "Obrigado! Sua mensagem foi registrada e será enviada ao responsável assim que o e-mail estiver disponível.", "ok")
            return redirect(url_for("sugestoes"))
        except ValueError as e:
            flash(str(e), "erro")
    lista = []
    if g.usuario["admin"]:
        lista = g.con.execute("SELECT * FROM feedback ORDER BY resolvido_em IS NOT NULL, id DESC LIMIT 100").fetchall()
    origem = request.form.get("origem") or request.args.get("de", "")
    return render_template("sugestoes.html", lista=lista, tipos=feedback.TIPOS, origem=origem,
                           nota_id=request.args.get("nota", ""), maximo=feedback.MAX_MENSAGEM,
                           f=request.form if request.method == "POST" else {})


# ------------------------------------------------------------------------------------- configuração
@admin_requerido
def configuracao():
    con = g.con
    if request.method == "POST":
        f = request.form
        acao = f.get("acao")
        try:
            if acao == "fiscal":
                _salvar_fiscal(con, f)
            elif acao == "saida":
                _salvar_saida(con, f)
            elif acao == "certificado":
                _upload_certificado(f)
            elif acao == "testar_pasta":
                flash(f"Pasta OK: {saida.testar_pasta(db.obter_config(con))}", "ok")
            elif acao == "testar_email":
                cfg = db.obter_config(con)
                destinos = saida.lista_emails(cfg["email_alertas"]) or saida.lista_emails(cfg["emails_destino"])
                saida.enviar_email(destinos, "NFS-e: teste de e-mail", "Se você recebeu esta mensagem, o envio funciona.", [])
                flash(f"E-mail de teste enviado para {', '.join(destinos)}.", "ok")
            elif acao == "testar_conexao":
                cfg = db.obter_config(con)
                return render_template("diagnostico.html", etapas=api_nfse.diagnosticar_conexao(cfg["ambiente"]), ambiente=cfg["ambiente"])
            elif acao == "testar_convenio":
                cfg = db.obter_config(con)
                resp = api_nfse.consultar_convenio_municipio(cfg["codigo_municipio_ibge"], cfg["ambiente"])
                flash(f"Resposta da Sefin sobre o município {cfg['codigo_municipio_ibge']}: {str(resp)[:600]}", "ok")
        except (ValueError, OSError, RuntimeError, api_nfse.ErroApiNfse, certificado.CertificadoIndisponivel) as e:
            flash(str(e), "erro")
        except Exception as e:  # noqa: BLE001 -- SMTP etc.: mostra o motivo em vez de erro 500
            flash(f"Falhou: {e}", "erro")
        return redirect(url_for("configuracao"))
    cfg = db.obter_config(con)
    caminho = certificado.caminho_certificado()
    return render_template("configuracao.html", cfg=cfg, cert_arquivo=caminho is not None,
                           cert_senha=bool(os.environ.get("NFSE_CERT_SENHA")), dias_cert=certificado.dias_para_vencer(),
                           smtp_ok=_smtp_ok(),
                           pasta_efetiva=str(saida.pasta_base(cfg)), cidade=municipios.rotulo(cfg["codigo_municipio_ibge"]))


def _smtp_ok() -> bool:
    from . import config
    return config.smtp() is not None


def _salvar_fiscal(con, f) -> None:
    cnpj = util.so_digitos(f.get("cnpj"))
    if not util.cnpj_valido(cnpj):
        raise ValueError("CNPJ do prestador inválido.")
    ibge = util.so_digitos(f.get("codigo_municipio_ibge"))
    if not municipios.nome_uf(ibge):
        raise ValueError("Código IBGE do município não encontrado na tabela oficial.")
    trib = util.so_digitos(f.get("codigo_servico_lc116"))
    if len(trib) != 6:
        raise ValueError("O código de tributação nacional tem 6 dígitos (ex.: 160201 = 16.02.01).")
    serie = util.so_digitos(f.get("serie_dps")) or "1"
    if int(serie) > 99999:
        raise ValueError("Série da DPS: até 5 dígitos.")
    atual = db.obter_config(con)
    ambiente = f.get("ambiente", "homologacao")
    if ambiente == "producao" and atual["ambiente"] != "producao" and f.get("confirmar_producao", "").strip().upper() != "PRODUCAO":
        raise ValueError("Para passar para PRODUÇÃO digite PRODUCAO no campo de confirmação. Em produção as notas "
                         "têm validade jurídica e geram imposto.")
    proximo = int(f.get("proximo_numero_dps") or atual["proximo_numero_dps"])
    if proximo != atual["proximo_numero_dps"] and f.get("confirmar_numero", "") != "1":
        raise ValueError("Você alterou o próximo número da DPS: marque a caixa de confirmação. Número errado "
                         "pode ser recusado pela Sefin.")
    aliquota = f.get("aliquota_iss", "").replace(",", ".").strip()
    con.execute(
        "UPDATE configuracao SET razao_social=?, cnpj=?, inscricao_municipal=?, telefone=?, email=?, codigo_municipio_ibge=?, "
        "regime_tributario=?, codigo_servico_lc116=?, codigo_tributacao_municipal=?, codigo_nbs=?, aliquota_iss=?, ambiente=?, "
        "serie_dps=?, proximo_numero_dps=?, atualizado_em=datetime('now','localtime') WHERE id=1",
        (f.get("razao_social", "").strip(), cnpj, f.get("inscricao_municipal", "").strip(), util.so_digitos(f.get("telefone")),
         f.get("email", "").strip(), ibge, "normal" if f.get("regime_tributario") == "normal" else "simples", trib,
         f.get("codigo_tributacao_municipal", "").strip(), f.get("codigo_nbs", "").strip(), float(aliquota) if aliquota else None,
         "producao" if ambiente == "producao" else "homologacao", serie.zfill(5), proximo))
    db.registrar_historico(con, g.usuario["login"], None, "configuracao", f"Fiscal salva (ambiente {ambiente})")
    flash("Configuração fiscal salva.", "ok")


def _salvar_saida(con, f) -> None:
    for campo in ("emails_destino", "email_alertas"):
        digitado = [e for e in re.split(r"[,;\s]+", f.get(campo, "")) if e]
        if len(saida.lista_emails(f.get(campo, ""))) != len(digitado):
            raise ValueError("Há um e-mail inválido na lista. Separe vários e-mails por vírgula.")
    pasta = f.get("pasta_saida", "").strip()
    con.execute("UPDATE configuracao SET salvar_em_pasta=?, pasta_saida=?, enviar_por_email=?, emails_destino=?, email_alertas=?, "
                "tolerancia_atraso_horas=?, atualizado_em=datetime('now','localtime') WHERE id=1",
                (1 if f.get("salvar_em_pasta") else 0, pasta, 1 if f.get("enviar_por_email") else 0,
                 ", ".join(saida.lista_emails(f.get("emails_destino", ""))), ", ".join(saida.lista_emails(f.get("email_alertas", ""))),
                 max(1, min(48, int(f.get("tolerancia_atraso_horas") or 6)))))
    flash("Destino dos arquivos salvo.", "ok")


def _upload_certificado(f) -> None:
    from . import config
    arq = request.files.get("pfx")
    if not arq or not arq.filename:
        raise ValueError("Escolha o arquivo do certificado (.pfx ou .p12).")
    dados = arq.read()
    senha = os.environ.get("NFSE_CERT_SENHA")
    if senha:
        from cryptography.hazmat.primitives.serialization import pkcs12
        try:
            pkcs12.load_key_and_certificates(dados, senha.encode("utf-8"))
        except Exception as e:  # noqa: BLE001
            raise ValueError("O arquivo não abre com a senha configurada em NFSE_CERT_SENHA.") from e
    destino = config.caminho_certificado_padrao()
    tmp = destino.with_name(".certificado.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(dados)
    os.replace(tmp, destino)
    flash("Certificado salvo." + ("" if senha else " Falta definir a variável NFSE_CERT_SENHA no ambiente."), "ok")


_P, _G = ["POST"], ["GET"]
_GP = ["GET", "POST"]
_ROTAS = [
    ("/entrar", "login", login, _GP), ("/sair", "sair", sair, _P), ("/primeiro-acesso", "primeiro_acesso", primeiro_acesso, _GP),
    ("/conta", "conta", conta, _GP), ("/usuarios", "usuarios", usuarios, _GP), ("/", "painel", painel, _G),
    ("/clientes", "clientes", clientes, _G), ("/clientes/novo", "cliente_novo", cliente_form, _GP),
    ("/clientes/<int:cid>", "cliente_editar", cliente_form, _GP),
    ("/notas", "notas", notas, _G), ("/notas/nova", "nota_nova", nota_nova, _GP),
    ("/notas/<int:nid>", "nota_detalhe", nota_detalhe, _GP), ("/notas/<int:nid>/<acao>", "nota_acao", nota_acao, _P),
    ("/notas/<int:nid>/arquivo/<tipo>", "nota_arquivo", nota_arquivo, _G),
    ("/agendamentos", "agendamentos", agendamentos, _G), ("/agendamentos/novo", "agendamento_novo", agendamento_form, _GP),
    ("/agendamentos/gerar", "agendamentos_gerar", agendamentos_gerar, _P),
    ("/agendamentos/<int:aid>", "agendamento_editar", agendamento_form, _GP),
    ("/sugestoes", "sugestoes", sugestoes, _GP),
    ("/configuracao", "configuracao", configuracao, _GP),
]
