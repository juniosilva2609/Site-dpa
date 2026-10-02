import pytest

from connectors.config import ConfigInvalida, carregar_empresas


def test_carrega_empresas_reais():
    empresas = carregar_empresas("config/empresas.yaml")
    ids = {e["id"] for e in empresas}
    assert {"dpa", "c3s", "licitprint"} <= ids


def test_banco_ativo_sem_credenciais_env_falha(tmp_path):
    caminho = tmp_path / "empresas.yaml"
    caminho.write_text(
        """
empresas:
  - id: teste
    razao_social: Teste Ltda
    status: ativo
    drive:
      extratos_id: "abc"
    bancos:
      - id: inter
        nome_exibicao: Inter
        conta: "123"
        agencia: "0001"
        integracao:
          tipo: api_oficial
          provider: banco_inter
          status: ativo
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigInvalida, match="credenciais_env"):
        carregar_empresas(caminho)


def test_empresa_sem_bancos_falha(tmp_path):
    caminho = tmp_path / "empresas.yaml"
    caminho.write_text(
        """
empresas:
  - id: teste
    razao_social: Teste Ltda
    status: ativo
    drive:
      extratos_id: "abc"
    bancos: []
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigInvalida, match="nenhum banco"):
        carregar_empresas(caminho)


def test_empresa_sem_campo_obrigatorio_falha(tmp_path):
    caminho = tmp_path / "empresas.yaml"
    caminho.write_text(
        """
empresas:
  - id: teste
    status: ativo
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigInvalida, match="razao_social"):
        carregar_empresas(caminho)


def _yaml_com_periodicidade(periodicidade_linha: str) -> str:
    return f"""
empresas:
  - id: teste
    razao_social: Teste Ltda
    status: ativo
    drive:
      extratos_id: "abc"
    bancos:
      - id: c6
        nome_exibicao: C6
        conta: "123"
        agencia: "0001"
{periodicidade_linha}
        integracao:
          tipo: api_oficial
          provider: c6_bank
          status: pendente_cadastro
"""


def test_periodicidade_invalida_falha(tmp_path):
    caminho = tmp_path / "empresas.yaml"
    caminho.write_text(_yaml_com_periodicidade("        periodicidade: semanal"), encoding="utf-8")
    with pytest.raises(ConfigInvalida, match="periodicidade"):
        carregar_empresas(caminho)


def test_periodicidade_mensal_e_ausente_sao_validas(tmp_path):
    for linha in ("        periodicidade: mensal", ""):
        caminho = tmp_path / "empresas.yaml"
        caminho.write_text(_yaml_com_periodicidade(linha), encoding="utf-8")
        assert carregar_empresas(caminho)[0]["bancos"][0]["id"] == "c6"
