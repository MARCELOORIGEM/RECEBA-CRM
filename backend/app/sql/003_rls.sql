-- Row Level Security — fecha a API pública do Supabase.
--
-- POR QUE ISTO EXISTE
--
-- O Supabase publica cada tabela numa API REST (PostgREST), alcançável com a
-- chave `anon`. Essa chave é pública por design: ela vai dentro do bundle do
-- navegador e qualquer pessoa consegue lê-la. O que separa "tabela publicada"
-- de "tabela aberta ao mundo" é exclusivamente o RLS.
--
-- Sem isto, a tabela `drivers` — com CPF, agência, conta e chave PIX dos
-- entregadores — ficaria legível por quem tivesse a chave. Seria o oposto da
-- regra que o resto do sistema cumpre: "esses dados só são legíveis com
-- sessão; a rota pública grava e não lê".
--
-- POR QUE NÃO HÁ NENHUMA POLICY AQUI
--
-- RLS ligado e sem policy nenhuma significa: ninguém passa. É o que queremos,
-- porque o CRM **não usa a API REST do Supabase**. A aplicação fala com o
-- banco pela connection string, como papel dono/`service_role`, que passa por
-- cima do RLS. O controle de acesso de verdade continua onde sempre esteve —
-- `app/deps.py`, com `get_current_user` e `require_admin` por rota.
--
-- Escrever policies aqui seria duplicar essa regra num segundo lugar, com o
-- risco das duas divergirem. A porta pública fica fechada; a da aplicação,
-- guardada pela aplicação.
--
-- NÃO USE `FORCE ROW LEVEL SECURITY`: ele sujeita também o dono da tabela ao
-- RLS, e é com o dono que a API conecta. Ligado, derrubaria o sistema inteiro.
--
-- Rodar de novo é inofensivo: habilitar o que já está habilitado não faz nada.

ALTER TABLE users            ENABLE ROW LEVEL SECURITY;
ALTER TABLE restaurants      ENABLE ROW LEVEL SECURITY;
ALTER TABLE drivers          ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders           ENABLE ROW LEVEL SECURITY;
ALTER TABLE contracts        ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments         ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads            ENABLE ROW LEVEL SECURITY;
ALTER TABLE activities       ENABLE ROW LEVEL SECURITY;
ALTER TABLE forms            ENABLE ROW LEVEL SECURITY;
ALTER TABLE form_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs       ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys         ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhooks         ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_logs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE login_attempts   ENABLE ROW LEVEL SECURITY;
ALTER TABLE password_resets  ENABLE ROW LEVEL SECURITY;
ALTER TABLE counters         ENABLE ROW LEVEL SECURITY;
ALTER TABLE migrations       ENABLE ROW LEVEL SECURITY;
