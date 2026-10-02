import pytest

from app import db, emissor
from app.fiscal import api_nfse

from .conftest import CNPJ_CLIENTE, nfse_falsa


@pytest.fixture
def client(app):
    from app import web
    web._FALHAS_LOGIN.clear()
    return app.test_client()


def _csrf(client):
    with client.session_transaction() as s:
        s.setdefault("csrf", "token-de-teste")
        return s["csrf"]


def post(client, url, dados=None, **kw):
    dados = dict(dados or {})
    dados["csrf_token"] = _csrf(client)
    return client.post(url, data=dados, follow_redirects=True, **kw)


@pytest.fixture
def admin(client):
    r = post(client, "/primeiro-acesso", {"nome": "Junio", "login": "junio", "senha": "senha-forte-1", "senha2": "senha-forte-1"})
    assert r.status_code == 200
    r = post(client, "/entrar", {"login": "junio", "senha": "senha-forte-1"})
    assert "Painel" in r.get_data(as_text=True)
    return client


def test_exige_login_e_primeiro_acesso(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302 and "/primeiro-acesso" in r.headers["Location"]


def test_post_sem_csrf_e_recusado(admin):
    assert admin.post("/clientes/novo", data={"nome": "x"}).status_code == 400


def test_login_errado_e_bloqueio_apos_tentativas(client, admin):
    client.post("/sair", data={"csrf_token": _csrf(client)})
    for _ in range(5):
        r = post(client, "/entrar", {"login": "junio", "senha": "errada"})
        assert "incorretos" in r.get_data(as_text=True)
    r = post(client, "/entrar", {"login": "junio", "senha": "senha-forte-1"})
    assert "Muitas tentativas" in r.get_data(as_text=True)


def test_fluxo_completo_cliente_agendamento_conferencia_emissao(admin, app, monkeypatch):
    monkeypatch.setattr(api_nfse, "emitir_nfse", lambda x, a: {"status_code": 200, "xml_resposta": nfse_falsa(x.decode())})
    r = post(admin, "/clientes/novo", {"nome": "DISTRIBUIDORA PERES & ARAUJO LTDA", "documento": "21.641.059/0001-39",
                                       "cep": "32430-090", "logradouro": "ANTONIO GERMANO", "numero": "688",
                                       "bairro": "PALMARES", "cidade": "Ibirité", "uf": "MG"})
    assert "Cliente salvo" in r.get_data(as_text=True)
    r = post(admin, "/clientes/novo", {"nome": "Outro", "documento": "123"})
    assert "inválido" in r.get_data(as_text=True)
    r = post(admin, "/clientes/novo", {"nome": "Dup", "documento": CNPJ_CLIENTE})
    assert "Já existe" in r.get_data(as_text=True)

    r = post(admin, "/agendamentos/novo", {"nome": "Transfer mensal", "cliente_id": "1", "valor": "500,00", "frequencia": "unica",
                                           "data_unica": "2031-01-01", "hora": "09:00", "antecedencia_dias": "3", "ativo": "1",
                                           "descricao": "Serviço de transfer de {mes_ano}"})
    assert "Agendamento salvo" in r.get_data(as_text=True)
    assert "Transfer mensal" in admin.get("/agendamentos").get_data(as_text=True)

    r = post(admin, "/notas/nova", {"cliente_id": "1", "prevista_data": "2030-01-10", "prevista_hora": "09:00", "valor": "1.500,00",
                                    "descricao": "Transfer\nItinerário: A x B"})
    html = r.get_data(as_text=True)
    assert "Nota #1" in html and "A conferir" in html and "R$" not in "" and "Conferi: aprovar" in html
    r = post(admin, "/notas/1/aprovar")
    assert "Aprovada" in r.get_data(as_text=True)
    r = post(admin, "/notas/1/desaprovar")
    assert "A conferir" in r.get_data(as_text=True)
    r = post(admin, "/notas/1/emitir")
    html = r.get_data(as_text=True)
    assert "emitida" in html.lower() and "Baixar PDF" in html
    assert admin.get("/notas/1/arquivo/xml").mimetype == "application/xml"
    pdf = admin.get("/notas/1/arquivo/pdf")
    assert pdf.mimetype == "application/pdf" and pdf.data.startswith(b"%PDF")
    assert "Emitida" in admin.get("/").get_data(as_text=True)


def test_todas_as_telas_abrem(admin, app):
    post(admin, "/clientes/novo", {"nome": "Cliente", "documento": "529.982.247-25"})
    for url in ("/", "/notas", "/notas?status=emitida&mes=2026-10", "/notas/nova", "/agendamentos", "/agendamentos/novo", "/clientes",
                "/clientes/novo", "/clientes/1", "/configuracao", "/usuarios", "/conta", "/saude"):
        r = admin.get(url)
        assert r.status_code == 200, url
    assert admin.get("/notas/999").status_code == 404


def test_configuracao_producao_exige_confirmacao(admin, app):
    campos = {"acao": "fiscal", "razao_social": "JL", "cnpj": "60.441.511/0001-70", "inscricao_municipal": "1", "telefone": "31",
              "email": "a@b.com", "codigo_municipio_ibge": "3106200", "regime_tributario": "simples", "codigo_servico_lc116": "160201",
              "codigo_tributacao_municipal": "004", "serie_dps": "1", "proximo_numero_dps": "1", "ambiente": "producao"}
    r = post(admin, "/configuracao", campos)
    assert "digite PRODUCAO" in r.get_data(as_text=True)
    con = db.conectar(app.config["DB_PATH"])
    assert db.obter_config(con)["ambiente"] == "homologacao"
    r = post(admin, "/configuracao", {**campos, "confirmar_producao": "producao"})
    assert "Configuração fiscal salva" in r.get_data(as_text=True)
    assert db.obter_config(con)["ambiente"] == "producao"
    r = post(admin, "/configuracao", {**campos, "proximo_numero_dps": "50"})
    assert "confirmação" in r.get_data(as_text=True) and db.obter_config(con)["proximo_numero_dps"] == 1


def test_operador_nao_acessa_configuracao_nem_cancela(admin, app):
    post(admin, "/usuarios", {"acao": "novo", "nome": "Maria", "login": "maria", "senha": "outra-senha-9"})
    admin.post("/sair", data={"csrf_token": _csrf(admin)})
    post(admin, "/entrar", {"login": "maria", "senha": "outra-senha-9"})
    assert admin.get("/configuracao").status_code == 403
    assert admin.get("/usuarios").status_code == 403
    assert admin.get("/").status_code == 200
    assert post(admin, "/notas/1/cancelar", {"motivo": "1", "texto": "x" * 20}).status_code in (403, 404)


def test_emissao_manual_pela_tela_com_erro_mostra_mensagem(admin, app, monkeypatch):
    monkeypatch.setattr(api_nfse, "emitir_nfse", lambda *_: (_ for _ in ()).throw(api_nfse.ErroApiNfse("E0166 regime obrigatório", 400)))
    post(admin, "/clientes/novo", {"nome": "Cliente", "documento": "529.982.247-25"})
    post(admin, "/notas/nova", {"cliente_id": "1", "prevista_data": "2030-01-10", "prevista_hora": "09:00", "valor": "10", "descricao": "x"})
    r = post(admin, "/notas/1/emitir")
    assert "E0166" in r.get_data(as_text=True) and "Erro: corrigir" in r.get_data(as_text=True)
    con = db.conectar(app.config["DB_PATH"])
    assert emissor and con.execute("SELECT status FROM nota WHERE id = 1").fetchone()[0] == "rejeitada"
