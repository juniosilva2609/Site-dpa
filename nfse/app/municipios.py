# -*- coding: utf-8 -*-
"""Cidade/UF <-> código IBGE (tabela oficial embutida em fiscal/municipios_ibge.json)."""

import json
import unicodedata
from functools import lru_cache
from pathlib import Path

_ARQ = Path(__file__).parent / "fiscal" / "municipios_ibge.json"


def _norm(texto: str) -> str:
    sem = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(sem.lower().replace("'", " ").split())


@lru_cache(maxsize=1)
def _tabela() -> dict[str, tuple[str, str]]:
    bruto = json.loads(_ARQ.read_text(encoding="utf-8"))
    return {cod: tuple(v.split("|")) for cod, v in bruto.items()}


@lru_cache(maxsize=1)
def _indice() -> dict[tuple[str, str], str]:
    return {(_norm(nome), uf): cod for cod, (nome, uf) in _tabela().items()}


def codigo(cidade: str, uf: str) -> str | None:
    return _indice().get((_norm(cidade), (uf or "").strip().upper()))


def nome_uf(cod: str | None) -> tuple[str, str] | None:
    return _tabela().get(cod or "")


def rotulo(cod: str | None) -> str:
    achado = nome_uf(cod)
    return f"{achado[0]} - {achado[1]}" if achado else (cod or "")


UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
       "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"]
