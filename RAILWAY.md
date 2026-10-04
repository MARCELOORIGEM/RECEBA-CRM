# Publicar no Railway

Guia do deploy em plataforma de serviço único, com o banco no Supabase.

> **Região:** crie o serviço do Railway e o projeto do Supabase na **mesma
> região**. A API faz algumas consultas por requisição; com o banco em outro
> continente cada uma paga a viagem (medido: ~380 ms do Brasil até o Supabase
> em `us-west-2`), e as telas passam de um segundo para abrir. Na mesma região,
> a viagem é de poucos milissegundos.

---

## O desenho

Um serviço só: a API serve o painel compilado, da mesma origem.

```
navegador ──HTTPS──> Railway ──> contêiner único
                                 ├── /api/*  FastAPI
                                 └── /*      bundle do React
                                        │
                                        └──> Supabase (PostgreSQL)
```

**Por que um serviço e não dois.** Com painel e API em domínios diferentes, o
cookie de sessão vira cross-site: precisa de `SameSite=None`, que exige
`Secure`, que exige HTTPS em tudo. Quando alguma peça não encaixa, o navegador
descarta o cookie **em silêncio** — o login responde 200, a sessão não gruda e
não há erro em lugar nenhum. Mesma origem elimina a classe inteira: sem CORS,
sem `SameSite=None`, sem terceiro domínio.

O `docker-compose.yml` continua existindo, com Nginx e Caddy, para quem
instalar numa VPS. São dois destinos, não um substituindo o outro.

---

## Passo a passo

### 1. Criar o serviço

No Railway: **New Project → Deploy from GitHub repo**, e aponte para este
repositório. O [railway.json](railway.json) já diz o resto:

- constrói pelo [Dockerfile](Dockerfile) da raiz (compila o painel e o embute
  na imagem da API);
- confere a saúde em `/api/health`, com 120 s de carência — o primeiro boot
  cria índices e roda as migrações, e um prazo curto mataria o contêiner no
  meio disso;
- reinicia no máximo 3 vezes em caso de falha, em vez de entrar em laço.

### 2. Variáveis de ambiente

Em **Variables**. Só a primeira linha é obrigatória:

| Variável | Valor |
|---|---|
| `DATABASE_URL` | a URI do Supabase (*Project Settings → Database → Connection string → URI*) |
| `JWT_SECRET` | `python scripts/gerar_segredos.py` e pegue só esta linha |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | conta criada no primeiro boot |
| `MANAGER_EMAIL` / `MANAGER_PASSWORD` | idem |
| `AMBIENTE` | `producao` |
| `TIMEZONE` | `America/Sao_Paulo` |
| `SEED_DEMO_DATA` | `false` |
| `PRIVACIDADE_URL` | link da política publicada (LGPD) |

**Cuidado com a senha do Supabase.** A URI vem com `[YOUR-PASSWORD]` e os
colchetes **não** fazem parte dela. Deixá-los faz a conexão falhar reclamando
de credencial inválida, sem mencionar colchete nenhum — é meia hora de
depuração no lugar errado.

**Conexões com o banco.** O pooler do Supabase na porta 5432 aceita **15
clientes no total** (plano gratuito). A imagem sobe 2 workers (`WEB_CONCURRENCY`)
e cada um abre até 5 conexões (`PG_POOL_MAX`): 10, com folga para o SQL Editor.
Se aumentar um dos dois, confira que `WEB_CONCURRENCY × PG_POOL_MAX` continua
abaixo do *Pool size* do plano — o que passa do limite é recusado com
`EMAXCONNSESSION`, e a requisição fica esperando até cair por timeout, sem erro
claro na tela.

**O que você NÃO precisa definir:**

- `PORT` — o Railway injeta, e o valor muda entre deploys. O Dockerfile usa
  `${PORT}`; fixar 8000 faria o healthcheck falhar em laço.
- `FRONTEND_URL` — sem ela, a aplicação usa `RAILWAY_PUBLIC_DOMAIN`, que a
  plataforma injeta. É o que liga `Secure` no cookie. Defina só se usar
  domínio próprio.
- `TRUSTED_PROXY` — não precisa: o comando da imagem já sobe o uvicorn com `--proxy-headers`, que lê o IP real do `X-Forwarded-For` do Railway.
- As chaves `sb_secret_` e `sb_publishable_` do Supabase: o CRM fala direto
  com o Postgres e não usa a API REST deles.

### 3. Domínio

**Settings → Networking → Generate Domain**, ou aponte o seu. O TLS é da
plataforma; não há Caddy nem certificado para gerenciar aqui.

Usando domínio próprio, defina `FRONTEND_URL=https://seu.dominio` — senão o
cookie sai configurado para o domínio `.up.railway.app`.

### 4. Conferir

```bash
curl https://SEU-DOMINIO/api/health      # {"status":"ok","database":"up"}
```

Depois entre com `ADMIN_EMAIL`, vá em **Minha conta** e troque a senha. A do
`.env` vale só na criação.

---

## O que muda em relação à VPS

| | VPS (docker compose) | Railway |
|---|---|---|
| TLS | Caddy, no repositório | da plataforma |
| Painel | Nginx, serviço separado | servido pela API |
| Banco | PostgreSQL no compose | Supabase |
| Porta | 8080 fixa | `$PORT`, injetada |
| Backup | `scripts/backup.sh` + cron | do Supabase |
| Vigia | `scripts/vigia.sh` no cron | healthcheck da plataforma |

Os scripts de backup e vigia **não se aplicam** aqui: eles usam
`docker compose exec`, que não existe no Railway. O backup passa a ser o do
Supabase (*Database → Backups*) — confira no plano contratado se ele está
ligado e com qual retenção, porque no plano gratuito ele é limitado.

---

## Vindo de uma instalação em MongoDB

O banco novo nasce vazio. Para trazer os dados de uma VPS que rodava a versão
em Mongo, use `scripts/mongo_para_postgres.py` com a `DATABASE_URL` do Supabase,
**antes** do primeiro deploy (a API cria as contas iniciais no boot, e o script
só aceita destino vazio). O passo a passo está em
[PRODUCAO.md, seção 1.1](PRODUCAO.md#11-vindo-de-uma-instalação-em-mongodb).
