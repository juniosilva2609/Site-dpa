import re

import pytest
import signxml
from lxml import etree

from app import util
from app.fiscal import assinatura, dps

from .conftest import CNPJ_CLIENTE, CPF_OK


def test_parse_valor():
    assert util.parse_valor("1.500,00") == 150000
    assert util.parse_valor("500") == 50000
    assert util.parse_valor("R$ 12,5") == 1250
    assert util.parse_valor("1500.50") == 150050
    for ruim in ("", "abc", "0", "-3"):
        with pytest.raises(ValueError):
            util.parse_valor(ruim)


def test_fmt_valor():
    assert util.fmt_valor(150050) == "R$ 1.500,50"
    assert util.fmt_valor(50000) == "R$ 500,00"


def test_documentos():
    assert util.cpf_valido(CPF_OK) and not util.cpf_valido("11111111111") and not util.cpf_valido("52998224724")
    assert util.cnpj_valido(CNPJ_CLIENTE) and util.cnpj_valido("60.441.511/0001-70")
    assert not util.cnpj_valido("60441511000171")


def test_tamanho_descricao_conta_espacos_repetidos_uma_vez():
    assert util.tamanho_descricao("a   b\n\nc") == 5


CFG = {"cnpj": "60441511000170", "codigo_municipio_ibge": "3106200", "serie_dps": "00001", "ambiente": "homologacao",
       "regime_tributario": "simples", "codigo_servico_lc116": "160201", "codigo_tributacao_municipal": "004",
       "codigo_nbs": "", "aliquota_iss": None, "telefone": "31971254546", "email": "contato@jlexecutivo.com"}
CLIENTE = {"nome": "DISTRIBUIDORA PERES & ARAUJO LTDA", "documento": CNPJ_CLIENTE, "logradouro": "ANTONIO GERMANO",
           "numero": "688", "bairro": "PALMARES", "cep": "32430090", "codigo_municipio": "3129806", "complemento": ""}
NOTA = {"descricao": "Serviço <de> transfer & cia\nItinerário: A x B", "valor_centavos": 50000, "competencia": None}


def test_id_dps_tem_45_caracteres():
    id_dps = dps.montar_id_dps(CFG, 329)
    assert id_dps == "DPS3106200" + "2" + "60441511000170" + "00001" + "000000000000329" and len(id_dps) == 45


def test_dps_xml_regras_aprendidas():
    xml, id_dps = dps.montar_dps_xml(NOTA, CLIENTE, CFG, 7)
    raiz = etree.fromstring(xml)
    texto = xml.decode()
    assert raiz.tag == "{http://www.sped.fazenda.gov.br/nfse}DPS"
    assert "<IM>" not in texto                                 # E0120
    prest = raiz.find(".//{*}prest")
    assert prest.find("{*}xNome") is None                      # E0121
    assert "<regApTribSN>1</regApTribSN>" in texto             # E0166
    assert re.search(r"<dhEmi>[^<]*-0[23]:00</dhEmi>", texto)  # fuso explícito (E0008)
    assert "<pAliq>" not in texto and "<opSimpNac>3</opSimpNac>" in texto
    assert "<cTribNac>160201</cTribNac>" in texto and "<cTribMun>004</cTribMun>" in texto
    assert "<vServ>500.00</vServ>" in texto and "<tpEmit>1</tpEmit>" in texto and "<nDPS>7</nDPS>" in texto
    assert "Serviço &lt;de&gt; transfer &amp; cia" in texto    # escape
    assert "<CNPJ>21641059000139</CNPJ>" in texto and "<end>" in texto
    assert 'Id="%s"' % id_dps in texto
    # a ordem dos filhos de cServ segue o schema: cTribNac, cTribMun, xDescServ
    assert texto.index("cTribNac") < texto.index("cTribMun") < texto.index("xDescServ")


def test_dps_sem_endereco_quando_incompleto_e_cpf():
    cli = {**CLIENTE, "documento": CPF_OK, "bairro": ""}
    xml, _ = dps.montar_dps_xml(NOTA, cli, CFG, 1)
    assert b"<end>" not in xml and f"<CPF>{CPF_OK}</CPF>".encode() in xml


def test_dps_documento_invalido():
    with pytest.raises(ValueError):
        dps.montar_dps_xml(NOTA, {**CLIENTE, "documento": "123"}, CFG, 1)


def test_dps_nao_optante_usa_indtottrib():
    xml, _ = dps.montar_dps_xml(NOTA, CLIENTE, {**CFG, "regime_tributario": "normal", "aliquota_iss": 2}, 1)
    assert b"<indTotTrib>0</indTotTrib>" in xml and b"<pAliq>2.00</pAliq>" in xml and b"regApTribSN" not in xml


def test_assinatura_sem_prefixo_e_valida(ambiente):
    xml, id_dps = dps.montar_dps_xml(NOTA, CLIENTE, CFG, 1)
    assinado = assinatura.assinar_xml(xml, id_dps)
    assert b"ds:" not in assinado and b"<Signature" in assinado          # E1228
    from app.fiscal import certificado
    cert_pem, _ = certificado.carregar()
    # `excise_empty_xmlns_declarations`: contorno conhecido de um bug do lxml na CANONICALIZAÇÃO feita pelo
    # verificador do signxml (acrescenta xmlns="" em subárvores); a assinatura em si segue a especificação.
    verificador = signxml.XMLVerifier()
    verificador.excise_empty_xmlns_declarations = True
    resultado = verificador.verify(etree.fromstring(assinado), x509_cert=cert_pem, id_attribute="Id")
    assert resultado.signed_xml is not None
    adulterado = assinado.replace(b"<vServ>500.00</vServ>", b"<vServ>900.00</vServ>")
    with pytest.raises(signxml.exceptions.InvalidDigest):
        verificador.verify(etree.fromstring(adulterado), x509_cert=cert_pem, id_attribute="Id")


def test_evento_cancelamento_xml():
    xml, id_ev = dps.montar_evento_cancelamento_xml(CFG, "3" * 50, "1", "Erro na emissão da nota")
    assert id_ev == "PRE" + "3" * 50 + "101101" and b"<cMotivo>1</cMotivo>" in xml
    with pytest.raises(ValueError):
        dps.montar_evento_cancelamento_xml(CFG, "3" * 50, "7", "x")
