# -*- coding: utf-8 -*-
"""Funções pequenas compartilhadas: dinheiro, CPF/CNPJ, datas em horário de Brasília."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
LIMITE_DESCRICAO = 1297  # acima disso o DANFSe do Portal Nacional corta a descrição com "..."
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]


def agora() -> datetime:
    """Agora, em Brasília, sem fuso (naive) -- é como a agenda guarda 'AAAA-MM-DD HH:MM'."""
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)


def so_digitos(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")


def parse_valor(texto: str) -> int:
    """'1.500,00' / '1500,5' / '1500.50' -> centavos. Levanta ValueError se inválido."""
    t = (texto or "").strip().replace("R$", "").replace(" ", "")
    if not t:
        raise ValueError("Informe o valor.")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(t)
    except InvalidOperation as e:
        raise ValueError(f"Valor inválido: {texto!r}.") from e
    if valor <= 0:
        raise ValueError("O valor precisa ser maior que zero.")
    return int((valor * 100).quantize(Decimal("1")))


def fmt_valor(centavos: int | None) -> str:
    if centavos is None:
        return "-"
    reais, cent = divmod(int(centavos), 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{cent:02d}"


def valor_para_campo(centavos: int | None) -> str:
    if centavos is None:
        return ""
    reais, cent = divmod(int(centavos), 100)
    return f"{reais},{cent:02d}"


def cpf_valido(cpf: str) -> bool:
    d = so_digitos(cpf)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if int(d[n]) != (soma * 10 % 11) % 10:
            return False
    return True


def cnpj_valido(cnpj: str) -> bool:
    d = so_digitos(cnpj)
    if len(d) != 14 or d == d[0] * 14:
        return False
    for n, pesos in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]), (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
        soma = sum(int(d[i]) * pesos[i] for i in range(n))
        resto = soma % 11
        if int(d[n]) != (0 if resto < 2 else 11 - resto):
            return False
    return True


def documento_valido(doc: str) -> bool:
    d = so_digitos(doc)
    return cpf_valido(d) if len(d) == 11 else cnpj_valido(d) if len(d) == 14 else False


def fmt_documento(doc: str | None) -> str:
    d = so_digitos(doc)
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return doc or ""


def tamanho_descricao(descricao: str | None) -> int:
    """Conta como o DANFSe conta: espaços/quebras repetidos valem um só."""
    return len(" ".join((descricao or "").split()))


def fmt_data_hora(texto: str | None) -> str:
    """'2026-10-05 09:00' -> '05/10/2026 09:00'."""
    if not texto:
        return "-"
    try:
        return datetime.fromisoformat(texto[:16]).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return texto


def fmt_data(texto: str | None) -> str:
    if not texto:
        return "-"
    try:
        return datetime.fromisoformat(texto[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return texto
