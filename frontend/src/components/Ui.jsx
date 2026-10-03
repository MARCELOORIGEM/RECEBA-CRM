import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { brl } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Cartão base usado em todas as telas — antes essa combinação de classes era
 *  reescrita em cada página, com pequenas divergências de padding e borda. */
export function Panel({ children, className = "", ...props }) {
  return (
    <div
      className={`rounded-xl border border-slate-800 bg-slate-900 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function SectionTitle({ children, right }) {
  return (
    <div className="flex items-center justify-between gap-3 mb-4">
      <h3 className="font-heading text-lg font-semibold text-slate-100">{children}</h3>
      {right}
    </div>
  );
}

export function MetricCard({ icon: Icon, label, value, hint, tone = "text-slate-50", testid }) {
  return (
    <Panel className="p-5" data-testid={testid}>
      <div className="flex items-center gap-2 text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2">
        {Icon && <Icon className="w-4 h-4" aria-hidden="true" />} {label}
      </div>
      <p className={`font-heading text-2xl font-bold ${tone}`}>{value}</p>
      {hint && <p className="text-xs text-slate-500 mt-1">{hint}</p>}
    </Panel>
  );
}

/** Variação do valor contra o período anterior. */
export function Delta({ value }) {
  if (value === null || value === undefined) return null;
  const n = Number(value) || 0;
  const cor = n > 0 ? "text-emerald-400" : n < 0 ? "text-red-400" : "text-slate-500";
  const sinal = n > 0 ? "+" : "";
  return (
    <span className={`text-xs font-semibold ${cor}`}>
      {sinal}
      {n.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}% vs ontem
    </span>
  );
}

export function EmptyState({ icon: Icon, titulo, descricao, acao, testid }) {
  return (
    <div
      className="flex flex-col items-center justify-center py-16 px-6 text-center"
      data-testid={testid || "empty-state"}
    >
      {Icon && (
        <div className="w-12 h-12 rounded-2xl bg-slate-800/60 flex items-center justify-center mb-3">
          <Icon className="w-6 h-6 text-slate-500" aria-hidden="true" />
        </div>
      )}
      <p className="font-heading font-semibold text-slate-300">{titulo}</p>
      {descricao && <p className="text-sm text-slate-500 mt-1 max-w-sm">{descricao}</p>}
      {acao && <div className="mt-4">{acao}</div>}
    </div>
  );
}

export function Loading({ className = "py-16" }) {
  return (
    <div className={`flex justify-center ${className}`} role="status" aria-label="Carregando">
      <Loader2 className="w-6 h-6 animate-spin text-primary" />
    </div>
  );
}

/** Paginação — antes as tabelas puxavam até 1000 registros e renderizavam todos. */
export function Pagination({ page, pages, total, onChange, label = "registros" }) {
  if (!total) return null;
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 border-t border-slate-800 text-sm">
      <p className="text-slate-500">
        {total.toLocaleString("pt-BR")} {label}
        {pages > 1 && ` • página ${page} de ${pages}`}
      </p>
      {pages > 1 && (
        <div className="flex items-center gap-1">
          <Button
            size="icon"
            variant="ghost"
            aria-label="Página anterior"
            data-testid="page-prev"
            disabled={page <= 1}
            onClick={() => onChange(page - 1)}
            className="h-8 w-8 text-slate-400 hover:text-slate-100 disabled:opacity-30"
          >
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            aria-label="Próxima página"
            data-testid="page-next"
            disabled={page >= pages}
            onClick={() => onChange(page + 1)}
            className="h-8 w-8 text-slate-400 hover:text-slate-100 disabled:opacity-30"
          >
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      )}
    </div>
  );
}

/** Botão só de ícone. O `aria-label` é obrigatório: sem ele, leitor de tela
 *  anuncia apenas "botão", que era o caso em todas as ações de tabela. */
export function IconButton({
  icon: Icon,
  label,
  tone = "hover:text-primary",
  className = "",
  ...props
}) {
  return (
    <Button
      size="icon"
      variant="ghost"
      aria-label={label}
      title={label}
      // `className` é mesclado, não sobrescrito: com o spread depois do
      // atributo, quem passasse um tamanho perdia também a cor do ícone.
      className={cn("h-8 w-8 text-slate-400 disabled:opacity-30", tone, className)}
      {...props}
    >
      <Icon className="w-4 h-4" aria-hidden="true" />
    </Button>
  );
}

export const tooltipChart = {
  contentStyle: {
    background: "#16171A",
    border: "1px solid #24262B",
    borderRadius: 12,
    color: "#F7F7F8",
    fontSize: 12,
  },
  labelStyle: { color: "#8B8F98" },
};

export const moeda = brl;
