# -*- coding: utf-8 -*-
"""Rotina agendada: a cada ~30 s gera as notas da agenda, emite as aprovadas que chegaram na hora,
entrega arquivos pendentes e, a cada ~15 min, faz a manutenção (alertas, certificado, backup).

Roda numa thread dentro do próprio servidor (`iniciar_thread`) ou avulsa: `python run.py agendador`."""

import logging
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timedelta

from . import agenda, alertas, conferencia, db, emissor, saida, util
from .fiscal import certificado

log = logging.getLogger("nfse.agendador")
INTERVALO_SEGUNDOS = 30
MAX_ENTREGA_TENTATIVAS = 6
_LIMITES_CERTIFICADO = (7, 15, 30, 60)


def _estado(con, chave, valor=None):
    if valor is None:
        r = con.execute("SELECT valor FROM estado WHERE chave = ?", (chave,)).fetchone()
        return r["valor"] if r else None
    con.execute("INSERT INTO estado (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                (chave, valor))
    return valor


def emitir_vencidas(con: sqlite3.Connection, agora: datetime | None = None) -> list[dict]:
    """Emite as notas APROVADAS cuja hora chegou. Passou da tolerância: vira 'atrasada' (nunca emite
    com dias de atraso sozinha, pois a competência/data seriam outras)."""
    agora = agora or util.agora()
    limite = (agora - timedelta(hours=conferencia.tolerancia_horas(con))).strftime(agenda.FORMATO)
    resultados = []
    # não conferidas a tempo
    for n in con.execute("SELECT id FROM nota WHERE status IN ('a_conferir','aprovada') AND prevista_em < ?",
                         (limite,)).fetchall():
        con.execute("UPDATE nota SET status = 'atrasada', mensagem_erro = ? WHERE id = ?",
                    ("Passou do horário previsto sem ser emitida. Confira e emita manualmente se ainda "
                     "fizer sentido.", n["id"]))
        alertas.abrir(con, f"atrasada-{n['id']}", f"Nota #{n['id']} não saiu no horário previsto "
                      "(não foi conferida a tempo ou o sistema estava parado).", "erro", n["id"])
        db.registrar_historico(con, None, n["id"], "atrasada", "Passou da tolerância")
    for n in con.execute("SELECT id FROM nota WHERE status = 'aprovada' AND prevista_em <= ? ORDER BY prevista_em, id "
                         "LIMIT 20", (agora.strftime(agenda.FORMATO),)).fetchall():
        r = emissor.emitir(con, n["id"], usuario="agenda", manual=False)
        resultados.append({"nota_id": n["id"], **r})
        if r.get("ocupado"):
            break
    return resultados


def lembretes_conferencia(con: sqlite3.Connection, agora: datetime | None = None) -> None:
    """Notas a conferir que vencem nas próximas 24 h geram alerta (e e-mail)."""
    agora = agora or util.agora()
    ate = (agora + timedelta(hours=24)).strftime(agenda.FORMATO)
    for n in con.execute("SELECT n.id, n.prevista_em, c.nome FROM nota n JOIN cliente c ON c.id = n.cliente_id "
                         "WHERE n.status = 'a_conferir' AND n.prevista_em <= ?", (ate,)):
        alertas.abrir(con, f"conferir-{n['id']}", f"Nota de {n['nome']} sai em {util.fmt_data_hora(n['prevista_em'])} "
                      "e ainda NÃO foi conferida -- sem conferência ela não é emitida.", "aviso", n["id"])


def entregas_pendentes(con: sqlite3.Connection) -> int:
    cfg = db.obter_config(con)
    feitas = 0
    for n in con.execute("SELECT * FROM nota WHERE status IN ('emitida','cancelada') AND xml_nfse IS NOT NULL "
                         "AND entrega_tentativas < ?", (MAX_ENTREGA_TENTATIVAS,)).fetchall():
        if saida.entrega_pendente(cfg, dict(n)):
            saida.entregar(con, n["id"])
            feitas += 1
    for n in con.execute("SELECT id, numero_nfse FROM nota WHERE status IN ('emitida','cancelada') AND "
                         "entrega_tentativas >= ?", (MAX_ENTREGA_TENTATIVAS,)).fetchall():
        full = dict(con.execute("SELECT * FROM nota WHERE id = ?", (n["id"],)).fetchone())
        if saida.entrega_pendente(cfg, full):
            alertas.abrir(con, f"entrega-{n['id']}", f"Não consegui entregar os arquivos da NFS-e "
                          f"{n['numero_nfse'] or n['id']} (pasta/e-mail). Veja a nota e use \"Entregar de novo\".",
                          "erro", n["id"])
    return feitas


def recuperar_emissoes_travadas(con: sqlite3.Connection) -> None:
    """Nota presa em 'emitindo' sem nenhuma emissão em andamento (a trava expirou) = o processo caiu no meio do envio: o resultado é
    DESCONHECIDO -> 'verificar' (nunca volta sozinha para a fila)."""
    ativa = con.execute("SELECT 1 FROM trava WHERE nome = ? AND ate > ?", (emissor.TRAVA, time.time())).fetchone()
    if ativa:
        return
    for n in con.execute("SELECT id FROM nota WHERE status = 'emitindo'").fetchall():
        con.execute("UPDATE nota SET status = 'verificar', mensagem_erro = ? WHERE id = ?",
                    ("O sistema parou durante a emissão: não se sabe se a Sefin autorizou a nota. Use \"Conferir "
                     "na Sefin\" ou confira no Portal Nacional antes de emitir de novo.", n["id"]))
        alertas.abrir(con, f"verificar-{n['id']}", f"Nota #{n['id']} ficou incerta (o sistema parou durante a "
                      "emissão). Confira antes de emitir de novo.", "erro", n["id"])


def alertas_certificado(con: sqlite3.Connection) -> None:
    dias = certificado.dias_para_vencer() if certificado.disponivel() else None
    for limite in _LIMITES_CERTIFICADO:
        alertas.resolver(con, f"cert-{limite}")
    alertas.resolver(con, "cert-vencido")
    if dias is None:
        return
    if dias < 0:
        alertas.abrir(con, "cert-vencido", "O certificado digital VENCEU: nenhuma nota poderá ser emitida.", "erro")
        return
    for limite in _LIMITES_CERTIFICADO:  # do menor para o maior: o primeiro que cobre é o alerta ativo
        if dias <= limite:
            alertas.abrir(con, f"cert-{limite}", f"O certificado digital vence em {dias} dia(s).",
                          "erro" if limite <= 15 else "aviso")
            return


def backup_diario(con: sqlite3.Connection) -> str | None:
    """Uma cópia consistente do banco por dia (API de backup do SQLite), 14 dias de histórico; copia também
    para <pasta de saída>/_backup quando a entrega em pasta está ligada."""
    from . import config
    hoje = util.agora().strftime("%Y%m%d")
    if _estado(con, "backup_dia") == hoje:
        return None
    pasta = config.pasta_dados() / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"nfse-{hoje}.db"
    alvo = sqlite3.connect(str(destino))
    try:
        con.backup(alvo)
    finally:
        alvo.close()
    for velho in sorted(pasta.glob("nfse-*.db"))[:-14]:
        velho.unlink(missing_ok=True)
    cfg = db.obter_config(con)
    if cfg["salvar_em_pasta"]:
        try:
            extra = saida.pasta_base(cfg) / "_backup"
            extra.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destino, extra / destino.name)
            for velho in sorted(extra.glob("nfse-*.db"))[:-14]:
                velho.unlink(missing_ok=True)
        except OSError as e:
            alertas.abrir(con, "backup-pasta", f"Não consegui copiar o backup para a pasta de saída: {e}", "aviso")
    _estado(con, "backup_dia", hoje)
    return str(destino)


def manutencao(con: sqlite3.Connection) -> None:
    recuperar_emissoes_travadas(con)
    lembretes_conferencia(con)
    alertas_certificado(con)
    entregas_pendentes(con)
    backup_diario(con)
    alertas.enviar_pendentes(con)


def tick(con: sqlite3.Connection, agora: datetime | None = None, forcar_manutencao: bool = False) -> dict:
    """Um ciclo completo. Seguro de chamar em paralelo (trava no banco)."""
    if not db.adquirir_trava(con, "tick", 25):
        return {"executou": False}
    try:
        criadas = agenda.gerar_notas(con, agora)
        emitidas = emitir_vencidas(con, agora)
        ultima = float(_estado(con, "ultima_manutencao") or 0)
        if forcar_manutencao or time.time() - ultima > 900:
            manutencao(con)
            _estado(con, "ultima_manutencao", str(time.time()))
        _estado(con, "ultimo_tick", util.agora().strftime("%Y-%m-%d %H:%M:%S"))
        return {"executou": True, "criadas": criadas, "emitidas": emitidas}
    finally:
        db.liberar_trava(con, "tick")


def _loop(caminho_banco=None):
    con = db.conectar(caminho_banco)
    while True:
        try:
            tick(con)
        except Exception:  # noqa: BLE001 -- o agendador nunca pode morrer
            log.exception("erro no ciclo do agendador")
        time.sleep(INTERVALO_SEGUNDOS)


def iniciar_thread(caminho_banco=None) -> threading.Thread:
    t = threading.Thread(target=_loop, args=(caminho_banco,), name="nfse-agendador", daemon=True)
    t.start()
    return t
