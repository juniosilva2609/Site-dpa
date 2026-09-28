"""Nome de arquivo padronizado (docs/padrao-nomenclatura.md):

    EMPRESA_BANCO_CONTA_COMPETENCIA_TIPO.ext
"""

from __future__ import annotations

from datetime import date

_EXTENSAO = {"pdf": "pdf", "ofx": "ofx", "xlsx": "xlsx"}
_SUFIXO_TIPO = {"pdf": "PDF", "ofx": "OFX", "xlsx": "EXCEL"}


def competencia(inicio: date) -> str:
    """`MM-AAAA-Q1` (período dia 01-15) ou `MM-AAAA-Q2` (dia 16-fim do mês).

    O arquivo é arquivado no mês/quinzena a que o período pertence, não no
    dia em que o download foi feito (docs/padrao-nomenclatura.md).
    """
    quinzena = "Q1" if inicio.day == 1 else "Q2"
    return f"{inicio.month:02d}-{inicio.year}-{quinzena}"


def montar_nome(empresa: dict, banco: dict, inicio: date, fim: date, tipo: str) -> str:
    empresa_codigo = empresa["id"].upper()
    banco_codigo = banco["codigo_padrao_nome"]
    conta = "".join(ch for ch in banco["conta"] if ch.isdigit())
    return (
        f"{empresa_codigo}_{banco_codigo}_{conta}_{competencia(inicio)}"
        f"_{_SUFIXO_TIPO[tipo]}.{_EXTENSAO[tipo]}"
    )
