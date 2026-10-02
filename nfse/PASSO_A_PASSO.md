# Passo a passo para colocar a NFS-e Automática no ar

Marque cada item ao concluir. Tempo total: cerca de 1 hora (a maior parte é esperar o deploy).

## A. Publicar no Render
1. Entre em https://render.com e crie a conta (ou entre com o GitHub).
2. **New > Blueprint** > conecte o GitHub > escolha o repositório `juniosilva2609/Site-dpa` > branch `claude/bold-davinci-vjjurh`.
3. O Render lê o `render.yaml` e mostra o serviço **nfse-automatica** (plano Starter + disco de 1 GB). Confirme o plano pago:
   o gratuito "dorme" e as notas agendadas não sairiam no horário.
4. Preencha as variáveis que ele pedir (nunca vão para o GitHub):
   | Variável | O que colocar |
   |---|---|
   | `NFSE_SETUP_CODE` | um código que você inventa (ex.: 8 letras e números); guarde-o |
   | `NFSE_CERT_SENHA` | senha do certificado e-CNPJ da JL |
   | `SMTP_HOST` | `smtp.gmail.com` |
   | `SMTP_USER` | o e-mail Gmail que vai enviar as notas |
   | `SMTP_SENHA` | **senha de app** do Gmail (passo B) |
   | `NFSE_SUPORTE_COPIA_ALERTAS` | opcional: `1` copia os alertas para junioaraujo.adv@gmail.com |
   | `NFSE_BACKUP_EMAIL` | opcional: `1` envia o backup diário por e-mail |
5. Clique em **Apply** e espere o deploy ficar "Live" (3 a 5 min). Copie o endereço `https://....onrender.com`.

## B. Criar a senha de app do Gmail (para o envio de e-mails)
1. Na conta Google que enviará os e-mails, ative a **verificação em duas etapas** (myaccount.google.com > Segurança).
2. Em myaccount.google.com/apppasswords crie uma senha de app (nome: "NFSE") e copie as 16 letras.
3. No Render > serviço > **Environment**, cole em `SMTP_SENHA` (sem espaços) e salve (o serviço reinicia).

## C. Primeiro acesso
1. Abra `https://<seu-endereço>/primeiro-acesso`.
2. Digite o `NFSE_SETUP_CODE`, seu nome, usuário e uma senha forte (8+ caracteres). Esse é o **administrador**.
3. Entre em `/entrar`. O painel mostrará avisos de configuração pendente: é normal.

## D. Configurar (menu Configuração)
1. **Certificado:** envie o arquivo `JL.p12`. Deve aparecer "Arquivo enviado" e "Senha definida". Clique em
   **Testar conexão com a Sefin** (todas as etapas devem dar OK) e **Testar convênio do município**.
2. **Dados fiscais:** confira CNPJ, inscrição municipal (16550350019), município (3106200), código 160201 e municipal 004,
   regime Simples. Mantenha **Homologação** por enquanto. Salve.
3. **Onde guardar/enviar:** marque "Salvar numa pasta" e "Enviar por e-mail"; informe os e-mails que recebem cada nota e os
   e-mails que recebem alertas. Salve. Use **Testar gravação** e **Enviar e-mail de teste** (deve chegar na sua caixa).
   (No Render a pasta fica no disco do servidor: o que vale é o e-mail.)
4. **Usuários:** crie um usuário "operador" para quem vai conferir/aprovar no dia a dia.

## E. Teste em homologação (sem validade jurídica)
1. **Clientes > Novo cliente:** cadastre um cliente de teste (CPF/CNPJ válido).
2. **Notas > Nova nota avulsa:** cliente, valor e descrição; salve. Na nota, confira a lista e clique **Emitir agora**.
3. Abra o **PDF** e compare com a nota modelo da JL. Confira que o e-mail chegou com PDF e XML.
4. Teste o formulário **Sugestões**: envie uma mensagem e confira que chegou em junioaraujo.adv@gmail.com.
5. (Opcional) Cancele a nota de teste (administrador) para validar o cancelamento.

## F. Passar para produção (notas reais)
1. Configuração > Ambiente > **Produção**, digite `PRODUCAO` no campo de confirmação e salve.
2. Emita **uma nota real, de valor verdadeiro**, e confira no Portal Nacional (www.nfse.gov.br/EmissorNacional) pelo CNPJ
   da JL: número, valor, tomador e descrição. Confira também o PDF e o e-mail.
3. Só depois siga para os agendamentos.

## G. Agendar as emissões padrão
1. **Agendamentos > Novo:** nome, cliente, valor, descrição (pode usar `{mes_ano}`), quando (ex.: todo dia 5, 09:00) e
   "entra para conferência X dias antes". **Deixe a aprovação automática desmarcada** no começo.
2. Alguns dias antes aparece uma nota "A conferir" no painel (e um lembrete). Abra, confira e clique **"Conferi: aprovar emissão"**.
3. No dia e hora marcados o sistema emite sozinho e entrega PDF + XML por e-mail.
4. Depois de 2 ou 3 ciclos sem problemas, se quiser, ative a aprovação automática nos agendamentos mais estáveis.

## H. Rotina e cuidados
- Veja o **Painel** todo dia: "Precisam da sua atenção" deve estar vazio.
- Nota em **Verificar**: não emita por outro lugar; use "Conferir na Sefin" ou anexe o XML do Portal.
- O certificado vence em **17/04/2027**: o sistema alerta com 60/30/15/7 dias.
- Guarde o `.pfx` e a senha em local seguro (não vão no backup). Troque senhas que já foram digitadas em conversas.
- Backup: automático por dia; manual `python run.py backup`; restauração `python run.py restaurar arquivo.db` (servidor parado).
- Dúvidas ou erros: menu **Sugestões** (chega por e-mail ao responsável).
