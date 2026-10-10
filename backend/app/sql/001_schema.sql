-- Miliano CRM — schema PostgreSQL (Supabase).
--
-- Tradução das 18 coleções do MongoDB. Três decisões valem explicação, porque
-- mudam o comportamento em relação ao que havia antes:
--
-- 1. DATAS VIRARAM TIMESTAMPTZ. No Mongo, `created_at` era string ISO, e as
--    agregações do painel precisavam converter texto em data a cada consulta
--    (`$dateFromString`) só para agrupar por dia. Aqui data é data: o
--    agrupamento no fuso do negócio vira
--    `created_at AT TIME ZONE 'America/Sao_Paulo'`.
--
-- 2. OS STATUS TÊM CHECK. Eram `Literal[...]` só no Pydantic; agora o banco
--    também recusa "voando". Validação na borda protege contra o cliente; no
--    banco, protege contra o próprio código.
--
-- 3. DINHEIRO CONTINUA DOUBLE PRECISION. NUMERIC seria melhor — é o tipo certo
--    para dinheiro — mas o Mongo já guardava double e `financials.py` faz as
--    contas em float. Trocar agora juntaria duas mudanças de risco numa só.
--    Fica anotado como melhoria separada, depois da migração estabilizar.
--
-- O `id` segue TEXT, e não UUID: a aplicação gera `str(uuid.uuid4())` e passa
-- essa string por toda parte, inclusive nas URLs. Converter o tipo obrigaria a
-- mexer em cada rota, sem ganho nenhum.

CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- busca parcial com índice

-- ---------------------------------------------------------------- contas
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'manager' CHECK (role IN ('admin', 'manager')),
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    -- Telas que o usuário enxerga (lista de chaves de app/permissoes.py).
    -- NULL = todas: é o estado das contas criadas antes de existir a escolha,
    -- que não podem perder acesso numa atualização. Ignorado para admin.
    permissoes    JSONB,
    -- Sessões emitidas antes deste instante deixam de valer. Trocar a senha
    -- (ou mudar o acesso) derruba quem estava logado com a credencial antiga.
    sessoes_desde TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------- restaurantes
CREATE TABLE IF NOT EXISTS restaurants (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL DEFAULT '',
    contact_person  TEXT NOT NULL DEFAULT '',
    email           TEXT NOT NULL DEFAULT '',
    phone           TEXT NOT NULL DEFAULT '',
    cnpj            TEXT NOT NULL DEFAULT '',
    address         TEXT NOT NULL DEFAULT '',
    commission_rate DOUBLE PRECISION NOT NULL DEFAULT 15.0
                    CHECK (commission_rate >= 0 AND commission_rate <= 100),
    status          TEXT NOT NULL DEFAULT 'ativo'
                    CHECK (status IN ('ativo', 'em_analise', 'suspenso', 'inativo')),
    notes           TEXT NOT NULL DEFAULT '',
    -- Saldos mantidos pelo motor financeiro, não digitados por ninguém.
    commission_due  DOUBLE PRECISION NOT NULL DEFAULT 0,
    orders_total    INTEGER NOT NULL DEFAULT 0,
    revenue_total   DOUBLE PRECISION NOT NULL DEFAULT 0,
    -- Marca quem nasceu pelo formulário público, para a equipe saber a origem.
    origem          TEXT NOT NULL DEFAULT '',
    -- Qual formulário gerou este cadastro, e as chaves que ele enviou sem
    -- coluna correspondente. No Mongo viravam campos soltos no documento;
    -- aqui ficam juntas num JSONB, sem perder nada e sem inchar a tabela.
    origem_form_id  TEXT NOT NULL DEFAULT '',
    extra_fields    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      TEXT NOT NULL DEFAULT ''
);

-- ----------------------------------------------------------- entregadores
CREATE TABLE IF NOT EXISTS drivers (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    vehicle_type     TEXT NOT NULL DEFAULT 'moto'
                     CHECK (vehicle_type IN ('moto', 'bike', 'carro', 'van')),
    phone            TEXT NOT NULL DEFAULT '',
    email            TEXT NOT NULL DEFAULT '',
    plate            TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'disponivel'
                     CHECK (status IN ('disponivel', 'em_entrega', 'offline', 'indisponivel')),
    rating           DOUBLE PRECISION NOT NULL DEFAULT 5.0
                     CHECK (rating >= 0 AND rating <= 5),
    photo            TEXT NOT NULL DEFAULT '',
    notes            TEXT NOT NULL DEFAULT '',
    -- Dados de pagamento: é com eles que o repasse sai. Leitura exige sessão.
    cpf              TEXT NOT NULL DEFAULT '' CHECK (cpf = '' OR cpf ~ '^[0-9]{11}$'),
    bank             TEXT NOT NULL DEFAULT '',
    bank_agency      TEXT NOT NULL DEFAULT '',
    bank_account     TEXT NOT NULL DEFAULT '',
    account_type     TEXT NOT NULL DEFAULT '' CHECK (account_type IN ('corrente', 'poupanca', '')),
    pix_key_type     TEXT NOT NULL DEFAULT ''
                     CHECK (pix_key_type IN ('cpf', 'celular', 'email', 'aleatoria', '')),
    pix_key          TEXT NOT NULL DEFAULT '',
    balance_due      DOUBLE PRECISION NOT NULL DEFAULT 0,
    paid_total       DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_deliveries INTEGER NOT NULL DEFAULT 0,
    origem           TEXT NOT NULL DEFAULT '',
    origem_form_id   TEXT NOT NULL DEFAULT '',
    extra_fields     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       TEXT NOT NULL DEFAULT ''
);

-- --------------------------------------------------------------- pedidos
CREATE TABLE IF NOT EXISTS orders (
    id                  TEXT PRIMARY KEY,
    code                TEXT NOT NULL UNIQUE,
    -- Guarda id E nome. O id liga ao cadastro (renomear propaga); o nome
    -- sobrevive à exclusão do cadastro, para o histórico não virar vazio.
    -- Sem FK por isso mesmo: apagar um restaurante não pode apagar o pedido.
    restaurant_id       TEXT NOT NULL DEFAULT '',
    restaurant_name     TEXT NOT NULL DEFAULT '',
    driver_id           TEXT NOT NULL DEFAULT '',
    driver_name         TEXT NOT NULL DEFAULT '',
    customer_name       TEXT NOT NULL,
    customer_address    TEXT NOT NULL DEFAULT '',
    customer_phone      TEXT NOT NULL DEFAULT '',
    amount              DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (amount >= 0),
    delivery_fee        DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (delivery_fee >= 0),
    distance_km         DOUBLE PRECISION NOT NULL DEFAULT 0
                        CHECK (distance_km >= 0 AND distance_km <= 500),
    status              TEXT NOT NULL DEFAULT 'criado'
                        CHECK (status IN ('criado', 'aguardando_coleta', 'em_transito',
                                          'entregue', 'cancelado')),
    notes               TEXT NOT NULL DEFAULT '',
    -- Lançamento financeiro: idempotente e reversível. Guarda QUEM foi
    -- creditado e SOBRE QUAL VALOR, para o estorno devolver exatamente o que
    -- entrou, mesmo que o cadastro seja renomeado ou o valor editado depois.
    financials_applied  BOOLEAN NOT NULL DEFAULT FALSE,
    driver_earning      DOUBLE PRECISION NOT NULL DEFAULT 0,
    platform_commission DOUBLE PRECISION NOT NULL DEFAULT 0,
    delivered_at        TIMESTAMPTZ,
    -- A fotografia do lançamento: a quem o valor foi creditado e sobre qual
    -- valor. Sem ela, estornar um pedido cujo entregador mudou (ou cujo valor
    -- foi editado) devolveria uma quantia diferente da que entrou, para a
    -- pessoa errada. É o que torna o estorno exato, e não aproximado.
    credited_driver_id     TEXT NOT NULL DEFAULT '',
    credited_restaurant_id TEXT NOT NULL DEFAULT '',
    credited_amount        DOUBLE PRECISION NOT NULL DEFAULT 0,
    -- Id do pedido no sistema de origem (marketplace). Nulo quando o pedido
    -- nasceu na tela: UNIQUE no Postgres ignora NULL, que é exatamente o
    -- `sparse` do índice que havia no Mongo.
    external_ref        TEXT UNIQUE,
    origem              TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by          TEXT NOT NULL DEFAULT ''
);

-- ------------------------------------------------------------- contratos
CREATE TABLE IF NOT EXISTS contracts (
    id         TEXT PRIMARY KEY,
    party_type TEXT NOT NULL CHECK (party_type IN ('restaurante', 'entregador')),
    party_id   TEXT NOT NULL DEFAULT '',
    party_name TEXT NOT NULL,
    rule_type  TEXT NOT NULL CHECK (rule_type IN ('taxa_fixa', 'valor_km', 'comissao_entrega')),
    value      DOUBLE PRECISION NOT NULL CHECK (value >= 0),
    status     TEXT NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'encerrado', 'suspenso')),
    notes      TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by TEXT NOT NULL DEFAULT '',
    -- Comissão por entrega é percentual: não passa de 100.
    CONSTRAINT comissao_ate_100 CHECK (rule_type <> 'comissao_entrega' OR value <= 100)
);

-- ------------------------------------------------------------ pagamentos
CREATE TABLE IF NOT EXISTS payments (
    id            TEXT PRIMARY KEY,
    creditor      TEXT NOT NULL,
    creditor_type TEXT NOT NULL CHECK (creditor_type IN ('restaurante', 'entregador')),
    creditor_id   TEXT NOT NULL DEFAULT '',
    amount        DOUBLE PRECISION NOT NULL CHECK (amount > 0),
    due_date      DATE NOT NULL,
    method        TEXT NOT NULL DEFAULT 'PIX'
                  CHECK (method IN ('PIX', 'Transferência', 'Dinheiro', 'Boleto')),
    status        TEXT NOT NULL DEFAULT 'pendente'
                  CHECK (status IN ('pendente', 'pago', 'atrasado', 'cancelado')),
    notes         TEXT NOT NULL DEFAULT '',
    paid_at       TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    TEXT NOT NULL DEFAULT ''
);

-- ------------------------------------------------------------------ funil
CREATE TABLE IF NOT EXISTS leads (
    id                      TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    contact_name            TEXT NOT NULL DEFAULT '',
    phone                   TEXT NOT NULL DEFAULT '',
    email                   TEXT NOT NULL DEFAULT '',
    city                    TEXT NOT NULL DEFAULT '',
    category                TEXT NOT NULL DEFAULT '',
    source                  TEXT NOT NULL DEFAULT 'prospeccao'
                            CHECK (source IN ('indicacao', 'instagram', 'prospeccao', 'site',
                                              'whatsapp', 'evento', 'outro')),
    -- Status da visita de campo (app/funil.py). A coluna segue chamada stage.
    stage                   TEXT NOT NULL DEFAULT 'a_visitar'
                            CHECK (stage IN ('a_visitar', 'nao_localizado', 'fechado_no_local', 'responsavel_ausente',
                                             'colhendo_dados', 'reuniao', 'segunda_visita', 'aguardando_documentos',
                                             'cadastro_enviado', 'ativado', 'sem_interesse', 'ja_parceiro',
                                             'fora_da_area')),
    estimated_value         DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (estimated_value >= 0),
    owner_name              TEXT NOT NULL DEFAULT '',
    notes                   TEXT NOT NULL DEFAULT '',
    lost_reason             TEXT NOT NULL DEFAULT '',
    -- Histórico de etapas: lista de {stage, at, by}. Registro append-only que
    -- só se lê inteiro, nunca filtrado por dentro — JSONB serve bem.
    stage_history           JSONB NOT NULL DEFAULT '[]'::jsonb,
    converted_restaurant_id TEXT NOT NULL DEFAULT '',
    -- Trabalho de campo: o lead é um restaurante que um BD visita.
    -- codigo_externo é o "LEAD ID" da planilha da operação; único quando
    -- preenchido (índice em 005), é por ele que a reimportação não duplica.
    codigo_externo          TEXT NOT NULL DEFAULT '',
    endereco                TEXT NOT NULL DEFAULT '',
    bairro                  TEXT NOT NULL DEFAULT '',
    bd_id                   TEXT NOT NULL DEFAULT '',
    bd_nome                 TEXT NOT NULL DEFAULT '',
    lider                   TEXT NOT NULL DEFAULT '',
    data_visita             DATE,
    origem                  TEXT NOT NULL DEFAULT '',
    origem_form_id          TEXT NOT NULL DEFAULT '',
    extra_fields            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by              TEXT NOT NULL DEFAULT ''
);

-- -------------------------------------------------------------- atividades
CREATE TABLE IF NOT EXISTS activities (
    id           TEXT PRIMARY KEY,
    kind         TEXT NOT NULL DEFAULT 'tarefa' CHECK (kind IN ('tarefa', 'interacao')),
    type         TEXT NOT NULL DEFAULT 'tarefa'
                 CHECK (type IN ('ligacao', 'whatsapp', 'email', 'reuniao', 'visita',
                                 'nota', 'tarefa')),
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    due_at       TIMESTAMPTZ,
    related_type TEXT CHECK (related_type IS NULL OR
                             related_type IN ('lead', 'restaurante', 'entregador', 'pedido')),
    related_id   TEXT NOT NULL DEFAULT '',
    related_name TEXT NOT NULL DEFAULT '',
    owner_name   TEXT NOT NULL DEFAULT '',
    done         BOOLEAN NOT NULL DEFAULT FALSE,
    completed_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by   TEXT NOT NULL DEFAULT ''
);

-- ------------------------------------------------------------ formulários
CREATE TABLE IF NOT EXISTS forms (
    id                TEXT PRIMARY KEY,
    -- O slug é o link que já foi distribuído no WhatsApp: editar o título não
    -- pode mudá-lo.
    slug              TEXT NOT NULL UNIQUE,
    title             TEXT NOT NULL,
    description       TEXT NOT NULL DEFAULT '',
    target            TEXT NOT NULL DEFAULT 'lead'
                      CHECK (target IN ('lead', 'restaurante', 'entregador')),
    -- Definição dos campos: lista de objetos com key, label, type, required,
    -- options, allow_other. É um documento de verdade, variável por formulário
    -- — normalizar em tabela daria uma junção a cada render, sem ganho.
    fields            JSONB NOT NULL DEFAULT '[]'::jsonb,
    active            BOOLEAN NOT NULL DEFAULT TRUE,
    success_message   TEXT NOT NULL DEFAULT '',
    submissions_count INTEGER NOT NULL DEFAULT 0,
    seed              BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by        TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS form_submissions (
    id                TEXT PRIMARY KEY,
    form_id           TEXT NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
    form_title        TEXT NOT NULL DEFAULT '',
    target            TEXT NOT NULL DEFAULT '',
    answers           JSONB NOT NULL DEFAULT '{}'::jsonb,
    record_name       TEXT NOT NULL DEFAULT '',
    created_record_id TEXT NOT NULL DEFAULT '',
    -- Prova de que a pessoa foi informada: guarda o texto do aviso que estava
    -- no ar no momento do envio, não um ponteiro para a versão atual (LGPD).
    consentimento     JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip                TEXT NOT NULL DEFAULT '',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -------------------------------------------------------------- auditoria
CREATE TABLE IF NOT EXISTS audit_logs (
    id          TEXT PRIMARY KEY,
    actor_id    TEXT NOT NULL DEFAULT '',
    actor_name  TEXT NOT NULL DEFAULT '',
    actor_email TEXT NOT NULL DEFAULT '',
    action      TEXT NOT NULL,
    entity      TEXT NOT NULL,
    entity_id   TEXT NOT NULL DEFAULT '',
    label       TEXT NOT NULL DEFAULT '',
    changes     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------ integrações
CREATE TABLE IF NOT EXISTS api_keys (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    environment TEXT NOT NULL DEFAULT 'sandbox'
                CHECK (environment IN ('production', 'sandbox')),
    -- Só o hash. O valor aparece uma única vez, na criação.
    key_hash    TEXT NOT NULL,
    key_preview TEXT NOT NULL DEFAULT '',
    last_used   TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS webhooks (
    id         TEXT PRIMARY KEY,
    provider   TEXT NOT NULL,
    url        TEXT NOT NULL,
    events     JSONB NOT NULL DEFAULT '[]'::jsonb,
    active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS webhook_logs (
    id          TEXT PRIMARY KEY,
    provider    TEXT NOT NULL DEFAULT '',
    event       TEXT NOT NULL DEFAULT '',
    status_code INTEGER NOT NULL DEFAULT 0,
    detalhe     TEXT NOT NULL DEFAULT '',
    ip          TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------- efêmeras (eram índices TTL)
-- O Mongo apagava sozinho com expireAfterSeconds. O Postgres não tem TTL: a
-- limpeza é feita pela aplicação, na própria consulta que usa a tabela (ver
-- app/repo.py). É mais previsível que depender de tarefa de fundo — e não
-- exige a extensão pg_cron, que nem toda instalação tem.
CREATE TABLE IF NOT EXISTS login_attempts (
    id         BIGSERIAL PRIMARY KEY,
    email      TEXT NOT NULL DEFAULT '',
    ip         TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS password_resets (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- Só o hash do token. Gerar um link novo invalida o anterior.
    token_hash TEXT NOT NULL UNIQUE,
    criado_por TEXT NOT NULL DEFAULT '',
    expira_em  TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------- utilitárias
-- Contador atômico dos códigos de pedido. Era find_one_and_update com $inc;
-- vira INSERT ... ON CONFLICT DO UPDATE ... RETURNING, igualmente atômico.
-- Uma SEQUENCE não serve: o nome do contador é dado em tempo de execução.
CREATE TABLE IF NOT EXISTS counters (
    name  TEXT PRIMARY KEY,
    value BIGINT NOT NULL DEFAULT 0
);

-- Migrações de dados já aplicadas, para não repetirem a cada boot.
CREATE TABLE IF NOT EXISTS migrations (
    name TEXT PRIMARY KEY,
    at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
