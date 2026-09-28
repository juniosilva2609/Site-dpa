from datetime import date

from connectors import runner
from connectors.base import BankConnector, Extrato


class _ConectorFalso(BankConnector):
    nome = "Falso"

    def __init__(self, resultado=None, excecao=None):
        self._resultado = resultado
        self._excecao = excecao

    def autenticar(self):
        pass

    def baixar_extrato(self, conta, inicio, fim):
        if self._excecao:
            raise self._excecao
        return self._resultado


def _montar_nome(empresa, banco, inicio, fim, tipo):
    return f"{empresa['id']}_{banco['id']}_{tipo}.{tipo}"


EMPRESA = {"id": "teste", "razao_social": "Teste Ltda"}
BANCO_OK = {"id": "inter", "conta": "123", "integracao": {"status": "ativo", "provider": "falso-ok"}}
BANCO_INATIVO = {
    "id": "santander",
    "conta": "?",
    "integracao": {"status": "pendente_cadastro", "provider": "santander_developers"},
}


def test_banco_com_status_nao_ativo_vira_indisponivel():
    resultado = runner.processar_banco(
        EMPRESA, BANCO_INATIVO, date(2026, 9, 1), date(2026, 9, 15), _montar_nome
    )
    assert resultado.status == "indisponivel"


def test_erro_em_um_banco_nao_propaga(monkeypatch):
    monkeypatch.setitem(
        runner.FABRICAS_CONECTOR,
        "falso-ok",
        lambda banco, empresa: _ConectorFalso(excecao=RuntimeError("boom")),
    )
    resultado = runner.processar_banco(EMPRESA, BANCO_OK, date(2026, 9, 1), date(2026, 9, 15), _montar_nome)
    assert resultado.status == "erro"
    assert resultado.motivo == "RuntimeError"


def test_download_com_sucesso_resolve_duplicidade(monkeypatch):
    extrato = Extrato(pdf=b"conteudo-pdf", ofx=b"conteudo-ofx", xlsx=None)
    monkeypatch.setitem(
        runner.FABRICAS_CONECTOR, "falso-ok", lambda banco, empresa: _ConectorFalso(resultado=extrato)
    )

    existentes = {"pdf": {"teste_inter_pdf.pdf": b"conteudo-pdf"}}
    resultado = runner.processar_banco(
        EMPRESA,
        BANCO_OK,
        date(2026, 9, 1),
        date(2026, 9, 15),
        _montar_nome,
        existentes_por_tipo=existentes,
    )

    assert resultado.status == "baixado"
    assert resultado.arquivos["teste_inter_pdf.pdf"][1] == "existente"
    assert resultado.arquivos["teste_inter_ofx.ofx"][1] == "novo"


def test_processar_periodo_isola_falha_entre_empresas(tmp_path, monkeypatch):
    caminho = tmp_path / "empresas.yaml"
    caminho.write_text(
        """
empresas:
  - id: empresa1
    razao_social: Empresa 1
    status: ativo
    drive: {extratos_id: "a"}
    bancos:
      - id: b1
        nome_exibicao: B1
        conta: "1"
        agencia: "0001"
        integracao: {tipo: api_oficial, provider: falso1, status: ativo, credenciais_env: {x: Y}}
  - id: empresa2
    razao_social: Empresa 2
    status: ativo
    drive: {extratos_id: "b"}
    bancos:
      - id: b2
        nome_exibicao: B2
        conta: "2"
        agencia: "0001"
        integracao: {tipo: api_oficial, provider: falso2, status: ativo, credenciais_env: {x: Y}}
""",
        encoding="utf-8",
    )

    monkeypatch.setitem(
        runner.FABRICAS_CONECTOR,
        "falso1",
        lambda banco, empresa: _ConectorFalso(excecao=RuntimeError("boom")),
    )
    monkeypatch.setitem(
        runner.FABRICAS_CONECTOR,
        "falso2",
        lambda banco, empresa: _ConectorFalso(resultado=Extrato(pdf=b"x", ofx=None, xlsx=None)),
    )

    resultados = runner.processar_periodo(
        date(2026, 9, 1), date(2026, 9, 15), _montar_nome, caminho_config=caminho
    )

    por_empresa = {r.empresa_id: r for r in resultados}
    assert por_empresa["empresa1"].status == "erro"
    assert por_empresa["empresa2"].status == "baixado"
