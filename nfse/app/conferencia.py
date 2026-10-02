# -*- coding: utf-8 -*-
"""Conferências automáticas ("o que o sistema checa antes de deixar emitir").

`conferir()` devolve uma lista de problemas {nivel: 'erro'|'aviso', texto}. Qualquer 'erro' BLOQUEIA a
aprovação e a emissão; 'aviso' só informa. O mesmo conjunto roda no momento da emissão, mesmo para
notas já aprovadas (o mundo muda: certificado vence, cadastro é editado)."""

import sqlite3
from datetime import datetime

from . import db, util
from .fiscal import certificado


def tolerancia_horas(con: sqlite3.Connection) -> int:
    return int(db.obter_config(con).get("tolerancia_atraso_horas") or 6)


def _erro(texto):
    return {"nivel": "erro", "texto": texto}


def _aviso(texto):
    return {"nivel": "aviso", "texto": texto}


def conferir_configuracao(cfg: dict) -> list[dict]:
    problemas = []
    if not util.cnpj_valido(cfg["cnpj"]):
        problemas.append(_erro("Configuração: o CNPJ do prestador é inválido."))
    if len(util.so_digitos(cfg["codigo_municipio_ibge"])) != 7:
        problemas.append(_erro("Configuração: código IBGE do município precisa ter 7 dígitos."))
    if len(util.so_digitos(cfg["codigo_servico_lc116"])) != 6:
        problemas.append(_erro("Configuração: o código de tributação nacional precisa ter 6 dígitos (ex.: 160201)."))
    if not certificado.disponivel():
        problemas.append(_erro("Certificado digital e-CNPJ não configurado (arquivo .pfx + senha no ambiente)."))
    else:
        dias = certificado.dias_para_vencer()
        if dias is None:
            problemas.append(_erro("Não consegui abrir o certificado digital (senha incorreta?)."))
        elif dias < 0:
            problemas.append(_erro("O certificado digital está VENCIDO."))
        elif dias <= 30:
            problemas.append(_aviso(f"O certificado digital vence em {dias} dia(s) -- renove."))
        cnpj_cert = certificado.cnpj_do_certificado()
        if cnpj_cert and cnpj_cert != util.so_digitos(cfg["cnpj"]):
            problemas.append(_erro("O CNPJ do certificado digital é diferente do CNPJ do prestador."))
    if cfg["ambiente"] != "producao":
        problemas.append(_aviso("Sistema em HOMOLOGAÇÃO (teste): as notas emitidas NÃO têm validade jurídica."))
    return problemas


def conferir(con: sqlite3.Connection, nota_id: int, incluir_config: bool = True) -> list[dict]:
    nota = con.execute("SELECT * FROM nota WHERE id = ?", (nota_id,)).fetchone()
    if nota is None:
        return [_erro("Nota não encontrada.")]
    nota = dict(nota)
    cfg = db.obter_config(con)
    problemas: list[dict] = []

    cliente = con.execute("SELECT * FROM cliente WHERE id = ?", (nota["cliente_id"],)).fetchone()
    if cliente is None:
        problemas.append(_erro("Cliente não encontrado."))
    else:
        cliente = dict(cliente)
        if not cliente["ativo"]:
            problemas.append(_erro("O cliente está desativado."))
        if not cliente["nome"].strip():
            problemas.append(_erro("O cliente está sem nome/razão social."))
        if not util.documento_valido(cliente["documento"]):
            problemas.append(_erro(f"CPF/CNPJ do cliente inválido ({util.fmt_documento(cliente['documento'])})."))
        endereco = [cliente["logradouro"], cliente["numero"], cliente["bairro"], cliente["cep"],
                    cliente["codigo_municipio"]]
        if any(endereco) and not all(endereco):
            problemas.append(_aviso("Endereço do cliente incompleto: ele NÃO será enviado na nota (ou preencha "
                                    "tudo, ou deixe tudo em branco)."))

    if not nota["valor_centavos"] or nota["valor_centavos"] <= 0:
        problemas.append(_erro("O valor da nota precisa ser maior que zero."))
    descricao = (nota["descricao"] or "").strip()
    if not descricao:
        problemas.append(_erro("A descrição do serviço está vazia."))
    elif "{" in descricao and "}" in descricao:
        problemas.append(_erro("A descrição ainda tem um campo entre chaves {…} não substituído."))
    tamanho = util.tamanho_descricao(descricao)
    if tamanho > util.LIMITE_DESCRICAO:
        problemas.append(_erro(f"Descrição com {tamanho} caracteres: o limite é {util.LIMITE_DESCRICAO} "
                               f"(encurte em {tamanho - util.LIMITE_DESCRICAO})."))

    if incluir_config:
        problemas += conferir_configuracao(cfg)

    # possível duplicidade: mesma nota (cliente + valor + mês) já emitida
    dup = con.execute(
        "SELECT id, numero_nfse FROM nota WHERE id != ? AND cliente_id = ? AND valor_centavos = ? "
        "AND status = 'emitida' AND substr(prevista_em,1,7) = substr(?,1,7) AND descricao = ?",
        (nota_id, nota["cliente_id"], nota["valor_centavos"], nota["prevista_em"], nota["descricao"])).fetchone()
    if dup:
        problemas.append(_aviso(f"Já existe uma nota emitida igual neste mês (nº {dup['numero_nfse'] or dup['id']})."))

    if nota["agendamento_id"]:
        ultima = con.execute(
            "SELECT valor_centavos FROM nota WHERE agendamento_id = ? AND id != ? AND status = 'emitida' "
            "ORDER BY prevista_em DESC LIMIT 1", (nota["agendamento_id"], nota_id)).fetchone()
        if ultima and ultima["valor_centavos"] != nota["valor_centavos"]:
            problemas.append(_aviso(f"Valor diferente da última nota deste agendamento "
                                    f"({util.fmt_valor(ultima['valor_centavos'])})."))

    quando = datetime.fromisoformat(nota["prevista_em"])
    if quando < util.agora() and nota["status"] in ("a_conferir", "aprovada"):
        problemas.append(_aviso("O horário previsto já passou."))
    return problemas


def erros(problemas: list[dict]) -> list[str]:
    return [p["texto"] for p in problemas if p["nivel"] == "erro"]
