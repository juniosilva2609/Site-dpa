"""Nome de arquivo padronizado (docs/padrao-nomenclatura.md):

    EMPRESA_BANCO_CONTA_COMPETENCIA_TIPO.ext
"""

from __future__ import annotations

import calendar
from datetime import date

_EXTENSAO = {"pdf": "pdf", "ofx": "ofx", "xlsx": "xlsx"}
_SUFIXO_TIPO = {"pdf": "PDF", "ofx": "OFX", "xlsx": "EXCEL"}


def ultimo_dia_do_mes(dia: date) -> date:
    return dia.replace(day=calendar.monthrange(dia.year, dia.month)[1])


def competencia(inicio: date, fim: date) -> str:
    """`MM-AAAA` (mês inteiro), `MM-AAAA-Q1` (dia 01-15) ou `MM-AAAA-Q2`
    (dia 16-fim do mês).

    O arquivo é arquivado no mês/quinzena a que o período pertence, não no
    dia em que o download foi feito (docs/padrao-nomenclatura.md).
    """
    mes_ano = f"{inicio.month:02d}-{inicio.year}"
    if inicio.day == 1 and fim == ultimo_dia_do_mes(inicio):
        return mes_ano
    quinzena = "Q1" if inicio.day == 1 else "Q2"
    return f"{mes_ano}-{quinzena}"


def montar_nome(empresa: dict, banco: dict, inicio: date, fim: date, tipo: str) -> str:
    empresa_codigo = empresa["id"].upper()
    banco_codigo = banco["codigo_padrao_nome"]
    conta = "".join(ch for ch in banco["conta"] if ch.isdigit())
    return (
        f"{empresa_codigo}_{banco_codigo}_{conta}_{competencia(inicio, fim)}"
        f"_{_SUFIXO_TIPO[tipo]}.{_EXTENSAO[tipo]}"
    )
