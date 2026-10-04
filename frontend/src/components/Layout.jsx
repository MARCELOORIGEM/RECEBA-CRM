import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart3, Bike, ChevronDown, FileInput, FileText, Filter, LayoutDashboard, LogOut,
  Menu, Package, Plug, Search, Settings2, Store, Users2, X,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { CommandPalette } from "@/components/CommandPalette";
import { AccountDialog } from "@/components/AccountDialog";
import { MarcaComMascote, SeloKeeta } from "@/components/Keeta";
import ErrorBoundary from "@/components/ErrorBoundary";

/* A navegação era uma barra lateral fixa de 256px. No topo ela devolve essa
   largura inteira ao conteúdo — que é onde ficam tabelas largas, kanban e
   gráficos — e usa o mesmo componente em celular e desktop.

   Os rótulos encurtaram ("Contratos & Pagamentos" -> "Financeiro"): na
   horizontal, nome comprido rouba espaço de todos os outros itens. */
const NAV = [
  { to: "/", modulo: "dashboard", label: "Dashboard", icon: LayoutDashboard, testid: "sidebar-link-dashboard" },
  { to: "/pedidos", modulo: "pedidos", label: "Pedidos", icon: Package, testid: "sidebar-link-pedidos" },
  { to: "/funil", modulo: "funil", label: "Funil", icon: Filter, testid: "sidebar-link-funil" },
  {
    to: "/atividades", modulo: "atividades",
    label: "Atividades",
    icon: FileText,
    testid: "sidebar-link-atividades",
    badge: "atividades",
  },
  { to: "/restaurantes", modulo: "restaurantes", label: "Restaurantes", icon: Store, testid: "sidebar-link-restaurantes" },
  { to: "/entregadores", modulo: "entregadores", label: "Entregadores", icon: Bike, testid: "sidebar-link-entregadores" },
  { to: "/formularios", modulo: "formularios", label: "Formulários", icon: FileInput, testid: "sidebar-link-formularios" },
  {
    to: "/contratos-pagamentos", modulo: "financeiro",
    label: "Financeiro",
    icon: FileText,
    testid: "sidebar-link-contratos",
  },
  { to: "/relatorios", modulo: "relatorios", label: "Relatórios", icon: BarChart3, testid: "sidebar-link-relatorios" },
  { to: "/integracoes", modulo: "integracoes", label: "Integrações", icon: Plug, testid: "sidebar-link-integracoes" },
  {
    to: "/usuarios",
    label: "Usuários",
    icon: Users2,
    testid: "sidebar-link-usuarios",
    adminOnly: true,
  },
];

const TITULOS = {
  "/": ["Dashboard", "Visão geral da operação"],
  "/funil": ["Funil de Vendas", "Prospecção até o fechamento"],
  "/atividades": ["Atividades", "Tarefas e follow-ups"],
  "/restaurantes": ["Restaurantes", "Parceiros contratados"],
  "/entregadores": ["Entregadores", "Time de entrega"],
  "/formularios": ["Formulários", "Cadastro público por link"],
  "/contratos-pagamentos": ["Contratos & Pagamentos", "Regras e repasses"],
  "/pedidos": ["Pedidos", "Acompanhamento das entregas"],
  "/relatorios": ["Relatórios", "Desempenho e balanço"],
  "/integracoes": ["Integrações API", "Chaves e webhooks"],
  "/usuarios": ["Gestão de Usuários", "Acessos ao painel"],
};

export default function Layout() {
  const { user, logout, isAdmin, pode } = useAuth();
  const location = useLocation();
  const [menuMovel, setMenuMovel] = useState(false);
  const [menuConta, setMenuConta] = useState(false);
  const [conta, setConta] = useState(false);
  const refConta = useRef(null);

  useEffect(() => setMenuMovel(false), [location.pathname]);

  // A tela de login define o título da aba e ninguém o devolvia: já dentro do
  // sistema, o navegador continuava anunciando "Entrar".
  useEffect(() => {
    const [nome] = TITULOS[location.pathname] || ["Painel"];
    document.title = `${nome} • Miliano CRM`;
  }, [location.pathname]);

  // Menu da conta fecha ao clicar fora ou apertar Esc — sem isso ele ficaria
  // aberto por cima do conteúdo.
  useEffect(() => {
    if (!menuConta) return undefined;
    const fora = (e) => {
      if (refConta.current && !refConta.current.contains(e.target)) setMenuConta(false);
    };
    const esc = (e) => e.key === "Escape" && setMenuConta(false);
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", esc);
    };
  }, [menuConta]);

  const { data: resumo } = useQuery({
    queryKey: ["activities-summary"],
    queryFn: async () => (await api.get("/activities/summary")).data,
    refetchInterval: 60_000,
    // Sem a tela de Atividades a API responde 403; não adianta perguntar.
    enabled: pode("atividades"),
  });

  const contadores = { atividades: resumo?.atrasadas || 0 };
  const [titulo, subtitulo] = TITULOS[location.pathname] || ["Painel", "Central de operações"];
  const visiveis = NAV.filter((i) => (i.adminOnly ? isAdmin : pode(i.modulo)));

  const iniciais = (user?.name || "U")
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const Item = ({ item, bloco = false, onClick }) => {
    const Icon = item.icon;
    const badge = item.badge ? contadores[item.badge] : 0;
    return (
      <NavLink
        to={item.to}
        end={item.to === "/"}
        data-testid={item.testid}
        onClick={onClick}
        className={({ isActive }) =>
          [
            "flex items-center gap-2 rounded-lg text-sm font-medium transition-colors",
            bloco ? "px-3 py-3" : "shrink-0 whitespace-nowrap px-3 py-2",
            isActive
              ? "bg-primary/15 text-primary"
              : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-100",
          ].join(" ")
        }
      >
        <Icon className="h-[17px] w-[17px] shrink-0" aria-hidden="true" />
        {item.label}
        {badge > 0 && (
          <span
            className="ml-0.5 min-w-[18px] rounded-full bg-red-500/20 px-1.5 text-center text-[10px] font-bold text-red-400"
            aria-label={`${badge} atrasadas`}
          >
            {badge}
          </span>
        )}
      </NavLink>
    );
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-40 border-b border-slate-800 bg-slate-950/85 backdrop-blur-xl">
        {/* Linha 1 — marca, parceria e conta */}
        <div className="flex items-center gap-3 px-4 py-3 sm:px-6">
          <button
            className="shrink-0 text-slate-300 lg:hidden"
            onClick={() => setMenuMovel((v) => !v)}
            aria-label={menuMovel ? "Fechar menu" : "Abrir menu"}
            aria-expanded={menuMovel}
            data-testid="open-sidebar"
          >
            {menuMovel ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
          </button>

          <MarcaComMascote tamanho="sm" className="shrink-0" />

          <div className="hidden h-8 w-px bg-slate-800 xl:block" />
          <SeloKeeta className="hidden xl:flex" />

          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <button
              onClick={() =>
                document.dispatchEvent(
                  new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true }),
                )
              }
              data-testid="open-search"
              aria-label="Buscar em todo o sistema"
              className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-1.5 text-slate-500 transition-colors hover:border-slate-700 hover:text-slate-300"
            >
              <Search className="h-4 w-4" aria-hidden="true" />
              <span className="hidden text-xs md:inline">Buscar</span>
              <kbd className="hidden rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] md:inline">
                Ctrl K
              </kbd>
            </button>

            <span className="hidden items-center gap-2 text-xs font-medium text-emerald-400 sm:flex">
              <span
                className="h-2 w-2 animate-pulse rounded-full bg-emerald-500"
                aria-hidden="true"
              />
              Ao vivo
            </span>

            <div className="relative" ref={refConta}>
              <button
                onClick={() => setMenuConta((v) => !v)}
                aria-label="Menu da conta"
                aria-expanded={menuConta}
                aria-haspopup="menu"
                data-testid="open-account-menu"
                className="flex items-center gap-2 rounded-lg py-1 pl-1 pr-2 transition-colors hover:bg-slate-800/60"
              >
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/20 text-sm font-bold text-primary">
                  {iniciais}
                </span>
                <span className="hidden max-w-[8rem] truncate text-left text-sm text-slate-200 sm:block">
                  {user?.name}
                </span>
                <ChevronDown className="hidden h-4 w-4 text-slate-500 sm:block" aria-hidden="true" />
              </button>

              {menuConta && (
                <div
                  role="menu"
                  className="absolute right-0 top-full z-50 mt-2 w-56 animate-fade-up overflow-hidden rounded-xl border border-slate-800 bg-slate-900 shadow-2xl"
                >
                  <div className="border-b border-slate-800 px-4 py-3">
                    <p className="truncate text-sm font-medium text-slate-100">{user?.name}</p>
                    <p className="truncate text-xs text-slate-500">{user?.email}</p>
                    <p className="mt-1 text-[11px] text-primary">
                      {isAdmin ? "Administrador" : "Gestor"}
                    </p>
                  </div>
                  <button
                    role="menuitem"
                    onClick={() => {
                      setMenuConta(false);
                      setConta(true);
                    }}
                    data-testid="open-account"
                    className="flex w-full items-center gap-3 px-4 py-2.5 text-sm text-slate-300 transition-colors hover:bg-slate-800 hover:text-slate-50"
                  >
                    <Settings2 className="h-4 w-4" aria-hidden="true" /> Minha conta
                  </button>
                  <button
                    role="menuitem"
                    onClick={logout}
                    data-testid="logout-button"
                    className="flex w-full items-center gap-3 px-4 py-2.5 text-sm text-slate-400 transition-colors hover:bg-red-500/10 hover:text-red-400"
                  >
                    <LogOut className="h-4 w-4" aria-hidden="true" /> Sair
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Linha 2 — navegação. Rola na horizontal quando não cabe, em vez de
            quebrar em duas linhas ou sumir atrás de um submenu. */}
        <nav
          className="hidden items-center gap-1 overflow-x-auto px-4 pb-2 sm:px-6 lg:flex"
          aria-label="Navegação principal"
        >
          {visiveis.map((item) => (
            <Item key={item.to} item={item} />
          ))}
        </nav>

        {menuMovel && (
          <nav
            className="grid grid-cols-2 gap-1 border-t border-slate-800 px-4 py-3 lg:hidden"
            aria-label="Navegação principal"
          >
            {visiveis.map((item) => (
              <Item key={item.to} item={item} bloco onClick={() => setMenuMovel(false)} />
            ))}
            <div className="col-span-2 pt-2">
              <SeloKeeta />
            </div>
          </nav>
        )}
      </header>

      <div className="px-4 pt-5 sm:px-6 lg:px-8">
        <h1 className="font-heading text-xl font-bold text-slate-50">{titulo}</h1>
        <p className="text-xs text-slate-500">{subtitulo}</p>
      </div>

      <main className="p-4 pt-4 sm:p-6 lg:p-8">
        {/* Uma exceção numa tela não derruba o menu nem o restante do app. */}
        <ErrorBoundary key={location.pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>

      <CommandPalette isAdmin={isAdmin} pode={pode} />
      <AccountDialog open={conta} onOpenChange={setConta} />
    </div>
  );
}
