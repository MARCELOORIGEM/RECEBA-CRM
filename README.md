# Miliano CRM

CRM da **Miliano Business Solutions** ([@recompensalogistica](https://instagram.com/recompensalogistica)),
empresa que conecta restaurantes a entregadores.

O sistema cobre o ciclo inteiro: prospecção do restaurante no funil, cadastro do
parceiro, regra de contrato, acompanhamento dos pedidos e o acerto financeiro
com as duas pontas.

---

## Como rodar

Pré-requisitos: **Python 3.11+**, **Node 18+** e um **PostgreSQL 15+** acessível
— o Supabase ou um local (`docker run -d -e POSTGRES_PASSWORD=dev -p 5432:5432
postgres:17-alpine` resolve). A conexão vai em `DATABASE_URL`, no `backend/.env`.

```bash
# Backend
cd backend
python -m venv .venv && .venv/Scripts/activate     # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                               # preencha antes de subir
uvicorn server:app --reload --port 8001

# Frontend (outro terminal)
cd frontend
cp .env.example .env                               # aponte REACT_APP_BACKEND_URL para a API
yarn install
yarn start
```

Na primeira subida o backend aplica o schema (tabelas, índices e RLS, tudo
idempotente), cria as contas de `ADMIN_EMAIL`/`MANAGER_EMAIL` e — se
`SEED_DEMO_DATA=true` — popula dados de exemplo.

Documentação interativa da API: `http://localhost:8001/docs`.

### Em produção

A pilha inteira (PostgreSQL, API e painel atrás de Nginx) sobe com um comando
— ou, em plataforma de serviço único com o banco no Supabase, veja
**[RAILWAY.md](RAILWAY.md)**:

```bash
python scripts/gerar_segredos.py https://crm.suaempresa.com.br > .env
# aponte o DNS do domínio para este servidor e abra as portas 80 e 443
docker compose up -d --build
./scripts/instalar_cron.sh          # backup diário + vigia do /api/health
```

Sobem quatro serviços: PostgreSQL, a API, o painel em Nginx e um
**Caddy terminando HTTPS**, com certificado Let's Encrypt obtido e renovado
sozinho. O banco não publica porta nenhuma e o HTTP interno fica no loopback.

**[PRODUCAO.md](PRODUCAO.md)** é o guia completo: o que o banco precisa ter e
como provisioná-lo, cada variável de ambiente, backup e restauração, as
obrigações de LGPD do formulário, a integração com marketplace e a lista do que
conferir antes de abrir para a equipe.

---

## Arquitetura

```
backend/
  server.py            ponto de entrada (uvicorn server:app)
  app/
    config.py          configuração vinda do .env
    pg.py              pool asyncpg, schema no boot, contador atômico
    sql/               schema PostgreSQL: tabelas, índices, RLS
    consulta.py        construtor de WHERE com parâmetros e colunas conferidas
    security.py        senhas (bcrypt), tokens JWT, cookies
    deps.py            get_current_user, require_admin
    models.py          modelos de entrada com validação
    repo.py            leitura, escrita, paginação e get_or_404
    financials.py      efeitos financeiros de uma entrega
    tempo.py           fronteiras de dia e mês no fuso do negócio
    rede.py            IP real do cliente (só confia no proxy quando mandado)
    observabilidade.py logs, id de requisição, Sentry
    audit.py           trilha de auditoria
    form_templates.py  modelos padrão dos formulários (fonte única)
    seed.py            contas iniciais, formulário padrão, dados de exemplo
    main.py            app FastAPI, CORS, tratadores de erro
    routers/           auth, restaurants, drivers, contracts, payments,
                       orders, leads, activities, dashboard, users,
                       integrations, forms, public, entrada, senha, misc
frontend/src/
  lib/api.js           cliente axios, renovação de sessão, formatação
  context/             autenticação
  components/          Logo, Keeta, Layout, CommandPalette, ConfirmDialog,
                       ErrorBoundary, DetailSheet, StatusBadge,
                       Ui (primitivas), ui/ (shadcn)
  pages/               Dashboard, Pipeline, Activities, Orders, Restaurants,
                       Drivers, Forms, PublicForm, ResetPassword, Contracts,
                       Reports, Integrations, Users
```

**Stack:** FastAPI + asyncpg/PostgreSQL (Supabase) · React 19 + React Router + TanStack Query +
Tailwind + shadcn/ui + Recharts.

---

## Modelo de dados

| Tabela | Papel |
|---|---|
| `leads` | funil comercial, com histórico de etapas e motivo de perda |
| `activities` | tarefas com prazo e interações registradas |
| `restaurants` / `drivers` | cadastros, com saldos calculados pelo sistema |
| `contracts` | regra de remuneração por parte (fixa, por km ou comissão) |
| `orders` | pedidos, com repasse e comissão lançados na entrega |
| `payments` | repasses e cobranças, com liquidação e estorno |
| `audit_logs` | quem mudou o quê, quando |
| `api_keys` / `webhooks` / `webhook_logs` | integrações |
| `forms` / `form_submissions` | formulários públicos e respostas recebidas |
| `users` | acessos ao painel |
| `password_resets` | pedidos de nova senha (só o hash do token; expira em 30 min) |

Cadastros se ligam por **id**, não por nome. Renomear um restaurante propaga o
novo nome para pedidos, contratos e pagamentos, em vez de deixar o histórico
apontando para um nome que não existe mais.

### Como o dinheiro é calculado

Marcar um pedido como **entregue** dispara `app/financials.py`:

- **Repasse ao entregador** — pela regra do contrato ativo: `valor_km × distância`,
  `comissão % × taxa de entrega`, ou zero para contrato de taxa fixa mensal
  (que não remunera por corrida). Sem contrato, vale a taxa de entrega cheia.
- **Comissão da Miliano** — `% do contrato` ou, na falta dele, a comissão do
  cadastro do restaurante, aplicada sobre o valor do pedido.
- Os dois lançamentos sobem `balance_due` do entregador e `commission_due` do
  restaurante; liquidar o pagamento correspondente baixa esses saldos.

O lançamento é idempotente (`financials_applied` no pedido) e reversível:
voltar o status ou excluir o pedido estorna os valores. O pedido guarda **quem
foi creditado e sobre qual valor**, então o estorno devolve exatamente o que
entrou — mesmo que o cadastro tenha sido renomeado ou o valor editado depois.

### Fuso horário

Tudo que fala em "hoje" — KPIs, gráfico por hora, tendência, abas da agenda,
repasses vencidos — usa as fronteiras de dia em `TIMEZONE` (padrão
`America/Sao_Paulo`), não em UTC. Em UTC, o dia viraria às 21h no horário de
Brasília, bem no pico das entregas: o que fosse entregue das 21h à meia-noite
contaria no dia seguinte.

---

## Formulário público de cadastro

O gestor monta o formulário em **Formulários**, escolhe os campos, copia o link
(`/f/<slug>`) e manda para quem vai se cadastrar. A resposta entra direto no
CRM, no destino escolhido: lead, restaurante ou entregador.

Na primeira subida o sistema já cria **"Cadastro de Entregadores"** — as mesmas
10 perguntas, ordem e instruções do formulário que a operação usava no Google
Forms, incluindo banco, agência, conta e chave PIX. Continua editável: dá para
acrescentar, remover, reordenar e mudar o tipo de cada campo.

A carga é travada pelo **slug**, não por "a coleção está vazia": formulários que
a equipe já tenha criado permanecem, e este entra ao lado sem sobrescrever nada.

### Dados de pagamento

CPF, banco, agência, conta e PIX são campos de verdade do entregador, não texto
solto — é com eles que o repasse sai, e aparecem no detalhe do cadastro. O
formulário é público; **o que ele gera não é**: ler qualquer um desses dados
exige sessão.

- Campos com chave conhecida (`name`, `phone`, `cnpj`…) gravam no próprio
  cadastro; qualquer outra chave vira **informação extra**, guardada no registro
  em vez de descartada.
- O **slug não muda** quando o título é editado: o link já está no WhatsApp de
  dezenas de pessoas.
- Quem chega pelo formulário nasce **em análise** (restaurante) ou **offline**
  (entregador), nunca ativo, e fica marcado com `origem: "formulario"`.

### Tipos de campo

`texto` · `email` · `telefone` · `cpf` · `numero` · `data` · `escolha`
(múltipla escolha em botões) · `selecao` (lista suspensa) · `textarea`

`cpf` guarda só os 11 dígitos, aceitando o valor formatado; `escolha` e
`selecao` recusam qualquer valor fora da lista.

### O que protege a rota aberta

`/api/public/*` responde sem sessão, então é tratada como se houvesse um robô do
outro lado:

- devolve **só** título, descrição e campos — nada de destino, autor, contadores
  ou ids internos;
- valida cada resposta contra a definição do campo (obrigatório, tipo, opções,
  tamanho) e **ignora qualquer chave** que o cliente invente, então ninguém
  escolhe o próprio `status` ou zera a comissão pelo corpo da requisição;
- limita envios por IP (10 por hora, ajustável em `MAX_ENVIOS_POR_IP`);
- **exige o aceite do aviso de privacidade** e guarda, junto da resposta, o
  texto que estava no ar no momento do envio;
- tem campo-isca invisível: preenchido, a resposta parece um sucesso e não grava
  nada — dizer "você é um robô" só ensina o robô a contornar;
- formulário desativado responde `410`, para ver e para responder.

---

## Identidade visual

A marca é **Miliano Business Solutions**: grafite quente, dourado e prata.

A **parceria oficial Keeta** aparece em três lugares — selo na barra do topo,
faixa no dashboard e cabeçalho do formulário público — com o verde e o amarelo
da marca deles. Essas duas cores ficam restritas a esses pontos: espalhá-las
pela interface apagaria as duas paletas.

A navegação fica **no topo**, não numa barra lateral: assim os 256px que a
lateral ocupava voltam para tabelas, kanban e gráficos, e o mesmo componente
serve celular e desktop.

As rampas `slate` e `orange` do Tailwind são **redefinidas** em
`tailwind.config.js` — `slate-*` é o grafite da marca e `orange-*` é o dourado
do logo, não as cores padrão do Tailwind. A interface usava essas classes em
~600 lugares; trocar o valor por trás do nome recolore tudo sem churn. O
componente `Logo` reproduz o arco dourado, o letreiro cromado e a assinatura.

Toda animação da marca respeita `prefers-reduced-motion`.

---

## Perfis de acesso

| | Gestor | Administrador |
|---|:--:|:--:|
| Cadastrar e editar tudo | ✅ | ✅ |
| Mover funil, pedidos, atividades | ✅ | ✅ |
| Liquidar pagamento | ✅ | ✅ |
| **Excluir** cadastros, pedidos, contratos | ❌ | ✅ |
| Estornar liquidação | ❌ | ✅ |
| Chaves de API e webhooks | ❌ | ✅ |
| Trocar a própria senha e o próprio nome | ✅ | ✅ |
| Gestão de usuários | ❌ | ✅ |
| Auditoria | ❌ | ✅ |

O sistema impede que reste zero administrador ativo.

---

## Segurança

- Senhas com bcrypt; sessão em cookie `httpOnly` com renovação automática.
- Flags do cookie derivadas do esquema de `FRONTEND_URL`: `Secure`+`SameSite=None`
  em HTTPS, `SameSite=Lax` em HTTP local.
- Cadastro público desligado por padrão (`ALLOW_PUBLIC_REGISTER`) e sem
  escolha de perfil pelo cliente.
- Limite de tentativas de login por e-mail + IP.
- Chaves de API guardadas só como hash SHA-256; o valor aparece uma única vez,
  na criação. A listagem mostra apenas um prefixo.
- Toda escrita passa por validação de tipo, faixa e enum antes de chegar ao banco.
- Cada pessoa troca a própria senha em **Minha conta** (no menu da conta),
  exigindo a senha atual. A senha do `.env` vale apenas na criação da conta:
  reescrevê-la a cada boot desfaria a troca feita pelo usuário.
- Quem esquece a senha não depende de alguém digitar outra por ela: o
  administrador gera, em **Usuários**, um **link de uso único** válido por 30
  minutos. O banco guarda só o hash do token, gerar um novo invalida o anterior
  e o uso apaga o pedido. Sem SMTP no caminho — o link vai pelo canal que a
  equipe já usa.
- `X-Forwarded-For` só é lido quando `TRUSTED_PROXY=true`. O cabeçalho é
  forjável: aceito sem proxy na frente, qualquer um escolheria o próprio IP e
  escaparia dos limites por IP.
- Chave de API vale como credencial na rota de entrada de eventos
  (`POST /api/integracoes/eventos/{provedor}`), conferida contra o hash.
- O `index.html` não carrega **nenhum script de terceiro**. O PostHog e o
  `assets.emergent.sh` que vinham do andaime foram removidos: essa mesma página
  serve o formulário onde o entregador digita CPF e conta bancária.
- Toda requisição carrega um `X-Request-ID`, devolvido também na mensagem de
  erro 500 — o usuário informa o código e ele leva direto à linha do log.

- As credenciais dos testes vêm do ambiente, não do código. Os roteiros de
  navegador e o `conftest.py` do pytest traziam o e-mail e a senha reais do
  administrador escritos dentro deles — num repositório publicado, isso é a
  conta do sistema entregue a quem clonar.

> **Antes de publicar:** gere um `JWT_SECRET` novo, troque as senhas das contas
> iniciais e deixe `SEED_DEMO_DATA=false`. O `.env` deixou de ser versionado —
> se ele já estava no histórico do Git, os segredos anteriores precisam ser
> rotacionados, porque continuam recuperáveis lá.

---

## Testes

```bash
cd backend
REACT_APP_BACKEND_URL=http://localhost:8001 pytest tests/ -n 2 --dist loadscope -q
```

179 testes cobrem autenticação, permissões por perfil, validação de entrada,
404 em recursos inexistentes, fluxo de status do pedido, cálculo e estorno
financeiro, fronteiras de fuso horário, funil, atividades, auditoria, busca,
conta do usuário, integrações, o formulário de entregadores com dados bancários
e o formulário público — incluindo o que a rota aberta se recusa a fazer —,
o link de nova senha, a entrada de eventos do marketplace, o aceite de
privacidade e o teto de envios por IP.

Boa parte deles é **teste de regressão**: cada um trava um comportamento que a
versão anterior errava, e o motivo está escrito no próprio teste.

### No CI

`.github/workflows/ci.yml` roda a cada push e PR, em três frentes: a suíte de
pytest contra um PostgreSQL de verdade (antes dela, `scripts/conferir_schema.py`
confere se toda coluna que o código grava ou filtra existe no schema), o build
do painel e o build das duas imagens Docker. Um PR que quebra o cálculo financeiro, a permissão por perfil ou o
build não chega a ser mesclado — antes, isso só aparecia se alguém lembrasse de
rodar os testes.

### No navegador

Sete roteiros abrem o sistema num Chrome de verdade e conferem o que o pytest
não alcança — a tela desenha, o clique faz o que promete, o dado entra e
aparece do outro lado:

```bash
cd tests_e2e && npm install        # uma vez
BASE=http://localhost:3000 ./rodar.sh   # credenciais vêm do backend/.env
```

São ~79 conferências cobrindo o painel inteiro, o perfil do gestor, o
formulário público ponta a ponta, a parceria Keeta, o construtor de
formulários, o "Outro:" do campo Banco e o link de nova senha. Cada roteiro
cria o que precisa e **apaga no fim** — detalhes em
[tests_e2e/README.md](tests_e2e/README.md).
