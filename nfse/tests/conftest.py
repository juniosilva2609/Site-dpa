import datetime as dt
import sys
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app, db  # noqa: E402

CNPJ_JL = "60441511000170"
CPF_OK = "52998224725"  # CPF válido de teste
CNPJ_CLIENTE = "21641059000139"  # DPA (do PDF modelo)
SENHA_CERT = "senha-teste"


def gerar_pfx(caminho: Path, cnpj: str = CNPJ_JL, dias: int = 365) -> None:
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"JL TRANSPORTES EXECUTIVOS LTDA:{cnpj}")])
    agora = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chave.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(agora - dt.timedelta(days=1))
            .not_valid_after(agora + dt.timedelta(days=dias)).sign(chave, hashes.SHA256()))
    caminho.write_bytes(pkcs12.serialize_key_and_certificates(
        b"teste", chave, cert, None, serialization.BestAvailableEncryption(SENHA_CERT.encode())))


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("NFSE_DATA_DIR", str(tmp_path / "dados"))
    monkeypatch.setenv("NFSE_SAIDA_DIR", str(tmp_path / "saida"))
    monkeypatch.setenv("NFSE_DEV", "1")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    pfx = tmp_path / "cert.pfx"
    gerar_pfx(pfx)
    monkeypatch.setenv("NFSE_CERT_PATH", str(pfx))
    monkeypatch.setenv("NFSE_CERT_SENHA", SENHA_CERT)
    return tmp_path


@pytest.fixture
def con(tmp_path):
    c = db.conectar(tmp_path / "t.db")
    db.migrar(c)
    return c


@pytest.fixture
def cliente_id(con):
    cur = con.execute("INSERT INTO cliente (nome, documento, email, logradouro, numero, bairro, cep, codigo_municipio) "
                      "VALUES ('DISTRIBUIDORA PERES & ARAUJO LTDA', ?, 'x@y.com', 'ANTONIO GERMANO', '688', 'PALMARES', "
                      "'32430090', '3129806')", (CNPJ_CLIENTE,))
    return cur.lastrowid


def criar_nota(con, cliente_id, status="aprovada", prevista=None, valor=50000, descricao="Serviço de transfer prestado\nItinerário:\nBarreiro x Lafaiete - R$500,00", **extra):
    from app import util
    prevista = prevista or util.agora().strftime("%Y-%m-%d %H:%M")
    cur = con.execute("INSERT INTO nota (cliente_id, prevista_em, descricao, valor_centavos, status, conferido_por) VALUES (?,?,?,?,?,?)",
                      (cliente_id, prevista, descricao, valor, status, "teste" if status == "aprovada" else None))
    for k, v in extra.items():
        con.execute(f"UPDATE nota SET {k} = ? WHERE id = ?", (v, cur.lastrowid))
    return cur.lastrowid


def nfse_falsa(xml_dps_assinado: str, numero: int = 481, cnpj: str = CNPJ_JL) -> str:
    """Simula o XML devolvido pela Sefin: <NFSe><infNFSe> embrulhando a DPS enviada."""
    dps = etree.fromstring(xml_dps_assinado.encode("utf-8"))
    ns = "http://www.sped.fazenda.gov.br/nfse"
    chave = f"3106200{2}{cnpj}{'00001'}{numero:013d}{'8750580997'}"[:50].ljust(50, "0")
    nfse = etree.Element(f"{{{ns}}}NFSe", nsmap={None: ns}, versao="1.01")
    inf = etree.SubElement(nfse, f"{{{ns}}}infNFSe", Id=f"NFS{chave}")
    for tag, texto in [("xLocEmi", "Belo Horizonte"), ("xLocPrestacao", "Belo Horizonte"), ("nNFSe", str(numero)),
                       ("xLocIncid", "Belo Horizonte"), ("xTribNac", "Outros serviços de transporte de natureza municipal."),
                       ("ambGer", "2"), ("tpEmis", "1"), ("cStat", "100"), ("dhProc", "2026-10-05T09:00:10-03:00")]:
        etree.SubElement(inf, f"{{{ns}}}{tag}").text = texto
    emit = etree.SubElement(inf, f"{{{ns}}}emit")
    etree.SubElement(emit, f"{{{ns}}}CNPJ").text = cnpj
    etree.SubElement(emit, f"{{{ns}}}xNome").text = "JL TRANSPORTES EXECUTIVOS LTDA"
    end = etree.SubElement(emit, f"{{{ns}}}enderNac")
    for tag, texto in [("xLgr", "RUA SAO PAULO"), ("nro", "818"), ("xBairro", "CENTRO"), ("cMun", "3106200"),
                       ("CEP", "30170131"), ("UF", "MG")]:
        etree.SubElement(end, f"{{{ns}}}{tag}").text = texto
    valores = etree.SubElement(inf, f"{{{ns}}}valores")
    vserv = dps.find(".//{%s}vServ" % ns).text
    etree.SubElement(valores, f"{{{ns}}}vLiq").text = vserv
    inf.append(dps)
    return etree.tostring(nfse, xml_declaration=True, encoding="UTF-8").decode()


@pytest.fixture
def app(tmp_path):
    return create_app(db_path=str(tmp_path / "app.db"), iniciar_agendador=False)
