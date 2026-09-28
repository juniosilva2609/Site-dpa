from datetime import date

from connectors.nomenclatura import competencia, montar_nome


def test_competencia_q1():
    assert competencia(date(2026, 9, 1)) == "09-2026-Q1"


def test_competencia_q2():
    assert competencia(date(2026, 8, 16)) == "08-2026-Q2"


def test_montar_nome():
    empresa = {"id": "dpa"}
    banco = {"codigo_padrao_nome": "INTER", "conta": "3620284-3"}
    nome = montar_nome(empresa, banco, date(2026, 9, 1), date(2026, 9, 15), "pdf")
    assert nome == "DPA_INTER_36202843_09-2026-Q1_PDF.pdf"
