"""Orquestrador do fechamento bancário quinzenal.

Percorre `config/empresas.yaml` e, para cada empresa/banco com
`integracao.status == "ativo"`, baixa o extrato do período isolando falhas:
um banco com erro nunca interrompe o processamento dos demais. Resolve
duplicidade de nome contra os arquivos já existentes na pasta de destino e
registra tudo em log persistente, sem nenhum dado sensível.

Este módulo não fala com o Google Drive diretamente. Quem chama
`processar_periodo` entrega, por empresa/banco, os arquivos já existentes na
pasta de destino (nome -> conteúdo) e é responsável por de fato gravar os
arquivos "novo"/"nova_versao" do resultado — o que mantém o módulo testável
sem depender de uma integração real com o Drive.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from .base import BankConnector, ConectorNaoConfigurado, Extrato
from .config import carregar_empresas
from .dedup import resolver_nome
from .inter import InterConnector
from .nomenclatura import montar_nome as montar_nome_padrao
from .retry import com_retry
from .santander import SantanderConnector
from .sicoob import SicoobConnector

logger = logging.getLogger("fechamento")

FABRICAS_CONECTOR: dict[str, Callable[[dict, dict], BankConnector]] = {
    "banco_inter": lambda banco, empresa: InterConnector(
        agencia=banco["agencia"],
        razao_social=empresa["razao_social"],
        credenciais_env=banco["integracao"]["credenciais_env"],
    ),
    "sicoob_developers": lambda banco, empresa: SicoobConnector(
        cooperativa=banco["cooperativa"],
        cooperativa_nome=banco["cooperativa_nome"],
        razao_social=empresa["razao_social"],
        credenciais_env=banco["integracao"]["credenciais_env"],
    ),
    "santander_developers": lambda banco, empresa: SantanderConnector(
        agencia=banco["agencia"],
        razao_social=empresa["razao_social"],
        credenciais_env=banco["integracao"]["credenciais_env"],
    ),
}


def configurar_logging(caminho_log: str | Path = "logs/fechamento.log") -> None:
    caminho = Path(caminho_log)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(caminho),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


@dataclass
class ResultadoBanco:
    empresa_id: str
    banco_id: str
    status: str  # "baixado" | "indisponivel" | "manual" | "erro"
    motivo: str | None = None
    # nome_final -> (conteudo, status_dedup: "novo" | "existente" | "nova_versao")
    arquivos: dict[str, tuple[bytes, str]] = field(default_factory=dict)


def _construir_conector(banco: dict, empresa: dict) -> BankConnector:
    integracao = banco["integracao"]
    nome_exibicao = banco.get("nome_exibicao", banco["id"])

    if integracao.get("status") != "ativo":
        return ConectorNaoConfigurado(nome=nome_exibicao, motivo=integracao.get("status", "desconhecido"))

    fabrica = FABRICAS_CONECTOR.get(integracao.get("provider"))
    if fabrica is None:
        return ConectorNaoConfigurado(
            nome=nome_exibicao,
            motivo=f"provider '{integracao.get('provider')}' sem conector implementado",
        )
    return fabrica(banco, empresa)


def processar_banco(
    empresa: dict,
    banco: dict,
    inicio: date,
    fim: date,
    montar_nome: Callable[[dict, dict, date, date, str], str] = montar_nome_padrao,
    existentes_por_tipo: dict[str, dict[str, bytes]] | None = None,
) -> ResultadoBanco:
    """Baixa e resolve duplicidade para um único empresa+banco.

    Isola erros por contrato: qualquer exceção durante a autenticação ou o
    download vira um ResultadoBanco de status "erro" — nunca propaga para
    quem está processando os outros bancos.
    """
    empresa_id, banco_id = empresa["id"], banco["id"]
    existentes_por_tipo = existentes_por_tipo or {}

    if banco["integracao"].get("status") == "manual":
        logger.info("empresa=%s banco=%s status=manual", empresa_id, banco_id)
        return ResultadoBanco(empresa_id, banco_id, "manual", motivo="extrato enviado manualmente")

    try:
        conector = _construir_conector(banco, empresa)
        extrato: Extrato = com_retry(lambda: conector.baixar_extrato(banco["conta"], inicio, fim))
    except KeyError:
        logger.error("empresa=%s banco=%s status=erro motivo=credencial_de_ambiente_ausente", empresa_id, banco_id)
        return ResultadoBanco(empresa_id, banco_id, "erro", motivo="credencial de ambiente ausente")
    except Exception as exc:  # noqa: BLE001 - isolamento proposital entre bancos
        logger.error("empresa=%s banco=%s status=erro motivo=%s", empresa_id, banco_id, type(exc).__name__)
        return ResultadoBanco(empresa_id, banco_id, "erro", motivo=type(exc).__name__)

    if extrato.indisponiveis and not (extrato.pdf or extrato.ofx or extrato.xlsx):
        logger.info("empresa=%s banco=%s status=indisponivel", empresa_id, banco_id)
        return ResultadoBanco(empresa_id, banco_id, "indisponivel", motivo="; ".join(extrato.indisponiveis))

    arquivos: dict[str, tuple[bytes, str]] = {}
    for tipo, conteudo in (("pdf", extrato.pdf), ("ofx", extrato.ofx), ("xlsx", extrato.xlsx)):
        if conteudo is None:
            continue
        nome_base = montar_nome(empresa, banco, inicio, fim, tipo)
        resolucao = resolver_nome(nome_base, conteudo, existentes_por_tipo.get(tipo, {}))
        arquivos[resolucao.nome_final] = (conteudo, resolucao.status)
        logger.info(
            "empresa=%s banco=%s arquivo=%s status=%s",
            empresa_id, banco_id, resolucao.nome_final, resolucao.status,
        )

    return ResultadoBanco(empresa_id, banco_id, "baixado", arquivos=arquivos)


def periodo_do_banco(banco: dict, inicio: date, fim: date) -> tuple[date, date] | None:
    """Período que este banco deve baixar no disparo [inicio, fim].

    Banco `mensal` só roda no disparo do dia 1 (período Q2 do mês anterior)
    e baixa o mês inteiro; no disparo do dia 16 (período Q1) devolve None.
    """
    if banco.get("periodicidade", "quinzenal") == "quinzenal":
        return inicio, fim
    if inicio.day == 1:
        return None
    return inicio.replace(day=1), fim


def processar_periodo(
    inicio: date,
    fim: date,
    montar_nome: Callable[[dict, dict, date, date, str], str] = montar_nome_padrao,
    existentes: dict[tuple[str, str], dict[str, dict[str, bytes]]] | None = None,
    caminho_config: str | Path = "config/empresas.yaml",
) -> list[ResultadoBanco]:
    """Percorre todas as empresas/bancos ativos de `empresas.yaml` para o
    período [inicio, fim]. `existentes` (opcional) mapeia
    (empresa_id, banco_id) -> {tipo: {nome: conteudo}} com os arquivos já
    salvos na pasta de destino, para a checagem de duplicidade.
    """
    existentes = existentes or {}
    resultados = []
    for empresa in carregar_empresas(caminho_config):
        if empresa.get("status") != "ativo":
            continue
        for banco in empresa["bancos"]:
            periodo = periodo_do_banco(banco, inicio, fim)
            if periodo is None:
                continue
            resultado = processar_banco(
                empresa,
                banco,
                *periodo,
                montar_nome,
                existentes_por_tipo=existentes.get((empresa["id"], banco["id"])),
            )
            resultados.append(resultado)
    return resultados
