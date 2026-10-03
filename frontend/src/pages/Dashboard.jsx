import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertCircle, Bike, CalendarClock, Filter, Package, Store, Target, TrendingUp, Truck, Wallet,
} from "lucide-react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, ComposedChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, brl, dataBR, num } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { Delta, EmptyState, Loading, Panel, SectionTitle, tooltipChart } from "@/components/Ui";
import { FaixaKeeta } from "@/components/Keeta";

const KPIS = [
  {
    key: "entregas_hoje",
    delta: "entregas_hoje_delta",
    label: "Entregas hoje",
    icon: Package,
    cor: "text-primary",
    fundo: "bg-primary/15",
    testid: "kpi-metric-entregas-hoje",
  },
  {
    key: "em_rota",
    label: "Em rota agora",
    icon: Truck,
    cor: "text-blue-400",
    fundo: "bg-blue-500/15",
    testid: "kpi-metric-em-rota",
  },
  {
    key: "taxa_sucesso",
    label: "Taxa de sucesso",
    sufixo: "%",
    icon: TrendingUp,
    cor: "text-emerald-400",
    fundo: "bg-emerald-500/15",
    dica: "Entregues ÷ pedidos finalizados",
    testid: "kpi-metric-taxa-sucesso",
  },
  {
    key: "entregadores_online",
    label: "Entregadores online",
    icon: Bike,
    cor: "text-amber-400",
    fundo: "bg-amber-500/15",
    testid: "kpi-metric-entregadores",
  },
];

export default function Dashboard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard"],
    queryFn: async () => (await api.get("/dashboard/stats")).data,
    refetchInterval: 30_000,
  });

  if (isLoading) return <Loading className="h-96 items-center" />;
  if (isError || !data) {
    return (
      <Panel>
        <EmptyState
          icon={AlertCircle}
          titulo="Não foi possível carregar o painel"
          descricao="Verifique a conexão com o servidor e recarregue a página."
        />
      </Panel>
    );
  }

  const { kpi, financeiro, funil, agenda, hourly, trend, by_category, recent_orders, pending_payments, top_restaurantes } = data;

  return (
    <div className="space-y-6 animate-fade-up" data-testid="dashboard-page">
      <FaixaKeeta />

      {/* Avisos que pedem ação — antes o painel só informava, nunca apontava
          o que estava atrasado. */}
      {(agenda?.atrasadas > 0 || financeiro?.repasses_vencidos > 0) && (
        <div className="flex flex-wrap gap-3">
          {agenda?.atrasadas > 0 && (
            <Link
              to="/atividades"
              data-testid="alert-atividades"
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-red-500/30 bg-red-500/10 text-sm text-red-300 hover:bg-red-500/15 transition-colors"
            >
              <CalendarClock className="w-4 h-4" aria-hidden="true" />
              <strong>{agenda.atrasadas}</strong> atividade(s) atrasada(s) — ver agenda
            </Link>
          )}
          {financeiro?.repasses_vencidos > 0 && (
            <Link
              to="/contratos-pagamentos"
              data-testid="alert-repasses"
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-amber-500/30 bg-amber-500/10 text-sm text-amber-300 hover:bg-amber-500/15 transition-colors"
            >
              <Wallet className="w-4 h-4" aria-hidden="true" />
              <strong>{financeiro.repasses_vencidos}</strong> repasse(s) vencido(s) — liquidar
            </Link>
          )}
        </div>
      )}

      {/* KPIs operacionais */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-6">
        {KPIS.map((k) => {
          const Icon = k.icon;
          return (
            <Panel
              key={k.key}
              data-testid={k.testid}
              className="p-5 hover:border-slate-700 transition-colors"
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  {k.label}
                </span>
                <div className={`w-9 h-9 rounded-lg ${k.fundo} flex items-center justify-center`}>
                  <Icon className={`w-[18px] h-[18px] ${k.cor}`} aria-hidden="true" />
                </div>
              </div>
              <p className="font-heading text-3xl font-extrabold text-slate-50">
                {num(kpi[k.key])}
                {k.sufixo || ""}
              </p>
              <div className="mt-1 min-h-[16px]">
                {k.delta ? <Delta value={kpi[k.delta]} /> : (
                  <span className="text-xs text-slate-500">{k.dica || ""}</span>
                )}
              </div>
            </Panel>
          );
        })}
      </div>

      {/* Financeiro do mês */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 sm:gap-6">
        <Panel className="p-5">
          <p className="flex items-center gap-2 text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2">
            <Wallet className="w-4 h-4" aria-hidden="true" /> Receita da Miliano
          </p>
          <p className="font-heading text-2xl font-bold text-emerald-400" data-testid="kpi-metric-receita">
            {brl(financeiro.receita_mes)}
          </p>
          <p className="text-xs text-slate-500 mt-1">Comissão do mês</p>
        </Panel>
        <Panel className="p-5">
          <p className="flex items-center gap-2 text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2">
            <TrendingUp className="w-4 h-4" aria-hidden="true" /> GMV do mês
          </p>
          <p className="font-heading text-2xl font-bold text-slate-50">{brl(financeiro.gmv_mes)}</p>
          <p className="text-xs text-slate-500 mt-1">Ticket médio {brl(financeiro.ticket_medio)}</p>
        </Panel>
        <Panel className="p-5">
          <p className="flex items-center gap-2 text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2">
            <Bike className="w-4 h-4" aria-hidden="true" /> Custo com entregas
          </p>
          <p className="font-heading text-2xl font-bold text-blue-400">
            {brl(financeiro.custo_entregadores)}
          </p>
          <p className="text-xs text-slate-500 mt-1">Margem {brl(financeiro.margem_mes)}</p>
        </Panel>
        <Panel className="p-5">
          <p className="flex items-center gap-2 text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2">
            <AlertCircle className="w-4 h-4" aria-hidden="true" /> Repasses pendentes
          </p>
          <p className="font-heading text-2xl font-bold text-amber-400">
            {brl(financeiro.repasse_pendente)}
          </p>
          <p className="text-xs text-slate-500 mt-1">
            {financeiro.repasses_vencidos > 0
              ? `${financeiro.repasses_vencidos} vencido(s)`
              : "Nenhum vencido"}
          </p>
        </Panel>
        <Panel className="p-5">
          <p className="flex items-center gap-2 text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2">
            <Target className="w-4 h-4" aria-hidden="true" /> Funil aberto
          </p>
          <p className="font-heading text-2xl font-bold text-primary">
            {brl(funil?.valor_em_aberto)}
          </p>
          <p className="text-xs text-slate-500 mt-1">{funil?.em_aberto || 0} negociações</p>
        </Panel>
      </div>

      {/* Tendência */}
      <Panel className="p-5">
        <SectionTitle>Últimos 14 dias</SectionTitle>
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={trend}>
            <CartesianGrid strokeDasharray="3 3" stroke="#24262B" vertical={false} />
            <XAxis dataKey="dia" stroke="#6B6F78" fontSize={11} tickLine={false} />
            <YAxis stroke="#6B6F78" fontSize={11} allowDecimals={false} tickLine={false} axisLine={false} />
            <Tooltip {...tooltipChart} cursor={{ fill: "#24262B33" }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="pedidos" name="Pedidos" fill="#363940" radius={[4, 4, 0, 0]} />
            <Line
              type="monotone"
              dataKey="entregues"
              name="Entregues"
              stroke="#F5A524"
              strokeWidth={2.5}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </Panel>

      {/* Hora a hora + categorias */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <Panel className="lg:col-span-7 p-5">
          <SectionTitle>Volume de hoje por hora</SectionTitle>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={hourly}>
              <defs>
                <linearGradient id="grad-laranja" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#F5A524" stopOpacity={0.5} />
                  <stop offset="95%" stopColor="#F5A524" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#24262B" vertical={false} />
              <XAxis dataKey="hora" stroke="#6B6F78" fontSize={11} tickLine={false} />
              <YAxis stroke="#6B6F78" fontSize={11} allowDecimals={false} tickLine={false} axisLine={false} />
              <Tooltip {...tooltipChart} />
              <Area
                type="monotone"
                dataKey="entregas"
                name="Pedidos"
                stroke="#F5A524"
                strokeWidth={2}
                fill="url(#grad-laranja)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </Panel>

        <Panel className="lg:col-span-5 p-5">
          <SectionTitle>Entregas por categoria</SectionTitle>
          {by_category?.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={by_category} layout="vertical" margin={{ left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#24262B" horizontal={false} />
                <XAxis type="number" stroke="#6B6F78" fontSize={11} allowDecimals={false} />
                <YAxis
                  type="category"
                  dataKey="categoria"
                  stroke="#6B6F78"
                  fontSize={11}
                  width={96}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip {...tooltipChart} cursor={{ fill: "#24262B" }} />
                <Bar dataKey="total" name="Entregas" fill="#3FBF8F" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState icon={Store} titulo="Sem entregas concluídas ainda" />
          )}
        </Panel>
      </div>

      {/* Feeds */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <Panel className="lg:col-span-7 p-5">
          <SectionTitle
            right={
              <Link to="/pedidos" className="text-xs text-primary hover:underline">
                ver todos
              </Link>
            }
          >
            Entregas recentes
          </SectionTitle>
          {recent_orders?.length ? (
            <ul className="space-y-2">
              {recent_orders.map((o) => (
                <li
                  key={o.id}
                  className="flex items-center justify-between gap-3 py-2.5 border-b border-slate-800/60 last:border-0"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-primary font-mono">{o.code}</p>
                    <p className="text-xs text-slate-500 truncate">
                      {o.restaurant_name} → {o.customer_name}
                    </p>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-sm text-slate-300">{brl(o.amount)}</span>
                    <StatusBadge status={o.status} />
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={Package} titulo="Nenhum pedido registrado" />
          )}
        </Panel>

        <div className="lg:col-span-5 space-y-6">
          <Panel className="p-5">
            <SectionTitle
              right={
                <Link to="/contratos-pagamentos" className="text-xs text-primary hover:underline">
                  liquidar
                </Link>
              }
            >
              Repasses pendentes
            </SectionTitle>
            {pending_payments?.length ? (
              <ul className="space-y-3">
                {pending_payments.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-100 truncate">{p.creditor}</p>
                      <p className="text-xs text-slate-500 capitalize">
                        {p.creditor_type} • vence {dataBR(p.due_date)}
                      </p>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-sm font-semibold text-amber-400">{brl(p.amount)}</p>
                      <StatusBadge status={p.status} />
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate-500">Nenhum repasse pendente.</p>
            )}
          </Panel>

          <Panel className="p-5">
            <SectionTitle
              right={
                <Link to="/funil" className="text-xs text-primary hover:underline">
                  abrir funil
                </Link>
              }
            >
              Top restaurantes do mês
            </SectionTitle>
            {top_restaurantes?.length ? (
              <ul className="space-y-2.5">
                {top_restaurantes.map((r, i) => (
                  <li key={r.nome} className="flex items-center gap-3">
                    <span className="w-5 text-xs font-bold text-slate-600">{i + 1}</span>
                    <span className="flex-1 min-w-0 text-sm text-slate-200 truncate">{r.nome}</span>
                    <span className="text-xs text-slate-500">{r.entregas} entregas</span>
                    <span className="text-sm font-semibold text-slate-100 w-24 text-right">
                      {brl(r.valor)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState icon={Filter} titulo="Sem entregas neste mês" />
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
