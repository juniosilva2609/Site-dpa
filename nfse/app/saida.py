# -*- coding: utf-8 -*-
"""Entrega dos arquivos de cada nota: grava PDF + XML na pasta indicada e/ou envia por e-mail.

A entrega NUNCA altera o status fiscal da nota nem bloqueia a emissão: falhas ficam registradas na
própria nota (`pasta_erro`, `email_erro`) e a rotina de manutenção tenta de novo."""

import os
import re
import smtplib
import sqlite3
import ssl
from email.message import EmailMessage
from pathlib import Path

from . import config, db, util
from .fiscal import danfse


def lista_emails(texto: str | None) -> list[str]:
    itens = [e.strip() for e in re.split(r"[,;\s]+", texto or "") if e.strip()]
    return [e for e in dict.fromkeys(itens) if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e)]


def limpar_nome(texto: str) -> str:
    texto = re.sub(r'[\\/:*?"<>|\r\n\t]', " ", texto)
    return re.sub(r"\s+", " ", texto).strip(" .")


def nome_arquivo(nota: dict, cliente_nome: str) -> str:
    """'NFSE 480 - Serviço de transfer prestado - Cliente' (cancelada: 'NFSE 480 - CANCELADA')."""
    numero = nota.get("numero_nfse") or nota["id"]
    if nota["status"] == "cancelada":
        base = f"NFSE {numero} - CANCELADA"
    else:
        descricao = limpar_nome(" ".join((nota["descricao"] or "").split()))[:25].strip()
        base = limpar_nome(f"NFSE {numero} - {descricao} - {cliente_nome}")[:150]
    return f"HOMOLOG - {base}" if nota.get("ambiente") == "homologacao" else base


def pasta_base(cfg: dict) -> Path:
    return Path(cfg["pasta_saida"].strip()) if cfg["pasta_saida"].strip() else config.pasta_saida_padrao()


def pasta_da_nota(cfg: dict, nota: dict) -> Path:
    """<pasta>/<ano>/<mes> de quando a nota foi emitida (cancelada fica no mês em que foi emitida)."""
    emitida = (nota.get("emitida_em") or nota["prevista_em"])[:7]
    return pasta_base(cfg) / emitida[:4] / emitida[5:7]


def _gravar_atomico(destino: Path, dados: bytes) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(f".{destino.name}.tmp")
    with open(tmp, "wb") as f:
        f.write(dados)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, destino)


def testar_pasta(cfg: dict) -> str:
    """Grava e apaga um arquivo de teste. Devolve o caminho absoluto, ou levanta OSError."""
    pasta = pasta_base(cfg)
    pasta.mkdir(parents=True, exist_ok=True)
    teste = pasta / ".teste_escrita"
    _gravar_atomico(teste, b"ok")
    teste.unlink(missing_ok=True)
    return str(pasta.resolve())


def enviar_email(destinos: list[str], assunto: str, corpo: str, anexos: list[tuple[str, bytes, str]],
                responder_para: str | None = None) -> None:
    """anexos: [(nome, bytes, 'tipo/subtipo')]. Levanta exceção se o SMTP não estiver configurado/falhar."""
    smtp = config.smtp()
    if not smtp:
        raise RuntimeError("E-mail não configurado: defina SMTP_HOST, SMTP_USER e SMTP_SENHA no ambiente.")
    if not destinos:
        raise RuntimeError("Nenhum e-mail de destino informado.")
    msg = EmailMessage()
    msg["From"] = smtp["remetente"]
    msg["To"] = ", ".join(destinos)
    msg["Subject"] = " ".join(assunto.split())[:200]   # uma linha só (sem injeção de cabeçalho)
    if responder_para:
        msg["Reply-To"] = responder_para
    msg.set_content(corpo)
    for nome, dados, tipo in anexos:
        principal, _, sub = tipo.partition("/")
        msg.add_attachment(dados, maintype=principal, subtype=sub or "octet-stream", filename=nome)
    contexto = ssl.create_default_context()
    if smtp["ssl"]:
        with smtplib.SMTP_SSL(smtp["host"], smtp["porta"], context=contexto, timeout=30) as s:
            s.login(smtp["usuario"], smtp["senha"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(smtp["host"], smtp["porta"], timeout=30) as s:
            s.starttls(context=contexto)
            s.login(smtp["usuario"], smtp["senha"])
            s.send_message(msg)


def _anexos(nota: dict, nome: str) -> tuple[bytes, bytes]:
    pdf = danfse.gerar_danfse_para_registro(nota["xml_nfse"], nota["status"])
    return pdf, nota["xml_nfse"].encode("utf-8")


def entregar(con: sqlite3.Connection, nota_id: int) -> dict:
    """Grava na pasta e envia por e-mail o que ainda falta. Nunca levanta exceção."""
    nota = dict(con.execute("SELECT * FROM nota WHERE id = ?", (nota_id,)).fetchone())
    cfg = db.obter_config(con)
    cliente = dict(con.execute("SELECT * FROM cliente WHERE id = ?", (nota["cliente_id"],)).fetchone())
    resultado = {"pasta": None, "email": None}
    if not nota.get("xml_nfse"):
        return resultado
    nome = nome_arquivo(nota, cliente["nome"])
    try:
        pdf, xml = _anexos(nota, nome)
    except Exception as e:  # noqa: BLE001 -- ex.: DanfseIndisponivel
        msg = f"Não consegui montar o PDF: {e}"[:500]
        con.execute("UPDATE nota SET pasta_erro = ?, email_erro = ?, entrega_tentativas = entrega_tentativas + 1 "
                    "WHERE id = ?", (msg, msg if cfg["enviar_por_email"] else None, nota_id))
        return {"pasta": msg, "email": msg}

    con.execute("UPDATE nota SET entrega_tentativas = entrega_tentativas + 1 WHERE id = ?", (nota_id,))
    if cfg["salvar_em_pasta"]:
        try:
            pasta = pasta_da_nota(cfg, nota)
            antigos = [p for p in (nota.get("pdf_path"), nota.get("xml_path")) if p]
            _gravar_atomico(pasta / f"{nome}.pdf", pdf)
            _gravar_atomico(pasta / f"{nome}.xml", xml)
            novos = {str(pasta / f"{nome}.pdf"), str(pasta / f"{nome}.xml")}
            for velho in antigos:  # renomeou (ex.: virou CANCELADA): mantém só os arquivos atuais
                if velho not in novos and nota["status"] != "cancelada":
                    Path(velho).unlink(missing_ok=True)
            con.execute("UPDATE nota SET pdf_path = ?, xml_path = ?, pasta_erro = NULL WHERE id = ?",
                        (str(pasta / f"{nome}.pdf"), str(pasta / f"{nome}.xml"), nota_id))
            resultado["pasta"] = "ok"
        except OSError as e:
            con.execute("UPDATE nota SET pasta_erro = ? WHERE id = ?", (f"Não consegui gravar na pasta: {e}"[:500], nota_id))
            resultado["pasta"] = str(e)

    ja_enviado = nota.get("email_enviado_em") and nota["status"] != "cancelada"
    if cfg["enviar_por_email"] and not ja_enviado:
        destinos = lista_emails(cfg["emails_destino"])
        if cliente["enviar_nota_por_email"]:
            destinos += [e for e in lista_emails(cliente["email"]) if e not in destinos]
        try:
            situacao = "CANCELADA" if nota["status"] == "cancelada" else ("(HOMOLOGAÇÃO - sem validade)"
                                                                          if nota["ambiente"] == "homologacao" else "")
            enviar_email(
                destinos, f"NFS-e {nota.get('numero_nfse') or ''} - {cliente['nome']} - {util.fmt_valor(nota['valor_centavos'])} {situacao}".strip(),
                f"Segue a NFS-e {nota.get('numero_nfse') or ''} emitida para {cliente['nome']} no valor de "
                f"{util.fmt_valor(nota['valor_centavos'])}.\n\nPDF e XML em anexo.", 
                [(f"{nome}.pdf", pdf, "application/pdf"), (f"{nome}.xml", xml, "application/xml")])
            con.execute("UPDATE nota SET email_enviado_em = datetime('now','localtime'), email_erro = NULL WHERE id = ?",
                        (nota_id,))
            resultado["email"] = "ok"
        except Exception as e:  # noqa: BLE001
            con.execute("UPDATE nota SET email_erro = ? WHERE id = ?", (f"Não consegui enviar o e-mail: {e}"[:500], nota_id))
            resultado["email"] = str(e)
    return resultado


def entrega_pendente(cfg: dict, nota: dict) -> bool:
    if nota["status"] not in ("emitida", "cancelada") or not nota["xml_nfse"]:
        return False
    if cfg["salvar_em_pasta"] and (not nota["pdf_path"] or nota["pasta_erro"]):
        return True
    return bool(cfg["enviar_por_email"] and (not nota["email_enviado_em"] or nota["email_erro"]))
