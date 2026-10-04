/**
 * Telas que o administrador libera por usuário.
 *
 * Espelha `MODULOS` de backend/app/permissoes.py — as chaves precisam bater.
 * O bloqueio de verdade é na API (um gestor sem "Funil" recebe 403 de
 * /api/leads); aqui é só o que o menu mostra e para onde as rotas mandam.
 */
export const MODULOS = [
  { chave: "dashboard", rotulo: "Dashboard", rota: "/", descricao: "Números do dia e do mês, incluindo receita" },
  { chave: "pedidos", rotulo: "Pedidos", rota: "/pedidos", descricao: "Criar, atribuir e acompanhar entregas" },
  { chave: "funil", rotulo: "Funil", rota: "/funil", descricao: "Leads e negociações comerciais" },
  { chave: "atividades", rotulo: "Atividades", rota: "/atividades", descricao: "Agenda de tarefas e follow-ups" },
  { chave: "restaurantes", rotulo: "Restaurantes", rota: "/restaurantes", descricao: "Cadastro e saldo dos parceiros" },
  { chave: "entregadores", rotulo: "Entregadores", rota: "/entregadores", descricao: "Cadastro, CPF e dados bancários" },
  { chave: "formularios", rotulo: "Formulários", rota: "/formularios", descricao: "Links públicos e respostas recebidas" },
  { chave: "financeiro", rotulo: "Financeiro", rota: "/contratos-pagamentos", descricao: "Contratos, repasses e liquidações" },
  { chave: "relatorios", rotulo: "Relatórios", rota: "/relatorios", descricao: "Desempenho e balanço do período" },
  { chave: "integracoes", rotulo: "Integrações", rota: "/integracoes", descricao: "Webhooks e logs dos marketplaces" },
];

export const TODAS = MODULOS.map((m) => m.chave);

/** Primeira tela que o usuário pode abrir, para onde mandá-lo ao entrar. */
export function primeiraRota(pode) {
  const m = MODULOS.find((x) => pode(x.chave));
  return m ? m.rota : null;
}
