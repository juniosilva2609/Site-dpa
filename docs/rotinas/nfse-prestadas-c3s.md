# Rotina: NFS-e prestadas da C3S → planilha de importação do Alterdata

> **Execução atual (desde 17/10/2026): tarefa agendada no PC do Júnio**, não a
> Rotina da nuvem. O Portal Nacional (`adn.nfse.gov.br`) derrubou a conexão
> (`Connection reset by peer`) a partir do ambiente cloud mesmo com rede
> completa; do PC funciona. A Rotina da nuvem (`trig_01VckNu8CQmo8NhzTauMeW6K`)
> foi **reaproveitada como verificadora** (ver abaixo).
>
> - Tarefa do Windows: **`NFSe C3S - Alterdata`**, todo dia 1 às 07:00; se o
>   PC estiver desligado, roda ao ligar (`StartWhenAvailable`).
> - Script: `C:\Users\Junio\ferramentas-nfse-c3s\rodar-nfse-c3s.ps1`
>   (`-Competencia AAAA-MM` para refazer um mês). Usa o clone
>   `C:\Users\Junio\Site-dpa-nfse` (faz `git pull` antes) e o e-CNPJ em PEM em
>   `ferramentas-nfse-c3s\cert` (acesso só do usuário).
> - Grava em `G:\Drives compartilhados\C3S Interno\C3S - Interno\Financeiro C3S\Extratos\AAAA\MM\`
>   e não sobrescreve. Log em `ferramentas-nfse-c3s\logs\AAAA-MM.log`.
> - **Aviso de erro:** se a execução falhar, aparece um balão do Windows na tela;
>   além disso, a Rotina `trig_01VckNu8CQmo8NhzTauMeW6K` ("Verificador NFS-e C3S")
>   roda nos dias 1 e 3 às 12:00, confere se o arquivo do mês está no Drive e,
>   se não estiver, manda e-mail para junioaraujo.adv@gmail.com.
> - **Reinstalar do zero** (PC novo, pasta apagada): `git clone --branch
>   claude/monthly-bank-closure-automation-d1huvk https://github.com/juniosilva2609/Site-dpa.git`,
>   depois `powershell -ExecutionPolicy Bypass -File ferramentas\nfse-c3s\instalar-nfse-c3s.ps1`
>   (pede a senha do e-CNPJ; o .pfx fica em `G:\Drives compartilhados\C3S Assessoria Contábil\CERTIFICADO C3S`).
> - Se o e-CNPJ for renovado (vence 21/08/2027), regere os PEM em `cert\`.

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
Sessão nova e não supervisionada: não faça perguntas, decida e execute. Fuso: America/Sao_Paulo. Antes de tudo, na raiz do repositório Site-dpa já clonado, rode `git fetch origin && git checkout claude/monthly-bank-closure-automation-d1huvk && git pull` e `python -m pip install -q -r requirements.txt` (use sempre `python -m pip`, para instalar no mesmo Python que roda o script). Nunca faça push para outra branch nem abra PR.

Gere a planilha de importação do Alterdata com as NFS-e de serviços PRESTADOS pela C3S Assessoria Contábil no mês anterior (competência = mês anterior à data de hoje em Brasília; no dia 01/01 é dezembro do ano anterior). Detalhes das regras em docs/rotinas/nfse-prestadas-c3s.md.

1. Rode `python -m nfse.prestadas AAAA-MM /tmp/saida` (AAAA-MM = competência). Ele lê o Portal Nacional da NFS-e com o certificado da C3S (variáveis DPA_C3S_NFSE_CERT e DPA_C3S_NFSE_KEY), exclui canceladas/substituídas e grava `IMPORT ALTERDATA NFSE SERV PREST MM-AAAA.xlsx`; a última linha impressa é um JSON com notas, total_bruto, iss_retido e clientes_sem_conta. Se falhar por rede/certificado, não tente contornar: reporte o erro exato (a última linha do traceback, ex.: ProxyError/ConnectionError/403 e o host).
2. No Google Drive, a pasta do ano 2026 é `1572IDs5W-hK0_Ez78WDUlgyUa7GKyYYb` (para outro ano, procure a pasta do ano ao lado, na pasta pai `1XjM8oydVEI5sgIuk07je4wZsicF5XftS`). Dentro dela, ache a subpasta do mês (título `MM`, ex.: `09`); crie se não existir.
3. Cheque duplicidade: se já existir arquivo com esse título na subpasta, NÃO sobrescreva; reporte que já existia. Senão, envie o .xlsx (create_file, conteúdo em base64), confira o tamanho/sha256 do que subiu contra o local e refaça até 3 vezes se divergir.
4. Envie e-mail (Gmail) para junioaraujo.adv@gmail.com, assunto 'NFS-e prestadas C3S MM-AAAA — OK' ou 'ATENÇÃO: <problema>', com: nº de notas, total bruto, ISS retido, notas excluídas por cancelamento/substituição, link do arquivo e, se houver, os clientes sem conta (CNPJ e nome) para cadastrar em nfse/contas_clientes_c3s.json. Poste o mesmo resumo como mensagem final.

Somente leitura no Portal Nacional: nunca emita, cancele ou altere nota. Nunca exponha certificado, chave ou senha em logs, relatório ou mensagens.
```

## Licitprint (mesma planilha, desde 17/10/2026)

- Tarefa do Windows **`NFSe Licitprint - Alterdata`**, dia 1 às 07:10:
  `rodar-nfse-c3s.ps1 -Empresa licitprint` (refazer um mês: `-Competencia AAAA-MM`).
- Prestador: Licitprint Comunicação Visual Ltda, CNPJ 65.942.303/0001-79. Certificado: gerar os PEM com
  `ferramentas\nfse-c3s\preparar-certificado.ps1 -Empresa licitprint -Pfx "J:\Meu Drive\Certificado Digital\LICITPRINT COMUNICACAO VISUAL LTDA65942303000179.pfx"`
  (pede a senha no terminal).
- Grava em `J:\Meu Drive\CONTABILIDADE\FINANCEIRO\MM\` (= pasta FINANCEIRO do Drive da Licitprint, sem pasta de ano).
- Contas: débito = cliente (`nfse/plano_clientes_licitprint.json`, por nome, e `nfse/contas_clientes_licitprint.json`,
  por CNPJ); nota sem tomador identificado = CONSUMIDOR FINAL (35); **crédito = 1652** (prestação de serviços).
  A conta do ISS retido da Licitprint não foi informada: se houver nota com ISS retido, a linha sai em amarelo.
- Setembro/2026: 7 NFS-e válidas, R$ 11.438,82; as nº 31 e 36 foram canceladas/substituídas e ficaram de fora.
- O Verificador na nuvem (dias 1 e 3, 12:00) confere as duas empresas.
