# PRD — Miliano Business Solutions CRM

## Problema
CRM para a Miliano Business Solutions (@recompensalogistica), que contrata
restaurantes e entregadores. Precisa cobrir a prospecção comercial, os cadastros,
as regras de contrato, o acompanhamento das entregas e o acerto financeiro com as
duas pontas.

## Arquitetura
- Backend: FastAPI + MongoDB (motor), JWT em cookie httpOnly, rotas `/api/*`,
  dividido em `app/routers/` por domínio.
- Frontend: React 19 + React Router + TanStack Query + Tailwind + shadcn/ui +
  Recharts + sonner.
- Tema escuro (laranja #F97316 / slate), fontes Plus Jakarta Sans + DM Sans.
  A classe `dark` fica no `<html>` para que portais do Radix herdem o tema.

## Perfis
- **Administrador** — acesso total, incluindo exclusões, chaves de API,
  gestão de usuários e auditoria.
- **Gestor operacional** — opera o dia a dia sem as ações acima.

## Requisitos
- Autenticação e-mail/senha com renovação de sessão e troca da própria senha
- Funil comercial (lead → contato → negociação → proposta → ganho/perdido),
  com motivo de perda obrigatório e conversão de lead em restaurante
- Atividades: tarefas com prazo e interações registradas por cadastro
- CRUD de restaurantes e entregadores, com linha do tempo por cadastro
- Contratos (taxa fixa / valor por km / comissão) e pagamentos com liquidação
  e estorno
- Pedidos com fluxo de status validado e lançamento financeiro automático
- Dashboard com KPIs, tendência, alertas acionáveis e resumo do funil
- Relatórios com período e exportação CSV/PDF
- Busca global (Ctrl/⌘+K), auditoria de alterações, integrações (chaves/webhooks)
- Formulário público personalizável: link `/f/<slug>` que alimenta lead,
  restaurante ou entregador direto no CRM. Vem com "Cadastro de Entregadores"
  pronto, reproduzindo o Google Forms que a operação usava (com dados bancários
  e PIX), e editável pela tela.
- Parceria oficial Keeta exibida no CRM e no formulário público

## Estado (2026-09)
Reescrita completa a partir da versão de 2026-06. O que a versão anterior
entregava continua funcionando; o que foi corrigido e acrescentado está no
README, na seção de arquitetura e segurança.

Pontos que definem o comportamento atual e não são óbvios pelo código:
- Relacionamentos por **id**, com propagação de nome para o histórico.
- `orders_month` é **calculado na leitura**; gravado no documento, um contador
  mensal nunca virava o mês.
- O motor financeiro (`app/financials.py`) é idempotente e reversível, e o
  pedido guarda quem foi creditado (`credited_driver_id`, `credited_amount`)
  para que o estorno devolva exatamente o que entrou.
- Todo recorte de "hoje" passa por `app/tempo.py`, no fuso `TIMEZONE`
  (padrão America/Sao_Paulo). Em UTC o dia virava às 21h de Brasília.
- A senha do `.env` só vale na criação da conta; o seed não a reescreve.
- `tailwind.config.js` REDEFINE as rampas `slate` e `orange`: são o grafite e o
  dourado da marca Miliano, não as cores padrão do Tailwind.
- O slug do formulário nunca muda depois de criado — é o link já distribuído.
- Cadastro vindo de formulário nasce em análise/offline e leva `origem`.
- A carga do formulário de entregadores é travada por SLUG, não por coleção
  vazia: formulários criados pela equipe não são sobrescritos.
- CPF, banco, agência, conta e PIX são campos do entregador (usados no
  repasse), e só são legíveis com sessão.
- Verde e amarelo Keeta ficam restritos aos pontos da parceria; o dourado
  continua sendo a cor do sistema.
- A navegação é no topo (`components/Layout.jsx`), não lateral.
- A migração de startup (`app/seed.py`) recalcula saldos a partir dos pedidos
  reais uma única vez, marcada em `migrations`.

## Credenciais
Definidas em `backend/.env` (`ADMIN_*` / `MANAGER_*`). Não versionar.

## Backlog
- P1: notificação de atividade vencendo (e-mail ou WhatsApp)
- P1: metas comerciais por gestor e relatório de conversão por origem de lead
- P2: anexos de documentos por cadastro (contrato social, CNH, CRLV)
- P2: recebimento real de webhooks dos marketplaces (hoje o painel só cadastra
  e lista; não há endpoint de entrada consumindo eventos)
- P2: autenticação de terceiros pelas chaves de API (as chaves são geradas e
  revogadas, mas nenhuma rota as aceita ainda como credencial)
- P3: modo claro
