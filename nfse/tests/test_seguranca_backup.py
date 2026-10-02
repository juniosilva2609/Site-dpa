import gzip
import sqlite3

import pytest

from app import alertas, db, emissor, saida, scheduler
from app.fiscal import api_nfse, danfse

from .conftest import criar_nota, nfse_falsa

XXE = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
       '<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse"><infNFSe Id="NFS' + "1" * 50 + '"><nNFSe>&e;</nNFSe></infNFSe></NFSe>')


def test_xml_com_doctype_entidade_e_recusado(con, cliente_id):
    with pytest.raises(ValueError, match="DOCTYPE"):
        emissor.dados_nfse(XXE)
    with pytest.raises(danfse.DanfseIndisponivel):
        danfse.gerar_danfse_pdf(XXE)
    nid = criar_nota(con, cliente_id, "verificar", numero_dps=1)
    r = emissor.anexar_xml(con, nid, XXE)
    assert not r["ok"] and "DOCTYPE" in r["erro"]


def test_primeiro_acesso_de_fora_exige_codigo(app, monkeypatch):
    monkeypatch.delenv("NFSE_SETUP_CODE", raising=False)
    c = app.test_client()
    assert c.get("/primeiro-acesso", environ_overrides={"REMOTE_ADDR": "203.0.113.9"}).status_code == 403
    assert c.get("/primeiro-acesso", environ_overrides={"REMOTE_ADDR": "127.0.0.1"}).status_code == 200
    monkeypatch.setenv("NFSE_SETUP_CODE", "abc")
    assert c.get("/primeiro-acesso", environ_overrides={"REMOTE_ADDR": "203.0.113.9"}).status_code == 200


def test_cabecalhos_de_seguranca_e_cookie(app):
    r = app.test_client().get("/entrar")
    assert r.headers["X-Frame-Options"] == "DENY" and "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["Cache-Control"] == "no-store"
    assert app.config["SESSION_COOKIE_HTTPONLY"] and app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_cookie_secure_por_padrao(tmp_path, monkeypatch):
    from app import create_app
    monkeypatch.delenv("NFSE_DEV")
    assert create_app(db_path=str(tmp_path / "x.db"), iniciar_agendador=False).config["SESSION_COOKIE_SECURE"] is True


def test_senha_do_certificado_nunca_aparece_no_banco_nem_em_erros(con, cliente_id, monkeypatch, tmp_path):
    from .conftest import SENHA_CERT
    monkeypatch.setattr(api_nfse, "emitir_nfse", lambda *_: (_ for _ in ()).throw(api_nfse.ErroApiNfse("erro qualquer", 400)))
    emissor.emitir(con, criar_nota(con, cliente_id))
    dump = "\n".join(con.iterdump())
    assert SENHA_CERT not in dump


def test_backup_verificado_e_restauracao(con, cliente_id, tmp_path):
    criar_nota(con, cliente_id, "a_conferir")
    arq = scheduler.backup_diario(con)
    assert arq and sqlite3.connect(arq).execute("SELECT COUNT(*) FROM nota").fetchone()[0] == 1
    assert (oct(__import__("os").stat(arq).st_mode & 0o777)) == "0o600"
    # estraga o banco "de produção" e restaura
    alvo = tmp_path / "producao.db"
    c2 = db.conectar(alvo)
    db.migrar(c2)
    c2.close()
    guardado = scheduler.restaurar_backup(arq, alvo)
    assert "antes-de-restaurar" in guardado
    assert sqlite3.connect(alvo).execute("SELECT COUNT(*) FROM nota").fetchone()[0] == 1


def test_backup_corrompido_e_recusado_na_restauracao(tmp_path):
    ruim = tmp_path / "ruim.db"
    ruim.write_bytes(b"isto nao e um sqlite" * 50)
    with pytest.raises(Exception):  # noqa: B017
        scheduler.restaurar_backup(ruim, tmp_path / "x.db")


def test_backup_copia_para_pasta_de_saida_e_por_email(con, cliente_id, monkeypatch, tmp_path):
    enviados = []
    monkeypatch.setenv("NFSE_BACKUP_EMAIL", "1")
    monkeypatch.setattr(saida, "enviar_email", lambda d, a, c, an: enviados.append(an))
    con.execute("UPDATE configuracao SET emails_destino = 'a@b.com'")
    arq = scheduler.backup_diario(con)
    assert list((tmp_path / "saida" / "_backup").glob("nfse-*.db"))
    assert enviados and enviados[0][0][0].endswith(".gz") and gzip.decompress(enviados[0][0][1])[:6] == b"SQLite"
    assert arq and scheduler.backup_diario(con) is None            # uma vez por dia


def test_passo_da_manutencao_que_falha_nao_impede_os_outros(con, monkeypatch):
    def quebra(_c):
        raise RuntimeError("boom")
    monkeypatch.setattr(scheduler, "alertas_certificado", quebra)
    scheduler.manutencao(con)
    assert any("certificado" in a["chave"] for a in alertas.abertos(con))
    assert con.execute("SELECT valor FROM estado WHERE chave = 'backup_dia'").fetchone()           # backup rodou mesmo assim


def test_nota_xml_de_homologacao_nao_vira_producao(con, cliente_id, monkeypatch):
    monkeypatch.setattr(api_nfse, "emitir_nfse", lambda x, a: {"status_code": 200, "xml_resposta": nfse_falsa(x.decode())})
    nid = criar_nota(con, cliente_id)
    emissor.emitir(con, nid)
    assert con.execute("SELECT ambiente FROM nota WHERE id = ?", (nid,)).fetchone()[0] == "homologacao"
