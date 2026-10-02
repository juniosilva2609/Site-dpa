# -*- coding: utf-8 -*-
"""Emissão, verificação e cancelamento de NFS-e. É aqui que mora a segurança contra nota duplicada.

Regras (herdadas do sistema anterior, validado em produção):
- Só emite quem passou na conferência; ela roda DE NOVO no instante da emissão.
- Uma emissão por vez (trava no banco) e reserva atômica da nota (status 'emitindo').
- O contador de nDPS é consumido ANTES do envio; se a Sefin rejeitar de forma clara, ele volta
  (a rejeição não consome número). Se a resposta for ambígua (queda de rede, timeout, HTTP 5xx), a
  nota vai para 'verificar' com o número reservado: o sistema NUNCA reemite sozinho, e a reemissão
  manual reusa o MESMO Id de DPS -- a Sefin recusa Id repetido, então não nasce nota em duplicidade.
- Falha de entrega (pasta/e-mail) nunca afeta a nota emitida."""

import sqlite3
from datetime import datetime

from lxml import etree

from . import alertas, conferencia, db, saida, util
from .fiscal import api_nfse, assinatura, certificado, dps, xmlseguro

_NS = {"n": "http://www.sped.fazenda.gov.br/nfse"}
TRAVA = "emissao"
_AVISO_AMBIGUA = (" ATENÇÃO: não é certo que esta DPS tenha sido rejeitada. NÃO emita de novo por fora: use "
                  "\"Conferir na Sefin\" nesta tela ou confira no Portal Nacional (www.nfse.gov.br) pelo CNPJ.")


# ---------------------------------------------------------------- leitura do XML da NFS-e
def dados_nfse(xml_texto: str) -> dict:
    """Extrai chave (50 dígitos), número, CNPJ do prestador e nDPS do XML oficial. Levanta ValueError se não
    parecer uma NFS-e autorizada."""
    try:
        raiz = xmlseguro.parse(xml_texto)
    except etree.XMLSyntaxError as e:
        raise ValueError(f"XML inválido: {e}") from e  # ValueError (DOCTYPE) já vem com mensagem própria
    inf = raiz if etree.QName(raiz).localname == "infNFSe" else raiz.find("n:infNFSe", namespaces=_NS)
    if inf is None:
        raise ValueError("O XML não tem o elemento infNFSe -- não parece uma NFS-e autorizada.")
    chave = (inf.get("Id") or "").removeprefix("NFS")
    if not (len(chave) == 50 and chave.isdigit()):
        raise ValueError("Não encontrei uma chave de acesso válida (50 dígitos) no XML.")

    def texto(caminho):
        no = inf.find(caminho, namespaces=_NS)
        return no.text.strip() if no is not None and no.text else None

    return {"chave": chave, "numero": texto("n:nNFSe"), "cnpj_prestador": texto("n:emit/n:CNPJ"),
            "ndps": texto("n:DPS/n:infDPS/n:nDPS"), "tp_amb": texto("n:DPS/n:infDPS/n:tpAmb")}


# ---------------------------------------------------------------- utilidades de estado
def _set_status(con, nota_id, status, mensagem=None, **extras):
    campos = {"status": status, "mensagem_erro": mensagem, **extras}
    sql = ", ".join(f"{k} = ?" for k in campos)
    con.execute(f"UPDATE nota SET {sql} WHERE id = ?", (*campos.values(), nota_id))


def _devolver_numero(con, numero: int) -> None:
    """Rejeição clara: o número volta ao contador (só se ninguém pegou o seguinte)."""
    con.execute("UPDATE configuracao SET proximo_numero_dps = ? WHERE id = 1 AND proximo_numero_dps = ?",
                (numero, numero + 1))


def _concluir(con, nota_id, xml_nfse: str, info: dict, ambiente: str, usuario: str | None) -> None:
    con.execute("UPDATE nota SET status = 'emitida', xml_nfse = ?, chave_acesso = ?, numero_nfse = ?, "
                "emitida_em = datetime('now','localtime'), mensagem_erro = NULL, ambiente = ? WHERE id = ?",
                (xml_nfse, info["chave"], info["numero"], ambiente, nota_id))
    alertas.resolver_da_nota(con, nota_id)
    db.registrar_historico(con, usuario, nota_id, "emitida", f"NFS-e nº {info['numero']} ({ambiente})")


def _entregar_sem_falhar(con, nota_id) -> None:
    try:
        saida.entregar(con, nota_id)
    except Exception as e:  # noqa: BLE001
        con.execute("UPDATE nota SET pasta_erro = ? WHERE id = ?", (f"Falha inesperada na entrega: {e}"[:500], nota_id))


# ---------------------------------------------------------------- emissão
def emitir(con: sqlite3.Connection, nota_id: int, usuario: str | None = None, manual: bool = False) -> dict:
    """Emite a nota. `manual=True` (clique do usuário) também aceita 'a_conferir'/'rejeitada'/'atrasada';
    a rotina automática só emite 'aprovada'. Devolve {ok, status, erro}."""
    permitidos = ("aprovada", "a_conferir", "rejeitada", "atrasada", "verificar") if manual else ("aprovada",)
    if not db.adquirir_trava(con, TRAVA, 300):
        return {"ok": False, "status": None, "erro": "Já existe uma emissão em andamento; tente em instantes.",
                "ocupado": True}
    try:
        return _emitir_com_trava(con, nota_id, usuario, permitidos)
    finally:
        db.liberar_trava(con, TRAVA)


def _emitir_com_trava(con, nota_id, usuario, permitidos) -> dict:
    # Reserva atômica: só uma chamada consegue mudar o status para 'emitindo'.
    marcas = ",".join("?" * len(permitidos))
    with db.transacao(con):
        anterior = con.execute("SELECT status FROM nota WHERE id = ?", (nota_id,)).fetchone()
        cur = con.execute(f"UPDATE nota SET status = 'emitindo', tentativas = tentativas + 1 "
                          f"WHERE id = ? AND status IN ({marcas})", (nota_id, *permitidos))
        reservou = cur.rowcount == 1
    if not reservou:
        return {"ok": False, "status": anterior["status"] if anterior else None,
                "erro": "Esta nota não está em um estado que permita emitir."}
    status_anterior = anterior["status"]

    problemas = conferencia.erros(conferencia.conferir(con, nota_id))
    if problemas:
        _set_status(con, nota_id, "a_conferir", "Conferência falhou: " + " ".join(problemas),
                    conferido_por=None, conferido_em=None)
        alertas.abrir(con, f"conferencia-{nota_id}", f"Nota #{nota_id} não foi emitida: " + " ".join(problemas),
                      "erro", nota_id)
        db.registrar_historico(con, usuario, nota_id, "bloqueada", " ".join(problemas))
        return {"ok": False, "status": "a_conferir", "erro": " ".join(problemas)}
    alertas.resolver(con, f"conferencia-{nota_id}")

    nota = dict(con.execute("SELECT * FROM nota WHERE id = ?", (nota_id,)).fetchone())
    cliente = dict(con.execute("SELECT * FROM cliente WHERE id = ?", (nota["cliente_id"],)).fetchone())
    cfg = db.obter_config(con)

    # Número da DPS: reusa o reservado (nota em 'verificar'), senão pega o próximo e já consome.
    with db.transacao(con):
        numero = nota["numero_dps"] if status_anterior == "verificar" and nota["numero_dps"] else None
        if numero is None:
            numero = con.execute("SELECT proximo_numero_dps FROM configuracao WHERE id = 1").fetchone()[0]
            con.execute("UPDATE configuracao SET proximo_numero_dps = ? WHERE id = 1", (numero + 1,))
        reaproveitado = status_anterior == "verificar" and nota["numero_dps"] == numero
    try:
        xml_bytes, id_dps = dps.montar_dps_xml(nota, cliente, cfg, numero)
        if status_anterior == "verificar" and nota["id_dps"] and nota["id_dps"] != id_dps:
            raise ValueError("Configuração (série/município/CNPJ) mudou desde a primeira tentativa; "
                             "confira no Portal Nacional antes de emitir de novo.")
        xml_assinado = assinatura.assinar_xml(xml_bytes, id_dps)
    except (ValueError, certificado.CertificadoIndisponivel) as e:
        if not reaproveitado:
            _devolver_numero(con, numero)
        _set_status(con, nota_id, "rejeitada" if status_anterior != "verificar" else "verificar", str(e),
                    numero_dps=None if not reaproveitado else numero)
        alertas.abrir(con, f"falha-{nota_id}", f"Nota #{nota_id}: {e}", "erro", nota_id)
        return {"ok": False, "status": "rejeitada", "erro": str(e)}

    # Grava o que vai ser enviado ANTES de enviar: se o processo cair no meio, a nota fica 'emitindo'
    # com número/Id registrados e a manutenção a manda para 'verificar'.
    con.execute("UPDATE nota SET numero_dps = ?, id_dps = ?, xml_dps = ?, ambiente = ? WHERE id = ?",
                (numero, id_dps, xml_assinado.decode("utf-8"), cfg["ambiente"], nota_id))
    db.registrar_historico(con, usuario, nota_id, "enviando", f"DPS {id_dps} ({cfg['ambiente']})")

    try:
        resultado = api_nfse.emitir_nfse(xml_assinado, cfg["ambiente"])
    except certificado.CertificadoIndisponivel as e:  # nem chegou a sair
        if not reaproveitado:
            _devolver_numero(con, numero)
        status = "verificar" if reaproveitado else "rejeitada"
        _set_status(con, nota_id, status, str(e), numero_dps=numero if reaproveitado else None)
        alertas.abrir(con, f"falha-{nota_id}", f"Nota #{nota_id}: {e}", "erro", nota_id)
        return {"ok": False, "status": status, "erro": str(e)}
    except api_nfse.ErroApiNfse as e:
        return _tratar_erro_api(con, nota_id, numero, id_dps, cfg["ambiente"], e, usuario, reaproveitado)

    xml_resposta = resultado.get("xml_resposta") or ""
    try:
        info = dados_nfse(xml_resposta)
    except ValueError:
        # A Sefin respondeu OK mas sem uma NFS-e legível: pode ter autorizado. Não afirmar nada.
        msg = "A Sefin respondeu, mas sem o XML da NFS-e." + _AVISO_AMBIGUA
        _set_status(con, nota_id, "verificar", msg, numero_dps=numero)
        alertas.abrir(con, f"verificar-{nota_id}", f"Nota #{nota_id}: {msg}", "erro", nota_id)
        return {"ok": False, "status": "verificar", "erro": msg}
    _concluir(con, nota_id, xml_resposta, info, cfg["ambiente"], usuario)
    _entregar_sem_falhar(con, nota_id)
    return {"ok": True, "status": "emitida", "numero_nfse": info["numero"], "chave": info["chave"]}


def _tratar_erro_api(con, nota_id, numero, id_dps, ambiente, erro, usuario, reaproveitado) -> dict:
    texto = str(erro)
    if erro.ambigua:
        msg = (texto + _AVISO_AMBIGUA)[:1500]
        _set_status(con, nota_id, "verificar", msg, numero_dps=numero)  # número fica reservado
        alertas.abrir(con, f"verificar-{nota_id}", f"Nota #{nota_id} precisa de verificação: {texto}", "erro", nota_id)
        db.registrar_historico(con, usuario, nota_id, "ambigua", texto)
        return {"ok": False, "status": "verificar", "erro": msg}
    if reaproveitado:
        # Reenvio de uma DPS que já tinha sido enviada: se a Sefin recusa (ex.: duplicidade), a nota original
        # pode existir -- continua em 'verificar' para o usuário anexar o XML do Portal Nacional.
        msg = (texto + " (Reenvio recusado pela Sefin. Se a mensagem indicar duplicidade, a nota JÁ existe: "
               "baixe o XML no Portal Nacional e anexe aqui.)")[:1500]
        _set_status(con, nota_id, "verificar", msg, numero_dps=numero)
        alertas.abrir(con, f"verificar-{nota_id}", f"Nota #{nota_id}: {texto}", "erro", nota_id)
        return {"ok": False, "status": "verificar", "erro": msg}
    _devolver_numero(con, numero)
    _set_status(con, nota_id, "rejeitada", texto[:1500], numero_dps=None)
    alertas.abrir(con, f"falha-{nota_id}", f"Nota #{nota_id} rejeitada pela Sefin: {texto}", "erro", nota_id)
    db.registrar_historico(con, usuario, nota_id, "rejeitada", texto)
    return {"ok": False, "status": "rejeitada", "erro": texto}


# ---------------------------------------------------------------- notas em 'verificar'
def consultar_na_sefin(con: sqlite3.Connection, nota_id: int, usuario: str | None = None) -> dict:
    """Para nota em 'verificar': pergunta à Sefin se já existe NFS-e para o Id da DPS. Se existir, baixa o XML e
    conclui a nota. Se não for possível saber, diz isso (e nada é alterado)."""
    nota = dict(con.execute("SELECT * FROM nota WHERE id = ?", (nota_id,)).fetchone())
    if nota["status"] != "verificar" or not nota["id_dps"]:
        return {"ok": False, "erro": "Esta nota não está aguardando verificação."}
    try:
        chave = api_nfse.consultar_dps(nota["id_dps"], nota["ambiente"])
        if not chave:
            return {"ok": False, "encontrada": False,
                    "erro": "A Sefin não retornou nota para esta DPS. Se você também não a vê no Portal Nacional, "
                            "pode usar \"Tentar emitir de novo\" (mesmo número: não duplica)."}
        xml = api_nfse.baixar_nfse(chave, nota["ambiente"])
        info = dados_nfse(xml or "")
    except (api_nfse.ErroApiNfse, certificado.CertificadoIndisponivel, ValueError) as e:
        return {"ok": False, "erro": f"Não consegui consultar a Sefin: {e}"}
    _concluir(con, nota_id, xml, info, nota["ambiente"], usuario)
    _entregar_sem_falhar(con, nota_id)
    return {"ok": True, "numero_nfse": info["numero"]}


def anexar_xml(con: sqlite3.Connection, nota_id: int, xml_texto: str, usuario: str | None = None) -> dict:
    """Para nota em 'verificar': conclui com o XML oficial baixado do Portal Nacional pelo usuário."""
    nota = dict(con.execute("SELECT * FROM nota WHERE id = ?", (nota_id,)).fetchone())
    if nota["status"] != "verificar":
        return {"ok": False, "erro": "Esta nota não está aguardando verificação."}
    cfg = db.obter_config(con)
    try:
        info = dados_nfse(xml_texto)
    except ValueError as e:
        return {"ok": False, "erro": str(e)}
    if info["cnpj_prestador"] != util.so_digitos(cfg["cnpj"]):
        return {"ok": False, "erro": "O XML é de outro prestador (CNPJ diferente)."}
    if nota["numero_dps"] is not None and info["ndps"] and int(info["ndps"]) != int(nota["numero_dps"]):
        return {"ok": False, "erro": f"O XML é da DPS nº {info['ndps']}, mas esta nota usou a DPS "
                                      f"nº {nota['numero_dps']}."}
    _concluir(con, nota_id, xml_texto, info, nota["ambiente"] or ("producao" if info["tp_amb"] == "1" else "homologacao"),
              usuario)
    _entregar_sem_falhar(con, nota_id)
    return {"ok": True, "numero_nfse": info["numero"]}


# ---------------------------------------------------------------- cancelamento
def cancelar(con: sqlite3.Connection, nota_id: int, motivo_codigo: str, motivo_texto: str,
             usuario: str | None = None) -> dict:
    nota = dict(con.execute("SELECT * FROM nota WHERE id = ?", (nota_id,)).fetchone())
    if nota["status"] != "emitida" or not nota["chave_acesso"]:
        return {"ok": False, "erro": "Só é possível cancelar uma NFS-e emitida (com chave de acesso)."}
    if len((motivo_texto or "").strip()) < 15:
        return {"ok": False, "erro": "Descreva o motivo do cancelamento (mínimo de 15 caracteres)."}
    cfg = db.obter_config(con)
    ambiente = nota["ambiente"] or cfg["ambiente"]
    try:
        xml, id_evento = dps.montar_evento_cancelamento_xml({**cfg, "ambiente": ambiente}, nota["chave_acesso"],
                                                            motivo_codigo, motivo_texto.strip())
        assinado = assinatura.assinar_xml(xml, id_evento)
        api_nfse.enviar_evento(assinado, nota["chave_acesso"], ambiente)
    except (ValueError, certificado.CertificadoIndisponivel) as e:
        return {"ok": False, "erro": str(e)}
    except api_nfse.ErroApiNfse as e:
        texto = str(e) + (_AVISO_AMBIGUA.replace("emita de novo por fora", "cancele de novo por fora")
                          if e.ambigua else "")
        return {"ok": False, "erro": texto}
    rotulo = dps.MOTIVOS_CANCELAMENTO[motivo_codigo]
    con.execute("UPDATE nota SET status = 'cancelada', cancelada_em = datetime('now','localtime'), "
                "motivo_cancelamento = ?, pdf_path = NULL, xml_path = NULL, email_enviado_em = NULL, "
                "pasta_erro = NULL, email_erro = NULL, entrega_tentativas = 0 WHERE id = ?",
                (f"[{rotulo}] {motivo_texto.strip()}", nota_id))
    db.registrar_historico(con, usuario, nota_id, "cancelada", f"[{rotulo}] {motivo_texto.strip()}")
    _entregar_sem_falhar(con, nota_id)
    return {"ok": True}


# ---------------------------------------------------------------- aprovação (conferência humana)
def aprovar(con: sqlite3.Connection, nota_id: int, usuario: str) -> dict:
    nota = con.execute("SELECT status FROM nota WHERE id = ?", (nota_id,)).fetchone()
    if nota is None or nota["status"] not in ("a_conferir", "atrasada", "rejeitada"):
        return {"ok": False, "erro": "Esta nota não pode ser aprovada agora."}
    problemas = conferencia.erros(conferencia.conferir(con, nota_id))
    if problemas:
        return {"ok": False, "erro": "Corrija antes de aprovar: " + " ".join(problemas)}
    con.execute("UPDATE nota SET status = 'aprovada', conferido_por = ?, conferido_em = ?, mensagem_erro = NULL "
                "WHERE id = ?", (usuario, util.agora().strftime("%Y-%m-%d %H:%M"), nota_id))
    alertas.resolver(con, f"conferir-{nota_id}")
    alertas.resolver(con, f"conferencia-{nota_id}")
    alertas.resolver(con, f"falha-{nota_id}")
    alertas.resolver(con, f"atrasada-{nota_id}")
    db.registrar_historico(con, usuario, nota_id, "aprovada", "Conferida e aprovada")
    return {"ok": True}


def desaprovar(con: sqlite3.Connection, nota_id: int, usuario: str) -> bool:
    cur = con.execute("UPDATE nota SET status = 'a_conferir', conferido_por = NULL, conferido_em = NULL "
                      "WHERE id = ? AND status = 'aprovada'", (nota_id,))
    if cur.rowcount:
        db.registrar_historico(con, usuario, nota_id, "desaprovada", "Voltou para conferência")
    return bool(cur.rowcount)


def pular(con: sqlite3.Connection, nota_id: int, usuario: str) -> bool:
    cur = con.execute("UPDATE nota SET status = 'pulada' WHERE id = ? AND status IN "
                      "('a_conferir','aprovada','atrasada','rejeitada')", (nota_id,))
    if cur.rowcount:
        alertas.resolver_da_nota(con, nota_id)
        db.registrar_historico(con, usuario, nota_id, "pulada", "Não será emitida")
    return bool(cur.rowcount)


def momento(texto: str) -> datetime:
    return datetime.fromisoformat(texto)
