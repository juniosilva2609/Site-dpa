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

## Status atual

| Banco | Status |
|---|---|
| Inter | pendente de credenciais (nova integração a ser criada) |
| Santander | pendente de cadastro |
| Sicoob | pendente de cadastro |

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
