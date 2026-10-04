import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  BarChart3, Bike, FileText, Filter, LayoutDashboard, Package, Plug, Store, Users2,
} from "lucide-react";
import {
  CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { api } from "@/lib/api";

const ATALHOS = [
  { rota: "/", modulo: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { rota: "/funil", modulo: "funil", label: "Funil de Vendas", icon: Filter },
  { rota: "/atividades", modulo: "atividades", label: "Atividades", icon: FileText },
  { rota: "/restaurantes", modulo: "restaurantes", label: "Restaurantes", icon: Store },
  { rota: "/entregadores", modulo: "entregadores", label: "Entregadores", icon: Bike },
  { rota: "/pedidos", modulo: "pedidos", label: "Pedidos", icon: Package },
  { rota: "/contratos-pagamentos", modulo: "financeiro", label: "Contratos & Pagamentos", icon: FileText },
  { rota: "/relatorios", modulo: "relatorios", label: "Relatórios", icon: BarChart3 },
  { rota: "/integracoes", modulo: "integracoes", label: "Integrações API", icon: Plug },
  { rota: "/usuarios", label: "Usuários", icon: Users2, adminOnly: true },
];

/**
 * Busca global por Ctrl/⌘+K. Antes, achar um pedido específico exigia abrir a
 * página certa e filtrar na mão — não havia busca que cruzasse os cadastros.
 */
export function CommandPalette({ isAdmin, pode = () => true }) {
  const [aberto, setAberto] = useState(false);
  const [termo, setTermo] = useState("");
  const [resultados, setResultados] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e) => {
      if (e.key?.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setAberto((v) => !v);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (termo.trim().length < 2) {
      setResultados([]);
      return undefined;
    }
    // Espera o usuário parar de digitar para não disparar uma busca por tecla.
    const id = setTimeout(async () => {
      try {
        const { data } = await api.get("/search", { params: { q: termo } });
        setResultados(data.results || []);
      } catch {
        setResultados([]);
      }
    }, 250);
    return () => clearTimeout(id);
  }, [termo]);

  const ir = (rota) => {
    setAberto(false);
    setTermo("");
    navigate(rota);
  };

  return (
    <CommandDialog open={aberto} onOpenChange={setAberto}>
      <CommandInput
        placeholder="Buscar restaurante, entregador, pedido, lead…"
        value={termo}
        onValueChange={setTermo}
        data-testid="command-input"
      />
      <CommandList>
        <CommandEmpty>
          {termo.trim().length < 2 ? "Digite ao menos 2 letras." : "Nada encontrado."}
        </CommandEmpty>

        {resultados.length > 0 && (
          <>
            <CommandGroup heading="Resultados">
              {resultados.map((r) => (
                <CommandItem
                  key={`${r.tipo}-${r.id}`}
                  value={`${r.titulo} ${r.subtitulo} ${r.tipo}`}
                  onSelect={() => ir(r.rota)}
                  data-testid={`search-result-${r.tipo}`}
                >
                  <span className="text-[10px] uppercase tracking-wider text-primary w-20 shrink-0">
                    {r.tipo}
                  </span>
                  <span className="truncate">{r.titulo}</span>
                  {r.subtitulo && (
                    <span className="ml-auto text-xs text-slate-500 truncate">{r.subtitulo}</span>
                  )}
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandSeparator />
          </>
        )}

        <CommandGroup heading="Ir para">
          {ATALHOS.filter((a) => (a.adminOnly ? isAdmin : pode(a.modulo))).map((a) => {
            const Icon = a.icon;
            return (
              <CommandItem key={a.rota} value={a.label} onSelect={() => ir(a.rota)}>
                <Icon className="w-4 h-4 mr-2 text-slate-500" />
                {a.label}
              </CommandItem>
            );
          })}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
