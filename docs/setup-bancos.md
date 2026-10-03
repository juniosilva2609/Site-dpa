# Configuração de acesso a cada banco (API oficial, somente leitura de extrato)

Cada banco exige um cadastro feito por você diretamente (login com CPF/CNPJ do
titular da conta). Eu não consigo acessar o internet banking — só configuro o
que for gerado nesse cadastro, como segredo neste ambiente (nunca no
repositório).

Peça sempre o escopo mínimo: **consulta de extrato/saldo**. Nunca solicite
escopos de pagamento, transferência, PIX ou emissão de cobrança para esta
automação.

## Pré-requisito de ambiente: liberar a rede (✅ resolvido em 16/09/2026)

Descobrimos (testando o Sicoob) que este ambiente de execução rodava com
uma política de rede restritiva ("trusted network access") que bloqueava
qualquer chamada de saída para domínios de banco — a chamada nem chegava a
sair do contêiner, então nenhuma credencial resolvia isso sozinha. O
usuário trocou a política de rede do ambiente (em claude.ai/code →
configurações do ambiente) e confirmamos, com uma chamada real à API do
Sicoob, que a saída para `auth.sicoob.com.br` e `api.sicoob.com.br` agora
funciona. Deixando registrado aqui: se um novo ambiente for criado do zero
para esta automação, esse mesmo ajuste de rede precisa ser feito de novo
antes de qualquer banco funcionar.

## Banco Inter

Fonte: [ajuda.inter.co](https://ajuda.inter.co/conta-digital-pessoa-juridica/como-cadastrar-uma-api) — disponível apenas para conta PJ (não PF/MEI).

1. Acesse o Internet Banking PJ do Inter.
2. **Soluções para sua empresa → Nova integração**.
3. Dê um nome (ex: `Automacao Fechamento Bancario`), escolha a conta corrente
   e o escopo de **extrato**.
4. Baixe o **Certificado (.crt)** e a **Chave (.key)** gerados.
5. Anote o **ClientID** e o **ClientSecret** exibidos.
6. Aguarde o status mudar para **Ativo** (leva alguns minutos).
7. Certificado válido por 12 meses — a automação deve alertar antes do
   vencimento.

Recomendação: crie uma integração **nova e separada** da que já está em uso
pelo ERP, para não depender do ciclo de vida daquele certificado.

Variáveis de ambiente esperadas (ver `config/empresas.yaml`):
`DPA_INTER_CLIENT_ID`, `DPA_INTER_CLIENT_SECRET`, `DPA_INTER_CERT_CRT`,
`DPA_INTER_CERT_KEY`.

**✅ Ativado e testado em 16/09/2026** — contrato confirmado por chamada real:
- Token: `POST /oauth/v2/token` (client_id + client_secret +
  grant_type=client_credentials + escopo `extrato.read`, mTLS).
- Lista de lançamentos (JSON): `GET /banking/v2/extrato?dataInicio=...&dataFim=...`.
- PDF nativo: `GET /banking/v2/extrato/exportar` (mesmos parâmetros) —
  devolve `{"pdf": "<base64>"}`. Parâmetros de formato (`tipoArquivo`,
  `formato`) são ignorados: esse endpoint **só** devolve PDF. **Não é
  usado por este conector** — vem com fontes embutidas grandes demais
  para o limite de upload por chamada do Google Drive usado aqui.
- **Não há exportação nativa de OFX nem Excel** nessa API — o conector
  (`connectors/inter.py`) gera OFX, Excel e também o **PDF salvo no
  Drive** localmente a partir do mesmo JSON de transações
  (`connectors/inter_pdf.py`, via reportlab — fontes padrão, sem
  embutimento, arquivo bem menor). Esse PDF não é o extrato oficial do
  banco; o rodapé do documento deixa isso explícito. O PDF nativo pode
  ser obtido direto no app/site do Inter quando o documento oficial for
  necessário.
- Agência e conta já informadas (`0001` / `3620284-3`), preenchidas em
  `config/empresas.yaml`.

## Sicoob

Fonte: [developers.sicoob.com.br](https://developers.sicoob.com.br/portal/#!/login).

1. Pré-requisito: certificado digital **ICP-Brasil (e-CNPJ)** da DPA, em dois
   formatos: `.pfx` (certificado A1, com senha) e `.cer` (chave pública).
2. No internet banking Sicoob, algumas cooperativas exigem liberar o acesso
   primeiro em **Outras Opções → Computadores → Gerenciamento de
   Computadores** — confirme se aparece essa exigência para a sua conta.
3. Crie login no Portal Developers Sicoob.
4. Cadastre uma nova aplicação/API: nome, conta corrente vinculada,
   descrição.
5. Selecione o produto **Conta Corrente** (extrato/saldo).
6. Envie o `.cer` para gerar o **ClientID**.
7. O `.pfx` (com senha) é usado depois na autenticação mTLS das chamadas.
8. Converta o `.pfx` uma única vez para o formato que o conector usa
   (`connectors/sicoob.py` já espera isso). Certificados e-CNPJ mais
   antigos usam criptografia RC2, que o OpenSSL 3.x não abre sem a flag
   `-legacy`:
   ```
   openssl pkcs12 -legacy -in certificado.pfx -clcerts -nokeys -out sicoob_cert.pem
   openssl pkcs12 -legacy -in certificado.pfx -nocerts -nodes -out sicoob_key.pem
   ```

Variáveis de ambiente esperadas:
`DPA_SICOOB_CLIENT_ID`, `DPA_SICOOB_CERT_PEM` (caminho do .pem gerado acima),
`DPA_SICOOB_CERT_KEY` (caminho do .pem da chave).

## Santander

Fonte: [Santander Developers Brasil](https://developer.santander.com.br).

1. Acesse developer.santander.com.br → **Entrar → Entrar como administrador**
   com os dados da empresa.
2. **Criar Aplicação em Produção**.
3. Selecione a API **Balance and Extract** (saldo e extrato).
4. Informe um nome para a aplicação e envie o certificado digital.
   O certificado precisa: ser x509 v3, ter no mínimo 90 dias de validade,
   estar em formato PEM, ter "Key Usage" com assinatura digital habilitada
   e "Enhanced Key Usage" incluindo Client Authentication
   (`1.3.6.1.5.5.7.3.2`) — inclua também os arquivos de certificado raiz e
   intermediário da cadeia.
5. Ao concluir, são gerados **ClientID** e **ClientSecret**.

Variáveis de ambiente esperadas:
`DPA_SANTANDER_CLIENT_ID`, `DPA_SANTANDER_CLIENT_SECRET`,
`DPA_SANTANDER_CERT_CRT`, `DPA_SANTANDER_CERT_KEY`.

**✅ Ativado e testado em 30/09/2026** — aplicação "Plataforma ERP-DPA API
SANTAND" (produto "Saldo e Extrato" / API "Bank Account Information" v1.0.0),
contrato confirmado por chamada real:
- Token: `POST /auth/oauth/v2/token` (host `trust-open.api.santander.com.br`,
  client_id + client_secret + grant_type=client_credentials, mTLS).
- Extrato de conta Santander própria: combina
  `GET /bank_account_information/v1/transactions/{agencia.conta}`
  (lançamentos efetivos) e `.../provisioneds/{agencia.conta}` (lançamentos
  provisionados) — `{agencia.conta}` é a agência (4 dígitos) + "." + conta
  com dígito só números, zero-padded a 12 dígitos (ex.: `4177.000130008210`).
  Cada chamada também exige o header `X-Application-Key: <client_id>`.
- **Não há exportação nativa de PDF/OFX/Excel** nessa API — o conector
  (`connectors/santander.py`) gera os três localmente a partir do JSON de
  transações (`connectors/santander_pdf.py` para o PDF, reportlab, mesmo
  padrão do Inter/Sicoob).
- Contrato completo (parâmetros, paginação, divergências entre a
  especificação técnica e a doc funcional do Portal) documentado no
  docstring de `connectors/santander.py`.

## C6 Bank (Licitprint) — 🖐️ ponte manual (cadastro no C6 Developers em andamento)

Fonte: [C6 Developers](https://developers.c6bank.com.br/). Conta PJ (C6
Empresas), agência `0001`, conta `428529984`. Autenticação OAuth2
`client_credentials` + mTLS (certificado .crt + chave .key emitidos pelo
próprio C6), mesmo modelo do Inter/Santander. A rede deste ambiente já
alcança os hosts da API do C6 (`baas-api.c6bank.info`), conferido em
02/10/2026.

**O C6 exige parceiro.** Em 03/10/2026 confirmamos que o campo
"Parceiro" de Integrações via API → Nova chave (internet banking) é
obrigatório: a chave fica vinculada a um parceiro cadastrado no C6. Por isso
a própria Licitprint precisa se cadastrar como parceira:

1. Cadastro da Licitprint no portal C6 Developers (CNPJ, e-mail
   acompanhado, responsável técnico). Uso declarado: integração própria,
   somente consulta de saldo/extrato da conta da própria empresa.
2. E-mails de onboarding / Jornada de Integração com credenciais de
   **sandbox** (ClientID, ClientSecret, certificado de teste).
3. Implementar `connectors/c6.py` e testar no sandbox.
4. Enviar as evidências de teste pedidas pelo C6 (sem segredos).
5. Assinar o termo de responsabilidade de uso das APIs.
6. Aprovação para produção → no internet banking, Integrações via API →
   Nova chave, selecionar a Licitprint no campo Parceiro, marcar **somente
   saldo/extrato** e baixar o .zip (.crt/.key) na hora (não dá para baixar
   de novo).

Há relatos de espera de semanas a cerca de 2 meses na liberação.

Variáveis de ambiente esperadas quando virar API (ver
`config/empresas.yaml`): `DPA_LICITPRINT_C6_CLIENT_ID`,
`DPA_LICITPRINT_C6_CLIENT_SECRET`, `DPA_LICITPRINT_C6_CERT_CRT`,
`DPA_LICITPRINT_C6_CERT_KEY`.

### Ponte manual (até a aprovação)

`integracao.status: manual` em `config/empresas.yaml`. Todo mês:

1. No internet banking do C6 Empresas, exportar o extrato do **mês
   anterior inteiro** (dia 01 ao último dia) em PDF — e em OFX/Excel, se o
   C6 oferecer.
2. Salvar em `FINANCEIRO/{MM}/C6 Bank/` (mesma pasta que a equipe já
   usava). A Rotina do dia 1 cria essa pasta se ela ainda não existir e
   lembra no relatório.
3. A auditoria mensal do dia 2 abre o PDF, confere se o período no texto
   cobre o mês inteiro e avisa se estiver faltando ou errado. Os nomes de
   arquivo da equipe não são alterados.

Periodicidade **mensal**: quando virar API, roda só no disparo do dia 01,
baixando o mês anterior inteiro (competência `MM-AAAA`).

## Como as credenciais ficam guardadas neste ambiente

Este ambiente não oferece um mecanismo de "variável de ambiente" permanente
configurável por mim. Na prática, guardo cada credencial num arquivo local
em `~/.dpa-secrets/<banco>.env` (fora do repositório, com permissão 600,
nunca versionado — o `.gitignore` do repo também bloqueia qualquer `.env`,
`.pem`, `.crt`, `.key` ou `.pfx` por segurança extra). A Rotina agendada
reaproveita esta mesma sessão a cada disparo, então esse arquivo continua
disponível de execução para execução; na hora de rodar um conector, eu
carrego essas variáveis a partir dali antes de chamar a API do banco.

## Como me repassar as credenciais

Não cole client_secret, senha de certificado ou o conteúdo do .crt/.key/.pfx
diretamente na conversa se puder evitar. Client ID sozinho costuma ser
seguro de compartilhar (o próprio Sicoob confirma isso), mas para
certificado/segredo eu confirmo com você antes de armazenar.
