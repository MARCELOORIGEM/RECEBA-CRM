import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Building2, CalendarDays, CheckCircle2, ChevronLeft, ChevronRight, Columns3, GripVertical,
  Loader2, MapPin, MoveRight, Plus, Search, Sheet, Trash2, UserPlus, Users, XCircle,
} from "lucide-react";
import { api, apiError, brl, getList } from "@/lib/api";
import { GANHO, INICIAL, ORIGENS, POR_CHAVE, STATUS, dataBr } from "@/lib/funil";
import { useAuth } from "@/context/AuthContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { BaixarPlanilha, ImportarLeads } from "@/components/ImportarLeads";
import { EmptyState, IconButton, Loading, MetricCard, Panel } from "@/components/Ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const VAZIO = {
  codigo_externo: "", name: "", endereco: "", bairro: "", bd_id: "", bd_nome: "", lider: "",
  data_visita: "", stage: INICIAL, notes: "",
  contact_name: "", phone: "", email: "", city: "", category: "",
  source: "prospeccao", estimated_value: 0,
};

const POR_PAGINA = 100;
const TODOS = "__todos__";

// A visão escolhida fica no navegador: quem trabalha na planilha não quer
// reabrir no quadro toda vez.
function lerVisao() {
  try {
    return localStorage.getItem("funil.visao") || "planilha";
  } catch {
    return "planilha";
  }
}

function BadgeStatus({ chave, className = "" }) {
  const st = POR_CHAVE[chave];
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${
        st?.badge || "border-slate-600 text-slate-300"
      } ${className}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {st?.rotulo || chave}
    </span>
  );
}

/** Seletor de status que mostra o próprio status como etiqueta colorida. */
function SeletorStatus({ lead, onMudar, testid }) {
  return (
    <Select value={lead.stage} onValueChange={(v) => onMudar(lead, v)}>
      <SelectTrigger
        className="h-auto w-auto border-0 bg-transparent p-0 shadow-none focus:ring-1 focus:ring-primary [&>svg]:ml-1 [&>svg]:h-3 [&>svg]:w-3"
        aria-label={`Status de ${lead.name}`}
        data-testid={testid}
      >
        <BadgeStatus chave={lead.stage} />
      </SelectTrigger>
      <SelectContent className="max-h-80">
        {STATUS.map((s) => (
          <SelectItem key={s.chave} value={s.chave}>
            {s.rotulo}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function Filtro({ rotulo, valor, opcoes, onChange, testid, icone: Icone }) {
  return (
    <Select value={valor || TODOS} onValueChange={(v) => onChange(v === TODOS ? "" : v)}>
      <SelectTrigger className="h-9 w-[160px] border-slate-700 bg-slate-900" data-testid={testid}>
        {/* div, não span: o gatilho aplica line-clamp aos spans filhos, e o
            ícone ia parar numa linha e o texto em outra. */}
        <div className="flex min-w-0 items-center gap-2">
          <Icone className="h-3.5 w-3.5 shrink-0 text-slate-500" aria-hidden="true" />
          <span className="truncate">
            <SelectValue placeholder={rotulo} />
          </span>
        </div>
      </SelectTrigger>
      <SelectContent className="max-h-80">
        <SelectItem value={TODOS}>{rotulo}: todos</SelectItem>
        {opcoes.map((o) => (
          <SelectItem key={o.valor} value={o.valor}>
            {o.rotulo}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function Campo({ id, rotulo, children, className = "" }) {
  return (
    <div className={`space-y-1.5 ${className}`}>
      <Label htmlFor={id} className="text-xs text-slate-400">
        {rotulo}
      </Label>
      {children}
    </div>
  );
}

export default function Pipeline() {
  const qc = useQueryClient();
  const confirmar = useConfirm();
  const { isAdmin } = useAuth();
  const [visao, setVisao] = useState(lerVisao);
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [lider, setLider] = useState("");
  const [bd, setBd] = useState("");
  const [status, setStatus] = useState("");
  const [pagina, setPagina] = useState(1);
  const [form, setForm] = useState(VAZIO);
  const [editId, setEditId] = useState(null);
  const [aberto, setAberto] = useState(false);
  const [arrastando, setArrastando] = useState(null);
  const [alvo, setAlvo] = useState(null);
  const [motivo, setMotivo] = useState(null); // { lead, stage, texto }
  const [importando, setImportando] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem("funil.visao", visao);
    } catch {
      /* navegador sem armazenamento: só não lembra a escolha */
    }
  }, [visao]);

  // A busca vai ao servidor só depois de uma pausa na digitação.
  useEffect(() => {
    const t = setTimeout(() => setBuscaAplicada(busca.trim()), 350);
    return () => clearTimeout(t);
  }, [busca]);
  useEffect(() => setPagina(1), [buscaAplicada, lider, bd, status, visao]);

  // No quadro o filtro de status não faz sentido: cada status é uma coluna.
  const statusFiltro = visao === "planilha" ? status : "";
  const { data: leads, isLoading, isFetching } = useQuery({
    queryKey: ["leads", { buscaAplicada, lider, bd, statusFiltro, pagina, visao }],
    queryFn: () =>
      getList("/leads", {
        search: buscaAplicada,
        lider,
        bd,
        stage: statusFiltro || "todos",
        page: visao === "planilha" ? pagina : 1,
        page_size: visao === "planilha" ? POR_PAGINA : 200,
      }),
    placeholderData: keepPreviousData,
  });
  const { data: funil } = useQuery({
    queryKey: ["funil"],
    queryFn: async () => (await api.get("/leads/funnel")).data,
  });
  const { data: filtros } = useQuery({
    queryKey: ["funil-filtros"],
    queryFn: async () => (await api.get("/leads/filtros")).data,
  });

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["leads"] });
    qc.invalidateQueries({ queryKey: ["funil"] });
    qc.invalidateQueries({ queryKey: ["funil-filtros"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const salvar = useMutation({
    mutationFn: (p) => {
      const corpo = { ...p, data_visita: p.data_visita || null };
      return editId ? api.put(`/leads/${editId}`, corpo) : api.post("/leads", corpo);
    },
    onSuccess: () => {
      invalidar();
      toast.success(editId ? "Lead atualizado" : "Lead criado");
      setAberto(false);
      setForm(VAZIO);
      setEditId(null);
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const mover = useMutation({
    mutationFn: ({ id, stage, lost_reason = "" }) =>
      api.patch(`/leads/${id}/stage`, { stage, lost_reason }),
    // O status muda na tela na hora do clique, sem esperar o servidor — quem
    // atualiza vinte linhas seguidas não pode esperar cada ida e volta. Se o
    // servidor recusar, a linha volta ao que era.
    onMutate: async ({ id, stage, lost_reason = "" }) => {
      await qc.cancelQueries({ queryKey: ["leads"] });
      const antes = qc.getQueriesData({ queryKey: ["leads"] });
      qc.setQueriesData({ queryKey: ["leads"] }, (velho) =>
        velho?.items
          ? {
              ...velho,
              items: velho.items.map((l) => (l.id === id ? { ...l, stage, lost_reason } : l)),
            }
          : velho,
      );
      setMotivo(null);
      return { antes };
    },
    onError: (e, _v, ctx) => {
      ctx?.antes?.forEach(([chave, dados]) => qc.setQueryData(chave, dados));
      toast.error(apiError(e));
    },
    onSuccess: (_r, v) => toast.success(`Status: ${POR_CHAVE[v.stage]?.rotulo}`),
    onSettled: invalidar,
  });

  const converter = useMutation({
    mutationFn: (id) => api.post(`/leads/${id}/convert`),
    onSuccess: ({ data }) => {
      invalidar();
      qc.invalidateQueries({ queryKey: ["restaurants"] });
      toast.success(`${data.restaurant.name} virou cliente e está em análise.`);
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const excluir = useMutation({
    mutationFn: (id) => api.delete(`/leads/${id}`),
    onSuccess: () => {
      invalidar();
      toast.success("Lead removido");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  // Arrastar, o menu "mover para" e o seletor da planilha passam pelo mesmo
  // caminho. Status que pede motivo abre a caixa antes de gravar.
  const moverPara = (lead, stage) => {
    if (!lead || lead.stage === stage) return;
    if (POR_CHAVE[stage]?.pedeMotivo) {
      setMotivo({ lead, stage, texto: "" });
      return;
    }
    mover.mutate({ id: lead.id, stage });
  };

  const soltar = (stage) => {
    setAlvo(null);
    const lead = arrastando;
    setArrastando(null);
    moverPara(lead, stage);
  };

  const abrirEdicao = (lead) => {
    setForm({ ...VAZIO, ...lead, data_visita: lead.data_visita || "" });
    setEditId(lead.id);
    setAberto(true);
  };

  const pedirExclusao = async (lead) => {
    const ok = await confirmar({
      titulo: `Excluir ${lead.name}?`,
      descricao:
        "O lead e as atividades ligadas a ele saem do funil. Esta ação não pode ser desfeita.",
      confirmar: "Excluir",
    });
    if (ok) excluir.mutate(lead.id);
  };

  const itens = leads?.items || [];
  const total = leads?.total || 0;
  const filtrando = !!(buscaAplicada || lider || bd || statusFiltro);
  const qtdStatus = useMemo(
    () => Object.fromEntries((funil?.stages || []).map((s) => [s.stage, s.qtd])),
    [funil],
  );

  const opcoes = (lista = []) => lista.map((v) => ({ valor: v, rotulo: v }));

  return (
    <div className="space-y-6 animate-fade-up" data-testid="pipeline-page">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-6">
        <MetricCard
          icon={Building2}
          label="Em aberto"
          value={funil?.em_aberto ?? "—"}
          hint="Ainda em trabalho de campo"
          testid="kpi-leads-abertos"
        />
        <MetricCard
          icon={MapPin}
          label="A visitar"
          value={qtdStatus.a_visitar ?? "—"}
          hint="Sem visita registrada"
          tone="text-primary"
        />
        <MetricCard
          icon={CheckCircle2}
          label="Ativados"
          value={funil?.ganhos ?? "—"}
          hint={`Taxa de ativação ${funil?.taxa_conversao ?? 0}%`}
          tone="text-emerald-400"
        />
        <MetricCard
          icon={XCircle}
          label="Descartados"
          value={funil?.perdidos ?? "—"}
          hint="Sem interesse, já parceiro, fora da área"
          tone="text-red-400"
        />
      </div>

      {/* Barra: visão, busca, filtros e ações */}
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-lg border border-slate-700 bg-slate-900 p-0.5" role="tablist">
            {[
              ["planilha", "Planilha", Sheet],
              ["quadro", "Quadro", Columns3],
            ].map(([v, rot, Icone]) => (
              <button
                key={v}
                role="tab"
                aria-selected={visao === v}
                onClick={() => setVisao(v)}
                data-testid={`visao-${v}`}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors ${
                  visao === v ? "bg-primary/15 text-primary" : "text-slate-400 hover:text-slate-100"
                }`}
              >
                <Icone className="h-4 w-4" aria-hidden="true" /> {rot}
              </button>
            ))}
          </div>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <Input
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Lead ID, nome, bairro, endereço…"
              data-testid="funil-busca"
              className="h-9 w-[240px] border-slate-700 bg-slate-900 pl-9"
            />
          </div>
          <Filtro rotulo="Líder" valor={lider} onChange={setLider} icone={Users}
            opcoes={opcoes(filtros?.lideres)} testid="filtro-lider" />
          <Filtro rotulo="BD" valor={bd} onChange={setBd} icone={UserPlus}
            opcoes={opcoes(filtros?.bds)} testid="filtro-bd" />
          {visao === "planilha" && (
            <Filtro rotulo="Status" valor={status} onChange={setStatus} icone={CheckCircle2}
              opcoes={STATUS.map((s) => ({ valor: s.chave, rotulo: s.rotulo }))}
              testid="filtro-status" />
          )}
          {filtrando && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setBusca("");
                setLider("");
                setBd("");
                setStatus("");
              }}
              className="text-xs text-slate-400"
            >
              Limpar filtros
            </Button>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <BaixarPlanilha />
          <Button
            variant="outline"
            onClick={() => setImportando(true)}
            data-testid="btn-importar-planilha"
            className="border-slate-700 gap-2"
          >
            <Sheet className="w-4 h-4" /> Importar planilha
          </Button>
          <Button
            onClick={() => {
              setForm(VAZIO);
              setEditId(null);
              setAberto(true);
            }}
            data-testid="btn-novo-lead"
            className="bg-primary hover:bg-orange-600 text-white gap-2"
          >
            <Plus className="w-4 h-4" /> Novo Lead
          </Button>
        </div>
      </div>

      <ImportarLeads
        aberto={importando}
        onFechar={() => setImportando(false)}
        onImportado={invalidar}
      />

      {isLoading ? (
        <Loading />
      ) : itens.length === 0 ? (
        <Panel>
          <EmptyState
            icon={Building2}
            titulo={filtrando ? "Nenhum lead com esses filtros" : "Nenhum lead no funil"}
            descricao={
              filtrando
                ? "Mude ou limpe os filtros para ver mais leads."
                : "Importe a planilha da operação ou cadastre os restaurantes da carteira para acompanhar cada visita."
            }
          />
        </Panel>
      ) : visao === "planilha" ? (
        /* ------------------------------------------------------ planilha */
        <Panel className="overflow-hidden">
          <div className="overflow-x-auto" data-testid="funil-planilha">
            <table className="w-full min-w-[1200px] text-left text-sm">
              <thead>
                <tr className="bg-[#1F4E4C] text-[11px] uppercase tracking-wider text-white">
                  {["Lead ID", "Nome lead", "Endereço", "Bairro", "BD ID", "Nome BD", "Líder",
                    "Data visita", "Status", "Obs", ""].map((h, i) => (
                    <th key={h || i} className="whitespace-nowrap px-3 py-2.5 font-semibold">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className={isFetching ? "opacity-60" : ""}>
                {itens.map((lead) => (
                  <tr
                    key={lead.id}
                    className="border-t border-slate-800 hover:bg-slate-800/40"
                    data-testid={`lead-linha-${lead.id}`}
                  >
                    <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-slate-400">
                      {lead.codigo_externo || "—"}
                    </td>
                    <td className="px-3 py-2">
                      <button
                        onClick={() => abrirEdicao(lead)}
                        className="text-left font-medium text-slate-100 hover:text-primary"
                        data-testid={`open-lead-${lead.id}`}
                      >
                        {lead.name}
                      </button>
                    </td>
                    <td className="max-w-[220px] truncate px-3 py-2 text-slate-300" title={lead.endereco}>
                      {lead.endereco || "—"}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-slate-300">{lead.bairro || "—"}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-slate-400">{lead.bd_id || "—"}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-slate-300">{lead.bd_nome || "—"}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-slate-300">{lead.lider || "—"}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-slate-300">
                      {dataBr(lead.data_visita) || "—"}
                    </td>
                    <td className="px-3 py-2">
                      <SeletorStatus lead={lead} onMudar={moverPara} testid={`status-${lead.id}`} />
                      {POR_CHAVE[lead.stage]?.grupo === "perdido" && lead.lost_reason && (
                        <p className="mt-1 max-w-[180px] truncate text-[11px] italic text-red-300/80" title={lead.lost_reason}>
                          {lead.lost_reason}
                        </p>
                      )}
                    </td>
                    <td className="max-w-[240px] truncate px-3 py-2 text-xs text-slate-400" title={lead.notes}>
                      {lead.notes || "—"}
                    </td>
                    <td className="whitespace-nowrap px-2 py-2 text-right">
                      {lead.stage === GANHO && !lead.converted_restaurant_id && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => converter.mutate(lead.id)}
                          disabled={converter.isPending}
                          className="h-7 gap-1 text-[11px] text-emerald-400 hover:text-emerald-300"
                        >
                          <UserPlus className="h-3 w-3" /> Virar cliente
                        </Button>
                      )}
                      {isAdmin && (
                        <IconButton
                          icon={Trash2}
                          label={`Excluir lead ${lead.name}`}
                          tone="hover:text-red-400"
                          data-testid={`delete-lead-${lead.id}`}
                          onClick={() => pedirExclusao(lead)}
                        />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between border-t border-slate-800 px-4 py-2.5 text-xs text-slate-500">
            <span>
              {total} lead(s){filtrando ? " com esses filtros" : ""}
            </span>
            {leads?.pages > 1 && (
              <div className="flex items-center gap-2">
                <IconButton
                  icon={ChevronLeft}
                  label="Página anterior"
                  disabled={pagina <= 1}
                  onClick={() => setPagina((p) => p - 1)}
                />
                <span>
                  Página {pagina} de {leads.pages}
                </span>
                <IconButton
                  icon={ChevronRight}
                  label="Próxima página"
                  disabled={pagina >= leads.pages}
                  onClick={() => setPagina((p) => p + 1)}
                />
              </div>
            )}
          </div>
        </Panel>
      ) : (
        /* -------------------------------------------------------- quadro */
        <div className="space-y-2">
          {total > itens.length && (
            <p className="text-xs text-amber-400">
              Mostrando {itens.length} de {total} leads. Filtre por líder ou BD para ver todos no quadro.
            </p>
          )}
          <div className="flex gap-3 overflow-x-auto pb-2 px-1 -mx-1 snap-x">
            {STATUS.map((col) => {
              const daColuna = itens.filter((l) => l.stage === col.chave);
              return (
                <div
                  key={col.chave}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setAlvo(col.chave);
                  }}
                  onDragLeave={() => setAlvo((a) => (a === col.chave ? null : a))}
                  onDrop={() => soltar(col.chave)}
                  data-testid={`pipeline-col-${col.chave}`}
                  className={`rounded-xl border border-t-2 bg-slate-900/60 p-2.5 min-h-[260px] w-[80vw] sm:w-[250px] shrink-0 snap-start transition-colors ${col.borda} ${
                    alvo === col.chave ? "border-primary bg-primary/5" : "border-slate-800"
                  }`}
                >
                  <div className="mb-2.5 flex items-baseline justify-between px-1">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-200">
                      {col.rotulo}
                    </p>
                    <span className="text-xs text-slate-500">{daColuna.length}</span>
                  </div>

                  <div className="space-y-2">
                    {daColuna.map((lead) => (
                      <div
                        key={lead.id}
                        draggable
                        onDragStart={() => setArrastando(lead)}
                        onDragEnd={() => setArrastando(null)}
                        data-testid={`lead-card-${lead.id}`}
                        className="group rounded-lg border border-slate-800 bg-slate-900 p-2.5 cursor-grab active:cursor-grabbing hover:border-slate-700"
                      >
                        <div className="flex items-start gap-1.5">
                          <GripVertical className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-700" aria-hidden="true" />
                          <button
                            onClick={() => abrirEdicao(lead)}
                            className="min-w-0 flex-1 text-left"
                            data-testid={`open-lead-card-${lead.id}`}
                          >
                            <p className="truncate text-sm font-semibold text-slate-100">{lead.name}</p>
                            {lead.codigo_externo && (
                              <p className="font-mono text-[10px] text-slate-500">ID {lead.codigo_externo}</p>
                            )}
                          </button>
                        </div>
                        <div className="mt-1.5 space-y-1 pl-5 text-[11px] text-slate-500">
                          {(lead.bairro || lead.endereco) && (
                            <p className="flex items-center gap-1.5 truncate" title={lead.endereco}>
                              <MapPin className="h-3 w-3 shrink-0" aria-hidden="true" />
                              {lead.bairro || lead.endereco}
                            </p>
                          )}
                          {(lead.bd_nome || lead.lider) && (
                            <p className="flex items-center gap-1.5 truncate">
                              <Users className="h-3 w-3 shrink-0" aria-hidden="true" />
                              {[lead.bd_nome, lead.lider].filter(Boolean).join(" • ")}
                            </p>
                          )}
                          {lead.data_visita && (
                            <p className="flex items-center gap-1.5">
                              <CalendarDays className="h-3 w-3 shrink-0" aria-hidden="true" />
                              {dataBr(lead.data_visita)}
                            </p>
                          )}
                          {lead.lost_reason && POR_CHAVE[lead.stage]?.grupo === "perdido" && (
                            <p className="italic text-red-300/80">{lead.lost_reason}</p>
                          )}
                        </div>
                        <div className="mt-1.5 flex items-center justify-end gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button
                                size="icon"
                                variant="ghost"
                                aria-label={`Mudar status de ${lead.name}`}
                                title="Mudar status"
                                data-testid={`move-lead-${lead.id}`}
                                className="h-7 w-7 text-slate-400 hover:text-primary"
                              >
                                <MoveRight className="h-3.5 w-3.5" aria-hidden="true" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="max-h-80 overflow-y-auto border-slate-800 bg-slate-900 text-slate-200">
                              <DropdownMenuLabel className="text-xs text-slate-500">Mudar para</DropdownMenuLabel>
                              {STATUS.filter((x) => x.chave !== lead.stage).map((x) => (
                                <DropdownMenuItem
                                  key={x.chave}
                                  onSelect={() => moverPara(lead, x.chave)}
                                  data-testid={`move-to-${x.chave}`}
                                  className="text-sm focus:bg-slate-800 focus:text-slate-50"
                                >
                                  {x.rotulo}
                                </DropdownMenuItem>
                              ))}
                            </DropdownMenuContent>
                          </DropdownMenu>
                          {lead.stage === GANHO && !lead.converted_restaurant_id && (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => converter.mutate(lead.id)}
                              disabled={converter.isPending}
                              data-testid={`convert-lead-${lead.id}`}
                              className="h-7 gap-1 text-[11px] text-emerald-400 hover:text-emerald-300"
                            >
                              <UserPlus className="h-3 w-3" /> Virar cliente
                            </Button>
                          )}
                          {lead.converted_restaurant_id && (
                            <span className="text-[10px] text-emerald-400/80">✓ já é cliente</span>
                          )}
                          {isAdmin && (
                            <IconButton
                              icon={Trash2}
                              label={`Excluir lead ${lead.name}`}
                              tone="hover:text-red-400"
                              onClick={() => pedirExclusao(lead)}
                            />
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ------------------------------------------- cadastro / edição */}
      <Dialog open={aberto} onOpenChange={setAberto}>
        <DialogContent className="max-h-[90vh] overflow-y-auto border-slate-800 bg-slate-900 text-slate-100 sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="font-heading">{editId ? "Editar Lead" : "Novo Lead"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-5 py-2">
            <section className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-wider text-primary">Visita</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Campo id="lead-codigo" rotulo="Lead ID">
                  <Input id="lead-codigo" value={form.codigo_externo} data-testid="lead-codigo-input"
                    onChange={(e) => setForm({ ...form, codigo_externo: e.target.value })}
                    className="border-slate-700 bg-slate-800 font-mono" />
                </Campo>
                <Campo id="lead-nome" rotulo="Nome lead *" className="col-span-2 sm:col-span-3">
                  <Input id="lead-nome" value={form.name} data-testid="lead-name-input"
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    className="border-slate-700 bg-slate-800" />
                </Campo>
                <Campo id="lead-end" rotulo="Endereço" className="col-span-2 sm:col-span-3">
                  <Input id="lead-end" value={form.endereco}
                    onChange={(e) => setForm({ ...form, endereco: e.target.value })}
                    className="border-slate-700 bg-slate-800" />
                </Campo>
                <Campo id="lead-bairro" rotulo="Bairro">
                  <Input id="lead-bairro" value={form.bairro}
                    onChange={(e) => setForm({ ...form, bairro: e.target.value })}
                    className="border-slate-700 bg-slate-800" />
                </Campo>
                <Campo id="lead-bdid" rotulo="BD ID">
                  <Input id="lead-bdid" value={form.bd_id}
                    onChange={(e) => setForm({ ...form, bd_id: e.target.value })}
                    className="border-slate-700 bg-slate-800" />
                </Campo>
                <Campo id="lead-bd" rotulo="Nome BD">
                  <Input id="lead-bd" value={form.bd_nome} list="lista-bds"
                    onChange={(e) => setForm({ ...form, bd_nome: e.target.value })}
                    className="border-slate-700 bg-slate-800" />
                </Campo>
                <Campo id="lead-lider" rotulo="Líder">
                  <Input id="lead-lider" value={form.lider} list="lista-lideres"
                    onChange={(e) => setForm({ ...form, lider: e.target.value })}
                    className="border-slate-700 bg-slate-800" />
                </Campo>
                <Campo id="lead-data" rotulo="Data visita">
                  <Input id="lead-data" type="date" value={form.data_visita || ""}
                    onChange={(e) => setForm({ ...form, data_visita: e.target.value })}
                    className="border-slate-700 bg-slate-800" />
                </Campo>
                {!editId && (
                  <Campo id="lead-status" rotulo="Status" className="col-span-2 sm:col-span-4">
                    <Select value={form.stage} onValueChange={(v) => setForm({ ...form, stage: v })}>
                      <SelectTrigger className="border-slate-700 bg-slate-800" data-testid="lead-status">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="max-h-80">
                        {STATUS.filter((s) => !s.pedeMotivo).map((s) => (
                          <SelectItem key={s.chave} value={s.chave}>{s.rotulo}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Campo>
                )}
                <Campo id="lead-obs" rotulo="Obs" className="col-span-2 sm:col-span-4">
                  <Textarea id="lead-obs" rows={2} value={form.notes}
                    onChange={(e) => setForm({ ...form, notes: e.target.value })}
                    className="border-slate-700 bg-slate-800" />
                </Campo>
              </div>
              {/* Sugestões dos líderes e BDs que já existem: evita "Tarcisio"
                  e "TARCÍSIO" virarem dois líderes no filtro. */}
              <datalist id="lista-lideres">
                {(filtros?.lideres || []).map((v) => <option key={v} value={v} />)}
              </datalist>
              <datalist id="lista-bds">
                {(filtros?.bds || []).map((v) => <option key={v} value={v} />)}
              </datalist>
            </section>

            <section className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Contato e comercial (opcional)
              </p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <Campo id="lead-contato" rotulo="Contato">
                  <Input id="lead-contato" value={form.contact_name}
                    onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
                    className="border-slate-700 bg-slate-800" />
                </Campo>
                <Campo id="lead-tel" rotulo="Telefone">
                  <Input id="lead-tel" value={form.phone}
                    onChange={(e) => setForm({ ...form, phone: e.target.value })}
                    className="border-slate-700 bg-slate-800" />
                </Campo>
                <Campo id="lead-email" rotulo="E-mail">
                  <Input id="lead-email" value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                    className="border-slate-700 bg-slate-800" />
                </Campo>
                <Campo id="lead-cidade" rotulo="Cidade">
                  <Input id="lead-cidade" value={form.city}
                    onChange={(e) => setForm({ ...form, city: e.target.value })}
                    className="border-slate-700 bg-slate-800" />
                </Campo>
                <Campo id="lead-cat" rotulo="Categoria">
                  <Input id="lead-cat" value={form.category}
                    onChange={(e) => setForm({ ...form, category: e.target.value })}
                    className="border-slate-700 bg-slate-800" />
                </Campo>
                <Campo id="lead-origem" rotulo="Origem">
                  <Select value={form.source} onValueChange={(v) => setForm({ ...form, source: v })}>
                    <SelectTrigger className="border-slate-700 bg-slate-800" data-testid="lead-source">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ORIGENS.map(([v, l]) => (
                        <SelectItem key={v} value={v}>{l}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Campo>
                <Campo id="lead-valor" rotulo="Valor estimado/mês (R$)">
                  <Input id="lead-valor" type="number" min="0" step="0.01" value={form.estimated_value}
                    onChange={(e) => setForm({ ...form, estimated_value: parseFloat(e.target.value) || 0 })}
                    className="border-slate-700 bg-slate-800" />
                </Campo>
              </div>
            </section>
            {editId && (
              <p className="text-xs text-slate-500">
                Status atual: <BadgeStatus chave={form.stage} className="ml-1" /> — mude pela
                planilha ou pelo quadro.
                {form.estimated_value > 0 && ` Valor estimado ${brl(form.estimated_value)}.`}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAberto(false)} className="text-slate-400">
              Cancelar
            </Button>
            <Button
              onClick={() => salvar.mutate(form)}
              disabled={!form.name.trim() || salvar.isPending}
              data-testid="save-lead-button"
              className="bg-primary hover:bg-orange-600 text-white"
            >
              {salvar.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Salvar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ----------------------- motivo, para status que pedem (Sem interesse) */}
      <Dialog open={!!motivo} onOpenChange={(v) => !v && setMotivo(null)}>
        <DialogContent className="border-slate-800 bg-slate-900 text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-heading">
              {POR_CHAVE[motivo?.stage]?.rotulo}: qual o motivo?
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label htmlFor="motivo">Motivo — {motivo?.lead?.name}</Label>
            <Textarea
              id="motivo"
              rows={3}
              autoFocus
              data-testid="lost-reason-input"
              value={motivo?.texto || ""}
              onChange={(e) => setMotivo((m) => ({ ...m, texto: e.target.value }))}
              placeholder="Ex.: achou a taxa alta, já usa outro app, vai fechar o negócio…"
              className="border-slate-700 bg-slate-800"
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setMotivo(null)} className="text-slate-400">
              Cancelar
            </Button>
            <Button
              onClick={() =>
                mover.mutate({ id: motivo.lead.id, stage: motivo.stage, lost_reason: motivo.texto })
              }
              disabled={!motivo?.texto?.trim() || mover.isPending}
              data-testid="confirm-lost-button"
              className="bg-red-600 text-white hover:bg-red-500"
            >
              Confirmar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
