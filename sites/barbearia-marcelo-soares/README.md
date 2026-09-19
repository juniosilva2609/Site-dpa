# Site — Barbearia Marcelo Soares

Site institucional (landing page) para a Barbearia Marcelo Soares, Jardim América — Belo Horizonte/MG.

Domínio registrado: **barbeariamarcelosoares.com.br**
Prévia interativa (Artifact): https://claude.ai/artifact/FtHbd6ZnP2MJ3d5mQzYf99

## Estrutura

- `index.html` — página única, sem dependências além do Google Fonts (CDN).
- `assets/logo.png` — logo recortada a partir da imagem enviada pelo usuário.

## Como colocar o domínio no ar

O domínio já foi registrado, mas registro ≠ hospedagem: falta apontar `barbeariamarcelosoares.com.br` para um servidor que sirva estes arquivos. Não tenho acesso à conta do registro.br nem a nenhuma conta de hospedagem do usuário, então esta parte precisa ser feita manualmente — mas é rápida. Duas opções:

**Opção A — Netlify (grátis, mais simples, ~10 min)**
1. Baixe/exporte esta pasta (`index.html` + `assets/`).
2. Acesse [app.netlify.com](https://app.netlify.com), crie uma conta grátis e arraste a pasta para "Deploy manually" (ou conecte este repositório GitHub e aponte o "base directory" para `sites/barbearia-marcelo-soares`).
3. Em **Domain settings → Add a domain**, adicione `barbeariamarcelosoares.com.br`.
4. O Netlify mostra os registros DNS a configurar. No painel do registro.br, em **DNS**, crie:
   - Um registro **A** em `@` apontando para `75.2.60.5`
   - Um registro **CNAME** em `www` apontando para o endereço `algumnome.netlify.app` que o Netlify indicar
5. Aguarde a propagação (de minutos a poucas horas) e ative o HTTPS automático (Netlify faz isso sozinho).

**Opção B — Vercel** segue o mesmo princípio: importar o repositório, definir `sites/barbearia-marcelo-soares` como diretório raiz do projeto, adicionar o domínio em Project Settings → Domains, e criar no registro.br os registros que a Vercel indicar.

Qualquer hospedagem de site estático (Hostinger, GitHub Pages, etc.) funciona da mesma forma: 1) subir estes arquivos, 2) apontar o DNS do registro.br para o provedor.

Se colar aqui os valores de DNS que o provedor pedir, posso conferir se estão corretos.

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
