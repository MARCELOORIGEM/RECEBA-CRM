import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Activity, Copy, KeyRound, Loader2, Lock, Plus, ShieldAlert, Trash2, Webhook,
} from "lucide-react";
import { api, apiError, dataHora } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { EmptyState, IconButton, Loading, Panel } from "@/components/Ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const PROVEDORES = {
  ifood: "iFood",
  rappi: "Rappi",
  delivery_much: "Delivery Much",
  pos: "Sistema POS",
};
const EVENTOS = [
  "pedido.criado",
  "pedido.aceito",
  "pedido.entregue",
  "pedido.cancelado",
  "sync.estoque",
];
const WEBHOOK_VAZIO = { provider: "ifood", url: "", events: ["pedido.criado"], active: true };

export default function Integrations() {
  const qc = useQueryClient();
  const confirmar = useConfirm();
  const { isAdmin } = useAuth();
  const [abertoChave, setAbertoChave] = useState(false);
  const [abertoWh, setAbertoWh] = useState(false);
  const [formChave, setFormChave] = useState({ name: "", environment: "sandbox" });
  const [formWh, setFormWh] = useState(WEBHOOK_VAZIO);
  const [chaveNova, setChaveNova] = useState(null);

  const { data: chaves, isLoading: carregandoChaves } = useQuery({
    queryKey: ["keys"],
    queryFn: async () => (await api.get("/integrations/keys")).data,
    enabled: isAdmin,
  });
  const { data: webhooks = [] } = useQuery({
    queryKey: ["webhooks"],
    queryFn: async () => (await api.get("/integrations/webhooks")).data,
  });
  const { data: logs = [] } = useQuery({
    queryKey: ["logs"],
    queryFn: async () => (await api.get("/integrations/logs")).data,
    refetchInterval: 30_000,
  });

  const criarChave = useMutation({
    mutationFn: (p) => api.post("/integrations/keys", p),
    onSuccess: ({ data }) => {
      qc.invalidateQueries({ queryKey: ["keys"] });
      setAbertoChave(false);
      setFormChave({ name: "", environment: "sandbox" });
      // O valor completo só existe nesta resposta: o servidor guarda o hash.
      setChaveNova(data);
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const revogarChave = useMutation({
    mutationFn: (id) => api.delete(`/integrations/keys/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["keys"] });
      toast.success("Chave revogada");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const criarWh = useMutation({
    mutationFn: (p) => api.post("/integrations/webhooks", p),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["webhooks"] });
      toast.success("Webhook criado");
      setAbertoWh(false);
      setFormWh(WEBHOOK_VAZIO);
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const alternarWh = useMutation({
    mutationFn: (wh) => api.put(`/integrations/webhooks/${wh.id}`, { ...wh, active: !wh.active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["webhooks"] }),
    onError: (e) => toast.error(apiError(e)),
  });

  const excluirWh = useMutation({
    mutationFn: (id) => api.delete(`/integrations/webhooks/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["webhooks"] });
      toast.success("Webhook removido");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const copiar = async (texto) => {
    try {
      await navigator.clipboard.writeText(texto);
      toast.success("Copiado para a área de transferência");
    } catch {
      toast.error("Não foi possível copiar automaticamente");
    }
  };

  return (
    <div className="space-y-6 animate-fade-up" data-testid="integrations-page">
      <Tabs defaultValue={isAdmin ? "keys" : "webhooks"}>
        <TabsList className="bg-slate-900 border border-slate-800">
          <TabsTrigger value="keys" data-testid="tab-keys">
            Chaves de API
          </TabsTrigger>
          <TabsTrigger value="webhooks" data-testid="tab-webhooks">
            Webhooks
          </TabsTrigger>
          <TabsTrigger value="logs" data-testid="tab-logs">
            Logs
          </TabsTrigger>
        </TabsList>

        <TabsContent value="keys" className="mt-4 space-y-4">
          {!isAdmin ? (
            <Panel>
              <EmptyState
                icon={Lock}
                titulo="Acesso restrito ao administrador"
                descricao="Chaves de API dão acesso programático à operação inteira, por isso só administradores podem vê-las e gerá-las."
              />
            </Panel>
          ) : (
            <>
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <p className="flex items-start gap-2 text-xs text-slate-500 max-w-xl">
                  <ShieldAlert className="w-4 h-4 mt-0.5 shrink-0 text-amber-500" aria-hidden="true" />
                  O sistema guarda apenas o hash da chave. O valor completo aparece uma única vez,
                  na criação — depois disso só é possível revogar e gerar outra.
                </p>
                <Button
                  onClick={() => setAbertoChave(true)}
                  data-testid="btn-nova-chave"
                  className="bg-primary hover:bg-orange-600 text-white gap-2"
                >
                  <Plus className="w-4 h-4" /> Gerar Chave
                </Button>
              </div>

              {carregandoChaves ? (
                <Loading />
              ) : !chaves?.length ? (
                <Panel>
                  <EmptyState icon={KeyRound} titulo="Nenhuma chave gerada" />
                </Panel>
              ) : (
                <div className="grid gap-4">
                  {chaves.map((k, i) => (
                    <Panel key={k.id} data-testid={`key-card-${i}`} className="p-5">
                      <div className="flex items-center justify-between gap-4 flex-wrap">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-lg bg-primary/15 flex items-center justify-center">
                            <KeyRound className="w-5 h-5 text-primary" aria-hidden="true" />
                          </div>
                          <div>
                            <p className="font-semibold text-slate-100">{k.name}</p>
                            <div className="flex items-center gap-2 mt-1">
                              <span
                                className={`inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold border ${
                                  k.environment === "production"
                                    ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                                    : "bg-amber-500/15 text-amber-400 border-amber-500/30"
                                }`}
                              >
                                {k.environment === "production" ? "Produção" : "Sandbox"}
                              </span>
                              <span className="text-[11px] text-slate-500">
                                criada {dataHora(k.created_at)}
                                {k.last_used ? ` • usada ${dataHora(k.last_used)}` : " • nunca usada"}
                              </span>
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <code className="font-mono text-sm text-slate-400 bg-slate-800 px-3 py-1.5 rounded-lg">
                            {k.key_preview || "••••••••"}
                          </code>
                          <IconButton
                            icon={Trash2}
                            label={`Revogar chave ${k.name}`}
                            tone="hover:text-red-400"
                            data-testid={`delete-key-${i}`}
                            onClick={async () => {
                              const ok = await confirmar({
                                titulo: `Revogar "${k.name}"?`,
                                descricao:
                                  "Qualquer integração que use esta chave para de funcionar imediatamente.",
                                confirmar: "Revogar",
                              });
                              if (ok) revogarChave.mutate(k.id);
                            }}
                          />
                        </div>
                      </div>
                    </Panel>
                  ))}
                </div>
              )}
            </>
          )}
        </TabsContent>

        <TabsContent value="webhooks" className="mt-4 space-y-4">
          {isAdmin && (
            <div className="flex justify-end">
              <Button
                onClick={() => setAbertoWh(true)}
                data-testid="btn-novo-webhook"
                className="bg-primary hover:bg-orange-600 text-white gap-2"
              >
                <Plus className="w-4 h-4" /> Novo Webhook
              </Button>
            </div>
          )}
          {!webhooks.length ? (
            <Panel>
              <EmptyState
                icon={Webhook}
                titulo="Nenhum webhook configurado"
                descricao="Webhooks avisam os marketplaces quando um pedido muda de status."
              />
            </Panel>
          ) : (
            <div className="grid gap-4">
              {webhooks.map((w, i) => (
                <Panel key={w.id} data-testid={`webhook-card-${i}`} className="p-5">
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div className="min-w-0">
                      <p className="font-semibold text-slate-100">
                        {PROVEDORES[w.provider] || w.provider}
                      </p>
                      <p className="font-mono text-xs text-slate-500 break-all mt-0.5">{w.url}</p>
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {(w.events || []).map((ev) => (
                          <span
                            key={ev}
                            className="px-2 py-0.5 rounded-full bg-slate-800 text-[11px] text-slate-400 border border-slate-700"
                          >
                            {ev}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <Switch
                        checked={w.active}
                        onCheckedChange={() => alternarWh.mutate(w)}
                        disabled={!isAdmin}
                        aria-label={`${w.active ? "Desativar" : "Ativar"} webhook ${w.provider}`}
                        data-testid={`toggle-webhook-${i}`}
                      />
                      {isAdmin && (
                        <IconButton
                          icon={Trash2}
                          label={`Excluir webhook ${w.provider}`}
                          tone="hover:text-red-400"
                          data-testid={`delete-webhook-${i}`}
                          onClick={async () => {
                            const ok = await confirmar({
                              titulo: "Excluir webhook?",
                              descricao: `${PROVEDORES[w.provider] || w.provider} deixa de receber eventos.`,
                              confirmar: "Excluir",
                            });
                            if (ok) excluirWh.mutate(w.id);
                          }}
                        />
                      )}
                    </div>
                  </div>
                </Panel>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="logs" className="mt-4">
          <Panel className="overflow-hidden">
            {!logs.length ? (
              <EmptyState icon={Activity} titulo="Nenhuma chamada registrada" />
            ) : (
              <ul className="divide-y divide-slate-800">
                {logs.map((l, i) => {
                  const ok = l.status_code >= 200 && l.status_code < 300;
                  return (
                    <li
                      key={l.id}
                      data-testid={`log-row-${i}`}
                      className="flex items-center gap-3 px-4 py-3"
                    >
                      <span
                        className={`w-2 h-2 rounded-full shrink-0 ${
                          ok ? "bg-emerald-500" : "bg-red-500"
                        }`}
                        aria-hidden="true"
                      />
                      <span className="text-sm text-slate-200 w-32 shrink-0">
                        {PROVEDORES[l.provider] || l.provider}
                      </span>
                      <span className="font-mono text-xs text-slate-400 flex-1 truncate">
                        {l.event}
                      </span>
                      <span
                        className={`font-mono text-xs shrink-0 ${
                          ok ? "text-emerald-400" : "text-red-400"
                        }`}
                      >
                        {l.status_code}
                      </span>
                      <span className="text-xs text-slate-500 shrink-0 w-28 text-right">
                        {dataHora(l.created_at)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </Panel>
        </TabsContent>
      </Tabs>

      {/* Gerar chave */}
      <Dialog open={abertoChave} onOpenChange={setAbertoChave}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-heading">Gerar Chave de API</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="k-nome">Nome da chave *</Label>
              <Input
                id="k-nome"
                data-testid="key-name-input"
                value={formChave.name}
                onChange={(e) => setFormChave({ ...formChave, name: e.target.value })}
                placeholder="Ex.: Integração iFood"
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Ambiente</Label>
              <Select
                value={formChave.environment}
                onValueChange={(v) => setFormChave({ ...formChave, environment: v })}
              >
                <SelectTrigger className="bg-slate-800 border-slate-700">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="sandbox">Sandbox</SelectItem>
                  <SelectItem value="production">Produção</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAbertoChave(false)} className="text-slate-400">
              Cancelar
            </Button>
            <Button
              onClick={() => criarChave.mutate(formChave)}
              disabled={!formChave.name.trim() || criarChave.isPending}
              data-testid="save-key-button"
              className="bg-primary hover:bg-orange-600 text-white"
            >
              {criarChave.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "Gerar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Exibição única da chave */}
      <Dialog open={!!chaveNova} onOpenChange={(v) => !v && setChaveNova(null)}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-heading">Copie a chave agora</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-sm text-slate-400">
              Esta é a única vez que <strong>{chaveNova?.name}</strong> aparece por completo. Guarde
              em local seguro antes de fechar.
            </p>
            <div className="flex items-center gap-2">
              <code
                className="flex-1 font-mono text-xs text-emerald-400 bg-slate-950 border border-slate-800 px-3 py-2.5 rounded-lg break-all"
                data-testid="new-key-value"
              >
                {chaveNova?.key}
              </code>
              <IconButton
                icon={Copy}
                label="Copiar chave"
                data-testid="copy-new-key"
                onClick={() => copiar(chaveNova?.key || "")}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() => setChaveNova(null)}
              className="bg-primary hover:bg-orange-600 text-white"
            >
              Já copiei
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Novo webhook */}
      <Dialog open={abertoWh} onOpenChange={setAbertoWh}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-heading">Novo Webhook</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label>Provedor</Label>
              <Select
                value={formWh.provider}
                onValueChange={(v) => setFormWh({ ...formWh, provider: v })}
              >
                <SelectTrigger className="bg-slate-800 border-slate-700">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(PROVEDORES).map(([v, l]) => (
                    <SelectItem key={v} value={v}>
                      {l}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="wh-url">URL de destino *</Label>
              <Input
                id="wh-url"
                data-testid="webhook-url-input"
                value={formWh.url}
                onChange={(e) => setFormWh({ ...formWh, url: e.target.value })}
                placeholder="https://api.exemplo.com/webhooks/recompensa"
                className="bg-slate-800 border-slate-700 font-mono text-sm"
              />
            </div>
            <div className="space-y-2">
              <Label>Eventos</Label>
              <div className="flex flex-wrap gap-2">
                {EVENTOS.map((ev) => {
                  const marcado = formWh.events.includes(ev);
                  return (
                    <button
                      key={ev}
                      type="button"
                      aria-pressed={marcado}
                      onClick={() =>
                        setFormWh({
                          ...formWh,
                          events: marcado
                            ? formWh.events.filter((x) => x !== ev)
                            : [...formWh.events, ev],
                        })
                      }
                      className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                        marcado
                          ? "bg-primary/15 text-primary border-primary/40"
                          : "bg-slate-800 text-slate-400 border-slate-700 hover:text-slate-200"
                      }`}
                    >
                      {ev}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAbertoWh(false)} className="text-slate-400">
              Cancelar
            </Button>
            <Button
              onClick={() => criarWh.mutate(formWh)}
              disabled={!/^https?:\/\//.test(formWh.url) || criarWh.isPending}
              data-testid="save-webhook-button"
              className="bg-primary hover:bg-orange-600 text-white"
            >
              {criarWh.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "Salvar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
