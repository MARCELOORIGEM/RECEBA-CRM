# Colocar o Miliano CRM no ar

Guia de quem vai provisionar e operar o sistema em produção: o que o banco
precisa ter, o que configurar, como subir, como fazer backup e o que conferir
antes de abrir para a equipe.

---

## 1. Precisa de banco de dados? Sim — MongoDB

O CRM guarda **tudo** no MongoDB: restaurantes, entregadores, pedidos,
contratos, pagamentos, leads, atividades, auditoria, usuários e as respostas do
formulário público. Não existe modo "sem banco", e não dá para trocar por
MySQL/Postgres sem reescrever a camada de dados — o código usa Motor (driver
assíncrono do Mongo) direto.

Hoje, em desenvolvimento, ele aponta para um Mongo local **sem senha**, no banco
`test_database`. Isso não vai para produção.

### E o Supabase? Não — e não vale a pena trocar

Supabase é PostgreSQL com uma camada de autenticação, storage e API em cima.
Este CRM não usa nada disso:

| O que o Supabase oferece | O que o CRM já tem |
|---|---|
| Banco Postgres | MongoDB, acessado direto pelo Motor em todo o código |
| Auth (login, JWT, reset de senha) | `app/security.py` + `app/routers/auth.py`, com bcrypt, cookie httpOnly, bloqueio por tentativa e link de nova senha |
| Row Level Security | `app/deps.py` — `get_current_user` e `require_admin` por rota |
| API REST automática | 86 rotas FastAPI com validação de tipo, faixa e enum |
| Storage de arquivos | não há upload de arquivo no sistema |

Migrar significaria **reescrever a camada de dados inteira** — todo documento,
toda consulta, toda agregação do dashboard, o contador atômico de `app/db.py`,
os índices TTL — e jogar fora a autenticação que já está testada, para ganhar
exatamente nada que o sistema precise. O Mongo deste compose não custa mensalidade,
não tem limite de linha e roda na mesma VPS.

Supabase faria sentido se o projeto estivesse começando do zero, ou se
precisasse de algo que ele resolve e o CRM não tem (um app de entregador com
login próprio, por exemplo). Hoje, não.

### O que provisionar

| Item | Valor |
|---|---|
| Motor | MongoDB **6.0 ou 7.0** (testado no 7) |
| Nome do banco | `miliano_crm` (ou outro; vai em `DB_NAME`) |
| Usuário da aplicação | um, com papel `readWrite` **só nesse banco** |
| Disco | **10 GB** cobrem o primeiro ano com folga (ver conta abaixo) |
| Memória | 2 GB para o Mongo é suficiente no porte de uma operação regional |
| Rede | alcançável **só** pela API — nunca exposto na internet |
| Backup | diário, com 14 dias de retenção |

**Não precisa** de réplica, sharding, Atlas Search, séries temporais nem
nenhum recurso pago. É um banco pequeno e de escrita modesta.

### Quanto de disco, na prática

Um pedido ocupa ~1 KB. Uma operação com 500 entregas por dia gera ~180 mil
pedidos por ano, ou seja **menos de 200 MB/ano** de pedidos, mais índices e as
coleções de apoio. Os 10 GB são folga para anos de histórico e para o backup
local conviver no mesmo disco.

Duas coleções já se limpam sozinhas (índice TTL): `login_attempts` (1 hora) e
`password_resets` (30 minutos). `refresh_tokens` expira junto com a sessão.

### As três formas de ter esse banco

**a) Junto, no docker compose (mais simples).** O `docker-compose.yml` deste
repositório já sobe um Mongo 7 com autenticação, volume persistente e **sem
porta publicada** — só a API o alcança. É o caminho recomendado para uma única
VPS. Você não precisa criar banco nenhum: `infra/mongo-init.js` cria o banco e o
usuário da aplicação no primeiro boot.

**b) MongoDB Atlas (gerenciado).** O tier **M10** (~US$ 57/mês) dá backup
automático e janela de manutenção. O M0 gratuito funciona para testar, mas tem
512 MB e cai sob carga — não use para a operação real. Com o Atlas:
- crie um usuário com `readWrite` no banco `miliano_crm`;
- libere o IP do servidor da API na lista de acesso (não use `0.0.0.0/0`);
- use a string `mongodb+srv://...` em `MONGO_URL` e remova o serviço `mongo` do
  compose.

**c) Mongo já existente na sua infra.** Só precisa do usuário com `readWrite` no
banco novo e da regra de rede liberando a API. Não compartilhe o banco com outro
sistema: a aplicação cria índices e assume que as coleções são dela.

### O que o sistema faz sozinho na primeira subida

Você não roda migração nenhuma à mão. No boot, a API:

1. cria **todos os índices** (inclusive os únicos e os TTL);
2. roda as migrações de dados de versões anteriores;
3. cria as contas de `ADMIN_EMAIL` e `MANAGER_EMAIL` com as senhas do `.env`
   — **só na criação**: depois, cada pessoa troca a sua e o `.env` não
   sobrescreve mais;
4. cria o formulário "Cadastro de Entregadores", se ainda não existir;
5. popula dados de exemplo **apenas** se `SEED_DEMO_DATA=true` (deixe `false`).

---

## 2. Configuração

Gere o `.env` da raiz com segredos aleatórios:

```bash
python scripts/gerar_segredos.py https://crm.suaempresa.com.br > .env
```

Depois abra e ajuste os e-mails das contas iniciais. **Guarde uma cópia num
cofre de senhas** — `JWT_SECRET` e as senhas do Mongo não dá para recuperar, e
trocar o `JWT_SECRET` desconecta todo mundo.

O `.env.example` descreve cada variável. As que mais importam:

| Variável | Para que serve |
|---|---|
| `MONGO_URL` | conexão com o banco (no compose é montada a partir do usuário/senha) |
| `DB_NAME` | nome do banco |
| `JWT_SECRET` | assina as sessões; trocar derruba todas |
| `FRONTEND_URL` | domínio do painel. Define o CORS **e** o modo do cookie: `https` liga `Secure`+`SameSite=None`, `http` usa `Lax` |
| `PUBLIC_API_URL` | endereço da API que vai **dentro do bundle** do navegador — muda só recompilando |
| `ADMIN_EMAIL` / `MANAGER_EMAIL` | contas criadas no primeiro boot |
| `SEED_DEMO_DATA` | dados fictícios. `false` em produção |
| `ALLOW_PUBLIC_REGISTER` | autocadastro de usuário. `false` |
| `TRUSTED_PROXY` | só `true` quando há um proxy reescrevendo `X-Forwarded-For`. Ligado sem proxy, qualquer um forja o próprio IP e escapa dos limites |
| `MAX_ENVIOS_POR_IP` | teto de envios do formulário público por hora, por IP (padrão 10). Suba em dia de ação de rua, quando muita gente se cadastra pela mesma rede |
| `PRIVACIDADE_URL` | link da política de privacidade, exibido no formulário |
| `SENTRY_DSN` | monitoramento de erro; vazio = desligado |
| `TIMEZONE` | fuso do negócio; define onde começa e termina "hoje" |

---

## 3. Subir

**Antes de subir**, com o TLS incluído na pilha, duas coisas precisam estar
prontas — senão a Let's Encrypt não consegue validar o domínio:

1. um registro **A/AAAA** de `DOMINIO` apontando para o IP deste servidor;
2. as portas **80 e 443** abertas na internet. A 80 não pode ser fechada: é por
   ela que o desafio de validação chega.

```bash
docker compose up -d --build
docker compose logs -f api        # acompanhe o primeiro boot
docker compose logs -f proxy      # acompanhe a emissão do certificado
```

Sobem quatro serviços:

- **mongo** — banco com autenticação, volume `mongo_dados`, sem porta publicada;
- **api** — FastAPI em usuário não-root, com healthcheck em `/api/health`;
- **web** — bundle do painel servido por Nginx, com cabeçalhos de segurança e
  `/api/` fazendo proxy para a API;
- **proxy** — Caddy terminando **HTTPS** nas portas 80 e 443, com certificado
  Let's Encrypt obtido e renovado sozinho, e HSTS no cabeçalho.

O HTTP interno continua existindo na `PORTA_HTTP` (8080), mas publicado **só no
loopback** (`BIND_HTTP=127.0.0.1`): quem atende a internet é o Caddy, em HTTPS.
Sem isso, o cookie de sessão não receberia `Secure` e senha e CPF trafegariam
em claro.

**Já tem um proxy com TLS na sua infra?** Suba sem o Caddy e aponte o seu proxy
para `127.0.0.1:8080`:

```bash
docker compose up -d --build mongo api web
```

Se esse proxy estiver em **outra máquina**, troque `BIND_HTTP` para `0.0.0.0` e
proteja a porta no firewall.

Todo serviço tem **teto de memória** (`MEM_*` no `.env`) e **rotação de log**
(10 MB × 5 arquivos). Sem o teto, um pico do Mongo leva a máquina junto; sem a
rotação, o log do Docker enche o disco e derruba o banco.

### Primeiro acesso

1. Entre com `ADMIN_EMAIL` e a senha do `.env`.
2. Vá em **Minha conta** (menu da conta, no topo) e troque a senha.
3. Em **Usuários**, crie as contas da equipe. Cada uma troca a própria senha.
4. Em **Formulários**, confira o "Cadastro de Entregadores" e copie o link.

### Quem esquecer a senha

Não há envio de e-mail de propósito — SMTP é mais uma peça para configurar,
monitorar e falhar. Em **Usuários**, o administrador clica no ícone de chave na
linha da pessoa e recebe um **link de uso único**, válido por 30 minutos, que
entrega pelo canal que a equipe já usa. A pessoa escolhe a própria senha; o
sistema guarda apenas o hash do token, e gerar um link novo invalida o anterior.

---

## 4. Backup

```bash
./scripts/backup.sh          # dump compactado em ./backups
./scripts/restaurar.sh ARQUIVO.gz
```

Agende no cron do servidor com um comando — instala backup diário (3h) e o
vigia de 5 em 5 minutos, sem duplicar se você rodar de novo:

```bash
./scripts/instalar_cron.sh
```

`RETENCAO_DIAS` (padrão 14) controla quantos dias ficam no disco local.

**A cópia para fora do servidor** sai junto, se você preencher `DESTINO_REMOTO`
no `.env` — backup que mora na mesma máquina não sobrevive à perda dela. Aceita
destino de `rclone` (`meubucket:miliano`) ou de `rsync`
(`usuario@outrohost:/backups`). Vazio, o script avisa no log a cada execução
que só existe cópia local.

**Teste a restauração pelo menos uma vez**, num banco separado. Backup que nunca
foi restaurado é uma suposição, não uma garantia.

---

## 5. Dados pessoais (LGPD)

O formulário público coleta **CPF, conta bancária e chave PIX** de pessoas
físicas. Isso traz obrigações concretas:

- O formulário mostra o aviso de privacidade e **exige o aceite** antes de
  enviar. O aceite fica guardado junto da resposta, com o texto que estava no ar
  naquele momento — é a prova de que a pessoa foi informada.
- Preencha `PRIVACIDADE_URL` com a sua política. Sem ela, o aviso aparece, mas
  sem o documento por trás.
- Esses dados **só são legíveis com sessão**: a rota pública grava e não lê.
- Os scripts de terceiros que vinham no andaime do projeto (PostHog e
  `assets.emergent.sh`) foram **removidos** do `index.html`. Não os traga de
  volta: essa página carrega o formulário onde o CPF é digitado, e qualquer
  script externo ali passa a enxergar o campo.
- `robots.txt` e a meta `noindex` mantêm painel e formulário fora dos
  buscadores.
- Quem pedir exclusão: apague o cadastro em **Entregadores** (botão de excluir,
  perfil administrador) e a resposta correspondente em **Formulários →
  Respostas**. A auditoria registra a exclusão.

---

## 6. Integração com marketplace

A chave de API deixou de ser decorativa. Em **Integrações**, o administrador
gera uma chave (ela aparece **uma única vez**) e o parceiro passa a empurrar
pedido para dentro do CRM:

```http
POST /api/integracoes/eventos/keeta
Authorization: Bearer mln_live_...
Content-Type: application/json

{
  "evento": "pedido.criado",
  "referencia": "KEETA-88231",
  "restaurante": "Cantina da Esquina",
  "cliente": "Maria",
  "endereco": "Rua X, 100",
  "valor": 80.0,
  "taxa_entrega": 10.0,
  "distancia_km": 4.2
}
```

Eventos: `pedido.criado`, `pedido.aceito`, `pedido.entregue`,
`pedido.cancelado`. A `referencia` é o id do pedido no sistema de origem e é
**única por provedor** — reenviar o mesmo evento atualiza o pedido existente em
vez de duplicar, o que importa porque reenvio é rotina quando a rede cai.
`pedido.entregue` dispara o mesmo motor financeiro da tela: lança repasse e
comissão. Voltar o status estorna.

Toda chamada entra em **Integrações → Logs**.

---

## 7. Monitoramento

- `GET /api/health` responde `{"status":"ok","database":"up"}`. O healthcheck
  do compose consulta isso — mas ele só reinicia contêiner, **não avisa
  ninguém**.
- Quem avisa é **`scripts/vigia.sh`**, instalado pelo `instalar_cron.sh` e
  rodando de 5 em 5 minutos. Preencha `WEBHOOK_ALERTA` no `.env` com uma URL de
  Slack, Discord ou Teams. Ele só dispara depois de **duas falhas seguidas**
  (uma costuma ser reinício ou rede piscando, e alerta por isso treina a equipe
  a ignorar o canal), alerta **uma vez por incidente** e manda um segundo aviso
  quando o sistema volta. Sem o webhook, ele registra em `backups/vigia.log` e
  ninguém fica sabendo.
- Toda requisição recebe um **`X-Request-ID`**, que aparece no log e na
  mensagem de erro 500. Quando alguém reclamar de um erro, peça o código: ele
  leva direto à linha do log.
- Com `SENTRY_DSN` preenchido, as exceções vão para o Sentry com o ambiente
  (`AMBIENTE`) marcado.

---

## 8. Conferir antes de abrir para a equipe

- [ ] `JWT_SECRET` gerado por `scripts/gerar_segredos.py`, não o de exemplo
- [ ] Senhas do Mongo trocadas e guardadas num cofre
- [ ] `ADMIN_EMAIL` e `MANAGER_EMAIL` são e-mails reais da empresa
- [ ] Senha do administrador trocada **pela tela** depois do primeiro acesso
- [ ] `SEED_DEMO_DATA=false` e nenhum dado de exemplo na base
- [ ] `DOMINIO` com A/AAAA apontando para este servidor, portas 80 e 443 abertas
- [ ] `ACME_EMAIL` é um e-mail que alguém lê (é por onde vem o aviso de falha
      na renovação do certificado)
- [ ] `docker compose logs proxy` mostra o certificado emitido, e o painel abre
      em `https://` com cadeado
- [ ] `FRONTEND_URL` e `PUBLIC_API_URL` com o domínio real e `https://`
- [ ] Porta 27017 **não** publicada em lugar nenhum
- [ ] `BIND_HTTP=127.0.0.1` (a porta 8080 não responde de fora: confira de
      outra máquina com `curl http://SEU_IP:8080`)
- [ ] `./scripts/instalar_cron.sh` rodado, e `crontab -l` mostra as duas linhas
- [ ] `DESTINO_REMOTO` preenchido e a primeira cópia confirmada no destino
- [ ] Restauração testada uma vez
- [ ] `WEBHOOK_ALERTA` preenchido e testado (pare a API e veja o alerta chegar)
- [ ] `PRIVACIDADE_URL` apontando para a política publicada
- [ ] `.env` fora do Git (se já esteve versionado, rotacione tudo que está nele)
- [ ] CI verde no repositório antes do deploy

---

## 9. O que ainda não existe

Para a operação não descobrir sozinha, no pior momento:

- **Não há e-mail transacional.** Nada é notificado por e-mail; a recuperação de
  senha é pelo link que o administrador entrega. O alerta de queda usa webhook
  (Slack/Discord/Teams), não e-mail.
- **Não há 2FA.** A proteção de conta é senha forte + bloqueio por tentativa.
- **Não há exportação para contabilidade.** Os relatórios ficam na tela; não há
  CSV/Excel nem integração fiscal.
- **Não há app de entregador.** O entregador se cadastra pelo formulário; o
  acompanhamento é feito pela equipe no painel.
- **Não há multiempresa.** Uma instalação atende uma operação.
