from datetime import datetime, timedelta

import pytest

from app import alertas, db, emissor, saida, scheduler, util
from app.fiscal import api_nfse, danfse

from .conftest import criar_nota, nfse_falsa


@pytest.fixture
def api_ok(monkeypatch):
    chamadas = []

    def falso(xml_assinado, ambiente):
        chamadas.append(xml_assinado)
        return {"status_code": 200, "xml_resposta": nfse_falsa(xml_assinado.decode(), numero=480 + len(chamadas))}
    monkeypatch.setattr(api_nfse, "emitir_nfse", falso)
    return chamadas


def test_emissao_com_sucesso_grava_arquivos_e_avanca_numero(con, cliente_id, api_ok, tmp_path):
    nid = criar_nota(con, cliente_id)
    r = emissor.emitir(con, nid, usuario="agenda")
    assert r["ok"] and r["status"] == "emitida"
    n = dict(con.execute("SELECT * FROM nota WHERE id = ?", (nid,)).fetchone())
    assert n["status"] == "emitida" and n["numero_nfse"] == "481" and len(n["chave_acesso"]) == 50
    assert n["numero_dps"] == 1 and db.obter_config(con)["proximo_numero_dps"] == 2
    assert n["pdf_path"] and n["xml_path"] and not n["pasta_erro"]
    pdf = open(n["pdf_path"], "rb").read()
    assert pdf.startswith(b"%PDF") and b"HOMOLOG" in n["pdf_path"].encode()      # homologação identificada no nome
    assert "/2026/" in n["pdf_path"] or "/20" in n["pdf_path"]
    assert open(n["xml_path"], encoding="utf-8").read() == n["xml_nfse"]
    # nova emissão da mesma nota é recusada (anti-duplicidade)
    assert not emissor.emitir(con, nid, usuario="agenda", manual=True)["ok"]
    assert len(api_ok) == 1


def test_duas_emissoes_seguidas_usam_numeros_diferentes(con, cliente_id, api_ok):
    a, b = criar_nota(con, cliente_id), criar_nota(con, cliente_id)
    emissor.emitir(con, a)
    emissor.emitir(con, b)
    ids = [con.execute("SELECT id_dps FROM nota WHERE id = ?", (x,)).fetchone()[0] for x in (a, b)]
    assert ids[0] != ids[1] and ids[0].endswith("1") and ids[1].endswith("2")


def test_rejeicao_clara_nao_consome_numero(con, cliente_id, monkeypatch):
    monkeypatch.setattr(api_nfse, "emitir_nfse", lambda *_: (_ for _ in ()).throw(
        api_nfse.ErroApiNfse("E0120 IM do prestador não deve ser informado", 400)))
    nid = criar_nota(con, cliente_id)
    r = emissor.emitir(con, nid)
    n = dict(con.execute("SELECT * FROM nota WHERE id = ?", (nid,)).fetchone())
    assert not r["ok"] and n["status"] == "rejeitada" and "E0120" in n["mensagem_erro"]
    assert db.obter_config(con)["proximo_numero_dps"] == 1 and n["numero_dps"] is None
    assert [a for a in alertas.abertos(con) if a["nivel"] == "erro"]


def test_falha_ambigua_vai_para_verificar_e_reserva_o_numero(con, cliente_id, monkeypatch):
    def cai(*_):
        raise api_nfse.ErroApiNfse("Falha de conexão (timeout)", ambigua=True)
    monkeypatch.setattr(api_nfse, "emitir_nfse", cai)
    nid = criar_nota(con, cliente_id)
    r = emissor.emitir(con, nid)
    n = dict(con.execute("SELECT * FROM nota WHERE id = ?", (nid,)).fetchone())
    assert r["status"] == "verificar" and n["numero_dps"] == 1 and "NÃO emita de novo" in n["mensagem_erro"]
    assert db.obter_config(con)["proximo_numero_dps"] == 2          # o número NÃO volta (pode ter sido usado)
    # a rotina automática jamais reemite nota em 'verificar'
    assert not emissor.emitir(con, nid, usuario="agenda", manual=False)["ok"]
    # nova nota não reaproveita o número reservado
    outra = criar_nota(con, cliente_id)
    monkeypatch.setattr(api_nfse, "emitir_nfse", lambda x, a: {"status_code": 200, "xml_resposta": nfse_falsa(x.decode())})
    emissor.emitir(con, outra)
    assert con.execute("SELECT numero_dps FROM nota WHERE id = ?", (outra,)).fetchone()[0] == 2


def test_reemissao_de_verificar_reusa_mesmo_id_dps(con, cliente_id, monkeypatch):
    monkeypatch.setattr(api_nfse, "emitir_nfse", lambda *_: (_ for _ in ()).throw(api_nfse.ErroApiNfse("timeout", ambigua=True)))
    nid = criar_nota(con, cliente_id)
    emissor.emitir(con, nid)
    primeiro = con.execute("SELECT id_dps FROM nota WHERE id = ?", (nid,)).fetchone()[0]
    enviados = []
    monkeypatch.setattr(api_nfse, "emitir_nfse",
                        lambda x, a: enviados.append(x) or {"status_code": 200, "xml_resposta": nfse_falsa(x.decode())})
    r = emissor.emitir(con, nid, manual=True)
    assert r["ok"] and con.execute("SELECT id_dps FROM nota WHERE id = ?", (nid,)).fetchone()[0] == primeiro
    assert db.obter_config(con)["proximo_numero_dps"] == 2


def test_reenvio_recusado_continua_em_verificar(con, cliente_id, monkeypatch):
    monkeypatch.setattr(api_nfse, "emitir_nfse", lambda *_: (_ for _ in ()).throw(api_nfse.ErroApiNfse("timeout", ambigua=True)))
    nid = criar_nota(con, cliente_id)
    emissor.emitir(con, nid)
    monkeypatch.setattr(api_nfse, "emitir_nfse", lambda *_: (_ for _ in ()).throw(api_nfse.ErroApiNfse("E0014 DPS duplicada", 400)))
    r = emissor.emitir(con, nid, manual=True)
    assert r["status"] == "verificar" and "duplicidade" in r["erro"]


def test_resposta_sem_xml_nao_afirma_sucesso(con, cliente_id, monkeypatch):
    monkeypatch.setattr(api_nfse, "emitir_nfse", lambda *_: {"status_code": 200, "xml_resposta": None})
    nid = criar_nota(con, cliente_id)
    assert emissor.emitir(con, nid)["status"] == "verificar"


def test_conferencia_roda_de_novo_na_hora_da_emissao(con, cliente_id, api_ok):
    nid = criar_nota(con, cliente_id)
    con.execute("UPDATE cliente SET documento = '11111111111' WHERE id = ?", (cliente_id,))   # cadastro estragado
    r = emissor.emitir(con, nid)
    n = dict(con.execute("SELECT * FROM nota WHERE id = ?", (nid,)).fetchone())
    assert not r["ok"] and n["status"] == "a_conferir" and "inválido" in n["mensagem_erro"] and not api_ok


def test_descricao_acima_do_limite_bloqueia(con, cliente_id, api_ok):
    nid = criar_nota(con, cliente_id, descricao="palavra " * 200)
    r = emissor.emitir(con, nid)
    assert not r["ok"] and "1297" in r["erro"] and not api_ok


def test_certificado_vencido_ou_ausente_bloqueia(con, cliente_id, api_ok, monkeypatch):
    monkeypatch.delenv("NFSE_CERT_SENHA")
    nid = criar_nota(con, cliente_id)
    r = emissor.emitir(con, nid)
    assert not r["ok"] and "ertificado" in r["erro"] and not api_ok


def test_nota_presa_em_emitindo_vira_verificar(con, cliente_id):
    nid = criar_nota(con, cliente_id, status="emitindo")
    scheduler.recuperar_emissoes_travadas(con)
    assert con.execute("SELECT status FROM nota WHERE id = ?", (nid,)).fetchone()[0] == "verificar"


def test_trava_impede_emissao_simultanea(con, cliente_id, api_ok):
    nid = criar_nota(con, cliente_id)
    assert db.adquirir_trava(con, emissor.TRAVA, 60)
    r = emissor.emitir(con, nid)
    assert r.get("ocupado") and not api_ok
    assert con.execute("SELECT status FROM nota WHERE id = ?", (nid,)).fetchone()[0] == "aprovada"


def test_anexar_xml_do_portal_conclui_nota_em_verificar(con, cliente_id, monkeypatch):
    monkeypatch.setattr(api_nfse, "emitir_nfse", lambda *_: (_ for _ in ()).throw(api_nfse.ErroApiNfse("timeout", ambigua=True)))
    nid = criar_nota(con, cliente_id)
    emissor.emitir(con, nid)
    dps_assinada = con.execute("SELECT xml_dps FROM nota WHERE id = ?", (nid,)).fetchone()[0]
    r = emissor.anexar_xml(con, nid, nfse_falsa(dps_assinada, numero=777), "joao")
    assert r["ok"] and con.execute("SELECT numero_nfse, status FROM nota WHERE id = ?", (nid,)).fetchone()[:] == ("777", "emitida")
    outra = criar_nota(con, cliente_id, status="verificar", numero_dps=5)
    assert not emissor.anexar_xml(con, outra, "<x/>")["ok"]
    assert not emissor.anexar_xml(con, outra, nfse_falsa(dps_assinada, numero=1, cnpj="21641059000139"))["ok"]


def test_consultar_na_sefin_conclui_quando_existe(con, cliente_id, monkeypatch):
    monkeypatch.setattr(api_nfse, "emitir_nfse", lambda *_: (_ for _ in ()).throw(api_nfse.ErroApiNfse("timeout", ambigua=True)))
    nid = criar_nota(con, cliente_id)
    emissor.emitir(con, nid)
    dps_assinada = con.execute("SELECT xml_dps FROM nota WHERE id = ?", (nid,)).fetchone()[0]
    xml = nfse_falsa(dps_assinada, numero=900)
    chave = emissor.dados_nfse(xml)["chave"]
    monkeypatch.setattr(api_nfse, "consultar_dps", lambda i, a: chave)
    monkeypatch.setattr(api_nfse, "baixar_nfse", lambda c, a: xml)
    assert emissor.consultar_na_sefin(con, nid)["ok"]
    assert con.execute("SELECT status, numero_nfse FROM nota WHERE id = ?", (nid,)).fetchone()[:] == ("emitida", "900")


def test_cancelamento(con, cliente_id, api_ok, monkeypatch):
    nid = criar_nota(con, cliente_id)
    emissor.emitir(con, nid)
    eventos = []
    monkeypatch.setattr(api_nfse, "enviar_evento", lambda xml, chave, amb: eventos.append(chave) or {})
    assert not emissor.cancelar(con, nid, "1", "curto")["ok"]
    assert emissor.cancelar(con, nid, "1", "Emitida com valor errado, será refeita")["ok"]
    n = dict(con.execute("SELECT * FROM nota WHERE id = ?", (nid,)).fetchone())
    assert n["status"] == "cancelada" and eventos == [n["chave_acesso"]]
    assert "CANCELADA" in n["pdf_path"]
    assert not emissor.cancelar(con, nid, "1", "Emitida com valor errado, será refeita")["ok"]


def test_nome_do_arquivo():
    n = {"id": 1, "numero_nfse": "480", "status": "emitida", "ambiente": "producao",
         "descricao": "Serviço de transfer / prestado: Junio *Silva*? muito longo mesmo"}
    nome = saida.nome_arquivo(n, 'DISTRIBUIDORA "PERES" & ARAUJO')
    assert nome.startswith("NFSE 480 - Serviço de transfer prest") and not any(c in nome for c in '\\/:*?"<>|')
    assert saida.nome_arquivo({**n, "status": "cancelada"}, "x") == "NFSE 480 - CANCELADA"
    assert saida.nome_arquivo({**n, "ambiente": "homologacao"}, "x").startswith("HOMOLOG - ")


def test_pdf_do_danfse_mantem_descricao_inteira(con, cliente_id, api_ok):
    desc = "Serviço de transfer prestado para Junio Silva Araújo\nItinerário:\nBarreiro x Conselheiro Lafaiete - R$500,00"
    nid = criar_nota(con, cliente_id, descricao=desc)
    emissor.emitir(con, nid)
    xml = con.execute("SELECT xml_nfse FROM nota WHERE id = ?", (nid,)).fetchone()[0]
    pdf = danfse.gerar_danfse_pdf(xml)
    assert pdf.startswith(b"%PDF") and len(pdf) > 5000
    assert danfse.gerar_danfse_pdf(xml, "CANCELADA").startswith(b"%PDF")
    assert danfse.gerar_danfse_pdf_v2(xml).startswith(b"%PDF")      # layout v2.0 segue disponível


def test_danfse_v1_igual_ao_modelo_da_jl(con, cliente_id, api_ok):
    """Texto do PDF = o do modelo (NFS-e da JL): títulos, 004, quebras do itinerário, CEP 00000-000, '...' no cód. municipal."""
    import io

    import pdfplumber
    desc = "Serviço de transfer prestado para Junio Silva Araújo\nItinerário:\nBarreiro x Conselheiro Lafaiete - R$500,00"
    nid = criar_nota(con, cliente_id, descricao=desc)
    emissor.emitir(con, nid)
    xml = con.execute("SELECT xml_nfse FROM nota WHERE id = ?", (nid,)).fetchone()[0]
    pdf = danfse.gerar_danfse_para_registro(xml, "emitida")
    texto = pdfplumber.open(io.BytesIO(pdf)).pages[0].extract_text()
    for esperado in ("DANFSe v1.0", "Prefeitura Municipal de Belo", "Secretaria Municipal de Fazenda - SMFA", "EMITENTE DA NFS-e",
                     "16550350019", "JL TRANSPORTES EXECUTIVOS LTDA", "30170-131", "32430-090", "Ibirité - MG",
                     "INTERMEDIÁRIO DO SERVIÇO NÃO IDENTIFICADO NA NFS-e", "16.02.01 - Outros serviços de", "Itinerário:",
                     "Barreiro x Conselheiro Lafaiete - R$500,00", "Operação Tributável", "Não Retido", "Valor Líquido da NFS-e",
                     "R$ 500,00", "TOTAIS APROXIMADOS DOS TRIBUTOS", "INFORMAÇÕES COMPLEMENTARES"):
        assert esperado in texto, esperado
    cancelada = danfse.gerar_danfse_para_registro(xml, "cancelada")
    assert b"CANCELADA" in cancelada or len(cancelada) != len(pdf)     # marca d'água aplicada ao status "cancelada"



# ------------------------------------------------------------------ agendador
def test_agendador_emite_so_aprovadas_no_horario(con, cliente_id, api_ok):
    agora = util.agora()
    passou = (agora - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M")
    futuro = (agora + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
    ok = criar_nota(con, cliente_id, "aprovada", passou)
    sem_conferir = criar_nota(con, cliente_id, "a_conferir", passou)
    ainda_nao = criar_nota(con, cliente_id, "aprovada", futuro)
    scheduler.emitir_vencidas(con, agora)
    st = {i: con.execute("SELECT status FROM nota WHERE id = ?", (i,)).fetchone()[0] for i in (ok, sem_conferir, ainda_nao)}
    assert st == {ok: "emitida", sem_conferir: "a_conferir", ainda_nao: "aprovada"}
    assert len(api_ok) == 1


def test_nota_muito_atrasada_nao_sai_sozinha(con, cliente_id, api_ok):
    agora = util.agora()
    velha = (agora - timedelta(days=2)).strftime("%Y-%m-%d %H:%M")
    nid = criar_nota(con, cliente_id, "aprovada", velha)
    scheduler.emitir_vencidas(con, agora)
    assert con.execute("SELECT status FROM nota WHERE id = ?", (nid,)).fetchone()[0] == "atrasada" and not api_ok
    assert emissor.aprovar(con, nid, "maria")["ok"]           # humano pode reaprovar e então sai
    scheduler.emitir_vencidas(con, util.agora())
    # reaprovada mas ainda além da tolerância: continua exigindo emissão manual
    assert con.execute("SELECT status FROM nota WHERE id = ?", (nid,)).fetchone()[0] == "atrasada"
    assert emissor.emitir(con, nid, "maria", manual=True)["ok"]


def test_tick_e_idempotente_e_gera_emite(con, cliente_id, api_ok):
    from app import agenda
    agora = datetime.now().replace(second=0, microsecond=0)
    con.execute("INSERT INTO agendamento (nome, cliente_id, descricao, valor_centavos, frequencia, data_unica, hora, "
                "antecedencia_dias, auto_aprovar, criado_em) VALUES ('t', ?, 'Serviço de {mes_ano}', 10000, 'unica', ?, ?, 3, 1, ?)",
                (cliente_id, agora.strftime("%Y-%m-%d"), agora.strftime("%H:%M"), (agora - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")))
    r1 = scheduler.tick(con, agora)
    r2 = scheduler.tick(con, agora)
    assert r1["executou"] and len(r1["criadas"]) == 1 and r2["criadas"] == []
    assert con.execute("SELECT COUNT(*) FROM nota").fetchone()[0] == 1
    n = dict(con.execute("SELECT * FROM nota").fetchone())
    assert n["status"] == "emitida" and util.MESES[agora.month - 1] in n["descricao"] and len(api_ok) == 1
    assert agenda.expandir_descricao("{x} {mes}", agora).startswith("{x} ")


def test_entrega_por_email(con, cliente_id, api_ok, monkeypatch):
    enviados = []
    monkeypatch.setattr(saida, "enviar_email", lambda d, a, c, an: enviados.append((d, a, [x[0] for x in an])))
    con.execute("UPDATE configuracao SET enviar_por_email = 1, emails_destino = 'contador@x.com'")
    con.execute("UPDATE cliente SET enviar_nota_por_email = 1 WHERE id = ?", (cliente_id,))
    nid = criar_nota(con, cliente_id)
    emissor.emitir(con, nid)
    assert enviados and enviados[0][0] == ["contador@x.com", "x@y.com"]
    assert [a for a in enviados[0][2] if a.endswith(".pdf")] and [a for a in enviados[0][2] if a.endswith(".xml")]
    assert con.execute("SELECT email_enviado_em FROM nota WHERE id = ?", (nid,)).fetchone()[0]


def test_falha_de_entrega_nao_afeta_nota_e_e_reentregue(con, cliente_id, api_ok, monkeypatch):
    def quebra(*a):
        raise RuntimeError("SMTP fora do ar")
    monkeypatch.setattr(saida, "enviar_email", quebra)
    con.execute("UPDATE configuracao SET enviar_por_email = 1, emails_destino = 'contador@x.com'")
    nid = criar_nota(con, cliente_id)
    assert emissor.emitir(con, nid)["status"] == "emitida"
    n = dict(con.execute("SELECT * FROM nota WHERE id = ?", (nid,)).fetchone())
    assert n["status"] == "emitida" and "SMTP" in n["email_erro"] and n["pdf_path"]
    enviados = []
    monkeypatch.setattr(saida, "enviar_email", lambda *a: enviados.append(a))
    assert scheduler.entregas_pendentes(con) == 1 and len(enviados) == 1
    assert scheduler.entregas_pendentes(con) == 0


def test_pasta_com_problema_gera_erro_e_nao_trava(con, cliente_id, api_ok, tmp_path):
    arquivo = tmp_path / "arquivo"
    arquivo.write_text("x")
    con.execute("UPDATE configuracao SET pasta_saida = ?", (str(arquivo / "dentro"),))   # pasta impossível
    nid = criar_nota(con, cliente_id)
    assert emissor.emitir(con, nid)["status"] == "emitida"
    assert con.execute("SELECT pasta_erro FROM nota WHERE id = ?", (nid,)).fetchone()[0]


def test_backup_diario(con):
    caminho = scheduler.backup_diario(con)
    assert caminho and caminho.endswith(".db") and scheduler.backup_diario(con) is None
