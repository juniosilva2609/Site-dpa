-- 001_inicial.sql -- estrutura inicial do sistema de NFS-e

CREATE TABLE usuario (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL,
    login       TEXT NOT NULL UNIQUE,
    senha_hash  TEXT NOT NULL,
    admin       INTEGER NOT NULL DEFAULT 0,
    ativo       INTEGER NOT NULL DEFAULT 1,
    criado_em   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Uma linha só (id = 1): dados do prestador, parâmetros fiscais e destino dos arquivos.
CREATE TABLE configuracao (
    id                          INTEGER PRIMARY KEY CHECK (id = 1),
    razao_social                TEXT NOT NULL DEFAULT 'JL TRANSPORTES EXECUTIVOS LTDA',
    cnpj                        TEXT NOT NULL DEFAULT '60441511000170',
    inscricao_municipal         TEXT NOT NULL DEFAULT '16550350019',
    telefone                    TEXT NOT NULL DEFAULT '31971254546',
    email                       TEXT NOT NULL DEFAULT 'contato@jlexecutivo.com',
    codigo_municipio_ibge       TEXT NOT NULL DEFAULT '3106200',          -- Belo Horizonte-MG
    regime_tributario           TEXT NOT NULL DEFAULT 'simples' CHECK (regime_tributario IN ('simples','normal')),
    codigo_servico_lc116        TEXT NOT NULL DEFAULT '160201',           -- 16.02.01 transporte municipal
    codigo_tributacao_municipal TEXT NOT NULL DEFAULT '004',
    codigo_nbs                  TEXT NOT NULL DEFAULT '',
    aliquota_iss                NUMERIC,                                  -- só regime 'normal'
    ambiente                    TEXT NOT NULL DEFAULT 'homologacao' CHECK (ambiente IN ('homologacao','producao')),
    serie_dps                   TEXT NOT NULL DEFAULT '00001',
    proximo_numero_dps          INTEGER NOT NULL DEFAULT 1,
    -- onde entregar os arquivos de cada nota emitida
    salvar_em_pasta             INTEGER NOT NULL DEFAULT 1,
    pasta_saida                 TEXT NOT NULL DEFAULT '',                 -- vazio = pasta padrão do sistema
    enviar_por_email            INTEGER NOT NULL DEFAULT 0,
    emails_destino              TEXT NOT NULL DEFAULT '',                 -- separados por vírgula
    email_alertas               TEXT NOT NULL DEFAULT '',
    -- agenda
    tolerancia_atraso_horas     INTEGER NOT NULL DEFAULT 6,
    atualizado_em               TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
INSERT INTO configuracao (id) VALUES (1);

CREATE TABLE cliente (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nome                TEXT NOT NULL,                  -- razão social / nome completo (como na Receita)
    documento           TEXT NOT NULL,                  -- CPF ou CNPJ, só dígitos
    email               TEXT NOT NULL DEFAULT '',
    telefone            TEXT NOT NULL DEFAULT '',
    cep                 TEXT NOT NULL DEFAULT '',
    logradouro          TEXT NOT NULL DEFAULT '',
    numero              TEXT NOT NULL DEFAULT '',
    complemento         TEXT NOT NULL DEFAULT '',
    bairro              TEXT NOT NULL DEFAULT '',
    codigo_municipio    TEXT NOT NULL DEFAULT '',       -- IBGE (7 dígitos)
    enviar_nota_por_email INTEGER NOT NULL DEFAULT 0,   -- manda a nota também para o e-mail do cliente
    ativo               INTEGER NOT NULL DEFAULT 1,
    criado_em           TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE UNIQUE INDEX ux_cliente_documento ON cliente(documento);

-- Modelo de emissão recorrente ("padrão"): gera uma nota por ocorrência.
CREATE TABLE agendamento (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    nome              TEXT NOT NULL,
    cliente_id        INTEGER NOT NULL REFERENCES cliente(id),
    descricao         TEXT NOT NULL,                    -- aceita {data} {mes} {ano} {mes_ano} {competencia}
    valor_centavos    INTEGER NOT NULL,
    frequencia        TEXT NOT NULL CHECK (frequencia IN ('mensal','semanal','unica')),
    dia_mes           INTEGER,                          -- 1..31 (dia maior que o mês = último dia)
    dia_semana        INTEGER,                          -- 0 = segunda .. 6 = domingo
    data_unica        TEXT,                             -- AAAA-MM-DD
    hora              TEXT NOT NULL DEFAULT '09:00',
    antecedencia_dias INTEGER NOT NULL DEFAULT 3,       -- a nota entra "A conferir" N dias antes
    auto_aprovar      INTEGER NOT NULL DEFAULT 0,       -- 1 = dispensa a conferência humana (se tudo estiver OK)
    ativo             INTEGER NOT NULL DEFAULT 1,
    criado_em         TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE nota (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    agendamento_id   INTEGER REFERENCES agendamento(id),
    cliente_id       INTEGER NOT NULL REFERENCES cliente(id),
    prevista_em      TEXT NOT NULL,                     -- 'AAAA-MM-DD HH:MM' (horário de Brasília)
    descricao        TEXT NOT NULL,
    valor_centavos   INTEGER NOT NULL,
    competencia      TEXT,                              -- AAAA-MM-DD; vazio = dia da emissão
    status           TEXT NOT NULL DEFAULT 'a_conferir' CHECK (status IN
                       ('a_conferir','aprovada','emitindo','emitida','rejeitada','verificar',
                        'atrasada','cancelada','pulada')),
    conferido_por    TEXT,
    conferido_em     TEXT,
    ambiente         TEXT,
    numero_dps       INTEGER,
    id_dps           TEXT,
    chave_acesso     TEXT,
    numero_nfse      TEXT,
    xml_dps          TEXT,
    xml_nfse         TEXT,
    mensagem_erro    TEXT,
    tentativas       INTEGER NOT NULL DEFAULT 0,
    emitida_em       TEXT,
    cancelada_em     TEXT,
    motivo_cancelamento TEXT,
    -- entrega dos arquivos (nunca afeta o status fiscal da nota)
    pdf_path         TEXT,
    xml_path         TEXT,
    pasta_erro       TEXT,
    email_enviado_em TEXT,
    email_erro       TEXT,
    entrega_tentativas INTEGER NOT NULL DEFAULT 0,
    criado_por       TEXT,
    criado_em        TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE UNIQUE INDEX ux_nota_ocorrencia ON nota(agendamento_id, prevista_em) WHERE agendamento_id IS NOT NULL;
CREATE INDEX ix_nota_status ON nota(status, prevista_em);

CREATE TABLE historico (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    em        TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    usuario   TEXT,
    nota_id   INTEGER,
    acao      TEXT NOT NULL,
    detalhe   TEXT
);
CREATE INDEX ix_historico_nota ON historico(nota_id);

CREATE TABLE alerta (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    chave             TEXT NOT NULL UNIQUE,             -- evita repetir o mesmo alerta
    nivel             TEXT NOT NULL DEFAULT 'aviso' CHECK (nivel IN ('info','aviso','erro')),
    mensagem          TEXT NOT NULL,
    nota_id           INTEGER,
    criado_em         TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    resolvido_em      TEXT,
    email_enviado_em  TEXT
);

-- Trava curta (lease) para garantir uma emissão por vez, mesmo com mais de um processo.
CREATE TABLE trava (
    nome  TEXT PRIMARY KEY,
    ate   REAL NOT NULL
);

CREATE TABLE estado (
    chave  TEXT PRIMARY KEY,
    valor  TEXT
);
