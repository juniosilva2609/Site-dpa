# -*- coding: utf-8 -*-
"""Leitura segura de XML vindo de fora (arquivo anexado pelo usuário): sem DTD/entidades (bloqueia XXE e
"billion laughs"), sem rede, sem árvores gigantes."""

from lxml import etree

_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False,
                          huge_tree=False, remove_pis=True)


def parse(texto: str):
    """Levanta etree.XMLSyntaxError se inválido, ou ValueError se o documento declara DOCTYPE/ENTITY."""
    dados = texto.encode("utf-8")
    cabeca = dados.upper()
    if b"<!DOCTYPE" in cabeca or b"<!ENTITY" in cabeca:
        raise ValueError("XML recusado: não pode conter DOCTYPE/ENTITY (uma NFS-e oficial não tem).")
    return etree.fromstring(dados, _PARSER)
