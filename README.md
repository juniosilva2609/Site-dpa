# Fechamento Bancário Automático — DPA

Automação para consultar os bancos da Distribuidora Peres & Araújo Ltda,
baixar os extratos (PDF, OFX e Excel) e organizá-los no Google Drive, com
nomenclatura padronizada e relatório de status por banco.

Somente consulta/leitura de extrato. Nunca realiza pagamentos, transferências
ou qualquer movimentação financeira.

## Estrutura

- `config/empresas.yaml` — cadastro de empresas, bancos, contas e pastas do
  Drive (sem segredos).
- `docs/padrao-nomenclatura.md` — regra de nome de arquivo e de
  não-sobrescrita.
- `docs/setup-bancos.md` — passo a passo para liberar a API de cada banco.
- `docs/processo-fechamento.md` — roteiro que a rotina agendada executa a
  cada disparo.
- `connectors/` — código de autenticação e download por banco (`inter.py`,
  `sicoob.py`); pronto para funcionar assim que as credenciais forem
  configuradas como variável de ambiente. Endpoints exatos devem ser
  reconferidos no portal do banco no momento da ativação.
  - `runner.py` — orquestrador: percorre `config/empresas.yaml`, isola erro
    por banco (um banco fora do ar nunca trava os outros), com retry
    automático para falha transitória de rede/servidor.
  - `config.py` — valida `empresas.yaml` na carga (falha cedo e com mensagem
    clara se faltar um campo obrigatório).
  - `dedup.py` — checagem de duplicidade por hash de conteúdo (não só nome
    de arquivo), implementando a regra de `docs/padrao-nomenclatura.md`.
  - `nomenclatura.py` — monta o nome padronizado do arquivo e a competência
    (quinzena) a partir da data do período.
  - `retry.py` — backoff exponencial para erro transitório de rede/5xx; erro
    de cliente (4xx, ex: credencial inválida) nunca é reprocessado.

  `runner.py` não fala com o Google Drive: devolve, por empresa/banco, os
  arquivos a gravar (já resolvidos como novo/existente/nova versão) para
  quem estiver integrando com o Drive.

## Testes

```
pip install -r requirements-dev.txt
pytest
```

Cobre os conectores (Inter/Sicoob, com API mockada), a validação de
`empresas.yaml`, a regra de duplicidade e o isolamento de erro entre
bancos/empresas no orquestrador.

## Status atual

| Banco | Status |
|---|---|
| Inter | ✅ **ativo** — testado de ponta a ponta em 16/09/2026 (autenticação real, PDF nativo da API, OFX/Excel gerados localmente). Falta só a agência/conta para nomear os arquivos. |
| Santander | pendente de cadastro |
| Sicoob | ✅ **ativo** — testado de ponta a ponta em 16/09/2026 (autenticação real, extrato real, PDF/OFX/Excel completos, arquivos organizados no Drive). |

A política de rede restritiva do ambiente ("trusted network access", que
bloqueava saída para domínios de banco) já foi trocada e resolvida — ver
histórico em `docs/setup-bancos.md`.

## Como adicionar um banco novo

1. Seguir o roteiro em `docs/setup-bancos.md` para aquele banco.
2. Adicionar/atualizar a entrada em `config/empresas.yaml` com
   `integracao.status: ativo` e as variáveis de ambiente das credenciais.
3. Nenhuma outra mudança é necessária — o roteiro em
   `docs/processo-fechamento.md` já cobre qualquer banco cadastrado como
   ativo.

## Como adicionar uma empresa nova

Replicar a estrutura de pastas do Drive (`01.2 Bancário/Extratos/{ano}/{mês}/
{Banco}/`) e adicionar a empresa em `config/empresas.yaml` com seus próprios
bancos e IDs de pasta.
