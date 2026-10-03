import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertCircle, CalendarClock, CheckCircle2, Circle, ClipboardList, Loader2, Mail,
  MessageSquare, Phone, Plus, StickyNote, Trash2, Users, MapPin,
} from "lucide-react";
import { api, apiError, dataHora, getList } from "@/lib/api";
import { useConfirm } from "@/components/ConfirmDialog";
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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const ABAS = [
  { key: "atrasadas", label: "Atrasadas" },
  { key: "hoje", label: "Hoje" },
  { key: "proximas", label: "Próximas" },
  { key: "concluidas", label: "Concluídas" },
  { key: "todas", label: "Todas" },
];

const TIPOS = [
  ["ligacao", "Ligação", Phone],
  ["whatsapp", "WhatsApp", MessageSquare],
  ["email", "E-mail", Mail],
  ["reuniao", "Reunião", Users],
  ["visita", "Visita", MapPin],
  ["nota", "Nota", StickyNote],
  ["tarefa", "Tarefa", ClipboardList],
];
const ICONE = Object.fromEntries(TIPOS.map(([k, , i]) => [k, i]));
const ROTULO = Object.fromEntries(TIPOS.map(([k, l]) => [k, l]));

const paraInputLocal = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const off = d.getTimezoneOffset() * 60000;
  return new Date(d.getTime() - off).toISOString().slice(0, 16);
};

const emUmaHora = () => paraInputLocal(new Date(Date.now() + 3600_000).toISOString());

const VAZIO = () => ({
  kind: "tarefa",
  type: "ligacao",
  title: "",
  description: "",
  due_at: emUmaHora(),
  related_type: "lead",
  related_id: "",
  related_name: "",
  done: false,
});

export default function Activities() {
  const qc = useQueryClient();
  const confirmar = useConfirm();
  const [aba, setAba] = useState("hoje");
  const [aberto, setAberto] = useState(false);
  const [form, setForm] = useState(VAZIO);
  const [editId, setEditId] = useState(null);

  const { data, isLoading } = useQuery({
    queryKey: ["activities", aba],
    queryFn: () => getList("/activities", { scope: aba, page_size: 100 }),
  });
  const { data: resumo } = useQuery({
    queryKey: ["activities-summary"],
    queryFn: async () => (await api.get("/activities/summary")).data,
    refetchInterval: 60_000,
  });
  const { data: leads } = useQuery({
    queryKey: ["leads"],
    queryFn: () => getList("/leads", { page_size: 200 }),
  });
  const { data: restaurantes } = useQuery({
    queryKey: ["restaurants", "todos"],
    queryFn: () => getList("/restaurants", { page_size: 200 }),
  });

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["activities"] });
    qc.invalidateQueries({ queryKey: ["activities-summary"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const salvar = useMutation({
    mutationFn: (p) => {
      const payload = {
        ...p,
        due_at: p.due_at ? new Date(p.due_at).toISOString() : null,
        related_id: p.related_id || "",
      };
      return editId ? api.put(`/activities/${editId}`, payload) : api.post("/activities", payload);
    },
    onSuccess: () => {
      invalidar();
      toast.success(editId ? "Atividade atualizada" : "Atividade criada");
      setAberto(false);
      setForm(VAZIO());
      setEditId(null);
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const alternar = useMutation({
    mutationFn: (id) => api.patch(`/activities/${id}/toggle`),
    onSuccess: () => invalidar(),
    onError: (e) => toast.error(apiError(e)),
  });

  const excluir = useMutation({
    mutationFn: (id) => api.delete(`/activities/${id}`),
    onSuccess: () => {
      invalidar();
      toast.success("Atividade removida");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const abrirNova = () => {
    setForm(VAZIO());
    setEditId(null);
    setAberto(true);
  };

  const abrirEdicao = (a) => {
    setForm({ ...VAZIO(), ...a, due_at: paraInputLocal(a.due_at) });
    setEditId(a.id);
    setAberto(true);
  };

  const relacionados = form.related_type === "lead" ? leads?.items : restaurantes?.items;
  const itens = data?.items || [];
  const atrasada = (a) => !a.done && a.due_at && new Date(a.due_at) < new Date();

  return (
    <div className="space-y-6 animate-fade-up" data-testid="activities-page">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
        <MetricCard
          icon={AlertCircle}
          label="Atrasadas"
          value={resumo?.atrasadas ?? "—"}
          tone={resumo?.atrasadas ? "text-red-400" : "text-slate-50"}
          testid="kpi-atividades-atrasadas"
        />
        <MetricCard
          icon={CalendarClock}
          label="Para hoje"
          value={resumo?.hoje ?? "—"}
          tone="text-amber-400"
        />
        <MetricCard icon={CalendarClock} label="Próximos 7 dias" value={resumo?.semana ?? "—"} />
        <MetricCard icon={ClipboardList} label="Abertas no total" value={resumo?.abertas ?? "—"} />
      </div>

      <div className="flex flex-col sm:flex-row gap-3 sm:items-center justify-between">
        <div className="overflow-x-auto">
          <Tabs value={aba} onValueChange={setAba}>
            <TabsList className="bg-slate-900 border border-slate-800">
              {ABAS.map((t) => (
                <TabsTrigger
                  key={t.key}
                  value={t.key}
                  data-testid={`activity-tab-${t.key}`}
                  className="text-xs"
                >
                  {t.label}
                  {t.key === "atrasadas" && resumo?.atrasadas > 0 && (
                    <span className="ml-1.5 px-1.5 rounded-full bg-red-500/20 text-red-400 text-[10px]">
                      {resumo.atrasadas}
                    </span>
                  )}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
        <Button
          onClick={abrirNova}
          data-testid="btn-nova-atividade"
          className="bg-primary hover:bg-orange-600 text-white gap-2 shrink-0"
        >
          <Plus className="w-4 h-4" /> Nova Atividade
        </Button>
      </div>

      <Panel>
        {isLoading ? (
          <Loading />
        ) : itens.length === 0 ? (
          <EmptyState
            icon={CheckCircle2}
            titulo={aba === "atrasadas" ? "Nada atrasado" : "Nenhuma atividade aqui"}
            descricao="Registre ligações, visitas e follow-ups para não perder o timing de cada negociação."
            acao={
              <Button onClick={abrirNova} className="bg-primary hover:bg-orange-600 text-white gap-2">
                <Plus className="w-4 h-4" /> Nova Atividade
              </Button>
            }
          />
        ) : (
          <ul className="divide-y divide-slate-800">
            {itens.map((a) => {
              const Icon = ICONE[a.type] || ClipboardList;
              return (
                <li
                  key={a.id}
                  data-testid={`activity-row-${a.id}`}
                  className="flex items-start gap-3 px-4 py-3 hover:bg-slate-800/30"
                >
                  <button
                    onClick={() => alternar.mutate(a.id)}
                    aria-label={a.done ? "Reabrir atividade" : "Concluir atividade"}
                    data-testid={`toggle-activity-${a.id}`}
                    className="mt-0.5 shrink-0"
                  >
                    {a.done ? (
                      <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                    ) : (
                      <Circle className="w-5 h-5 text-slate-600 hover:text-primary transition-colors" />
                    )}
                  </button>

                  <button onClick={() => abrirEdicao(a)} className="flex-1 min-w-0 text-left">
                    <p
                      className={`text-sm font-medium truncate ${
                        a.done ? "text-slate-500 line-through" : "text-slate-100"
                      }`}
                    >
                      {a.title}
                    </p>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-xs text-slate-500">
                      <span className="flex items-center gap-1">
                        <Icon className="w-3 h-3" aria-hidden="true" /> {ROTULO[a.type] || a.type}
                      </span>
                      {a.related_name && (
                        <span className="truncate max-w-[200px]">↳ {a.related_name}</span>
                      )}
                      {a.due_at && (
                        <span className={atrasada(a) ? "text-red-400 font-semibold" : ""}>
                          {atrasada(a) ? "venceu " : "vence "}
                          {dataHora(a.due_at)}
                        </span>
                      )}
                      {a.owner_name && <span>• {a.owner_name}</span>}
                    </div>
                    {a.description && (
                      <p className="text-xs text-slate-600 mt-1 line-clamp-2">{a.description}</p>
                    )}
                  </button>

                  <IconButton
                    icon={Trash2}
                    label={`Excluir atividade ${a.title}`}
                    tone="hover:text-red-400"
                    data-testid={`delete-activity-${a.id}`}
                    onClick={async () => {
                      const ok = await confirmar({
                        titulo: "Excluir atividade?",
                        descricao: `"${a.title}" sai do histórico do cadastro relacionado.`,
                        confirmar: "Excluir",
                      });
                      if (ok) excluir.mutate(a.id);
                    }}
                  />
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      <Dialog open={aberto} onOpenChange={setAberto}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-heading">
              {editId ? "Editar Atividade" : "Nova Atividade"}
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4 py-2">
            <div className="space-y-1.5">
              <Label>Natureza</Label>
              <Select value={form.kind} onValueChange={(v) => setForm({ ...form, kind: v })}>
                <SelectTrigger className="bg-slate-800 border-slate-700" data-testid="activity-kind">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="tarefa">Tarefa a fazer</SelectItem>
                  <SelectItem value="interacao">Registrar o que já aconteceu</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Tipo</Label>
              <Select value={form.type} onValueChange={(v) => setForm({ ...form, type: v })}>
                <SelectTrigger className="bg-slate-800 border-slate-700" data-testid="activity-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIPOS.map(([v, l]) => (
                    <SelectItem key={v} value={v}>
                      {l}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="atv-titulo">Título *</Label>
              <Input
                id="atv-titulo"
                data-testid="activity-title-input"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="Ex.: Ligar para o Seu Antônio sobre a proposta"
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Relacionado a</Label>
              <Select
                value={form.related_type}
                onValueChange={(v) =>
                  setForm({ ...form, related_type: v, related_id: "", related_name: "" })
                }
              >
                <SelectTrigger className="bg-slate-800 border-slate-700">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="lead">Lead</SelectItem>
                  <SelectItem value="restaurante">Restaurante</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Cadastro</Label>
              <Select
                value={form.related_id}
                onValueChange={(v) => {
                  const alvo = relacionados?.find((x) => x.id === v);
                  setForm({ ...form, related_id: v, related_name: alvo?.name || "" });
                }}
              >
                <SelectTrigger
                  className="bg-slate-800 border-slate-700"
                  data-testid="activity-related"
                >
                  <SelectValue placeholder="Opcional" />
                </SelectTrigger>
                <SelectContent>
                  {(relacionados || []).map((x) => (
                    <SelectItem key={x.id} value={x.id}>
                      {x.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="atv-prazo">
                {form.kind === "interacao" ? "Quando aconteceu" : "Vencimento"}
              </Label>
              <Input
                id="atv-prazo"
                type="datetime-local"
                data-testid="activity-due-input"
                value={form.due_at}
                onChange={(e) => setForm({ ...form, due_at: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="atv-desc">Detalhes</Label>
              <Textarea
                id="atv-desc"
                rows={3}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAberto(false)} className="text-slate-400">
              Cancelar
            </Button>
            <Button
              onClick={() => salvar.mutate(form)}
              disabled={!form.title.trim() || salvar.isPending}
              data-testid="save-activity-button"
              className="bg-primary hover:bg-orange-600 text-white"
            >
              {salvar.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "Salvar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
