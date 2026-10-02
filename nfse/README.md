# NFS-e Automática

Sistema web simples para **emitir NFS-e de serviço prestado** (Sistema Nacional / Portal Nacional),
com **emissões padrão agendadas**: o sistema monta a nota alguns dias antes, você **confere e aprova**,
e na **data e hora marcadas** ele emite sozinho e entrega **PDF + XML** numa pasta e/ou por e-mail.

Prestador pré-configurado a partir da nota modelo: **JL Transportes Executivos Ltda**
(CNPJ 60.441.511/0001-70, Belo Horizonte-MG, Simples Nacional ME/EPP, código 16.02.01, cód. municipal 004).
Tudo pode ser alterado em *Configuração*.

## Como funciona (3 passos)

1. **Clientes** — cadastre quem recebe a nota (CPF ou CNPJ válidos; endereço é opcional).
2. **Agendamentos** — crie o modelo da emissão padrão: cliente, valor, descrição e quando
   (todo mês no dia X, toda semana, ou uma vez). A descrição aceita `{mes_ano}`, `{data}`, `{mes}`, `{ano}`,
   `{competencia}`, trocados em cada emissão.
3. **Conferir e aprovar** — a nota entra em *A conferir* N dias antes. Abra, veja a lista de conferências
   automáticas, ajuste o que precisar e clique **“Conferi: aprovar emissão”**. No horário, o sistema emite.

Nota **sem aprovação não é emitida** (a menos que o agendamento esteja marcado para aprovação automática).
Também é possível criar nota avulsa e usar **Emitir agora**.

### Estados de uma nota
| Estado | Significado |
|---|---|
| A conferir | Aguardando você conferir/aprovar |
| Aprovada | Sai sozinha no horário marcado |
| Emitida | NFS-e autorizada; PDF/XML disponíveis |
| Erro: corrigir | A Sefin recusou com uma mensagem clara; corrija e emita de novo |
| **Verificar** | A resposta da Sefin foi incerta (queda de conexão/timeout). **Não duplica**: ver abaixo |
| Atrasada | Passou da tolerância (padrão 6 h) sem sair; só emite com seu OK manual |
| Cancelada / Pulada | Cancelada na Sefin / ocorrência descartada |

## Conferências automáticas (bloqueiam a emissão)
CPF/CNPJ do cliente válido e cliente ativo · valor > 0 · descrição preenchida, sem `{campo}` sobrando e ≤ 1297
caracteres (acima disso o DANFSe oficial corta o texto) · CNPJ do prestador válido · certificado presente, aberto
com a senha, **não vencido** e com o **mesmo CNPJ** do prestador. Avisos (não bloqueiam): homologação, certificado
perto de vencer, valor diferente da última nota, possível nota duplicada no mês, endereço do cliente incompleto.
As mesmas conferências rodam **de novo no instante da emissão**.

## Por que é seguro contra nota duplicada
* Uma emissão por vez (trava no banco) e reserva atômica da nota; clique duplo não gera duas notas.
* O número da DPS (nDPS) é reservado antes do envio. Rejeição clara **devolve** o número.
* Falha de rede/timeout/HTTP 5xx → nota vai para **Verificar**; o número fica reservado e o sistema **nunca reemite sozinho**.
  Na tela você pode: *Conferir na Sefin*, *Tentar emitir de novo* (usa o **mesmo Id de DPS**, que a Sefin recusa se
  já existir) ou *Anexar o XML* baixado do Portal Nacional.
* Se o programa cair no meio de uma emissão, a nota fica em **Verificar** (nunca volta sozinha para a fila).
* Falha de pasta/e-mail **nunca** muda o estado fiscal da nota; a rotina tenta de novo e alerta.

## Início, Dashboard e Relatórios
* **Início:** resumo do mês (faturamento e variação), atalhos, o que precisa de atenção, próximas emissões e últimas notas.
* **Dashboard** (menu Dashboard): filtros de período (mês, trimestre, ano, 12 meses, personalizado), dados (produção/teste) e
  cliente. Indicadores (faturamento com variação vs período anterior, notas, ticket médio, clientes, pendências,
  inconsistências), **colunas** de faturamento por mês, **roscas** (pizza) de faturamento por cliente, por agendamento/avulsas
  e situação das notas, e ranking de clientes. Gráficos em SVG próprio, com dica ao passar o mouse e legenda/tabela com os valores.
* **Relatórios** (PDF e CSV para Excel, ou imprimir): *Notas emitidas* (para o contador), *Faturamento* (por mês e por
  cliente) e *Inconsistências*. Faturamento conta só notas emitidas (cancelada aparece à parte) pela data de emissão;
  notas de teste só entram se você escolher "Testes" ou "Todos".
* **Auditoria de inconsistências** (nada é corrigido sozinho): número de NFS-e e de DPS pulados, número de NFS-e repetido,
  notas possivelmente duplicadas (mesmo dia = erro; < 7 dias = atenção; cobrança mensal recorrente não alerta), notas em
  "Verificar"/atrasadas/presas, arquivos ou e-mails não entregues, arquivo sumido da pasta, cliente com CPF/CNPJ inválido,
  valor muito acima do habitual e agendamento mensal sem nota num mês.

## Sugestões e inconsistências
Menu **Sugestões** (e o link "Reportar problema nesta nota"): qualquer usuário escreve uma sugestão ou relata uma
inconsistência; fica registrada no sistema e **chega por e-mail em junioaraujo.adv@gmail.com** (troque com
`NFSE_SUPORTE_EMAIL`), já com usuário, tela, nota e ambiente. Sem SMTP/e-mail fora do ar, a mensagem fica *pendente* e é
reenviada automaticamente (o administrador vê a lista, pode reenviar e marcar como resolvida). Opcional:
`NFSE_SUPORTE_COPIA_ALERTAS=1` copia também os alertas do sistema para esse e-mail. Requer SMTP configurado.

## Entrega dos arquivos
*Configuração → 3.* Salva em `<pasta>/<ano>/<mês>/NFSE <nº> - <descrição> - <cliente>.pdf|xml`
(notas de teste levam o prefixo `HOMOLOG -`). E/ou envia por e-mail (PDF+XML anexos) para a lista que você definir e,
se marcado no cliente, para o e-mail dele. O PDF é o **DANFSe v1.0 idêntico ao modelo da JL** (Prefeitura de BH, com brasão), gerado a partir do XML oficial;
conferido caractere a caractere contra o PDF modelo (desvio máximo de 0,26 pt). O layout v2.0 da NT 008/2026 continua
disponível com `NFSE_DANFSE_LAYOUT=v2`. A pasta pode ser uma pasta sincronizada (Google Drive para computador, OneDrive etc.).

## Instalação
```bash
cd nfse
pip install -r requirements.txt
export NFSE_ADMIN_SENHA='uma-senha-forte'   # cria o administrador "admin" no 1º start (ou use /primeiro-acesso)
export NFSE_CERT_SENHA='senha-do-certificado'
export NFSE_DEV=1                           # SÓ para teste local em HTTP
python run.py                               # http://127.0.0.1:8000
```
Em produção: `gunicorn wsgi:app --workers 1 --threads 4 --timeout 120` (ver `Procfile` e o `render.yaml` na raiz do repositório), sempre com HTTPS.
**Use 1 worker**: o agendador roda numa thread do próprio servidor (há trava no banco, mas 1 processo é o suportado).
Sem servidor sempre ligado? `python run.py ciclo` roda um ciclo e sai (use no cron a cada minuto).

### Variáveis de ambiente (segredos nunca vão para banco/tela/log/git)
| Variável | Para quê |
|---|---|
| `NFSE_CERT_SENHA` | Senha do certificado e-CNPJ A1 (obrigatória) |
| `NFSE_CERT_PATH` | Caminho do .pfx (padrão: o enviado na tela Configuração, em `<dados>/certificado.pfx`) |
| `NFSE_DATA_DIR` | Pasta persistente do banco, certificado e backups (padrão `nfse/data`) |
| `NFSE_SAIDA_DIR` | Pasta padrão dos PDF/XML (padrão `nfse/saida`) |
| `SECRET_KEY` | Chave das sessões (se ausente, é gerada e guardada em `<dados>/secret_key`) |
| `NFSE_ADMIN_USER` / `NFSE_ADMIN_SENHA` | Cria o administrador inicial |
| `NFSE_SETUP_CODE` | Se definida, `/primeiro-acesso` exige esse código (recomendado em servidor público) |
| `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_SENHA` `SMTP_FROM` `SMTP_SSL` | Envio de e-mail (Gmail: porta 587 + senha de app) |
| `NFSE_PROXY=1` | Atrás de proxy (Render): usa o IP/https reais |
| `NFSE_BACKUP_EMAIL=1` | Envia o backup diário compactado por e-mail |
| `NFSE_DANFSE_LAYOUT` | `v1` (padrão, igual ao modelo da JL) ou `v2` (NT 008/2026) |
| `NFSE_SUPORTE_EMAIL` / `NFSE_SUPORTE_COPIA_ALERTAS` | Destino das sugestões (padrão: junioaraujo.adv@gmail.com) / copia alertas a ele |
| `NFSE_DEV=1` | Só desenvolvimento local em HTTP (desliga o cookie “Secure”) |

## Roteiro para entrar em produção
1. **Configuração → Certificado**: envie o .pfx; defina `NFSE_CERT_SENHA`. Clique *Testar conexão com a Sefin* e *Testar convênio do município*.
2. Confira o cadastro do prestador e o código **16.02.01 / 004**; defina pasta e e-mails; *Testar gravação* e *E-mail de teste*.
3. Em **homologação**, emita 1 nota avulsa (“Emitir agora”), abra o PDF e compare com o modelo da JL.
4. Passe para **produção** (digite `PRODUCAO`), emita **1 nota real de teste** e confira no Portal Nacional.
5. Só então crie os agendamentos — comece **sem** aprovação automática.

## Rotinas de prevenção (a cada ~15 min)
Alertas no painel (e por e-mail, uma vez cada): certificado vencendo (60/30/15/7 dias) ou vencido · nota não conferida
a menos de 24 h do horário · nota atrasada · nota em *Verificar* · entrega de arquivos que falhou · agendador parado.
Backup diário do banco (14 dias) em `<dados>/backups` e em `<pasta de saída>/_backup`, **com teste de restauração**
(integrity_check + contagem de registros; cópia que falha é descartada e gera alerta). Opcional: `NFSE_BACKUP_EMAIL=1`
envia a cópia compactada por e-mail (o banco tem CPF/CNPJ de clientes: use um e-mail seu). Os PDF/XML também ficam
na pasta de saída e o XML de qualquer nota pode ser rebaixado da Sefin pela chave de acesso.
* Fazer backup agora: `python run.py backup` · Restaurar (servidor parado): `python run.py restaurar nfse-AAAAMMDD.db`
  (o banco atual é guardado ao lado antes de substituir).
* **O certificado não entra no backup**: guarde o `.pfx` e a senha em local seguro.

## Segurança
* Senha do certificado só em variável de ambiente; arquivo `.pfx` com permissão 600; chaves temporárias de mTLS em
  pasta 700 apagada ao fim de cada chamada. `*.pfx`/`*.p12` no `.gitignore`.
* Login com senha em hash (scrypt), limite de 5 tentativas por 5 min, sessão com cookie HttpOnly + SameSite + Secure,
  CSRF em todo POST, CSP restritiva, `X-Frame-Options: DENY`, `no-store`. Perfis: operador (emite) e administrador
  (configura e cancela). Usuário desativado perde o acesso na hora.
* XML anexado pelo usuário é lido sem DTD/entidades (bloqueia XXE) e limitado a 5 MB; SQL sempre parametrizado.
* Primeiro acesso: sem `NFSE_SETUP_CODE`/`NFSE_ADMIN_SENHA`, só a própria máquina cria o administrador.
* Atrás do proxy do Render defina `NFSE_PROXY=1` (IP real no limite de login). Sempre use HTTPS.
* Trocar senhas que já circularam em conversa/e-mail (inclusive a do certificado, se possível).

## Testes
```bash
pip install -r requirements-dev.txt && python -m pytest -q && ruff check .
```
Cobrem DPS (Simples/normal, id, regras de rejeições reais), assinatura (válida e à prova de adulteração), agenda,
conferências, emissão (sucesso, rejeição, falha ambígua, reenvio, anexar XML, cancelamento), agendador, entrega e telas.

## Validado contra a Sefin de homologação (com o e-CNPJ da JL)
Conexão mTLS, assinatura, emissão (nota nº 1 de teste), `cTribMun` 004, consulta por DPS (`GET /dps/{id}`), download
do XML (`GET /nfse/{chave}`), recusa de DPS repetida (E0014, base da proteção anti-duplicidade) e cancelamento.
O PDF gerado foi conferido contra o modelo da JL.
* **Belo Horizonte exige a Inscrição Municipal na DPS** (E0116); ela é enviada quando preenchida em Configuração
  (em municípios que a proíbem, como Ibirité, deixe em branco).

## O que ainda depende de você
* Enviar o `.pfx` pela tela Configuração, definir `NFSE_CERT_SENHA` e passar para **produção** (digitando `PRODUCAO`).
* Emitir **1 nota real de teste** e conferir no Portal Nacional antes de criar os agendamentos.
* Configurar pasta de saída, e-mails e SMTP (não há credenciais de e-mail neste ambiente, então o envio por e-mail
  só foi testado com simulação).
* A tabela de cidades/UF e o motor do DANFSe (`app/fiscal/danfse.py`, fontes e logo) vieram do sistema anterior
  (com dois ajustes: código municipal e quebras de linha da descrição, como na nota modelo).
