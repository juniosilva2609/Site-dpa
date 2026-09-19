# Site — Barbearia Marcelo Soares

Site institucional (landing page) para a Barbearia Marcelo Soares, Jardim América — Belo Horizonte/MG.

Prévia interativa (Artifact): https://claude.ai/artifact/FtHbd6ZnP2MJ3d5mQzYf99

## Estrutura

- `index.html` — página única, sem dependências além do Google Fonts (CDN).
- `assets/logo.png` — logo recortada a partir da imagem enviada pelo usuário.

Basta abrir `index.html` em um navegador, ou hospedar a pasta em qualquer serviço de hospedagem estática (Vercel, Netlify, Hostinger, GitHub Pages etc.) após a compra do domínio.

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
