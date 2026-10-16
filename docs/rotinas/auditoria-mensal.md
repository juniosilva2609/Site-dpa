# Rotina: Auditoria Mensal — Fechamento Bancário

Cópia de segurança da configuração da Rotina em claude.ai/code (sem nenhum
segredo). Se a Rotina sumir ou for apagada, recrie com estes dados — ver
`docs/RECUPERACAO.md`.

| Campo | Valor |
|---|---|
| ID (16/10/2026) | `trig_01GHDLo2LDxZ8gKLTXepxyNd` |
| Agenda | `CRON_TZ=America/Sao_Paulo 10 0 2 * *` (dia 2, 00:10) |
| Sessão | nova a cada execução (`persist_session: false`) |
| Ambiente | `env_01Y2j6UdnhXHLqxdrGcx6DcL` |
| Repositório | `https://github.com/juniosilva2609/Site-dpa` |
| Conectores | Google Drive, Gmail |

## Prompt

```text
Sessão nova e não supervisionada: não faça perguntas, decida e execute. Fuso: America/Sao_Paulo. Antes de tudo, na raiz do repositório Site-dpa já clonado, rode `git fetch origin && git checkout claude/monthly-bank-closure-automation-d1huvk && git pull`. Nunca faça push para outra branch nem abra PR.

Rode a auditoria mensal do sistema de fechamento bancário (repositório Site-dpa, branch claude/monthly-bank-closure-automation-d1huvk). Isto é uma verificação separada da Rotina quinzenal que já baixa os extratos — o objetivo aqui é conferir que nada ficou pendente ou quebrado no mês anterior.

1. Rode `pytest` na raiz do repositório. Qualquer teste falhando é uma inconsistência de código.
2. Valide que config/empresas.yaml carrega sem erro (connectors.config.carregar_empresas) — pega campo obrigatório faltando ou mal formatado.
3. Para cada empresa/banco com integracao.status: ativo em config/empresas.yaml, confira no Google Drive (a partir de drive.extratos_id de cada empresa) se os 3 arquivos (PDF, OFX, Excel) do mês anterior (mês = mês anterior à data de hoje) existem de fato nas pastas — use as ferramentas do Google Drive (search_files por título, sintaxe `title contains '...'`) para confirmar, não assuma pelo código. Bancos quinzenais (padrão) têm DUAS competências: MM-AAAA-Q1 e MM-AAAA-Q2 (6 arquivos). Bancos com `periodicidade: mensal` têm UMA competência: MM-AAAA, sem Q1/Q2 (3 arquivos). Esse é o ponto mais importante: nunca deixar passar batido um extrato que devia ter sido salvo e não foi.
4. Bancos com integracao.status: manual (hoje: C6 Bank da Licitprint, enquanto o cadastro no C6 Developers não é aprovado) — o extrato é exportado à mão pela equipe, com nome livre. Liste a pasta do banco no mês anterior (Licitprint: FINANCEIRO/{MM}/{nome_exibicao}/, ex: FINANCEIRO/09/C6 Bank/, usando search_files com `parentId = '<id da pasta>'`), abra o(s) PDF(s) com read_file_content e confirme que o texto traz o período do mês inteiro (ex: "Período • 1 de setembro de 2026 até 30 de setembro de 2026") e a conta cadastrada em empresas.yaml. Se a pasta não existir, estiver vazia, ou o período/conta não baterem: avise o usuário dizendo exatamente o que falta. Não renomeie nem mova os arquivos da equipe — só confira.
5. Bancos com integracao.status pendente (pendente_cadastro/pendente_credenciais) — reporte só como lembrete informativo, não como erro, a menos que o usuário já tenha indicado que deveria estar ativo.
6. Revise rapidamente se config/empresas.yaml, docs/processo-fechamento.md e o código em connectors/ ainda estão consistentes entre si (nenhuma mudança manual recente quebrou algo).

Se tudo estiver certo (testes passando, config válida, todos os arquivos esperados presentes no Drive, inclusive o extrato manual): NÃO precisa interromper o usuário — apenas conclua a execução com um resumo curto como mensagem final, sem e-mail.

Se encontrar QUALQUER inconsistência (teste falhando, config quebrada, arquivo que deveria existir e não existe, extrato manual faltando ou com período errado, erro de conector, etc.): avise o usuário imediatamente por e-mail (ferramenta do Gmail) para junioaraujo.adv@gmail.com, assunto '⚠️ Auditoria fechamento bancário <MM-AAAA> — pendências', dizendo exatamente o que está errado/faltando e o que precisa ser feito para corrigir — não deixe para o próximo ciclo. Repita o mesmo conteúdo como mensagem final da sessão.

Nunca exponha credencial, token, certificado ou senha na mensagem ao usuário nem em nenhum log.
```
