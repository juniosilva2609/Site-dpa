# Auditoria do sistema — setembro/2026

## Escopo real (leia antes do resto)

O pedido de auditoria original cobria telas, banco de dados, login,
perfis/permissões de usuário e backup de banco de dados — um roteiro
pensado para uma aplicação web multiusuário.

Uma exploração completa do repositório (estrutura de diretórios, git log,
grep por "auth"/"login"/"senha"/"permission"/"usuario") confirmou que
**este repositório não é isso**: é só a automação de fechamento bancário
quinzenal da DPA/C3S/Licitprint. Não existe site, tela, banco de dados,
login nem perfil de usuário em nenhum arquivo versionado — apenas
`config/`, `connectors/`, `docs/`, `tests/`, `README.md` e arquivos de
dependência. A única coisa parecida com "autenticação" é OAuth2 + mTLS
máquina-a-máquina contra as APIs dos bancos (Inter/Sicoob), não um sistema
de usuários.

Por isso, os itens abaixo marcam **N/A** onde o item pedido não se aplica a
este código, em vez de forçar uma resposta para um sistema que não existe
aqui. Se existir de fato um site/sistema web da DPA em outro repositório,
ele precisa ser anexado à sessão para ser auditado à parte.

## 1. Problemas críticos encontrados

- **Não existia orquestrador versionado.** `connectors/__init__.py` estava
  vazio — quem percorria `config/empresas.yaml`, isolava erro por banco,
  checava duplicidade e registrava log era um agente de IA interpretando
  `docs/processo-fechamento.md` a cada disparo da Rotina agendada, não
  código determinístico e testável. Isso significava: sem retry, sem log
  persistente, sem dedup em código, sem testes — e nenhuma garantia de que
  duas execuções do "mesmo processo" se comportassem de forma idêntica.
  **Corrigido**: `connectors/runner.py` (+ `config.py`, `dedup.py`,
  `nomenclatura.py`, `retry.py`) implementa isso em código, com 25 testes
  automatizados cobrindo os casos principais.
- **Nenhum isolamento de falha entre bancos/empresas.** Ambos os conectores
  chamavam `resp.raise_for_status()` sem `try/except` ao redor — um erro em
  um banco (ex: Sicoob fora do ar) derrubaria o processamento sem
  isolamento explícito em código. **Corrigido**: `runner.processar_banco`
  captura qualquer exceção e devolve status `"erro"` só para aquele
  banco/empresa; `tests/test_runner.py::test_processar_periodo_isola_falha_entre_empresas`
  comprova que uma empresa com erro não impede a outra de ser processada.

## 2. Problemas de segurança

Nenhum problema crítico. Achados menores, já corrigidos:

- `requirements.txt` usava `>=` sem teto de versão (risco de supply-chain —
  uma versão futura quebrada/maliciosa seria instalada automaticamente).
  **Corrigido**: tetos de versão adicionados (`<3`, `<7` etc.).
- `playwright>=1.47` era dependência órfã (não usada desde o commit
  `7277348`, quando a geração de PDF migrou para `reportlab`). **Corrigido**:
  removida de `requirements.txt`.

Confirmado como já correto (nenhuma ação necessária):
- Nenhum segredo hardcoded no repositório (`git grep` por
  `client_secret`/`password`/`BEGIN PRIVATE KEY`/`.pfx`/`.pem` etc. só
  encontra nomes de variável de ambiente e prosa de documentação).
- `.gitignore` cobre `*.pem`, `*.crt`, `*.key`, `*.pfx`, `*.cer`, `.env`.
- Credenciais só carregadas via `os.environ["VAR"]` (nunca `.get()` com
  fallback silencioso) em `connectors/inter.py` e `connectors/sicoob.py` —
  uma variável ausente falha alto, com `KeyError`, em vez de silenciosamente
  usar um valor vazio.
- Sem SQL injection nem command injection possível: não há banco de dados
  nem chamada de shell em nenhum lugar do código.
- Nenhum log imprime corpo de requisição/resposta (que poderia conter dado
  financeiro ou token) — `runner.py` só loga
  `empresa=... banco=... status=... motivo=<NomeDaExceção>`, nunca a
  mensagem completa do erro nem o payload.

**N/A** (não existe no repo): controle de acesso por usuário/perfil,
proteção de sessão web, XSS, CSRF, upload de arquivo por usuário final.

## 3. Problemas de usabilidade

**N/A** — não há tela nem interface de usuário neste repositório; a
"interface" é a Rotina agendada + relatório de texto ao final de cada
execução (`docs/processo-fechamento.md`, seção "Relatório final").

## 4. Problemas de integração

- Ver item 1 (isolamento de falha) e item 6 (confiabilidade) — a
  integração com cada banco em si (contrato de API, autenticação,
  parsing) estava correta e validada em produção (16-17/09/2026 conforme
  `config/empresas.yaml`), o problema era a ausência de orquestração
  robusta ao redor dela.
- A integração com o Google Drive (upload final dos arquivos) permanece
  fora deste repositório — depende da sessão de agente autenticada no
  Google Drive do usuário, não de um cliente/API versionado em código.
  Isso é uma limitação conhecida e documentada (`docs/setup-bancos.md`,
  seção "Como as credenciais ficam guardadas neste ambiente"), não um bug
  introduzido por esta auditoria — só está sendo reafirmado aqui porque é
  o principal ponto único de falha remanescente (ver item 6).

## 5. Problemas de backup

**N/A quanto a banco de dados** (não existe). O que existe de fato para
"backup e recuperação" neste projeto:
- **Os extratos em si** já ficam armazenados de forma redundante: uma cópia
  no Google Drive (fonte de verdade para o usuário) e a fonte original
  sempre pode ser re-obtida direto do banco (Inter/Sicoob mantêm histórico
  de extrato por conta própria), então não há perda real possível de dado
  financeiro.
- **O ponto real de risco é credencial, não dado**: cada credencial
  bancária vive só como arquivo local (`~/.dpa-secrets/<banco>.env`) dentro
  da sessão de agente específica que a Rotina reaproveita a cada disparo
  (`docs/setup-bancos.md:114-123`, já documentado pelo próprio projeto). Se
  essa sessão for perdida/arquivada, as credenciais precisam ser
  recadastradas do zero em cada banco. Recomendação (não implementada nesta
  auditoria, por exigir decisão do usuário sobre onde guardar segredo fora
  desta sessão): mover as credenciais para um cofre de segredos do próprio
  ambiente Claude Code (environment secrets), se disponível, em vez de um
  arquivo dentro de uma sessão específica.

## 6. Problemas de performance

Não identificado nenhum problema de performance relevante — o volume de
dados por execução é pequeno (extrato quinzenal de poucas contas), sem
paginação necessária nas APIs consultadas, sem consulta repetida
desnecessária. Não é uma prioridade neste estágio do projeto.

## 7. Melhorias realizadas nesta auditoria

1. `connectors/config.py` — validação de `config/empresas.yaml` na carga,
   com mensagem de erro nomeando empresa/banco/campo faltando.
2. `connectors/retry.py` — retry com backoff exponencial para erro
   transitório de rede/servidor (nunca para erro de cliente 4xx).
3. `connectors/dedup.py` — checagem de duplicidade por hash de conteúdo
   (`docs/padrao-nomenclatura.md`), incluindo o caso de `_v2`, `_v3`... já
   existirem com conteúdo diferente.
4. `connectors/nomenclatura.py` — geração do nome padronizado do arquivo e
   da competência (`MM-AAAA-Q1`/`Q2`), extraída para módulo próprio e
   testada isoladamente.
5. `connectors/runner.py` — orquestrador determinístico: percorre
   `config/empresas.yaml`, isola erro por banco/empresa, aplica retry e
   dedup, registra log persistente sem dado sensível
   (`logs/fechamento.log`, `logging.basicConfig`).
6. `tests/` — 25 testes automatizados (`pytest`) cobrindo conectores
   (Inter/Sicoob com API mockada), validação de config, regra de
   duplicidade, retry e isolamento de erro no orquestrador.
7. `requirements.txt` — teto de versão adicionado; dependência órfã
   (`playwright`) removida.
8. `docs/processo-fechamento.md` e `README.md` atualizados para refletir
   o que agora é código (testável, versionado) vs. o que ainda depende da
   sessão de agente (upload real no Drive).

## 8. Melhorias recomendadas (não implementadas — dependem de decisão do usuário)

- **Credenciais fora da sessão de agente**: avaliar mover
  `~/.dpa-secrets/*.env` para um mecanismo de segredo do próprio ambiente
  Claude Code, para não depender do ciclo de vida de uma sessão específica.
- **Alerta de vencimento de certificado**: os certificados mTLS (Inter,
  Sicoob) têm validade de ~12 meses; hoje não há nenhum lembrete automático
  antes do vencimento (mencionado como intenção em
  `docs/processo-fechamento.md`, mas não implementado). Poderia virar uma
  Rotina separada, mensal, checando a data de emissão registrada em
  `config/empresas.yaml`.
- **Concluir o cadastro do Santander** (`config/empresas.yaml`:
  `status: pendente_cadastro`) quando o usuário tiver as credenciais.
- **Integração real com o Google Drive em código** (API do Drive com
  service account ou OAuth próprio), se o usuário quiser eliminar de vez a
  dependência da sessão de agente para o upload final — troca de
  arquitetura maior, fora do escopo desta auditoria.

## 9. Testes realizados e resultados

- `pytest` (25 testes) — conectores Inter/Sicoob (autenticação OK, erro
  4xx/5xx propagado corretamente, parsing de JSON), validação de
  `empresas.yaml` (carga real do arquivo do projeto + casos de erro),
  regra de duplicidade (novo/existente/nova versão, incluindo cadeia
  `_v2`→`_v3`), retry (sucesso após falha transitória, erro de cliente sem
  retry, esgotamento de tentativas), e isolamento de erro no orquestrador
  (uma empresa com erro não impede o processamento da outra).
- Todos os testes rodam com a API mockada (`unittest.mock`) — nenhuma
  chamada real às APIs bancárias foi feita durante a auditoria, então
  nenhum dado de produção foi tocado.

## 10. Nível geral de confiabilidade do sistema

**Antes desta auditoria**: baixo para uso desacompanhado — a automação
"funcionava" apenas enquanto a mesma sessão de agente estivesse ativa para
interpretar o roteiro em `docs/processo-fechamento.md` a cada disparo, sem
retry, sem isolamento de erro em código, sem teste automatizado.

**Depois desta auditoria**: médio-alto para a parte que já é código
(autenticação, download, dedup, isolamento de erro, retry) — coberta por
teste automatizado e revisável por diff de código, como qualquer outro
software. A parte que ainda depende da sessão de agente (upload real no
Google Drive) continua sendo o principal fator limitante de confiabilidade
de ponta a ponta; isso é uma decisão de arquitetura pendente do usuário
(item 8), não um defeito silencioso.

## 11. O que ainda falta antes de considerar "pronto para uso empresarial"

- Decidir e, se aprovado, implementar a integração com o Drive fora da
  sessão de agente (item 8) — hoje é o maior ponto único de falha real.
- Cadastro do Santander (bloqueado no usuário, credenciais pendentes).
- Confirmar que a chave de conta de serviço do Google Cloud exposta
  acidentalmente em sessão anterior (não relacionada à integração com os
  bancos) foi revogada — item já sinalizado ao usuário anteriormente, ainda
  sem confirmação.
- Alerta de vencimento de certificado mTLS (item 8).

Fora isso, para o que este repositório de fato é — a automação de
fechamento bancário — o código está seguro, testado e sem problema
crítico pendente.
