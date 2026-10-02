# -*- coding: utf-8 -*-
"""Consultas gerenciais: faturamento por período/cliente/agendamento, situação das notas e comparativos.

Regras: faturamento = notas com status 'emitida' (cancelada não conta; aparece à parte), pela DATA DE EMISSÃO.
Notas de homologação (teste) só entram quando o filtro de ambiente pede."""

import calendar
import sqlite3
from datetime import date, timedelta

from . import db, util

AMBIENTES = {"producao": "Produção (notas reais)", "homologacao": "Testes (homologação)", "todos": "Todos"}
PRESETS = {
    "mes": "Este mês", "mes_anterior": "Mês anterior", "trimestre": "Últimos 3 meses", "ano": "Este ano",
    "ano_anterior": "Ano anterior", "12m": "Últimos 12 meses", "tudo": "Todo o período", "custom": "Personalizado",
}
CORES_MAX = 5   # fatias com cor própria; o resto vira "Outros" (nunca se gera uma 7ª cor)


def _fim_mes(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _meses_atras(d: date, n: int) -> date:
    m = d.month - 1 - n
    return date(d.year + m // 12, m % 12 + 1, 1)


def periodo(preset: str | None, de: str | None = None, ate: str | None = None, hoje: date | None = None):
    """-> (inicio, fim, rotulo, preset_efetivo). Datas inclusivas."""
    hoje = hoje or util.agora().date()
    p = preset if preset in PRESETS else "ano"
    if p == "mes":
        i, f = hoje.replace(day=1), _fim_mes(hoje)
    elif p == "mes_anterior":
        i = _meses_atras(hoje, 1)
        f = _fim_mes(i)
    elif p == "trimestre":
        i, f = _meses_atras(hoje, 2), _fim_mes(hoje)
    elif p == "ano":
        i, f = date(hoje.year, 1, 1), date(hoje.year, 12, 31)
    elif p == "ano_anterior":
        i, f = date(hoje.year - 1, 1, 1), date(hoje.year - 1, 12, 31)
    elif p == "12m":
        i, f = _meses_atras(hoje, 11), _fim_mes(hoje)
    elif p == "tudo":
        i, f = date(2000, 1, 1), date(2100, 12, 31)
    else:
        try:
            i, f = date.fromisoformat(de or ""), date.fromisoformat(ate or "")
            if f < i:
                i, f = f, i
        except ValueError:
            i, f, p = date(hoje.year, 1, 1), date(hoje.year, 12, 31), "ano"
    rotulo = PRESETS[p] if p not in ("custom", "tudo") else (f"{util.fmt_data(i.isoformat())} a {util.fmt_data(f.isoformat())}"
                                                              if p == "custom" else "Todo o período")
    return i, f, rotulo, p


def periodo_anterior(i: date, f: date) -> tuple[date, date]:
    dias = (f - i).days + 1
    return i - timedelta(days=dias), i - timedelta(days=1)


def ambiente_padrao(con: sqlite3.Connection, escolhido: str | None) -> str:
    if escolhido in AMBIENTES:
        return escolhido
    return db.obter_config(con)["ambiente"]


def _where_amb(ambiente: str) -> tuple[str, list]:
    if ambiente == "todos":
        return "", []
    return " AND COALESCE(n.ambiente, 'producao') = ?", [ambiente]


def notas_emitidas(con, ini: date, fim: date, ambiente: str, cliente_id: int | None = None, status=("emitida",)) -> list[dict]:
    amb, args = _where_amb(ambiente)
    marcas = ",".join("?" * len(status))
    sql = (f"SELECT n.*, c.nome AS cliente, c.documento AS cliente_doc, a.nome AS agendamento FROM nota n "
           f"JOIN cliente c ON c.id = n.cliente_id LEFT JOIN agendamento a ON a.id = n.agendamento_id "
           f"WHERE n.status IN ({marcas}) AND substr(COALESCE(n.emitida_em, n.prevista_em),1,10) BETWEEN ? AND ?{amb}")
    params = [*status, ini.isoformat(), fim.isoformat(), *args]
    if cliente_id:
        sql += " AND n.cliente_id = ?"
        params.append(cliente_id)
    sql += " ORDER BY COALESCE(n.emitida_em, n.prevista_em), n.id"
    return [dict(r) for r in con.execute(sql, params)]


def _top(itens: list[tuple[str, int, int]], maximo: int = CORES_MAX) -> list[dict]:
    """[(rotulo, centavos, qtd)] -> até `maximo` fatias + 'Outros', com percentual."""
    itens = sorted((i for i in itens if i[1] > 0), key=lambda x: -x[1])
    total = sum(i[1] for i in itens) or 1
    fatias = [{"rotulo": r, "valor": v, "qtd": q} for r, v, q in itens[:maximo]]
    resto = itens[maximo:]
    if resto:
        fatias.append({"rotulo": "Outros", "valor": sum(i[1] for i in resto), "qtd": sum(i[2] for i in resto),
                       "outros": True, "n_outros": len(resto)})
    for f in fatias:
        f["pct"] = f["valor"] * 100 / total
    return fatias


def faturamento(con: sqlite3.Connection, ini: date, fim: date, ambiente: str, cliente_id: int | None = None) -> dict:
    notas = notas_emitidas(con, ini, fim, ambiente, cliente_id)
    cancel = notas_emitidas(con, ini, fim, ambiente, cliente_id, status=("cancelada",))
    total = sum(n["valor_centavos"] for n in notas)
    qtd = len(notas)
    por_mes: dict[str, list[int]] = {}
    por_cliente: dict[str, list[int]] = {}
    por_agend: dict[str, list[int]] = {}
    for n in notas:
        ym = (n["emitida_em"] or n["prevista_em"])[:7]
        for dic, chave in ((por_mes, ym), (por_cliente, n["cliente"]), (por_agend, n["agendamento"] or "Notas avulsas")):
            acc = dic.setdefault(chave, [0, 0])
            acc[0] += n["valor_centavos"]
            acc[1] += 1
    # meses sem nota aparecem com zero (até 36 colunas); "tudo" começa no primeiro mês com nota
    meses = []
    a_ini = ini if ini.year > 2001 else (date.fromisoformat(min(por_mes) + "-01") if por_mes else None)
    if a_ini is not None:
        a_fim = fim if fim.year < 2100 else (date.fromisoformat(max(por_mes) + "-01") if por_mes else a_ini)
        y, m = a_ini.year, a_ini.month
        while (y, m) <= (a_fim.year, a_fim.month):
            meses.append(f"{y:04d}-{m:02d}")
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        meses = meses[-36:]
    mensal = [{"mes": ym, "valor": por_mes.get(ym, [0, 0])[0], "qtd": por_mes.get(ym, [0, 0])[1]} for ym in meses]
    clientes = [(k, v[0], v[1]) for k, v in por_cliente.items()]
    ranking = sorted(({"cliente": k, "valor": v[0], "qtd": v[1], "ticket": v[0] // v[1],
                       "pct": v[0] * 100 / (total or 1)} for k, v in por_cliente.items()), key=lambda x: -x["valor"])
    ant_i, ant_f = periodo_anterior(ini, fim) if ini.year > 2001 else (None, None)
    anterior = sum(n["valor_centavos"] for n in notas_emitidas(con, ant_i, ant_f, ambiente, cliente_id)) if ant_i else None
    variacao = None
    if anterior:
        variacao = (total - anterior) * 100 / anterior
    return {
        "total": total, "qtd": qtd, "ticket": total // qtd if qtd else 0, "n_clientes": len(por_cliente),
        "cancelado_valor": sum(n["valor_centavos"] for n in cancel), "cancelado_qtd": len(cancel),
        "mensal": mensal, "clientes": _top(clientes), "ranking": ranking,
        "agendamentos": _top([(k, v[0], v[1]) for k, v in por_agend.items()]),
        "anterior": anterior, "variacao": variacao, "notas": notas,
        "maior": max(notas, key=lambda n: n["valor_centavos"]) if notas else None,
    }


def situacao_notas(con: sqlite3.Connection, ini: date, fim: date, ambiente: str) -> list[dict]:
    """Quantas notas em cada situação (pela data prevista), agrupadas em 4 classes + puladas."""
    amb, args = _where_amb(ambiente)
    classes = {"Emitidas": ("emitida",), "Aguardando emissão": ("a_conferir", "aprovada", "emitindo"),
               "Com problema": ("rejeitada", "verificar", "atrasada"), "Canceladas / puladas": ("cancelada", "pulada")}
    saida = []
    for rotulo, sts in classes.items():
        marcas = ",".join("?" * len(sts))
        r = con.execute(f"SELECT COUNT(*) q, COALESCE(SUM(valor_centavos),0) v FROM nota n WHERE n.status IN ({marcas}) "
                        f"AND substr(n.prevista_em,1,10) BETWEEN ? AND ?{amb}", [*sts, ini.isoformat(), fim.isoformat(), *args]).fetchone()
        saida.append({"rotulo": rotulo, "qtd": r["q"], "valor": r["v"]})
    total = sum(s["qtd"] for s in saida) or 1
    for s in saida:
        s["pct"] = s["qtd"] * 100 / total
    return saida


def clientes_do_filtro(con) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT id, nome FROM cliente ORDER BY nome")]
