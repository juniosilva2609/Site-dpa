# Configuração de acesso a cada banco (API oficial, somente leitura de extrato)

Cada banco exige um cadastro feito por você diretamente (login com CPF/CNPJ do
titular da conta). Eu não consigo acessar o internet banking — só configuro o
que for gerado nesse cadastro, como segredo neste ambiente (nunca no
repositório).

Peça sempre o escopo mínimo: **consulta de extrato/saldo**. Nunca solicite
escopos de pagamento, transferência, PIX ou emissão de cobrança para esta
automação.

## Pré-requisito de ambiente: liberar a rede

Descobrimos (testando o Sicoob) que este ambiente de execução roda com uma
política de rede restritiva ("trusted network access") que **bloqueia
qualquer chamada de saída para domínios de banco** por padrão — a chamada
nem chega a sair do contêiner, então nenhuma credencial resolve isso
sozinha. Antes de ativar qualquer banco, é preciso trocar a política de
rede deste ambiente (em claude.ai/code → configurações do ambiente) para
uma que permita acesso amplo/externo. Isso só precisa ser feito uma vez
para valer para todos os bancos.

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
