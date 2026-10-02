# -*- coding: utf-8 -*-
"""Auditoria de inconsistências: procura no próprio banco o que merece conferência humana.

Cada achado: {tipo, severidade: erro|aviso|info, titulo, detalhe, nota_id}. Nada é corrigido sozinho."""

import re
import sqlite3
import statistics
from datetime import datetime, timedelta
from pathlib import Path

from . import db, util

SEVERIDADES = {"erro": "Erro", "aviso": "Atenção", "info": "Informação"}


def _achado(tipo, sev, titulo, detalhe="", nota_id=None):
    return {"tipo": tipo, "severidade": sev, "titulo": titulo, "detalhe": detalhe, "nota_id": nota_id}


def _faixas(numeros: list[int]) -> list[tuple[int, int]]:
    """[1,2,5,6,9] (faltantes entre min e max) -> [(3,4),(7,8)]"""
    if not numeros:
        return []
    presentes = set(numeros)
    faltam = [n for n in range(min(numeros), max(numeros) + 1) if n not in presentes]
    faixas = []
    for n in faltam:
        if faixas and faixas[-1][1] == n - 1:
            faixas[-1] = (faixas[-1][0], n)
        else:
            faixas.append((n, n))
    return faixas


def _fmt_faixa(a, b):
    return str(a) if a == b else f"{a} a {b}"


def numeracao(con: sqlite3.Connection) -> list[dict]:
    achados = []
    # --- nDPS por (ambiente, série): número consumido e depois sumido
    grupos: dict[tuple, list[int]] = {}
    for r in con.execute("SELECT ambiente, id_dps, numero_dps FROM nota WHERE numero_dps IS NOT NULL AND id_dps IS NOT NULL "
                         "AND status NOT IN ('pulada')"):
        serie = r["id_dps"][25:30] if len(r["id_dps"]) >= 45 else "?"
        grupos.setdefault((r["ambiente"] or "?", serie), []).append(r["numero_dps"])
    for (amb, serie), nums in grupos.items():
        for a, b in _faixas(nums):
            achados.append(_achado("furo_dps", "aviso", f"Número da DPS pulado: {_fmt_faixa(a, b)}",
                                   f"Série {serie}, ambiente {amb}. A sequência vai de {min(nums)} a {max(nums)}, mas esse número não está em "
                                   "nenhuma nota. Pode ser nota emitida fora do sistema com a mesma série, ou número perdido."))
    # --- nNFSe emitida
    por_amb: dict[str, list[int]] = {}
    repetidos: dict[tuple, list[int]] = {}
    for r in con.execute("SELECT id, ambiente, numero_nfse FROM nota WHERE numero_nfse IS NOT NULL AND status IN ('emitida','cancelada')"):
        if str(r["numero_nfse"]).isdigit():
            por_amb.setdefault(r["ambiente"] or "?", []).append(int(r["numero_nfse"]))
            repetidos.setdefault((r["ambiente"], int(r["numero_nfse"])), []).append(r["id"])
    for amb, nums in por_amb.items():
        for a, b in _faixas(nums):
            achados.append(_achado("furo_nfse", "aviso", f"Número da NFS-e pulado: {_fmt_faixa(a, b)}",
                                   f"Ambiente {amb}. Entre as notas {min(nums)} e {max(nums)} faltam esses números: podem ter sido emitidos "
                                   "pelo Portal Nacional/outro sistema (confira lá) ou haver nota não registrada aqui."))
    for (amb, num), ids in repetidos.items():
        if len(ids) > 1:
            achados.append(_achado("nfse_repetida", "erro", f"Número de NFS-e repetido: {num}",
                                   f"Aparece nas notas internas {', '.join('#' + str(i) for i in ids)} (ambiente {amb}).", ids[0]))
    return achados


def _norm(texto: str) -> str:
    return re.sub(r"\W+", " ", (texto or "").lower()).strip()


def duplicidades(con: sqlite3.Connection) -> list[dict]:
    """Um achado por GRUPO (cliente + valor + descrição + ambiente), nunca um por par:
    - erro: duas ou mais notas emitidas no MESMO DIA;
    - aviso: notas com menos de 7 dias de diferença (cobrança recorrente mensal não dispara isto)."""
    achados = []
    grupos: dict[tuple, list[dict]] = {}
    for r in con.execute("SELECT n.*, c.nome AS cliente FROM nota n JOIN cliente c ON c.id = n.cliente_id WHERE n.status = 'emitida' "
                         "ORDER BY COALESCE(n.emitida_em, n.prevista_em)"):
        n = dict(r)
        grupos.setdefault((n["cliente_id"], n["valor_centavos"], n["ambiente"], _norm(n["descricao"])), []).append(n)
    for notas in grupos.values():
        if len(notas) < 2:
            continue
        quando = [datetime.fromisoformat((n["emitida_em"] or n["prevista_em"])[:19]) for n in notas]
        por_dia: dict = {}
        for n, q in zip(notas, quando, strict=True):
            por_dia.setdefault(q.date(), []).append(n)
        rotulo = lambda ns: ", ".join(f"#{n['id']} (nº {n['numero_nfse']})" for n in ns)  # noqa: E731
        mesmo_dia = [ns for ns in por_dia.values() if len(ns) > 1]
        for ns in mesmo_dia:
            achados.append(_achado("duplicidade", "erro", f"Possível nota em duplicidade: {ns[0]['cliente']}",
                                   f"Notas {rotulo(ns)}: mesmo cliente, mesmo valor ({util.fmt_valor(ns[0]['valor_centavos'])}) e descrição, "
                                   "emitidas no mesmo dia. Se for engano, cancele a repetida.", ns[-1]["id"]))
        proximas = [(a, b) for (a, qa), (b, qb) in zip(zip(notas, quando, strict=True), list(zip(notas, quando, strict=True))[1:], strict=False)
                    if qa.date() != qb.date() and (qb - qa).days < 7 and not (a["agendamento_id"] and a["agendamento_id"] == b["agendamento_id"])]
        if proximas:
            ids = sorted({n["id"] for par in proximas for n in par})
            ns = [n for n in notas if n["id"] in ids]
            achados.append(_achado("duplicidade", "aviso", f"Notas muito parecidas: {ns[0]['cliente']}",
                                   f"Notas {rotulo(ns)}: mesmo cliente, valor ({util.fmt_valor(ns[0]['valor_centavos'])}) e descrição, "
                                   "emitidas com menos de 7 dias de diferença.", ns[-1]["id"]))
    return achados


def situacao(con: sqlite3.Connection) -> list[dict]:
    achados = []
    agora = util.agora()
    for n in con.execute("SELECT n.*, c.nome AS cliente FROM nota n JOIN cliente c ON c.id = n.cliente_id "
                         "WHERE n.status IN ('verificar','atrasada','rejeitada','emitindo','a_conferir')"):
        quando = util.fmt_data_hora(n["prevista_em"])
        if n["status"] == "verificar":
            achados.append(_achado("verificar", "erro", f"Nota #{n['id']} aguardando verificação ({n['cliente']})",
                                   "Não se sabe se a Sefin autorizou. Resolva antes de emitir de novo.", n["id"]))
        elif n["status"] == "atrasada":
            achados.append(_achado("atrasada", "erro", f"Nota #{n['id']} atrasada ({n['cliente']})",
                                   f"Era para sair em {quando} e não saiu.", n["id"]))
        elif n["status"] == "rejeitada":
            achados.append(_achado("rejeitada", "aviso", f"Nota #{n['id']} com erro ({n['cliente']})", (n["mensagem_erro"] or "")[:300], n["id"]))
        elif n["status"] == "emitindo":
            parada = datetime.fromisoformat(n["prevista_em"]) < agora - timedelta(minutes=15)
            if parada:
                achados.append(_achado("emitindo", "erro", f"Nota #{n['id']} presa em \"Emitindo\" ({n['cliente']})",
                                       "O sistema pode ter parado no meio da emissão.", n["id"]))
        elif n["status"] == "a_conferir":
            if datetime.fromisoformat(n["prevista_em"]) < agora + timedelta(days=1):
                achados.append(_achado("a_conferir", "aviso", f"Nota #{n['id']} sem conferência ({n['cliente']})",
                                       f"Sai em {quando} e ainda não foi aprovada: sem aprovação ela não é emitida.", n["id"]))
    return achados


def entregas_e_arquivos(con: sqlite3.Connection) -> list[dict]:
    achados = []
    cfg = db.obter_config(con)
    for n in con.execute("SELECT n.*, c.nome AS cliente FROM nota n JOIN cliente c ON c.id = n.cliente_id "
                         "WHERE n.status IN ('emitida','cancelada')"):
        rot = f"Nota #{n['id']} (nº {n['numero_nfse']}, {n['cliente']})"
        if not n["xml_nfse"]:
            achados.append(_achado("sem_xml", "erro", f"{rot} sem XML guardado", "Sem o XML não é possível gerar o PDF.", n["id"]))
        if cfg["salvar_em_pasta"]:
            if n["pasta_erro"]:
                achados.append(_achado("pasta", "aviso", f"{rot}: falha ao salvar na pasta", n["pasta_erro"], n["id"]))
            elif not n["pdf_path"]:
                achados.append(_achado("pasta", "aviso", f"{rot}: arquivos ainda não salvos na pasta", "", n["id"]))
            elif not Path(n["pdf_path"]).exists() or not Path(n["xml_path"] or "").exists():
                achados.append(_achado("arquivo_sumiu", "aviso", f"{rot}: arquivo não encontrado na pasta",
                                       "O PDF/XML não está mais onde foi salvo (pasta apagada ou disco novo?). Use \"Entregar de novo\".", n["id"]))
        if cfg["enviar_por_email"] and (n["email_erro"] or not n["email_enviado_em"]):
            achados.append(_achado("email", "aviso", f"{rot}: e-mail não enviado", n["email_erro"] or "Ainda não enviado.", n["id"]))
    return achados


def cadastro_e_valores(con: sqlite3.Connection) -> list[dict]:
    achados = []
    for c in con.execute("SELECT * FROM cliente"):
        if not util.documento_valido(c["documento"]) and con.execute("SELECT 1 FROM nota WHERE cliente_id = ?", (c["id"],)).fetchone():
            achados.append(_achado("cliente_doc", "erro", f"Cliente com CPF/CNPJ inválido: {c['nome']}", util.fmt_documento(c["documento"])))
    # valor muito acima do habitual do cliente
    for c in con.execute("SELECT DISTINCT cliente_id FROM nota WHERE status = 'emitida'"):
        vals = [r for r in con.execute("SELECT id, valor_centavos, numero_nfse FROM nota WHERE cliente_id = ? AND status = 'emitida' "
                                       "ORDER BY id", (c["cliente_id"],))]
        if len(vals) >= 4:
            med = statistics.median(v["valor_centavos"] for v in vals[:-1])
            ult = vals[-1]
            if med and ult["valor_centavos"] > 3 * med:
                achados.append(_achado("valor_atipico", "aviso", f"Valor muito acima do habitual (nota #{ult['id']})",
                                       f"{util.fmt_valor(ult['valor_centavos'])} contra mediana de {util.fmt_valor(int(med))} das notas anteriores deste cliente.", ult["id"]))
    return achados


def agendamentos_sem_nota(con: sqlite3.Connection) -> list[dict]:
    """Agendamento mensal ativo sem nenhuma nota (emitida/pendente) num mês completo desde que foi criado."""
    achados = []
    hoje = util.agora().date()
    for a in con.execute("SELECT * FROM agendamento WHERE ativo = 1 AND frequencia = 'mensal'"):
        criado = datetime.fromisoformat(a["criado_em"]).date()
        y, m = criado.year, criado.month
        while (y, m) < (hoje.year, hoje.month):
            if (y, m) > (criado.year, criado.month):   # mês de criação é parcial: não cobra
                ym = f"{y:04d}-{m:02d}"
                tem = con.execute("SELECT status FROM nota WHERE agendamento_id = ? AND substr(prevista_em,1,7) = ?", (a["id"], ym)).fetchall()
                if not tem:
                    achados.append(_achado("sem_nota_mes", "aviso", f"Sem nota de \"{a['nome']}\" em {m:02d}/{y}",
                                           "O agendamento estava ativo mas nenhuma nota foi gerada nesse mês."))
                elif all(t["status"] == "pulada" for t in tem):
                    achados.append(_achado("pulada", "info", f"Nota de \"{a['nome']}\" pulada em {m:02d}/{y}", "Foi descartada de propósito."))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return achados


def ambiente_misto(con: sqlite3.Connection) -> list[dict]:
    cfg = db.obter_config(con)
    achados = []
    if cfg["ambiente"] == "producao":
        n = con.execute("SELECT COUNT(*) FROM nota WHERE ambiente = 'homologacao' AND status IN ('emitida','cancelada')").fetchone()[0]
        if n:
            achados.append(_achado("teste", "info", f"{n} nota(s) de teste (homologação) no sistema",
                                   "Não entram no faturamento de produção. São só notas de teste, sem validade jurídica."))
    return achados


def auditar(con: sqlite3.Connection) -> list[dict]:
    achados = []
    for etapa in (situacao, duplicidades, numeracao, entregas_e_arquivos, cadastro_e_valores, agendamentos_sem_nota, ambiente_misto):
        achados += etapa(con)
    ordem = {"erro": 0, "aviso": 1, "info": 2}
    return sorted(achados, key=lambda a: (ordem[a["severidade"]], a["tipo"]))


def resumo(achados: list[dict]) -> dict:
    return {s: sum(1 for a in achados if a["severidade"] == s) for s in SEVERIDADES}
