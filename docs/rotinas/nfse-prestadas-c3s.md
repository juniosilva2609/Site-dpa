# Rotina: NFS-e prestadas da C3S → planilha de importação do Alterdata

Cópia de segurança da configuração (sem nenhum segredo). Se a Rotina sumir,
recrie com estes dados — ver `docs/RECUPERACAO.md`.

| Campo | Valor |
|---|---|
| ID (17/10/2026) | `trig_01VckNu8CQmo8NhzTauMeW6K` |
| Agenda | `CRON_TZ=America/Sao_Paulo 20 0 1 * *` (dia 1, 00:20) |
| Sessão | nova a cada execução (`persist_session: false`) |
| Ambiente | `env_01Y2j6UdnhXHLqxdrGcx6DcL` (precisa liberar `adn.nfse.gov.br` na rede e ter `DPA_C3S_NFSE_CERT` / `DPA_C3S_NFSE_KEY`) |
| Repositório | `https://github.com/juniosilva2609/Site-dpa` |
| Conectores | Google Drive, Gmail |
| Destino | Drive da C3S, pasta `2026` (`1572IDs5W-hK0_Ez78WDUlgyUa7GKyYYb`) → subpasta do mês (`09`, `10`…) |

## Regras da planilha

- Só NFS-e **prestadas** pela C3S (CNPJ 47.553.447/0001-51), emitidas no mês
  anterior, **válidas**: ficam de fora as que têm evento de cancelamento
  (`e101101`), cancelamento por substituição (`e105102`, aponta a nota
  substituída) ou cancelamento deferido (`e105104`).
- Colunas: DATA EMISSAO, NUM NFSE, VALOR, CLIENTE, HISTORICO CONTABIL,
  CONTA DEBITO, CONTA CREDITO.
- Linha da nota: valor bruto, débito = conta do cliente, crédito = 861,
  histórico `PREST. SERV. CONF. NFSE <n> CLIENTE <nome>`.
- ISS retido pelo tomador (`tpRetISSQN = 2`): linha logo abaixo, mesma data e
  nota, valor = ISS, débito 1393, crédito = conta do cliente, histórico
  `ISS RETIDO SERV. PREST. CONF. NFSE <n> CLIENTE <nome>`.
- Contas dos clientes: `nfse/contas_clientes_c3s.json` (por CNPJ). Cliente
  novo sem conta sai com débito em branco (linha amarela) e entra no aviso.
- Nome: `IMPORT ALTERDATA NFSE SERV PREST MM-AAAA.xlsx`.

## Prompt

```text
Sessão nova e não supervisionada: não faça perguntas, decida e execute. Fuso: America/Sao_Paulo. Antes de tudo, na raiz do repositório Site-dpa já clonado, rode `git fetch origin && git checkout claude/monthly-bank-closure-automation-d1huvk && git pull` e `pip install -r requirements.txt`. Nunca faça push para outra branch nem abra PR.

Gere a planilha de importação do Alterdata com as NFS-e de serviços PRESTADOS pela C3S Assessoria Contábil no mês anterior (competência = mês anterior à data de hoje em Brasília; no dia 01/01 é dezembro do ano anterior). Detalhes das regras em docs/rotinas/nfse-prestadas-c3s.md.

1. Rode `python -m nfse.prestadas AAAA-MM /tmp/saida` (AAAA-MM = competência). Ele lê o Portal Nacional da NFS-e com o certificado da C3S (variáveis DPA_C3S_NFSE_CERT e DPA_C3S_NFSE_KEY), exclui canceladas/substituídas e grava `IMPORT ALTERDATA NFSE SERV PREST MM-AAAA.xlsx`; a última linha impressa é um JSON com notas, total_bruto, iss_retido e clientes_sem_conta. Se falhar por rede/certificado, não tente contornar: reporte o erro exato.
2. No Google Drive, a pasta do ano 2026 é `1572IDs5W-hK0_Ez78WDUlgyUa7GKyYYb` (para outro ano, procure a pasta do ano ao lado, na pasta pai `1XjM8oydVEI5sgIuk07je4wZsicF5XftS`). Dentro dela, ache a subpasta do mês (título `MM`, ex.: `09`); crie se não existir.
3. Cheque duplicidade: se já existir arquivo com esse título na subpasta, NÃO sobrescreva; reporte que já existia. Senão, envie o .xlsx (create_file, conteúdo em base64), confira o tamanho/sha256 do que subiu contra o local e refaça até 3 vezes se divergir.
4. Envie e-mail (Gmail) para junioaraujo.adv@gmail.com, assunto 'NFS-e prestadas C3S MM-AAAA — OK' ou 'ATENÇÃO: <problema>', com: nº de notas, total bruto, ISS retido, notas excluídas por cancelamento/substituição, link do arquivo e, se houver, os clientes sem conta (CNPJ e nome) para cadastrar em nfse/contas_clientes_c3s.json. Poste o mesmo resumo como mensagem final.

Somente leitura no Portal Nacional: nunca emita, cancele ou altere nota. Nunca exponha certificado, chave ou senha em logs, relatório ou mensagens.
```
