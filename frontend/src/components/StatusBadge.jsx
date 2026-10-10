import { STATUS } from "@/lib/funil";

const VERDE = "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
const AZUL = "bg-blue-500/15 text-blue-400 border-blue-500/30";
const AMBAR = "bg-amber-500/15 text-amber-400 border-amber-500/30";
const CINZA = "bg-slate-500/15 text-slate-300 border-slate-500/30";
const VERMELHO = "bg-red-500/15 text-red-400 border-red-500/30";

const STYLES = {
  // pedidos
  entregue: VERDE,
  em_transito: AZUL,
  aguardando_coleta: AMBAR,
  criado: CINZA,
  cancelado: VERMELHO,
  // entregadores
  disponivel: VERDE,
  em_entrega: AZUL,
  offline: CINZA,
  indisponivel: VERMELHO,
  // financeiro
  pago: VERDE,
  pendente: AMBAR,
  atrasado: VERMELHO,
  // cadastros e contratos
  ativo: VERDE,
  suspenso: VERMELHO,
  inativo: CINZA,
  em_analise: AMBAR,
  encerrado: CINZA,
  // funil: as cores dos status de visita vêm de lib/funil.js
  ...Object.fromEntries(STATUS.map((st) => [st.chave, st.badge])),
};

const LABELS = {
  entregue: "Entregue",
  em_transito: "Em trânsito",
  aguardando_coleta: "Aguardando coleta",
  criado: "Criado",
  cancelado: "Cancelado",
  disponivel: "Disponível",
  em_entrega: "Em entrega",
  offline: "Offline",
  indisponivel: "Indisponível",
  pago: "Pago",
  pendente: "Pendente",
  atrasado: "Atrasado",
  ativo: "Ativo",
  suspenso: "Suspenso",
  inativo: "Inativo",
  em_analise: "Em análise",
  encerrado: "Encerrado",
  ...Object.fromEntries(STATUS.map((st) => [st.chave, st.rotulo])),
};

export const statusLabel = (s) => LABELS[s] || s || "—";

export function StatusBadge({ status, testid, className = "" }) {
  const cls = STYLES[status] || CINZA;
  return (
    <span
      data-testid={testid}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border whitespace-nowrap ${cls} ${className}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" aria-hidden="true" />
      {statusLabel(status)}
    </span>
  );
}
