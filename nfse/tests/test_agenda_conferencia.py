from datetime import datetime, timedelta

from app import agenda, conferencia, util

from .conftest import criar_nota


def _ag(**kw):
    base = {"frequencia": "mensal", "dia_mes": 31, "dia_semana": None, "data_unica": None, "hora": "09:00"}
    return {**base, **kw}


def test_mensal_dia_31_vira_ultimo_dia_do_mes():
    r = agenda.ocorrencias(_ag(), datetime(2027, 1, 1), datetime(2027, 4, 30, 23, 59))
    assert [d.strftime("%m-%d") for d in r] == ["01-31", "02-28", "03-31", "04-30"]
    assert agenda.ocorrencias(_ag(), datetime(2028, 2, 1), datetime(2028, 2, 29, 23))[0].day == 29   # bissexto


def test_mensal_respeita_janela_e_virada_de_ano():
    r = agenda.ocorrencias(_ag(dia_mes=5, hora="08:30"), datetime(2026, 11, 20), datetime(2027, 1, 10))
    assert [d.strftime("%Y-%m-%d %H:%M") for d in r] == ["2026-12-05 08:30", "2027-01-05 08:30"]


def test_semanal_e_unica():
    seg = agenda.ocorrencias(_ag(frequencia="semanal", dia_semana=0), datetime(2026, 10, 1), datetime(2026, 10, 20, 23))
    assert [d.day for d in seg] == [5, 12, 19] and all(d.weekday() == 0 for d in seg)
    uni = agenda.ocorrencias(_ag(frequencia="unica", data_unica="2026-10-15"), datetime(2026, 10, 1), datetime(2026, 10, 30))
    assert uni == [datetime(2026, 10, 15, 9, 0)]


def test_descricao_com_variaveis():
    t = agenda.expandir_descricao("Transfer de {mes_ano} (competência {competencia}) dia {data} {ano} {inexistente}", datetime(2026, 10, 5))
    assert t == "Transfer de outubro/2026 (competência 10/2026) dia 05/10/2026 2026 {inexistente}"


def _novo_ag(con, cliente_id, **kw):
    campos = {"nome": "Mensal", "cliente_id": cliente_id, "descricao": "Serviço de {mes_ano}", "valor_centavos": 50000,
              "frequencia": "mensal", "dia_mes": 5, "hora": "09:00", "antecedencia_dias": 3, "auto_aprovar": 0,
              "criado_em": "2026-10-01 08:00:00", **kw}
    cur = con.execute(f"INSERT INTO agendamento ({','.join(campos)}) VALUES ({','.join('?' * len(campos))})", tuple(campos.values()))
    return cur.lastrowid


def test_gera_nota_na_janela_de_antecedencia_sem_duplicar(con, cliente_id):
    _novo_ag(con, cliente_id)
    assert agenda.gerar_notas(con, datetime(2026, 10, 1, 12)) == []                 # 4 dias antes: ainda cedo
    criadas = agenda.gerar_notas(con, datetime(2026, 10, 2, 12))                     # 3 dias antes
    assert len(criadas) == 1 and agenda.gerar_notas(con, datetime(2026, 10, 3)) == []
    n = dict(con.execute("SELECT * FROM nota WHERE id = ?", (criadas[0],)).fetchone())
    assert n["status"] == "a_conferir" and n["prevista_em"] == "2026-10-05 09:00" and "outubro/2026" in n["descricao"]


def test_nao_gera_backlog_anterior_a_criacao(con, cliente_id):
    _novo_ag(con, cliente_id, dia_mes=1, criado_em="2026-10-10 10:00:00")
    assert agenda.gerar_notas(con, datetime(2026, 10, 11)) == []           # dia 1 deste mês já tinha passado


def test_auto_aprovar_so_com_conferencia_ok(con, cliente_id):
    agora = datetime.now().replace(second=0, microsecond=0)
    amanha = (agora + timedelta(days=1)).strftime("%Y-%m-%d")
    criado = (agora - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    _novo_ag(con, cliente_id, frequencia="unica", data_unica=amanha, hora="10:00", auto_aprovar=1, criado_em=criado)
    (nid,) = agenda.gerar_notas(con, agora)
    assert tuple(con.execute("SELECT status, conferido_por FROM nota WHERE id = ?", (nid,)).fetchone()) == ("aprovada", "automático")
    # cadastro com problema: não aprova sozinha
    con.execute("UPDATE cliente SET documento = '123'")
    _novo_ag(con, cliente_id, nome="2", frequencia="unica", data_unica=amanha, hora="11:00", auto_aprovar=1, criado_em=criado)
    (nid2,) = agenda.gerar_notas(con, agora)
    assert con.execute("SELECT status FROM nota WHERE id = ?", (nid2,)).fetchone()[0] == "a_conferir"


def test_pausado_nao_gera(con, cliente_id):
    ag = _novo_ag(con, cliente_id)
    con.execute("UPDATE agendamento SET ativo = 0 WHERE id = ?", (ag,))
    assert agenda.gerar_notas(con, datetime(2026, 10, 4)) == []


def textos(lista):
    return " | ".join(p["texto"] for p in lista)


def test_conferencia_detecta_problemas(con, cliente_id):
    nid = criar_nota(con, cliente_id, "a_conferir", valor=50000, descricao="ok")
    assert not conferencia.erros(conferencia.conferir(con, nid))
    con.execute("UPDATE nota SET descricao = 'Serviço {mes}' WHERE id = ?", (nid,))
    assert "chaves" in textos(conferencia.conferir(con, nid))
    con.execute("UPDATE nota SET descricao = '   ', valor_centavos = 0 WHERE id = ?", (nid,))
    t = textos(conferencia.conferir(con, nid))
    assert "vazia" in t and "maior que zero" in t
    con.execute("UPDATE cliente SET documento = '123', ativo = 0")
    t = textos(conferencia.conferir(con, nid))
    assert "inválido" in t and "desativado" in t


def test_conferencia_avisa_valor_diferente_e_duplicidade(con, cliente_id):
    ag = _novo_ag(con, cliente_id)
    mes = util.agora().strftime("%Y-%m")
    emitida = criar_nota(con, cliente_id, "emitida", f"{mes}-05 09:00", 50000, "igual", agendamento_id=ag, numero_nfse="10")
    nova = criar_nota(con, cliente_id, "a_conferir", (util.agora() + timedelta(days=1)).strftime("%Y-%m-%d 09:00"), 60000, "outra", agendamento_id=ag)
    assert "Valor diferente" in textos(conferencia.conferir(con, nova))
    dup = criar_nota(con, cliente_id, "a_conferir", f"{mes}-20 09:00", 50000, "igual")
    assert "nota emitida igual" in textos(conferencia.conferir(con, dup)) and emitida


def test_cnpj_do_certificado_diferente_bloqueia(con, cliente_id):
    con.execute("UPDATE configuracao SET cnpj = '21641059000139'")
    nid = criar_nota(con, cliente_id, "a_conferir")
    assert "diferente do CNPJ" in textos(conferencia.conferir(con, nid))
