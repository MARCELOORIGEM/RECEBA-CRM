-- Permissões por tela e corte de sessões.
--
-- As colunas também estão no CREATE TABLE de 001_schema.sql, para instalação
-- nova. Este arquivo existe para o banco que já tinha a tabela `users` antes
-- delas: CREATE TABLE IF NOT EXISTS não acrescenta coluna a tabela existente.
-- Idempotente, como os outros: rodar de novo não muda nada.

ALTER TABLE users ADD COLUMN IF NOT EXISTS permissoes    JSONB;
ALTER TABLE users ADD COLUMN IF NOT EXISTS sessoes_desde TIMESTAMPTZ;
