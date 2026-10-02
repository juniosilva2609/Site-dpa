# -*- coding: utf-8 -*-
"""Cliente HTTP (mTLS com o e-CNPJ) da Sefin Nacional / Emissor Público Nacional NFS-e.

URLs e formato confirmados em produção no sistema anterior (LicitPrint):

    produção    https://sefin.nfse.gov.br/sefinnacional        (minúsculo!)
    homologação https://sefin.producaorestrita.nfse.gov.br/SefinNacional

Emissão:  POST {base}/nfse  com JSON {"dpsXmlGZipB64": base64(gzip(xml_assinado))}
          (XML cru dá 415). Sucesso devolve {"nfseXmlGZipB64": ...}.
Evento:   POST {base}/nfse/{chave}/eventos  com {"pedidoRegistroEventoXmlGZipB64": ...}.

Falhas se dividem em duas famílias, e a diferença é CRÍTICA para não duplicar nota:
  * rejeição clara (HTTP 4xx com mensagem da Sefin): a DPS não virou nota;
  * falha AMBÍGUA (queda de conexão, timeout, HTTP 5xx): a Sefin pode ter autorizado a nota
    antes da conexão cair. `ErroApiNfse.ambigua` marca esse caso -- quem chama NUNCA reemite
    sem antes conferir (ver `consultar_dps`)."""

import base64
import contextlib
import gzip
import json

import requests

from . import certificado

BASES = {
    "producao": "https://sefin.nfse.gov.br/sefinnacional",
    "homologacao": "https://sefin.producaorestrita.nfse.gov.br/SefinNacional",
}
# Só para o teste de convênio/diagnóstico (a base Sefin é a única usada para emitir).
_ORIGENS_DIAGNOSTICO = {
    "producao": [BASES["producao"], "https://adn.nfse.gov.br", "https://adn.nfse.gov.br/contribuintes"],
    "homologacao": [BASES["homologacao"], "https://adn.producaorestrita.nfse.gov.br",
                    "https://adn.producaorestrita.nfse.gov.br/contribuintes"],
}


class ErroApiNfse(Exception):
    def __init__(self, mensagem: str, status_code: int | None = None, corpo: str | None = None,
                 ambigua: bool = False):
        super().__init__(mensagem)
        self.status_code = status_code
        self.corpo = corpo
        self.ambigua = ambigua


def _mensagem_erro(resp) -> str:
    """A Sefin responde erro em JSON, ex. {"erro":[{"codigo":"E0120","descricao":"..."}]} ou
    {"message": "..."}; devolve só o texto útil."""
    try:
        corpo = resp.json()
    except ValueError:
        return resp.text[:500]
    if isinstance(corpo, dict):
        itens = corpo.get("erro") or corpo.get("erros")
        if isinstance(itens, list) and itens:
            textos = []
            for item in itens:
                if isinstance(item, dict):
                    cod = item.get("codigo") or item.get("Codigo") or ""
                    desc = item.get("descricao") or item.get("Descricao") or item.get("mensagem") or ""
                    textos.append(f"{cod} {desc}".strip())
                else:
                    textos.append(str(item))
            return " | ".join(textos)[:800]
        return str(corpo.get("message") or corpo.get("mensagem") or corpo.get("erro") or corpo)[:500]
    return str(corpo)[:500]


def _motivo(erro: Exception) -> str:
    texto = str(erro)
    for marcador in ("Errno", "Remote end closed", "reset by peer", "timed out", "Name or service",
                     "Connection refused", "handshake", "certificate", "SSL", "alert"):
        pos = texto.find(marcador)
        if pos >= 0:
            return texto[max(0, pos - 20):pos + 140].strip(" (:'\"")
    return texto[:160]


@contextlib.contextmanager
def _sessao_mtls():
    with certificado.arquivos_temporarios_para_requests() as (cert_path, key_path):
        with requests.Session() as sessao:
            sessao.cert = (cert_path, key_path)
            yield sessao


def _requisitar(metodo: str, ambiente: str, caminho: str, **kwargs) -> requests.Response:
    """Uma requisição à base Sefin. Levanta ErroApiNfse (ambigua=True em falha de rede/5xx)."""
    url = f"{BASES[ambiente]}{caminho}"
    timeout = kwargs.pop("timeout", 60)
    try:
        with _sessao_mtls() as sessao:
            resp = sessao.request(metodo, url, timeout=timeout, **kwargs)
    except requests.exceptions.SSLError as e:
        raise ErroApiNfse(f"Falha SSL/certificado ao falar com a Sefin Nacional ({_motivo(e)}). Confira se o "
                          "certificado está válido (não vencido) e se a senha está certa.",
                          ambigua=True) from e
    except requests.exceptions.RequestException as e:
        raise ErroApiNfse(f"Falha de conexão com a Sefin Nacional ({e.__class__.__name__}: {_motivo(e)}).",
                          ambigua=True) from e
    if resp.status_code >= 500:
        raise ErroApiNfse(f"A Sefin Nacional respondeu erro {resp.status_code}: {_mensagem_erro(resp)}",
                          resp.status_code, resp.text, ambigua=True)
    if resp.status_code >= 400:
        raise ErroApiNfse(_mensagem_erro(resp), resp.status_code, resp.text)
    return resp


def _enviar_xml_gzip_json(ambiente: str, caminho: str, campo_json: str, xml_assinado: bytes) -> dict:
    corpo = json.dumps({campo_json: base64.b64encode(gzip.compress(xml_assinado)).decode("ascii")})
    resp = _requisitar("POST", ambiente, caminho, data=corpo.encode("utf-8"),
                       headers={"Content-Type": "application/json;charset=utf-8"})
    try:
        resultado = resp.json()
    except ValueError:
        return {"status_code": resp.status_code, "xml_resposta": None, "resposta_bruta": resp.text[:2000]}
    xml_resposta = None
    if isinstance(resultado, dict) and resultado.get("nfseXmlGZipB64"):
        xml_resposta = gzip.decompress(base64.b64decode(resultado["nfseXmlGZipB64"])).decode("utf-8")
    return {"status_code": resp.status_code, "xml_resposta": xml_resposta, "resposta_bruta": resultado}


def emitir_nfse(dps_assinada_xml: bytes, ambiente: str) -> dict:
    return _enviar_xml_gzip_json(ambiente, "/nfse", "dpsXmlGZipB64", dps_assinada_xml)


def enviar_evento(evento_assinado_xml: bytes, chave_nfse: str, ambiente: str) -> dict:
    return _enviar_xml_gzip_json(ambiente, f"/nfse/{chave_nfse}/eventos",
                                 "pedidoRegistroEventoXmlGZipB64", evento_assinado_xml)


def consultar_dps(id_dps: str, ambiente: str) -> str | None:
    """Pergunta à Sefin se já existe NFS-e para este Id de DPS (GET {base}/dps/{id}) e devolve a
    chave de acesso, ou None se não existir (404). Usado para resolver uma falha ambígua sem
    arriscar duplicidade. ATENÇÃO: rota da API pública da Sefin Nacional ainda NÃO exercitada
    em produção por este sistema -- por isso o resultado só é usado para CONFIRMAR uma nota;
    na dúvida o sistema deixa a nota em "Verificar" e pede conferência humana."""
    try:
        resp = _requisitar("GET", ambiente, f"/dps/{id_dps}", timeout=30)
    except ErroApiNfse as e:
        if e.status_code == 404:
            return None
        raise
    try:
        corpo = resp.json()
    except ValueError:
        return None
    chave = corpo.get("chaveAcesso") if isinstance(corpo, dict) else None
    return chave if chave and len(str(chave)) == 50 else None


def baixar_nfse(chave: str, ambiente: str) -> str | None:
    """GET {base}/nfse/{chave} -> XML oficial da NFS-e (ou None)."""
    resp = _requisitar("GET", ambiente, f"/nfse/{chave}", timeout=30)
    try:
        corpo = resp.json()
    except ValueError:
        return None
    if isinstance(corpo, dict) and corpo.get("nfseXmlGZipB64"):
        return gzip.decompress(base64.b64decode(corpo["nfseXmlGZipB64"])).decode("utf-8")
    return None


def consultar_convenio_municipio(codigo_municipio_ibge: str, ambiente: str) -> dict:
    """GET .../parametros-municipais/{cMun}/convenio -- o município aderiu ao Sistema Nacional?"""
    sufixos = [f"/parametros-municipais/{codigo_municipio_ibge}/convenio",
               f"/parametros_municipais/{codigo_municipio_ibge}/convenio"]
    ultimo = None
    with _sessao_mtls() as sessao:
        for origem in _ORIGENS_DIAGNOSTICO[ambiente]:
            for sufixo in sufixos:
                try:
                    resp = sessao.get(f"{origem}{sufixo}", timeout=30)
                except requests.exceptions.RequestException as e:
                    ultimo = f"{origem}{sufixo}: falha de conexão ({_motivo(e)})"
                    continue
                if resp.status_code == 404:
                    ultimo = f"{origem}{sufixo}: 404"
                    continue
                if resp.status_code >= 400:
                    raise ErroApiNfse(f"{origem}{sufixo} respondeu {resp.status_code}: {_mensagem_erro(resp)}",
                                      resp.status_code, resp.text)
                return resp.json()
    raise ErroApiNfse(f"Não consegui consultar o convênio do município. Último resultado: {ultimo}")


def diagnosticar_conexao(ambiente: str) -> list[dict]:
    """Testa por etapas, SEM enviar DPS: DNS, TCP 443, TLS e HTTPS com o certificado (mTLS)."""
    import socket
    import ssl
    from urllib.parse import urlparse

    etapas = []

    def registrar(etapa, ok, detalhe):
        etapas.append({"etapa": etapa, "ok": ok, "detalhe": detalhe})

    base = BASES[ambiente]
    host = urlparse(base).hostname
    try:
        ips = sorted({i[4][0] for i in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)})
        registrar("DNS", True, ", ".join(ips))
    except OSError as e:
        registrar("DNS", False, str(e))
        return etapas
    try:
        with socket.create_connection((host, 443), timeout=10):
            registrar("Conexão TCP (porta 443)", True, "aberta")
    except OSError as e:
        registrar("Conexão TCP (porta 443)", False, str(e))
        return etapas
    try:
        with socket.create_connection((host, 443), timeout=10) as bruto:
            with ssl.create_default_context().wrap_socket(bruto, server_hostname=host) as seguro:
                registrar("TLS", True, seguro.version() or "ok")
    except (OSError, ssl.SSLError) as e:
        registrar("TLS", False, str(e)[:200])
    try:
        with _sessao_mtls() as sessao:
            resp = sessao.get(f"{base}/nfse", timeout=20)
        registrar("HTTPS com o certificado e-CNPJ", True,
                  f"respondeu HTTP {resp.status_code} (qualquer resposta HTTP = conexão funcionando)")
    except requests.exceptions.RequestException as e:
        registrar("HTTPS com o certificado e-CNPJ", False, f"{e.__class__.__name__}: {_motivo(e)}")
    except certificado.CertificadoIndisponivel as e:
        registrar("HTTPS com o certificado e-CNPJ", False, str(e))
    return etapas
