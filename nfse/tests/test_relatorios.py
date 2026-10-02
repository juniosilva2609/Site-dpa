from datetime import date

import pytest
from lxml import etree

from app import auditoria, db, exportar, graficos, relatorios, util

from .conftest import criar_nota
from .test_web import admin, client, post  # noqa: F401


def emitida(con, cliente_id, valor, dia, numero, dps=None, desc="Transfer", amb="producao", **extra):
    nid = criar_nota(con, cliente_id, "emitida", f"{dia} 09:00", valor, desc, ambiente=amb, emitida_em=f"{dia} 09:30:00", numero_nfse=str(numero),
                     xml_nfse="<x/>", pdf_path="x", xml_path="x", **extra)
    if dps:
        con.execute("UPDATE nota SET numero_dps = ?, id_dps = ? WHERE id = ?", (dps, f"DPS3106200260441511000170000010{dps:015d}", nid))
    return nid


@pytest.fixture
def cfg_sem_arquivos(con):
    con.execute("UPDATE configuracao SET salvar_em_pasta = 0, ambiente = 'producao'")


def outro_cliente(con, nome, doc):
    return con.execute("INSERT INTO cliente (nome, documento) VALUES (?, ?)", (nome, doc)).lastrowid


def test_periodos_pre_definidos():
    hoje = date(2026, 10, 2)
    assert relatorios.periodo("mes", hoje=hoje)[:2] == (date(2026, 10, 1), date(2026, 10, 31))
    assert relatorios.periodo("mes_anterior", hoje=hoje)[:2] == (date(2026, 9, 1), date(2026, 9, 30))
    assert relatorios.periodo("ano", hoje=hoje)[:2] == (date(2026, 1, 1), date(2026, 12, 31))
    assert relatorios.periodo("12m", hoje=hoje)[:2] == (date(2025, 11, 1), date(2026, 10, 31))
    assert relatorios.periodo("trimestre", hoje=hoje)[:2] == (date(2026, 8, 1), date(2026, 10, 31))
    i, f, _, p = relatorios.periodo("custom", "2026-03-10", "2026-03-01", hoje=hoje)    # invertido: corrige
    assert (i, f, p) == (date(2026, 3, 1), date(2026, 3, 10), "custom")
    assert relatorios.periodo("custom", "lixo", None, hoje=hoje)[3] == "ano"
    assert relatorios.periodo_anterior(date(2026, 10, 1), date(2026, 10, 31)) == (date(2026, 8, 31), date(2026, 9, 30))


def test_faturamento_regras(con, cliente_id, cfg_sem_arquivos):
    c2 = outro_cliente(con, "SEGUNDO LTDA", "11222333000181")
    emitida(con, cliente_id, 100000, "2026-09-10", 1)
    emitida(con, cliente_id, 50000, "2026-10-05", 2)
    emitida(con, c2, 30000, "2026-10-06", 3)
    cancel = emitida(con, c2, 99900, "2026-10-07", 4)
    con.execute("UPDATE nota SET status = 'cancelada' WHERE id = ?", (cancel,))
    emitida(con, c2, 77700, "2026-10-08", 5, amb="homologacao")                       # teste não conta em produção
    f = relatorios.faturamento(con, date(2026, 10, 1), date(2026, 10, 31), "producao")
    assert (f["total"], f["qtd"], f["ticket"], f["n_clientes"]) == (80000, 2, 40000, 2)
    assert (f["cancelado_valor"], f["cancelado_qtd"]) == (99900, 1)
    assert f["anterior"] == 100000 and round(f["variacao"], 1) == -20.0            # vs período anterior (setembro)
    assert [r["cliente"] for r in f["ranking"]] == ["DISTRIBUIDORA PERES & ARAUJO LTDA", "SEGUNDO LTDA"]
    assert relatorios.faturamento(con, date(2026, 10, 1), date(2026, 10, 31), "todos")["total"] == 80000 + 77700
    assert relatorios.faturamento(con, date(2026, 10, 1), date(2026, 10, 31), "homologacao")["total"] == 77700
    assert relatorios.faturamento(con, date(2026, 10, 1), date(2026, 10, 31), "producao", cliente_id=c2)["total"] == 30000
    anual = relatorios.faturamento(con, date(2026, 1, 1), date(2026, 12, 31), "producao")
    assert len(anual["mensal"]) == 12 and sum(m["valor"] for m in anual["mensal"]) == 180000
    assert [m["valor"] for m in anual["mensal"]][8:10] == [100000, 80000]


def test_top_clientes_dobra_o_resto_em_outros(con, cfg_sem_arquivos):
    ids = [outro_cliente(con, f"CLIENTE {i}", d) for i, d in enumerate(
        ["11222333000181", "45723174000110", "03778130000147", "27865757000102", "34028316000103", "52998224725", "11144477735", "21641059000139"])]
    for k, cid in enumerate(ids):
        emitida(con, cid, (8 - k) * 10000, "2026-10-05", 100 + k)
    f = relatorios.faturamento(con, date(2026, 10, 1), date(2026, 10, 31), "producao")
    assert len(f["clientes"]) == relatorios.CORES_MAX + 1 and f["clientes"][-1]["rotulo"] == "Outros" and f["clientes"][-1]["n_outros"] == 3
    assert abs(sum(x["pct"] for x in f["clientes"]) - 100) < 0.01
    assert graficos.classes_cores(f["clientes"]) == ["s1", "s2", "s3", "s4", "s5", "so"]


def test_graficos_svg_valido_com_dicas():
    mensal = [{"mes": f"2026-{m:02d}", "valor": v, "qtd": 1} for m, v in enumerate([100000, 0, 250000, 175000], start=1)]
    svg = graficos.colunas(mensal)
    raiz = etree.fromstring(svg.encode())
    assert raiz.tag.endswith("svg") and svg.count('class="coluna"') == 3 and svg.count("data-tip=") == 4
    assert "jan/26" in svg and "R$ 2,5 mil" in svg
    fat = [{"rotulo": "A & B", "valor": 70, "pct": 70.0}, {"rotulo": "Outros", "valor": 30, "pct": 30.0, "outros": True}]
    r = graficos.rosca(fat, ["s1", "so"], "Total", "R$ 1", "teste")
    etree.fromstring(r.encode())
    assert r.count('class="fatia ') == 2 and "A &amp; B" in r
    unica = graficos.rosca(fat[:1], ["s1"], "Total", "R$ 1", "teste")
    assert 'class="fatia anel s1"' in unica                                         # 100%: anel, não arco degenerado
    assert 'class="vazio"' in graficos.rosca([], [], "Total", "R$ 0", "vazio")
    assert "Sem dados" in graficos.colunas([])


def test_auditoria_numeracao_e_duplicidade(con, cliente_id, cfg_sem_arquivos):
    c2 = outro_cliente(con, "SEGUNDO LTDA", "11222333000181")
    emitida(con, cliente_id, 10000, "2026-10-01", 10, dps=1, desc="A")
    emitida(con, cliente_id, 20000, "2026-10-02", 11, dps=2, desc="B")
    emitida(con, cliente_id, 30000, "2026-10-03", 14, dps=5, desc="C")               # pulou nNFSe 12-13 e nDPS 3-4
    emitida(con, c2, 55000, "2026-10-04", 15, dps=6, desc="Igual")
    emitida(con, c2, 55000, "2026-10-04", 16, dps=7, desc="Igual")                    # mesmo dia -> erro
    emitida(con, c2, 99000, "2026-10-10", 17, dps=8, desc="X")
    emitida(con, c2, 99000, "2026-10-12", 18, dps=9, desc="X")                        # < 7 dias -> aviso
    emitida(con, cliente_id, 70000, "2026-08-05", 19, dps=10, desc="Mensal")
    emitida(con, cliente_id, 70000, "2026-09-05", 20, dps=11, desc="Mensal")          # recorrente mensal: NÃO sinaliza
    ach = auditoria.auditar(con)
    tipos = [(a["tipo"], a["severidade"]) for a in ach]
    assert ("furo_dps", "aviso") in tipos and ("furo_nfse", "aviso") in tipos
    titulos = " | ".join(a["titulo"] for a in ach)
    assert "pulado: 3 a 4" in titulos and "pulado: 12 a 13" in titulos
    dup = [a for a in ach if a["tipo"] == "duplicidade"]
    assert sorted(a["severidade"] for a in dup) == ["aviso", "erro"]                  # um achado por grupo, não por par
    assert not any("Mensal" in a["detalhe"] or "70.000" in a["detalhe"] for a in dup)
    r = auditoria.resumo(ach)
    assert r["erro"] >= 1 and r["aviso"] >= 3


def test_auditoria_situacoes_e_cadastro(con, cliente_id, cfg_sem_arquivos):
    emitida(con, cliente_id, 10000, "2026-10-01", 7, dps=1)
    emitida(con, cliente_id, 10000, "2026-09-01", 7, dps=2, desc="outra")              # nº de NFS-e repetido
    criar_nota(con, cliente_id, "verificar", "2026-10-02 09:00")
    criar_nota(con, cliente_id, "atrasada", "2026-10-01 09:00")
    con.execute("UPDATE cliente SET documento = '123'")
    tipos = {a["tipo"] for a in auditoria.auditar(con)}
    assert {"nfse_repetida", "verificar", "atrasada", "cliente_doc"} <= tipos


def test_auditoria_arquivo_sumiu_e_valor_atipico(con, cliente_id):
    con.execute("UPDATE configuracao SET salvar_em_pasta = 1, ambiente = 'producao'")
    for k in range(4):
        emitida(con, cliente_id, 10000, f"2026-0{k + 5}-01", 30 + k, dps=20 + k, desc=f"d{k}")
    emitida(con, cliente_id, 90000, "2026-09-01", 40, dps=30, desc="grande")
    tipos = {a["tipo"] for a in auditoria.auditar(con)}
    assert "arquivo_sumiu" in tipos and "valor_atipico" in tipos


def test_csv_excel_ptbr_e_protecao_de_formula():
    dados = exportar.csv_bytes(["Nome", "Valor (R$)"], [["=HYPERLINK(\"x\")", exportar.reais(150050)], ["Acentuação ç", exportar.reais(-500)]])
    assert dados.startswith(b"\xef\xbb\xbf") and b"Nome;Valor" in dados
    texto = dados.decode("utf-8-sig")
    assert "'=HYPERLINK" in texto and "1500,50" in texto and "Acentuação ç;-5,00" in texto


def test_pdf_relatorio_gera_documento():
    pdf = exportar.pdf_relatorio("Teste", "out/2026", [("Total", "R$ 1,00")], [{"titulo": "T", "cabecalho": ["a", "b"], "linhas": [["x & <y>", "1"]] * 80,
                                                                                "larguras": [60, 30], "direita": [1]}])
    assert pdf.startswith(b"%PDF") and len(pdf) > 4000


def test_paginas_e_exportacoes(admin, app, cfg_sem_arquivos):  # noqa: F811
    con = db.conectar(app.config["DB_PATH"])
    con.execute("UPDATE configuracao SET salvar_em_pasta = 0, ambiente = 'producao'")
    post(admin, "/clientes/novo", {"nome": "Cliente Um", "documento": "529.982.247-25"})
    hoje = util.agora().strftime("%Y-%m-%d")
    for k, v in enumerate([100000, 50000, 25000]):
        emitida(con, 1, v, hoje, 500 + k, dps=1 + k, desc=f"Serviço {k}")
    for url in ("/dashboard", "/dashboard?periodo=mes", "/dashboard?periodo=tudo&ambiente=todos", "/dashboard?periodo=custom&de=2026-01-01&ate=2026-12-31",
                "/relatorios", "/relatorios/notas", "/relatorios/faturamento", "/relatorios/inconsistencias", "/relatorios/notas?situacao=todas&cliente=1"):
        r = admin.get(url)
        assert r.status_code == 200, url
    html = admin.get("/dashboard?periodo=mes").get_data(as_text=True)
    assert "R$ 1.750,00" in html and "Faturamento por cliente" in html and 'class="rosca"' in html and "data-tip=" in html
    assert "Cliente Um" in html and "Início" in admin.get("/").get_data(as_text=True)
    csv = admin.get("/relatorios/notas?periodo=mes&formato=csv")
    assert csv.mimetype == "text/csv" and b"Cliente Um" in csv.data and b"1000,00" in csv.data
    assert admin.get("/relatorios/faturamento?periodo=mes&formato=csv&tabela=cliente").data.decode("utf-8-sig").count("\n") == 2
    for url in ("/relatorios/notas?formato=pdf", "/relatorios/faturamento?formato=pdf", "/relatorios/inconsistencias?formato=pdf"):
        r = admin.get(url)
        assert r.mimetype == "application/pdf" and r.data.startswith(b"%PDF"), url
    assert admin.get("/relatorios/inconsistencias?formato=csv").mimetype == "text/csv"
