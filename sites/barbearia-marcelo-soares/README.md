# Site — Barbearia Marcelo Soares

Site institucional (landing page) para a Barbearia Marcelo Soares, Jardim América — Belo Horizonte/MG.

Domínio registrado: **barbeariamarcelosoares.com.br**
Prévia interativa (Artifact): https://claude.ai/artifact/FtHbd6ZnP2MJ3d5mQzYf99

## Estrutura

- `index.html` — página única, sem dependências além do Google Fonts (CDN).
- `assets/logo.png` — logo recortada a partir da imagem enviada pelo usuário.

## Como colocar o domínio no ar (via GitHub Pages)

O domínio já foi registrado, mas registro ≠ hospedagem: falta apontar `barbeariamarcelosoares.com.br` para um servidor que sirva estes arquivos. Este repositório é **público**, então o GitHub Pages (grátis) funciona direto daqui. Já deixei tudo pronto do lado do código:

- Workflow `.github/workflows/deploy-barbearia-pages.yml` — publica automaticamente a pasta `sites/barbearia-marcelo-soares` (só ela, não o resto do repositório) toda vez que houver um push nela nesta branch, ou pode ser disparado manualmente.
- Arquivo `sites/barbearia-marcelo-soares/CNAME` já criado com `barbeariamarcelosoares.com.br`, para o domínio persistir a cada novo deploy.

O único passo que **não consigo fazer por aqui** (exige acesso à interface do GitHub, que não tenho) é ativar o Pages nas configurações do repositório — é rápido:

1. No GitHub, abra **Settings → Pages** deste repositório (`juniosilva2609/Site-dpa`).
2. Em **Build and deployment → Source**, selecione **"GitHub Actions"**.
3. Isso já dispara o workflow (ou rode manualmente em **Actions → Deploy Barbearia Marcelo Soares (GitHub Pages) → Run workflow**). Depois de rodar, a URL temporária `https://juniosilva2609.github.io/Site-dpa/` deve funcionar.
4. Ainda em **Settings → Pages**, no campo **Custom domain**, digite `barbeariamarcelosoares.com.br` e salve.
5. No painel de DNS do **registro.br**, crie os registros abaixo (documentados pela própria GitHub):
   - 4 registros **A** em `@` (raiz do domínio) apontando para:
     `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
   - 1 registro **CNAME** em `www` apontando para `juniosilva2609.github.io`
6. Aguarde a propagação do DNS (de minutos a algumas horas). Quando o GitHub confirmar a verificação do domínio em Settings → Pages, marque **"Enforce HTTPS"** para ativar o certificado SSL automático.

**Alternativas** (mesmo princípio, caso prefira): Netlify ou Vercel — importe este repositório, defina `sites/barbearia-marcelo-soares` como diretório raiz do projeto, adicione o domínio nas configurações do site/projeto e crie no registro.br os registros de DNS que a plataforma indicar.

Se colar aqui os valores de DNS que aparecerem, posso conferir se estão corretos.

## Pendências antes de publicar

1. **Avaliações do Google**: a seção "Avaliações" linka para o perfil real do Google (`share.google/hAx23m9HWjk2uno0j`) mas não exibe comentários específicos — não há acesso automatizado a essas avaliações. Para exibir a nota e os comentários reais dentro do site, use um widget oficial (Google Business Profile embed) ou um serviço como Elfsight/EmbedSocial, usando o Place ID da barbearia.
2. **Horários de funcionamento**: não foram informados; o site direciona para o app de agendamento em vez de exibir um horário fixo. Se quiser exibir horário fixo, adicione-o ao JSON-LD (`openingHoursSpecification`) e a uma seção visível.
3. **Serviços e preços**: os serviços listados são os típicos de barbearia (corte, barba, combo, sobrancelha, pézinho, coloração). Ajuste nomes/descrições conforme o cardápio real; os valores ficam a cargo do app de agendamento.

## Fluxo de agendamento

- CTA principal ("Agendar horário") sempre aponta para o app de agendamento: `https://sites.appbarber.com.br/barbeariamarcel-wgns`.
- WhatsApp (`31 97314-6142`) aparece como opção adicional no topo (ícone no cabeçalho), no herói, na seção de contato e no botão flutuante — para quem prefere falar antes de agendar.

## Sugestões de domínio

1. `barbeariamarcelosoares.com.br` — melhor opção: nome de marca completo, fácil de lembrar.
2. `marcelosoaresbarbearia.com.br`
3. `marcelobarbeirobh.com.br` — casa com o Instagram pessoal (@marcelobarbeirobh).
4. `bmarcelosoares.com.br` — versão curta.
5. `cortecommarcelo.com.br` — apelo mais comercial/campanha.

Verifique a disponibilidade em registro.br antes de decidir.
