from datetime import date

from nfse.prestadas import canceladas, linhas, notas_validas

C3S = "47553447000151"


def nfse(chave, numero, dh, valor, ret="1", iss="50.00", tomador="11111111000111", emit=C3S):
    xml = (f'<NFSe><infNFSe><nNFSe>{numero}</nNFSe><cStat>100</cStat><emit><CNPJ>{emit}</CNPJ></emit>'
           f'<DPS><infDPS><dhEmi>{dh}</dhEmi><toma><CNPJ>{tomador}</CNPJ><xNome>CLIENTE &amp; CIA</xNome></toma>'
           f'<vServ>{valor}</vServ><tpRetISSQN>{ret}</tpRetISSQN></infDPS></DPS><vISSQN>{iss}</vISSQN></infNFSe></NFSe>')
    return {"TipoDocumento": "NFSE", "ChaveAcesso": chave, "xml": xml}


def evento(chave, tipo):
    return {"TipoDocumento": "EVENTO", "ChaveAcesso": "x", "xml": f"<evento><chNFSe>{chave}</chNFSe><{tipo}><xDesc>d</xDesc></{tipo}></evento>"}


DOCS = [
    nfse("A", 10, "2026-09-03T10:00:00-03:00", "1000.00", ret="2", iss="50.00"),
    nfse("B", 11, "2026-09-04T10:00:00-03:00", "500.00"),
    nfse("C", 12, "2026-09-05T10:00:00-03:00", "700.00"),
    nfse("D", 13, "2026-10-01T10:00:00-03:00", "800.00"),
    nfse("E", 14, "2026-09-06T10:00:00-03:00", "900.00", emit="99999999000199"),  # C3S é tomadora
    evento("B", "e101101"),   # cancelada
    evento("C", "e105102"),   # substituída
]


def test_so_validas_prestadas_do_mes():
    assert [n.numero for n in notas_validas(DOCS, 2026, 9)] == [10]
    assert canceladas(DOCS) == {"B", "C"}


def test_linha_do_iss_retido_vem_logo_abaixo():
    contas = {"11111111000111": {"conta": 50001, "nome": "Cliente & Cia"}}
    ls = linhas(notas_validas(DOCS, 2026, 9), contas)
    assert ls[0] == (date(2026, 9, 3), 10, 1000.0, "CLIENTE & CIA", "PREST. SERV. CONF. NFSE 10 CLIENTE CLIENTE & CIA", 50001, 861)
    assert ls[1][2:] == (50.0, "CLIENTE & CIA", "ISS RETIDO SERV. PREST. CONF. NFSE 10 CLIENTE CLIENTE & CIA", 1393, 50001)


def test_cliente_sem_conta_fica_em_branco():
    ls = linhas(notas_validas(DOCS, 2026, 9), {})
    assert ls[0][5] is None and ls[1][6] is None
