# Processo de fechamento bancário quinzenal — roteiro de execução

Este é o roteiro que a Rotina agendada segue a cada disparo (dia 1 e dia 16
de cada mês). Só cobre bancos com `integracao.status: ativo` em
`config/empresas.yaml` — qualquer outro valor de status (pendente de
cadastro, pendente de certificado, bloqueado por rede etc.) entra no
relatório como pendente, sem travar os outros bancos.

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
2. **Autenticar** na API do banco (OAuth2 + certificado mTLS), usando as
   variáveis de ambiente listadas em `config/empresas.yaml`.
3. **Consultar o extrato** do período para a conta cadastrada.
4. **Baixar em PDF, OFX e Excel** (quando o banco oferecer o formato).
5. **Montar o nome padronizado** conforme `docs/padrao-nomenclatura.md`.
6. **Localizar/criar a pasta de destino** no Drive:
   `01.2 Bancário/Extratos/{ano}/{mês}/{Banco}/` (a partir dos IDs fixos em
   `config/empresas.yaml`; mês e banco são localizados por nome ou criados
   se ainda não existirem).
7. **Checar duplicidade** antes de gravar (ver regra de não sobrescrita).
8. **Registrar no log** desta execução: arquivo baixado / indisponível
   naquele banco / erro (com a causa, nunca com dado sensível).
9. Repetir para os próximos bancos/empresas.

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
