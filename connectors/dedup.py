"""Regra de não sobrescrita (docs/padrao-nomenclatura.md):

- Não existe arquivo com esse nome -> grava normalmente ("novo").
- Existe e o conteúdo é idêntico (mesmo hash) -> não duplica ("existente").
- Existe mas o conteúdo é diferente -> não sobrescreve; grava com sufixo
  "_v2", "_v3"... e sinaliza para conferência manual ("nova_versao").

Comparação por hash de conteúdo, não só pelo nome do arquivo — dois PDFs do
mesmo período podem ter o mesmo nome mas conteúdo diferente se o extrato foi
retificado pelo banco entre duas execuções.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


def hash_conteudo(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


@dataclass(frozen=True)
class ResolucaoNome:
    nome_final: str
    status: str  # "novo" | "existente" | "nova_versao"


def resolver_nome(nome_base: str, conteudo: bytes, existentes: dict[str, bytes]) -> ResolucaoNome:
    """`existentes` mapeia nome_do_arquivo_ja_salvo -> conteúdo (bytes) —
    tipicamente a listagem já baixada da pasta de destino (ex: no Drive)."""
    if nome_base not in existentes:
        return ResolucaoNome(nome_final=nome_base, status="novo")

    if hash_conteudo(existentes[nome_base]) == hash_conteudo(conteudo):
        return ResolucaoNome(nome_final=nome_base, status="existente")

    stem, _, ext = nome_base.rpartition(".")
    versao = 2
    while True:
        candidato = f"{stem}_v{versao}.{ext}"
        if candidato not in existentes:
            return ResolucaoNome(nome_final=candidato, status="nova_versao")
        if hash_conteudo(existentes[candidato]) == hash_conteudo(conteudo):
            return ResolucaoNome(nome_final=candidato, status="existente")
        versao += 1
