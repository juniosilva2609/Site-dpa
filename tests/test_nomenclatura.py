from datetime import date

from connectors.nomenclatura import competencia, montar_nome


def test_competencia_q1():
    assert competencia(date(2026, 9, 1), date(2026, 9, 15)) == "09-2026-Q1"


def test_competencia_q2():
    assert competencia(date(2026, 8, 16), date(2026, 8, 31)) == "08-2026-Q2"


def test_competencia_mes_inteiro():
    assert competencia(date(2026, 9, 1), date(2026, 9, 30)) == "09-2026"
    assert competencia(date(2028, 2, 1), date(2028, 2, 29)) == "02-2028"


def test_montar_nome():
    empresa = {"id": "dpa"}
    banco = {"codigo_padrao_nome": "INTER", "conta": "3620284-3"}
    nome = montar_nome(empresa, banco, date(2026, 9, 1), date(2026, 9, 15), "pdf")
    assert nome == "DPA_INTER_36202843_09-2026-Q1_PDF.pdf"


def test_montar_nome_mensal():
    empresa = {"id": "licitprint"}
    banco = {"codigo_padrao_nome": "C6", "conta": "1234567-8"}
    nome = montar_nome(empresa, banco, date(2026, 9, 1), date(2026, 9, 30), "xlsx")
    assert nome == "LICITPRINT_C6_12345678_09-2026_EXCEL.xlsx"
