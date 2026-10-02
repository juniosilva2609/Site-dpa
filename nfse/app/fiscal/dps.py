# -*- coding: utf-8 -*-
r"""Monta o XML da DPS (Declaração de Prestação de Serviço, versão 1.01, Sistema Nacional NFS-e) e o
evento de cancelamento. Regras aprendidas com rejeições REAIS da Sefin Nacional no sistema anterior
(não repetir):

- NÃO enviar <IM> do prestador (E0120) nem <xNome> do prestador com tpEmit=1 (E0121).
- <regApTribSN>1 é obrigatório para optante do Simples (E0166).
- dhEmi com fuso America/Sao_Paulo explícito (container roda em UTC -> E0008).
- Nenhum prefixo de namespace em nada, inclusive no <Signature> (E1228).
- Sem <pAliq> quando o município é conveniado (a Sefin aplica a alíquota parametrizada).
- O prestador sempre emite a própria nota (tpEmit=1).
- <end> do tomador só quando TODOS os campos obrigatórios existem (nunca pela metade).
"""

import re
from datetime import datetime
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

_NS = "http://www.sped.fazenda.gov.br/nfse"
_TZ = ZoneInfo("America/Sao_Paulo")
VER_APLIC = "NfseAuto-1.0"
MOTIVOS_CANCELAMENTO = {"1": "Erro na Emissão", "2": "Serviço não Prestado", "9": "Outros"}


def _digitos(texto) -> str:
    return re.sub(r"\D", "", texto or "")


def _cnpj_prestador(config: dict) -> str:
    cnpj = _digitos(config.get("cnpj"))
    if len(cnpj) != 14:
        raise ValueError("Configuração: o CNPJ do prestador precisa ter 14 dígitos.")
    return cnpj


def montar_id_dps(config: dict, numero_dps: int) -> str:
    """'DPS' + cMun(7) + tpInsc(1: CNPJ=2) + CNPJ(14) + série(5) + nDPS(15)."""
    return (f"DPS{config['codigo_municipio_ibge']}2{_cnpj_prestador(config)}"
            f"{str(config['serie_dps']).zfill(5)}{str(numero_dps).zfill(15)}")


def _bloco_endereco_tomador(cliente: dict) -> str:
    campos = (cliente.get("logradouro"), cliente.get("numero"), cliente.get("bairro"),
              cliente.get("cep"), cliente.get("codigo_municipio"))
    if not all(campos):
        return ""
    logradouro, numero, bairro, cep, cod_mun = campos
    complemento = cliente.get("complemento")
    xcpl = f"<xCpl>{escape(complemento)}</xCpl>" if complemento else ""
    return (f"<end><endNac><cMun>{_digitos(cod_mun)}</cMun><CEP>{_digitos(cep)}</CEP></endNac>"
            f"<xLgr>{escape(logradouro)}</xLgr><nro>{escape(numero)}</nro>{xcpl}"
            f"<xBairro>{escape(bairro)}</xBairro></end>")


def _bloco_tributacao(config: dict) -> str:
    aliquota = config.get("aliquota_iss")
    p_aliq = f"<pAliq>{float(aliquota):.2f}</pAliq>" if aliquota and config["regime_tributario"] == "normal" else ""
    trib_mun = f"<tribMun><tribISSQN>1</tribISSQN><tpRetISSQN>1</tpRetISSQN>{p_aliq}</tribMun>"
    if config["regime_tributario"] == "simples":
        tot = "<totTrib><pTotTribSN>0.00</pTotTribSN></totTrib>"
    else:
        tot = "<totTrib><indTotTrib>0</indTotTrib></totTrib>"
    return trib_mun + tot


def montar_dps_xml(nota: dict, cliente: dict, config: dict, numero_dps: int) -> tuple[bytes, str]:
    """Devolve (xml_sem_assinatura, id_dps). `nota` traz descricao/valor_centavos/competencia."""
    id_dps = montar_id_dps(config, numero_dps)
    agora = datetime.now(_TZ)
    cnpj = _cnpj_prestador(config)
    simples = config["regime_tributario"] == "simples"

    doc = _digitos(cliente.get("documento"))
    if len(doc) == 14:
        tag_doc = f"<CNPJ>{doc}</CNPJ>"
    elif len(doc) == 11:
        tag_doc = f"<CPF>{doc}</CPF>"
    else:
        raise ValueError("O cliente não tem CPF/CNPJ válido -- obrigatório para emitir a NFS-e.")

    valor = nota["valor_centavos"] / 100
    c_trib_mun = (config.get("codigo_tributacao_municipal") or "").strip()
    fone = _digitos(config.get("telefone"))
    email = (config.get("email") or "").strip()

    xml = f'''<DPS xmlns="{_NS}" versao="1.01">
  <infDPS Id="{id_dps}">
    <tpAmb>{"1" if config["ambiente"] == "producao" else "2"}</tpAmb>
    <dhEmi>{agora.isoformat(timespec="seconds")}</dhEmi>
    <verAplic>{VER_APLIC}</verAplic>
    <serie>{int(config["serie_dps"])}</serie>
    <nDPS>{numero_dps}</nDPS>
    <dCompet>{nota.get("competencia") or agora.date().isoformat()}</dCompet>
    <tpEmit>1</tpEmit>
    <cLocEmi>{config["codigo_municipio_ibge"]}</cLocEmi>
    <prest>
      <CNPJ>{cnpj}</CNPJ>
      {f"<fone>{fone}</fone>" if fone else ""}
      {f"<email>{escape(email)}</email>" if email else ""}
      <regTrib>
        <opSimpNac>{"3" if simples else "1"}</opSimpNac>
        {"<regApTribSN>1</regApTribSN>" if simples else ""}
        <regEspTrib>0</regEspTrib>
      </regTrib>
    </prest>
    <toma>
      {tag_doc}
      <xNome>{escape(cliente["nome"][:300])}</xNome>
      {_bloco_endereco_tomador(cliente)}
    </toma>
    <serv>
      <locPrest>
        <cLocPrestacao>{config["codigo_municipio_ibge"]}</cLocPrestacao>
      </locPrest>
      <cServ>
        <cTribNac>{config["codigo_servico_lc116"]}</cTribNac>
        {f"<cTribMun>{escape(c_trib_mun)}</cTribMun>" if c_trib_mun else ""}
        <xDescServ>{escape(nota["descricao"])}</xDescServ>
        {f"<cNBS>{escape(config['codigo_nbs'])}</cNBS>" if config.get("codigo_nbs") else ""}
      </cServ>
    </serv>
    <valores>
      <vServPrest>
        <vServ>{valor:.2f}</vServ>
      </vServPrest>
      <trib>{_bloco_tributacao(config)}</trib>
    </valores>
  </infDPS>
</DPS>'''
    return xml.encode("utf-8"), id_dps


def montar_evento_cancelamento_xml(config: dict, chave_nfse: str, motivo_codigo: str, motivo_texto: str
                                   ) -> tuple[bytes, str]:
    """Evento e101101 (Cancelamento de NFS-e), assinado depois referenciando o Id do infPedReg."""
    if motivo_codigo not in MOTIVOS_CANCELAMENTO:
        raise ValueError(f"Motivo de cancelamento inválido: {motivo_codigo!r}.")
    id_evento = f"PRE{chave_nfse}101101"
    dh = datetime.now(_TZ).isoformat(timespec="seconds")
    xml = f'''<pedRegEvento xmlns="{_NS}" versao="1.01">
  <infPedReg Id="{id_evento}">
    <tpAmb>{"1" if config["ambiente"] == "producao" else "2"}</tpAmb>
    <verAplic>{VER_APLIC}</verAplic>
    <dhEvento>{dh}</dhEvento>
    <CNPJAutor>{_cnpj_prestador(config)}</CNPJAutor>
    <chNFSe>{chave_nfse}</chNFSe>
    <e101101>
      <xDesc>Cancelamento de NFS-e</xDesc>
      <cMotivo>{motivo_codigo}</cMotivo>
      <xMotivo>{escape(motivo_texto[:255])}</xMotivo>
    </e101101>
  </infPedReg>
</pedRegEvento>'''
    return xml.encode("utf-8"), id_evento
