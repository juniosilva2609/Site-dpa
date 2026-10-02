import pytest

from app import alertas, feedback, saida, scheduler

from .test_web import admin, client, post  # noqa: F401


@pytest.fixture
def emails(monkeypatch):
    enviados = []
    monkeypatch.setattr(saida, "enviar_email", lambda d, a, c, an, responder_para=None: enviados.append((d, a, c)))
    return enviados


def test_registra_e_envia_ao_responsavel(con, emails):
    fid = feedback.registrar(con, "maria", "inconsistencia", "A nota saiu com o valor errado no cliente X", "/notas/3", None, "ambiente=producao")
    assert emails[0][0] == ["junioaraujo.adv@gmail.com"]
    assert "Inconsistência" in emails[0][1] and "maria" in emails[0][1]
    assert "valor errado" in emails[0][2] and "/notas/3" in emails[0][2]
    assert con.execute("SELECT enviado_em FROM feedback WHERE id = ?", (fid,)).fetchone()[0]


def test_destino_pode_ser_trocado_por_variavel(con, emails, monkeypatch):
    monkeypatch.setenv("NFSE_SUPORTE_EMAIL", "outro@exemplo.com")
    feedback.registrar(con, "maria", "sugestao", "Seria bom ter um filtro por cliente", "/notas")
    assert emails[0][0] == ["outro@exemplo.com"]


def test_sem_smtp_fica_pendente_e_reenvia(con, monkeypatch):
    # sem SMTP configurado (autouse remove SMTP_HOST): registra mesmo assim
    fid = feedback.registrar(con, "maria", "sugestao", "Gostaria de exportar a lista de notas", "/notas")
    r = con.execute("SELECT enviado_em, envio_erro FROM feedback WHERE id = ?", (fid,)).fetchone()
    assert r["enviado_em"] is None and "E-mail não configurado" in r["envio_erro"]
    enviados = []
    monkeypatch.setattr(saida, "enviar_email", lambda d, a, c, an, responder_para=None: enviados.append(d))
    assert scheduler.manutencao(con) is None and enviados
    assert con.execute("SELECT enviado_em FROM feedback WHERE id = ?", (fid,)).fetchone()[0]


def test_validacoes_e_limite(con, emails):
    for tipo, msg in (("x", "mensagem válida e longa"), ("sugestao", "curta"), ("sugestao", "a" * 4001)):
        with pytest.raises(ValueError):
            feedback.registrar(con, "maria", tipo, msg)
    for _ in range(feedback.LIMITE_POR_HORA):
        feedback.registrar(con, "joao", "sugestao", "mensagem de teste suficiente")
    with pytest.raises(ValueError, match="Muitos envios"):
        feedback.registrar(con, "joao", "sugestao", "mensagem de teste suficiente")
    feedback.registrar(con, "maria", "sugestao", "outra pessoa pode enviar normalmente")


def test_assunto_nao_permite_injecao_de_cabecalho(con, emails):
    feedback.registrar(con, "evil\r\nBcc: x@y.com", "sugestao", "mensagem de teste suficiente")
    assert "\n" not in emails[0][1] and "\r" not in emails[0][1]


def test_origem_externa_e_nota_inexistente_sao_ignoradas(con, emails):
    fid = feedback.registrar(con, "maria", "sugestao", "mensagem de teste suficiente", "http://evil.com", 9999)
    r = con.execute("SELECT origem, nota_id FROM feedback WHERE id = ?", (fid,)).fetchone()
    assert tuple(r) == ("", None)


def test_copia_dos_alertas_para_o_responsavel_e_opt_in(con, emails, monkeypatch):
    con.execute("UPDATE configuracao SET email_alertas = 'dono@x.com'")
    alertas.abrir(con, "k", "algo deu errado", "erro")
    monkeypatch.setenv("NFSE_SUPORTE_COPIA_ALERTAS", "1")
    alertas.enviar_pendentes(con)
    assert emails[0][0] == ["dono@x.com", "junioaraujo.adv@gmail.com"]


def test_tela_envio_e_lista_so_para_admin(admin, app, emails):  # noqa: F811
    r = post(admin, "/sugestoes", {"tipo": "inconsistencia", "mensagem": "O PDF veio sem o telefone do cliente", "origem": "/notas/1"})
    html = r.get_data(as_text=True)
    assert "Obrigado" in html and "O PDF veio sem o telefone" in html     # admin vê a lista
    assert emails and "telefone do cliente" in emails[0][2]
    r = post(admin, "/sugestoes", {"tipo": "sugestao", "mensagem": "curta"})
    assert "mínimo de 10" in r.get_data(as_text=True)
    post(admin, "/usuarios", {"acao": "novo", "nome": "Maria", "login": "maria", "senha": "outra-senha-9"})
    admin.post("/sair", data={"csrf_token": "token-de-teste"})
    post(admin, "/entrar", {"login": "maria", "senha": "outra-senha-9"})
    r = admin.get("/sugestoes")
    assert r.status_code == 200 and "Mensagens recebidas" not in r.get_data(as_text=True)    # operador não vê as dos outros
    assert "Sugestões" in admin.get("/").get_data(as_text=True)
