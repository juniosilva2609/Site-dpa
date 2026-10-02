-- 002_feedback.sql -- sugestões e inconsistências enviadas pelos usuários (também vão por e-mail)
CREATE TABLE feedback (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    em           TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    usuario      TEXT NOT NULL,
    tipo         TEXT NOT NULL CHECK (tipo IN ('sugestao','inconsistencia')),
    mensagem     TEXT NOT NULL,
    origem       TEXT NOT NULL DEFAULT '',     -- tela em que o usuário estava
    nota_id      INTEGER,
    contexto     TEXT NOT NULL DEFAULT '',     -- ambiente, navegador etc. (sem dados fiscais sensíveis)
    enviado_em   TEXT,                         -- quando o e-mail saiu
    envio_erro   TEXT,
    resolvido_em TEXT
);
