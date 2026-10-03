import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowRight, Building2, GripVertical, Loader2, MapPin, MoveRight, Phone, Plus, Trash2,
  TrendingUp, UserPlus,
} from "lucide-react";
import { api, apiError, brl, getList } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
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
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

// O funil é uma faixa única com rolagem horizontal. Em grade, as seis etapas
// quebravam em duas linhas de três e a ordem deixava de ser legível da esquerda
// para a direita.
const COLUNAS = [
  { stage: "novo", label: "Novo", cor: "border-t-slate-500" },
  { stage: "contatado", label: "Contatado", cor: "border-t-blue-500" },
  { stage: "negociacao", label: "Em negociação", cor: "border-t-amber-500" },
  { stage: "proposta", label: "Proposta", cor: "border-t-violet-500" },
  { stage: "ganho", label: "Ganho", cor: "border-t-emerald-500" },
  { stage: "perdido", label: "Perdido", cor: "border-t-red-500" },
];

const ORIGENS = [
  ["indicacao", "Indicação"],
  ["instagram", "Instagram"],
  ["prospeccao", "Prospecção ativa"],
  ["site", "Site"],
  ["whatsapp", "WhatsApp"],
  ["evento", "Evento"],
  ["outro", "Outro"],
];

const VAZIO = {
  name: "", contact_name: "", phone: "", email: "", city: "", category: "",
  source: "prospeccao", stage: "novo", estimated_value: 0, notes: "",
};

export default function Pipeline() {
  const qc = useQueryClient();
  const confirmar = useConfirm();
  const { isAdmin } = useAuth();
  const [form, setForm] = useState(VAZIO);
  const [editId, setEditId] = useState(null);
  const [aberto, setAberto] = useState(false);
  const [arrastando, setArrastando] = useState(null);
  const [alvo, setAlvo] = useState(null);
  const [perda, setPerda] = useState(null); // { lead, motivo }

  const { data: leads, isLoading } = useQuery({
    queryKey: ["leads"],
    queryFn: () => getList("/leads", { page_size: 200 }),
  });
  const { data: funil } = useQuery({
    queryKey: ["funil"],
    queryFn: async () => (await api.get("/leads/funnel")).data,
  });

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["leads"] });
    qc.invalidateQueries({ queryKey: ["funil"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const salvar = useMutation({
    mutationFn: (p) => (editId ? api.put(`/leads/${editId}`, p) : api.post("/leads", p)),
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
    onSuccess: () => {
      invalidar();
      setPerda(null);
    },
    onError: (e) => toast.error(apiError(e)),
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

  // Arrastar e o menu "mover para" passam pelo mesmo caminho. O menu existe
  // porque arrastar não funciona por teclado nem em leitor de tela — sem ele,
  // mover uma negociação era impossível sem mouse.
  const moverPara = (lead, stage) => {
    if (!lead || lead.stage === stage) return;
    if (stage === "perdido") {
      setPerda({ lead, motivo: "" });
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
    setForm({ ...VAZIO, ...lead });
    setEditId(lead.id);
    setAberto(true);
  };

  const itens = leads?.items || [];

  return (
    <div className="space-y-6 animate-fade-up" data-testid="pipeline-page">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-6">
        <MetricCard
          icon={Building2}
          label="Leads em aberto"
          value={funil?.em_aberto ?? "—"}
          hint="Fora de ganho/perdido"
          testid="kpi-leads-abertos"
        />
        <MetricCard
          icon={TrendingUp}
          label="Receita potencial"
          value={brl(funil?.valor_em_aberto)}
          hint="Soma do valor estimado"
          tone="text-primary"
        />
        <MetricCard
          icon={ArrowRight}
          label="Taxa de conversão"
          value={`${funil?.taxa_conversao ?? 0}%`}
          hint={`${funil?.ganhos ?? 0} ganhos • ${funil?.perdidos ?? 0} perdidos`}
          tone="text-emerald-400"
        />
        <MetricCard
          icon={UserPlus}
          label="Ganhos"
          value={funil?.ganhos ?? "—"}
          hint="Prontos para virar cliente"
          tone="text-emerald-400"
        />
      </div>

      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">
          Arraste os cartões entre as colunas — ou use o botão de mover no cartão.
        </p>
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

      {isLoading ? (
        <Loading />
      ) : itens.length === 0 ? (
        <Panel>
          <EmptyState
            icon={Building2}
            titulo="Nenhum lead no funil"
            descricao="Cadastre os restaurantes que estão em prospecção para acompanhar cada negociação até o fechamento."
          />
        </Panel>
      ) : (
        <div className="flex gap-4 overflow-x-auto pb-2 px-1 -mx-1 snap-x">
          {COLUNAS.map((col) => {
            const daColuna = itens.filter((l) => l.stage === col.stage);
            const total = daColuna.reduce((s, l) => s + (l.estimated_value || 0), 0);
            return (
              <div
                key={col.stage}
                onDragOver={(e) => {
                  e.preventDefault();
                  setAlvo(col.stage);
                }}
                onDragLeave={() => setAlvo((a) => (a === col.stage ? null : a))}
                onDrop={() => soltar(col.stage)}
                data-testid={`pipeline-col-${col.stage}`}
                className={`rounded-xl border border-t-2 bg-slate-900/60 p-3 min-h-[260px] w-[85vw] sm:w-[300px] shrink-0 snap-start transition-colors ${col.cor} ${
                  alvo === col.stage ? "border-primary bg-primary/5" : "border-slate-800"
                }`}
              >
                <div className="flex items-baseline justify-between mb-3 px-1">
                  <p className="text-sm font-semibold text-slate-200">{col.label}</p>
                  <span className="text-xs text-slate-500">{daColuna.length}</span>
                </div>
                {total > 0 && (
                  <p className="px-1 mb-3 text-xs font-semibold text-primary">{brl(total)}</p>
                )}

                <div className="space-y-2">
                  {daColuna.map((lead) => (
                    <div
                      key={lead.id}
                      draggable
                      onDragStart={() => setArrastando(lead)}
                      onDragEnd={() => setArrastando(null)}
                      data-testid={`lead-card-${lead.id}`}
                      className="group rounded-lg border border-slate-800 bg-slate-900 p-3 cursor-grab active:cursor-grabbing hover:border-slate-700"
                    >
                      <div className="flex items-start gap-1.5">
                        <GripVertical
                          className="w-3.5 h-3.5 text-slate-700 mt-0.5 shrink-0"
                          aria-hidden="true"
                        />
                        <button
                          onClick={() => abrirEdicao(lead)}
                          className="flex-1 min-w-0 text-left"
                          data-testid={`open-lead-${lead.id}`}
                        >
                          <p className="text-sm font-semibold text-slate-100 truncate">
                            {lead.name}
                          </p>
                          {lead.contact_name && (
                            <p className="text-xs text-slate-500 truncate">{lead.contact_name}</p>
                          )}
                        </button>
                      </div>

                      <div className="mt-2 space-y-1 pl-5">
                        {lead.city && (
                          <p className="flex items-center gap-1.5 text-[11px] text-slate-500">
                            <MapPin className="w-3 h-3" aria-hidden="true" /> {lead.city}
                          </p>
                        )}
                        {lead.phone && (
                          <p className="flex items-center gap-1.5 text-[11px] text-slate-500">
                            <Phone className="w-3 h-3" aria-hidden="true" /> {lead.phone}
                          </p>
                        )}
                        {lead.estimated_value > 0 && (
                          <p className="text-xs font-semibold text-primary">
                            {brl(lead.estimated_value)}
                          </p>
                        )}
                        {lead.stage === "perdido" && lead.lost_reason && (
                          <p className="text-[11px] text-red-400/80 italic">{lead.lost_reason}</p>
                        )}
                      </div>

                      <div className="flex items-center justify-end gap-1 mt-2 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              size="icon"
                              variant="ghost"
                              aria-label={`Mover ${lead.name} para outra etapa`}
                              title="Mover para outra etapa"
                              data-testid={`move-lead-${lead.id}`}
                              className="h-7 w-7 text-slate-400 hover:text-primary"
                            >
                              <MoveRight className="w-3.5 h-3.5" aria-hidden="true" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent
                            align="end"
                            className="bg-slate-900 border-slate-800 text-slate-200"
                          >
                            <DropdownMenuLabel className="text-xs text-slate-500">
                              Mover para
                            </DropdownMenuLabel>
                            {COLUNAS.filter((x) => x.stage !== lead.stage).map((x) => (
                              <DropdownMenuItem
                                key={x.stage}
                                onSelect={() => moverPara(lead, x.stage)}
                                data-testid={`move-to-${x.stage}`}
                                className="text-sm focus:bg-slate-800 focus:text-slate-50"
                              >
                                {x.label}
                              </DropdownMenuItem>
                            ))}
                          </DropdownMenuContent>
                        </DropdownMenu>
                        {lead.stage === "ganho" && !lead.converted_restaurant_id && (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => converter.mutate(lead.id)}
                            disabled={converter.isPending}
                            data-testid={`convert-lead-${lead.id}`}
                            className="h-7 text-[11px] text-emerald-400 hover:text-emerald-300 gap-1"
                          >
                            <UserPlus className="w-3 h-3" /> Virar cliente
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
                            data-testid={`delete-lead-${lead.id}`}
                            onClick={async () => {
                              const ok = await confirmar({
                                titulo: `Excluir ${lead.name}?`,
                                descricao:
                                  "O lead e as atividades ligadas a ele saem do funil. Esta ação não pode ser desfeita.",
                                confirmar: "Excluir",
                              });
                              if (ok) excluir.mutate(lead.id);
                            }}
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
      )}

      {/* Cadastro / edição */}
      <Dialog open={aberto} onOpenChange={setAberto}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-heading">
              {editId ? "Editar Lead" : "Novo Lead"}
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4 py-2">
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="lead-nome">Estabelecimento *</Label>
              <Input
                id="lead-nome"
                data-testid="lead-name-input"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lead-contato">Contato</Label>
              <Input
                id="lead-contato"
                value={form.contact_name}
                onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lead-tel">Telefone</Label>
              <Input
                id="lead-tel"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lead-cidade">Cidade</Label>
              <Input
                id="lead-cidade"
                value={form.city}
                onChange={(e) => setForm({ ...form, city: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lead-cat">Categoria</Label>
              <Input
                id="lead-cat"
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Origem</Label>
              <Select
                value={form.source}
                onValueChange={(v) => setForm({ ...form, source: v })}
              >
                <SelectTrigger className="bg-slate-800 border-slate-700" data-testid="lead-source">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ORIGENS.map(([v, l]) => (
                    <SelectItem key={v} value={v}>
                      {l}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lead-valor">Valor estimado/mês (R$)</Label>
              <Input
                id="lead-valor"
                type="number"
                min="0"
                step="0.01"
                value={form.estimated_value}
                onChange={(e) =>
                  setForm({ ...form, estimated_value: parseFloat(e.target.value) || 0 })
                }
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="lead-obs">Observações</Label>
              <Textarea
                id="lead-obs"
                rows={3}
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
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
              disabled={!form.name.trim() || salvar.isPending}
              data-testid="save-lead-button"
              className="bg-primary hover:bg-orange-600 text-white"
            >
              {salvar.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "Salvar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Motivo da perda — o backend exige, e é o dado mais útil do funil */}
      <Dialog open={!!perda} onOpenChange={(v) => !v && setPerda(null)}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-heading">Por que perdemos?</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label htmlFor="motivo">Motivo da perda — {perda?.lead?.name}</Label>
            <Textarea
              id="motivo"
              rows={3}
              autoFocus
              data-testid="lost-reason-input"
              value={perda?.motivo || ""}
              onChange={(e) => setPerda((p) => ({ ...p, motivo: e.target.value }))}
              placeholder="Ex.: achou a comissão alta, fechou com concorrente, fechou as portas…"
              className="bg-slate-800 border-slate-700"
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setPerda(null)} className="text-slate-400">
              Cancelar
            </Button>
            <Button
              onClick={() =>
                mover.mutate({
                  id: perda.lead.id,
                  stage: "perdido",
                  lost_reason: perda.motivo,
                })
              }
              disabled={!perda?.motivo?.trim() || mover.isPending}
              data-testid="confirm-lost-button"
              className="bg-red-600 hover:bg-red-500 text-white"
            >
              Marcar como perdido
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
