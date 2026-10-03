-- Índices — tradução dos 42 que o Mongo criava em `ensure_indexes()`.
--
-- Os únicos e as chaves primárias já saíram no 001 (PRIMARY KEY e UNIQUE
-- criam índice sozinhos). Aqui ficam os de filtro, ordenação e busca.
--
-- Duas famílias merecem explicação:
--
-- BUSCA PARCIAL. O Mongo usava índice TEXT, que casa palavra inteira: buscar
-- "cant" não achava "Cantina". O código contornava isso com regex, que o
-- índice TEXT não atende — ou seja, toda busca fazia varredura. Aqui é GIN com
-- `gin_trgm_ops`: o `ILIKE '%cant%'` do repo passa a ser atendido por índice.
-- É mais rápido E acha mais que a versão anterior.
--
-- ORDENAÇÃO COMPOSTA. `(status, created_at DESC)` serve a listagem filtrada
-- por status e ordenada por data, que é o que as telas fazem. A ordem das
-- colunas importa: igualdade primeiro, faixa/ordenação depois.

-- ------------------------------------------------------------ restaurantes
CREATE INDEX IF NOT EXISTS ix_restaurants_status_created
    ON restaurants (status, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_restaurants_busca
    ON restaurants USING gin ((name || ' ' || cnpj || ' ' || contact_person) gin_trgm_ops);

-- ------------------------------------------------------------- entregadores
CREATE INDEX IF NOT EXISTS ix_drivers_status_created
    ON drivers (status, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_drivers_busca
    ON drivers USING gin ((name || ' ' || plate || ' ' || phone) gin_trgm_ops);

-- ----------------------------------------------------------------- pedidos
CREATE INDEX IF NOT EXISTS ix_orders_status_created ON orders (status, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_orders_restaurant    ON orders (restaurant_id);
CREATE INDEX IF NOT EXISTS ix_orders_driver        ON orders (driver_id);
CREATE INDEX IF NOT EXISTS ix_orders_created       ON orders (created_at DESC);
-- O painel soma e agrupa só o que foi entregue, no mês corrente. Parcial,
-- porque pedido cancelado ou em rota nunca entra nessas contas.
CREATE INDEX IF NOT EXISTS ix_orders_entregues
    ON orders (created_at DESC) WHERE status = 'entregue';
CREATE INDEX IF NOT EXISTS ix_orders_busca
    ON orders USING gin (
        (code || ' ' || customer_name || ' ' || restaurant_name || ' ' || driver_name)
        gin_trgm_ops
    );

-- --------------------------------------------------------------- contratos
CREATE INDEX IF NOT EXISTS ix_contracts_party_status ON contracts (party_type, status);
CREATE INDEX IF NOT EXISTS ix_contracts_party        ON contracts (party_id);

-- -------------------------------------------------------------- pagamentos
CREATE INDEX IF NOT EXISTS ix_payments_status_due ON payments (status, due_date);
CREATE INDEX IF NOT EXISTS ix_payments_creditor   ON payments (creditor_id);

-- -------------------------------------------------------------------- funil
CREATE INDEX IF NOT EXISTS ix_leads_stage_updated ON leads (stage, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_leads_busca
    ON leads USING gin ((name || ' ' || contact_name || ' ' || city) gin_trgm_ops);

-- ---------------------------------------------------------------- atividades
CREATE INDEX IF NOT EXISTS ix_activities_done_due ON activities (done, due_at);
CREATE INDEX IF NOT EXISTS ix_activities_related  ON activities (related_type, related_id);

-- -------------------------------------------------------------- formulários
CREATE INDEX IF NOT EXISTS ix_form_submissions_form
    ON form_submissions (form_id, created_at DESC);
-- Contagem de envios por IP na última hora, do limite anti-robô da rota aberta.
CREATE INDEX IF NOT EXISTS ix_form_submissions_ip
    ON form_submissions (ip, created_at DESC);

-- ----------------------------------------------------------------- auditoria
CREATE INDEX IF NOT EXISTS ix_audit_created ON audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_entity  ON audit_logs (entity, entity_id);

-- --------------------------------------------------------------- integrações
CREATE INDEX IF NOT EXISTS ix_api_keys_hash     ON api_keys (key_hash);
CREATE INDEX IF NOT EXISTS ix_webhook_logs_created ON webhook_logs (created_at DESC);

-- ------------------------------------------------------------------ efêmeras
-- Limite de tentativas de login: conta por e-mail+IP numa janela de minutos.
CREATE INDEX IF NOT EXISTS ix_login_attempts_email_ip
    ON login_attempts (email, ip, created_at DESC);
-- Usado pela limpeza preguiçosa, que apaga o que passou da validade.
CREATE INDEX IF NOT EXISTS ix_login_attempts_created ON login_attempts (created_at);
CREATE INDEX IF NOT EXISTS ix_password_resets_user   ON password_resets (user_id);
CREATE INDEX IF NOT EXISTS ix_password_resets_expira ON password_resets (expira_em);
