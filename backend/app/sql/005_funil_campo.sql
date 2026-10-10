-- Funil de visita de campo: campos do trabalho do BD e os status novos.
--
-- As colunas também estão no CREATE TABLE de 001 (instalação nova); aqui é
-- para o banco que já existia. Idempotente: na segunda vez, ADD COLUMN não
-- faz nada, o UPDATE não acha mais etapa antiga e a regra é recriada igual.

ALTER TABLE leads ADD COLUMN IF NOT EXISTS codigo_externo TEXT NOT NULL DEFAULT '';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS endereco       TEXT NOT NULL DEFAULT '';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS bairro         TEXT NOT NULL DEFAULT '';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS bd_id          TEXT NOT NULL DEFAULT '';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS bd_nome        TEXT NOT NULL DEFAULT '';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS lider          TEXT NOT NULL DEFAULT '';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS data_visita    DATE;

-- A regra antiga recusaria os status novos: sai antes da conversão.
ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_stage_check;

-- Etapas da versão anterior -> status equivalentes (app/funil.py, LEGADO).
UPDATE leads SET stage = CASE stage
        WHEN 'novo' THEN 'a_visitar'
        WHEN 'contatado' THEN 'colhendo_dados'
        WHEN 'negociacao' THEN 'reuniao'
        WHEN 'proposta' THEN 'cadastro_enviado'
        WHEN 'ganho' THEN 'ativado'
        WHEN 'perdido' THEN 'sem_interesse'
    END
 WHERE stage IN ('novo', 'contatado', 'negociacao', 'proposta', 'ganho', 'perdido');

ALTER TABLE leads ALTER COLUMN stage SET DEFAULT 'a_visitar';
ALTER TABLE leads ADD CONSTRAINT leads_stage_check CHECK (stage IN ('a_visitar', 'nao_localizado', 'fechado_no_local', 'responsavel_ausente',
                                             'colhendo_dados', 'reuniao', 'segunda_visita', 'aguardando_documentos',
                                             'cadastro_enviado', 'ativado', 'sem_interesse', 'ja_parceiro',
                                             'fora_da_area'));

-- LEAD ID único quando preenchido: a reimportação da mesma planilha encontra
-- o lead em vez de criar outro. Vazio fica de fora (lead cadastrado na tela).
CREATE UNIQUE INDEX IF NOT EXISTS ux_leads_codigo_externo
    ON leads (codigo_externo) WHERE codigo_externo <> '';

-- Filtros da tela: por líder e por BD.
CREATE INDEX IF NOT EXISTS ix_leads_lider   ON leads (lider);
CREATE INDEX IF NOT EXISTS ix_leads_bd_nome ON leads (bd_nome);
