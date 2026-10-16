# Rotina: Fechamento Bancário Quinzenal — Todas as Empresas

Cópia de segurança da configuração da Rotina em claude.ai/code (sem nenhum
segredo). Se a Rotina sumir ou for apagada, recrie com estes dados — ver
`docs/RECUPERACAO.md`.

| Campo | Valor |
|---|---|
| ID (16/10/2026) | `trig_01FUV8WtqytyZ7ALRbicRkYU` |
| Agenda | `CRON_TZ=America/Sao_Paulo 5 0 1,16 * *` (dias 1 e 16, 00:05) |
| Sessão | nova a cada execução (`persist_session: false`) |
| Ambiente | `env_01Y2j6UdnhXHLqxdrGcx6DcL` (com as variáveis `DPA_*` e rede liberada para os bancos) |
| Repositório | `https://github.com/juniosilva2609/Site-dpa` |
| Conectores | Google Drive, Gmail |

## Prompt

```text
Sessão nova e não supervisionada: não faça perguntas, decida e execute. Fuso: America/Sao_Paulo (use a data de hoje em Brasília). Antes de tudo, na raiz do repositório Site-dpa já clonado, rode `git fetch origin && git checkout claude/monthly-bank-closure-automation-d1huvk && git pull` — todo o código, a config e a documentação do processo estão nessa branch. Nunca faça push para outra branch nem abra PR.

Execute o ciclo de fechamento bancário quinzenal de TODAS as empresas cadastradas, repositório Site-dpa, branch claude/monthly-bank-closure-automation-d1huvk.

1. Determine o período pela data de hoje:
   - Se hoje é dia 16: baixar o período do dia 01 ao dia 15 do mês corrente (competência MM-AAAA-Q1).
   - Se hoje é dia 01: baixar o período do dia 16 ao último dia do mês anterior (competência MM-AAAA-Q2, referente ao mês anterior).
   - Exceção: bancos com `periodicidade: mensal` em config/empresas.yaml (ex: C6 da Licitprint) NÃO rodam no dia 16; no dia 01 baixam o mês anterior inteiro (dia 01 ao último dia), com competência MM-AAAA (sem Q1/Q2). Isso já está implementado em connectors/runner.py:periodo_do_banco e connectors/nomenclatura.py:competencia — use-os, não recalcule à mão.
2. Leia config/empresas.yaml. Para CADA empresa listada (atualmente: dpa, c3s, licitprint — pode haver mais no futuro), processe apenas os bancos com integracao.status: ativo daquela empresa. Bancos com outro status (pendente_credenciais/pendente_cadastro) entram no relatório como "pendente de configuração" — não é erro, não interrompe o processo nem das outras empresas.
   - Bancos com integracao.status: manual (hoje: C6 Bank da Licitprint, enquanto o cadastro no C6 Developers não é aprovado) não são baixados pela automação: a equipe exporta o extrato do mês à mão. Somente no disparo do dia 01 (são mensais): garanta que a pasta do mês anterior existe no Drive — para a Licitprint, FINANCEIRO/{MM do mês anterior}/{nome_exibicao}/ (ex: FINANCEIRO/10/C6 Bank/), criando o que faltar — e inclua no relatório o lembrete: "C6 Bank (Licitprint): exportar o extrato de {mês por extenso} inteiro no internet banking e salvar em FINANCEIRO/{MM}/C6 Bank/". Não é erro.
3. Para cada banco ativo, siga docs/processo-fechamento.md: autenticar via connectors/<banco>.py usando as credenciais_env daquele banco específico (cada empresa tem suas próprias variáveis de ambiente, nomeadas de forma distinta em config/empresas.yaml — nunca misturar credenciais entre empresas), baixar PDF/OFX/Excel do período, montar o nome padronizado conforme docs/padrao-nomenclatura.md (incluindo o nome da empresa), checar duplicidade no Drive (use as ferramentas do conector Google Drive) antes de gravar (nunca sobrescrever sem confirmar), e salvar a partir da raiz `drive.extratos_id` de cada empresa, respeitando a estrutura de pastas própria dela (ver docs/processo-fechamento.md — DPA e C3S usam Extratos/{ano}/{mês}/{Banco}/, Licitprint usa FINANCEIRO/{mês}/{Banco}/ sem ano). Localizar ou criar a(s) pasta(s) que faltarem. Se as ferramentas do Google Drive não estiverem disponíveis nesta execução, registre isso claramente no relatório em vez de tentar contornar.
4. A colaboradora Vanessa (vanessaoliveira020691@gmail.com) já tem acesso de leitura permanente às pastas raiz de Extratos das três empresas (DPA, C3S e Licitprint) — o Júnio garantiu isso manualmente. Não é necessário compartilhar nada com ela durante o ciclo.
5. Nunca realizar pagamento, transferência ou qualquer operação financeira — somente consulta/leitura.
6. Nunca expor client_id, client_secret, certificado, chave ou senha em logs, relatório ou mensagens.
7. Ao final, monte um resumo curto agrupado por empresa → banco: status (baixado / indisponível no banco / pendente de configuração / manual / erro), quantos arquivos novos foram salvos e quantos já existiam (duplicidade evitada), mais os lembretes de bancos manuais. Poste o resumo como mensagem final da sessão E envie-o por e-mail (ferramenta do Gmail) para junioaraujo.adv@gmail.com, assunto 'Fechamento bancário <competência> — <OK | ATENÇÃO: erro em X>'. Se o Gmail não estiver disponível, registre isso na mensagem final.

Se para alguma empresa nenhum banco estiver com integracao.status: ativo ainda, apenas relate isso em uma linha para aquela empresa e siga para a próxima (não é necessário alertar ativamente todo ciclo enquanto estiver tudo pendente — apenas registre e siga).
```
