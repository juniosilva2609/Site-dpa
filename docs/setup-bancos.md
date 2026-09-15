# Configuração de acesso a cada banco (API oficial, somente leitura de extrato)

Cada banco exige um cadastro feito por você diretamente (login com CPF/CNPJ do
titular da conta). Eu não consigo acessar o internet banking — só configuro o
que for gerado nesse cadastro, como segredo neste ambiente (nunca no
repositório).

Peça sempre o escopo mínimo: **consulta de extrato/saldo**. Nunca solicite
escopos de pagamento, transferência, PIX ou emissão de cobrança para esta
automação.

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

Variáveis de ambiente esperadas:
`DPA_SICOOB_CLIENT_ID`, `DPA_SICOOB_CERT_PFX`, `DPA_SICOOB_CERT_PFX_SENHA`.

## Santander

Portal: Santander Developers Brasil (developers.santander.com.br) — cadastro
de aplicação PJ com certificado mTLS, nos mesmos moldes dos bancos acima.
Vou detalhar o passo a passo exato quando você for iniciar esse cadastro,
para confirmar a tela atual do portal antes de te passar instruções.

Variáveis de ambiente esperadas:
`DPA_SANTANDER_CLIENT_ID`, `DPA_SANTANDER_CLIENT_SECRET`,
`DPA_SANTANDER_CERT_CRT`, `DPA_SANTANDER_CERT_KEY`.

## Como me repassar as credenciais

Não cole client_secret, senha de certificado ou o conteúdo do .crt/.key/.pfx
diretamente na conversa se puder evitar. Prefira que eu te oriente a
configurá-los como variável de ambiente/segredo deste ambiente de execução
assim que estivermos prontos para ativar aquele banco.
