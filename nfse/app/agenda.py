# -*- coding: utf-8 -*-
"""Recorrência: calcula as datas/horas de um agendamento e gera as notas "A conferir"."""

import calendar
import re
import sqlite3
from datetime import date, datetime, time, timedelta

from . import util

FORMATO = "%Y-%m-%d %H:%M"


def _hora(texto: str) -> time:
    h, m = texto.split(":")
    return time(int(h), int(m))


def ocorrencias(ag: dict, de: datetime, ate: datetime) -> list[datetime]:
    """Todas as ocorrências do agendamento com `de <= data <= ate` (horário de Brasília)."""
    hora = _hora(ag["hora"])
    resultado: list[datetime] = []
    if ag["frequencia"] == "unica":
        if ag.get("data_unica"):
            quando = datetime.combine(date.fromisoformat(ag["data_unica"]), hora)
            if de <= quando <= ate:
                resultado.append(quando)
    elif ag["frequencia"] == "semanal":
        dia = de.date()
        while dia <= ate.date():
            if dia.weekday() == ag["dia_semana"]:
                quando = datetime.combine(dia, hora)
                if de <= quando <= ate:
                    resultado.append(quando)
            dia += timedelta(days=1)
    elif ag["frequencia"] == "mensal":
        ano, mes = de.year, de.month
        while (ano, mes) <= (ate.year, ate.month):
            dia = min(ag["dia_mes"], calendar.monthrange(ano, mes)[1])
            quando = datetime.combine(date(ano, mes, dia), hora)
            if de <= quando <= ate:
                resultado.append(quando)
            ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return resultado


def proxima(ag: dict, a_partir_de: datetime | None = None) -> datetime | None:
    """Próxima ocorrência futura (para mostrar na tela)."""
    inicio = a_partir_de or util.agora()
    lista = ocorrencias(ag, inicio, inicio + timedelta(days=400))
    return lista[0] if lista else None


class _Seguro(dict):
    def __missing__(self, chave):
        return "{" + chave + "}"


def expandir_descricao(modelo: str, quando: datetime) -> str:
    """Troca {data} {mes} {ano} {mes_ano} {competencia} pelos valores da ocorrência. Chaves
    desconhecidas ficam como estão (aparecem na conferência), nunca quebram."""
    valores = _Seguro(
        data=quando.strftime("%d/%m/%Y"), mes=util.MESES[quando.month - 1], ano=str(quando.year),
        mes_ano=f"{util.MESES[quando.month - 1]}/{quando.year}", competencia=quando.strftime("%m/%Y"))
    return re.sub(r"\{(\w+)\}", lambda m: valores[m.group(1)], modelo)


def gerar_notas(con: sqlite3.Connection, agora: datetime | None = None) -> list[int]:
    """Cria as notas das ocorrências que já entraram na janela de antecedência. Idempotente (índice único
    agendamento+data). Nunca gera ocorrência anterior à criação do agendamento (sem backlog surpresa)."""
    from . import conferencia  # evita import circular

    agora = agora or util.agora()
    criadas = []
    for ag in con.execute("SELECT * FROM agendamento WHERE ativo = 1").fetchall():
        ag = dict(ag)
        criado = datetime.fromisoformat(ag["criado_em"])
        inicio = max(criado.replace(second=0), agora - timedelta(days=45))
        fim = agora + timedelta(days=ag["antecedencia_dias"])
        for quando in ocorrencias(ag, inicio, fim):
            prevista = quando.strftime(FORMATO)
            if con.execute("SELECT 1 FROM nota WHERE agendamento_id = ? AND prevista_em = ?",
                           (ag["id"], prevista)).fetchone():
                continue
            cur = con.execute(
                "INSERT INTO nota (agendamento_id, cliente_id, prevista_em, descricao, valor_centavos, status, "
                "criado_por) VALUES (?,?,?,?,?, 'a_conferir', 'agenda')",
                (ag["id"], ag["cliente_id"], prevista, expandir_descricao(ag["descricao"], quando),
                 ag["valor_centavos"]))
            nota_id = cur.lastrowid
            criadas.append(nota_id)
            from .db import registrar_historico
            registrar_historico(con, None, nota_id, "gerada", f"Agendamento: {ag['nome']}")
            tolerancia = timedelta(hours=conferencia.tolerancia_horas(con))
            if quando < agora - tolerancia:
                con.execute("UPDATE nota SET status = 'atrasada', mensagem_erro = ? WHERE id = ?",
                            ("O horário previsto já passou (o sistema estava desligado?). Confira e emita "
                             "manualmente se ainda fizer sentido.", nota_id))
            elif ag["auto_aprovar"] and not [p for p in conferencia.conferir(con, nota_id) if p["nivel"] == "erro"]:
                con.execute("UPDATE nota SET status = 'aprovada', conferido_por = 'automático', "
                            "conferido_em = ? WHERE id = ?", (agora.strftime(FORMATO), nota_id))
                registrar_historico(con, None, nota_id, "aprovada", "Aprovação automática (agendamento)")
    return criadas
