# Processo de fechamento bancário quinzenal — roteiro de execução

Este é o roteiro que a Rotina agendada segue a cada disparo (dia 1 e dia 16
de cada mês). Só cobre bancos com `integracao.status: ativo` em
`config/empresas.yaml` — qualquer outro valor de status (pendente de
cadastro, pendente de certificado, bloqueado por rede etc.) entra no
relatório como pendente, sem travar os outros bancos.

Status `manual` (ex: C6 da Licitprint enquanto o cadastro no C6
Developers não é aprovado): não há download pela automação — a equipe
exporta o extrato do mês e salva na pasta do banco. No disparo do dia 1 a
Rotina cria a pasta do mês anterior se faltar e põe um lembrete no
relatório; a auditoria mensal do dia 2 confere se o PDF está lá e cobre o
mês inteiro (ver `docs/setup-bancos.md`).

**Desde a auditoria de 09/2026, os passos 1-4 e 7-8 abaixo são código
determinístico e testado** (`connectors/runner.py`, `connectors/dedup.py`,
`connectors/nomenclatura.py`, `connectors/retry.py`), não mais só uma
descrição em prosa interpretada a cada execução — ver
`connectors/runner.py:processar_periodo`. O que continua fora deste
repositório é só a integração real com o Google Drive (passos 6 e a
gravação dos arquivos), que hoje depende de uma sessão de agente autenticada
no Drive; `processar_periodo` já devolve, por empresa/banco, quais arquivos
são "novo"/"existente"/"nova_versao" para quem for gravar decidir o que
fazer com cada um.

**Pré-requisito de ambiente**: a política de rede deste ambiente de
execução precisa permitir saída para os domínios de API de cada banco
ativo (ex: `auth.sicoob.com.br`, `api.sicoob.com.br`,
`cdpj.partners.bancointer.com.br`). Por padrão o ambiente vem com uma
política restritiva ("trusted network access") que bloqueia esses
domínios — ver `docs/setup-bancos.md`.

## Passo a passo por empresa → banco

1. **Determinar a competência** a partir da data do disparo:
   - dia 16 → período = dia 01 ao dia 15 do mês corrente (`Q1`).
   - dia 01 → período = dia 16 ao último dia do mês anterior (`Q2`).
   - Exceção: banco com `periodicidade: mensal` em `config/empresas.yaml`
     (ex: C6 da Licitprint) é pulado no dia 16 e, no dia 01, baixa o mês
     anterior inteiro (competência `MM-AAAA`, sem Q1/Q2) —
     `connectors/runner.py:periodo_do_banco`.
2. **Autenticar** na API do banco (OAuth2 + certificado mTLS), usando as
   variáveis de ambiente listadas em `config/empresas.yaml`.
3. **Consultar o extrato** do período para a conta cadastrada.
4. **Baixar em PDF, OFX e Excel** (quando o banco oferecer o formato).
5. **Montar o nome padronizado** conforme `docs/padrao-nomenclatura.md`.
6. **Localizar/criar a pasta de destino** no Drive, a partir da raiz fixa em
   `empresas.<id>.drive.extratos_id` (`config/empresas.yaml`). Cada empresa
   tem sua própria estrutura, já usada antes desta automação — respeitar a
   que já existe, sem inventar uma nova:
   - **DPA**: `Extratos/{ano}/{mês}/{Banco}/`
   - **C3S**: `Extratos/{ano}/{mês}/{Banco}/`
   - **Licitprint**: `FINANCEIRO/{mês}/{Banco}/` (sem pasta de ano)

   Ano (quando houver), mês e banco são localizados por nome ou criados se
   ainda não existirem.
7. **Checar duplicidade** antes de gravar (ver regra de não sobrescrita em
   `docs/padrao-nomenclatura.md`, implementada em `connectors/dedup.py`).
8. **Registrar no log** desta execução: arquivo baixado / indisponível
   naquele banco / erro (com a causa, nunca com dado sensível) — grava em
   `logs/fechamento.log` via `connectors/runner.py:configurar_logging`.
9. Repetir para os próximos bancos/empresas — uma falha (erro de rede, API
   fora do ar, credencial expirada) em um banco nunca impede os demais:
   `connectors/runner.py:processar_banco` isola cada chamada e devolve
   status `"erro"` só para aquele banco, com retry automático (backoff
   exponencial, `connectors/retry.py`) para falha transitória de rede/5xx.

## Relatório final

Ao fim de cada execução, gerar um resumo com:

- Empresa, banco, conta, competência.
- Status: ✅ baixado / ⚠️ indisponível no banco / ⏳ pendente de
  configuração / ❌ erro (com motivo resumido).
- Total de arquivos novos salvos vs. já existentes (duplicidade evitada).
- Alertas: certificado próximo do vencimento, banco sem integração ativa.

## Segurança

- Nenhuma credencial, token, certificado ou senha aparece no log ou no
  relatório — apenas nome do banco e status.
- Somente operações de leitura/consulta. Nunca iniciar pagamento,
  transferência, PIX ou qualquer movimentação financeira.
- Arquivos de certificado/chave usados durante a execução ficam apenas em
  memória/temporário e não são commitados no repositório.
