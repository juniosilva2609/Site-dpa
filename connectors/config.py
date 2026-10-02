"""Carrega e valida config/empresas.yaml.

Antes desta validação, um campo obrigatório faltando ou com nome errado só
seria percebido no meio do processamento de um banco, com um erro genérico
e difícil de rastrear. Aqui falha alto e cedo, com uma mensagem que já diz
qual empresa/banco/campo está errado.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CAMPOS_OBRIGATORIOS_EMPRESA = ("id", "razao_social", "status", "drive", "bancos")
CAMPOS_OBRIGATORIOS_BANCO = ("id", "nome_exibicao", "conta", "agencia", "integracao")
CAMPOS_OBRIGATORIOS_INTEGRACAO = ("tipo", "provider", "status")
PERIODICIDADES = ("quinzenal", "mensal")


class ConfigInvalida(ValueError):
    """Um campo obrigatório está ausente ou malformado em empresas.yaml."""


def carregar_empresas(caminho: str | Path = "config/empresas.yaml") -> list[dict[str, Any]]:
    caminho = Path(caminho)
    with caminho.open("r", encoding="utf-8") as f:
        dados = yaml.safe_load(f)

    empresas = (dados or {}).get("empresas")
    if not empresas:
        raise ConfigInvalida(f"{caminho}: chave 'empresas' ausente ou vazia")

    for empresa in empresas:
        _validar_empresa(empresa, caminho)

    return empresas


def _validar_empresa(empresa: dict, caminho: Path) -> None:
    empresa_id = empresa.get("id", "<sem id>")
    for campo in CAMPOS_OBRIGATORIOS_EMPRESA:
        if campo not in empresa:
            raise ConfigInvalida(f"{caminho}: empresa '{empresa_id}' sem campo obrigatório '{campo}'")

    if "extratos_id" not in empresa["drive"]:
        raise ConfigInvalida(f"{caminho}: empresa '{empresa_id}'.drive sem 'extratos_id'")

    if not empresa["bancos"]:
        raise ConfigInvalida(f"{caminho}: empresa '{empresa_id}' sem nenhum banco cadastrado")

    for banco in empresa["bancos"]:
        _validar_banco(banco, empresa_id, caminho)


def _validar_banco(banco: dict, empresa_id: str, caminho: Path) -> None:
    banco_id = banco.get("id", "<sem id>")
    prefixo = f"{caminho}: empresa '{empresa_id}', banco '{banco_id}'"
    for campo in CAMPOS_OBRIGATORIOS_BANCO:
        if campo not in banco:
            raise ConfigInvalida(f"{prefixo} sem campo obrigatório '{campo}'")

    periodicidade = banco.get("periodicidade", "quinzenal")
    if periodicidade not in PERIODICIDADES:
        raise ConfigInvalida(
            f"{prefixo}.periodicidade '{periodicidade}' inválida — use um de {PERIODICIDADES}"
        )

    integracao = banco["integracao"]
    for campo in CAMPOS_OBRIGATORIOS_INTEGRACAO:
        if campo not in integracao:
            raise ConfigInvalida(f"{prefixo}.integracao sem campo obrigatório '{campo}'")

    if integracao["status"] == "ativo" and "credenciais_env" not in integracao:
        raise ConfigInvalida(
            f"{prefixo}.integracao.status é 'ativo' mas não define 'credenciais_env' — "
            "não é possível autenticar sem saber o nome das variáveis de ambiente"
        )
