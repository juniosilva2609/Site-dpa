# -*- coding: utf-8 -*-
"""Assina XML fiscal (DPS ou evento de NFS-e, como cancelamento) com o
certificado digital da LicitPrint (XML-DSig, assinatura embutida
referenciando o atributo Id do elemento raiz interno -- infDPS ou
infPedReg -- exigido pelo schema oficial, que importa
xmldsig-core-schema.xsd).

A Sefin Nacional rejeita QUALQUER elemento com prefixo de namespace no
XML (erro E1228 "Xml declarado com prefixo de namespace") -- inclusive
o próprio <Signature>, que o signxml por padrão prefixa como <ds:...>.
Setar `signer.namespaces = {None: signxml.namespaces.ds}` faz o signxml
declarar o namespace do XML-DSig como padrão (sem prefixo) só dentro do
bloco <Signature>, resolvendo isso sem mexer no resto do documento."""

import signxml
from lxml import etree
from signxml import XMLSigner
from signxml.algorithms import CanonicalizationMethod

from . import certificado


def assinar_xml(xml_bytes: bytes, id_referencia: str) -> bytes:
    cert_pem, chave_pem = certificado.carregar()
    raiz = etree.fromstring(xml_bytes)

    signer = XMLSigner(
        c14n_algorithm=CanonicalizationMethod.CANONICAL_XML_1_0,
    )
    signer.namespaces = {None: signxml.namespaces.ds}
    assinado = signer.sign(
        raiz, key=chave_pem, cert=cert_pem, reference_uri=f"#{id_referencia}", id_attribute="Id",
    )
    return etree.tostring(assinado, xml_declaration=True, encoding="UTF-8", standalone=False)
