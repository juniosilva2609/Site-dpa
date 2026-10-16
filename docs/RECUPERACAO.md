# Recuperação do fechamento bancário

Roteiro para pôr a automação de pé de novo se algo for perdido. Escrito
depois de 16/10/2026, quando a sessão fixa das Rotinas quebrou e as
credenciais, que só existiam dentro dela, se perderam.

## Onde fica cada peça

| Peça | Onde fica | Cópia de segurança |
|---|---|---|
| Código, config e documentação | GitHub, `juniosilva2609/Site-dpa`, branch `claude/monthly-bank-closure-automation-d1huvk` | o próprio GitHub |
| Extratos | Google Drive de cada empresa | o próprio Drive (e o banco mantém o histórico) |
| Configuração das Rotinas (agenda, prompt, conectores) | claude.ai/code → Rotinas | `docs/rotinas/*.md` |
| Credenciais dos bancos | variáveis `DPA_*` do ambiente cloud em claude.ai/code | arquivo criptografado do titular (abaixo) |
| Política de rede do ambiente (liberar os bancos) | configuração do ambiente cloud | descrita em `docs/setup-bancos.md` |

Nenhuma Rotina depende mais de uma conversa específica: cada execução abre
uma sessão nova, clona o repositório e lê as credenciais do ambiente.

## Cópia de segurança das credenciais

As credenciais **não podem** ir para o repositório. A cópia fica com o
titular, criptografada:

1. Guarde os arquivos de origem numa pasta (ex.: `credenciais-para-colar`,
   com os `.txt` em base64 e uma lista com os Client IDs/Secrets).
2. Rode `ferramentas/backup-credenciais.ps1` (Windows). Ele pede uma senha
   e gera `credenciais-AAAA-MM-DD.zip.enc` (AES-256). Guarde esse arquivo
   em dois lugares (ex.: Google Drive pessoal e pendrive) e a senha num
   gerenciador de senhas.
3. Para abrir: `ferramentas/backup-credenciais.ps1 -Restaurar <arquivo>`.

Refaça a cópia sempre que trocar alguma credencial ou certificado.

## Recriar do zero

1. **Ambiente cloud** (claude.ai/code → ambiente → ⚙):
   - liberar a rede para os domínios dos bancos (`docs/setup-bancos.md`);
   - colar as variáveis `DPA_*` (nomes em `config/empresas.yaml`), a partir
     da cópia criptografada.
2. **Rotinas**: recriar as duas com os dados de `docs/rotinas/`, no mesmo
   ambiente, com sessão nova a cada execução e os conectores Google Drive e
   Gmail.
3. **Testar**: disparar a Rotina quinzenal manualmente e conferir o e-mail
   "Fechamento bancário <competência>".

## Vencimentos

| Certificado | Vence em |
|---|---|
| e-CNPJ A1 da DPA (Sicoob e Santander) | 14/01/2027 |
| Inter DPA | 12/09/2027 |
| Inter C3S | 17/09/2027 |
| Inter Licitprint | 17/09/2027 |

Ao renovar, atualize a variável no ambiente e refaça a cópia criptografada.
