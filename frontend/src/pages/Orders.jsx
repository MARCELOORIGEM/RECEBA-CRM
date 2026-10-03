import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Bike, DollarSign, Loader2, MapPin, Package, Pencil, Plus, Route, Search, Store, Trash2,
} from "lucide-react";
import { api, apiError, brl, dataHora, getList } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { StatusBadge, statusLabel } from "@/components/StatusBadge";
import { EmptyState, IconButton, Loading, Pagination, Panel } from "@/components/Ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const ABAS = [
  { key: "todos", label: "Todos" },
  { key: "criado", label: "Criados" },
  { key: "aguardando_coleta", label: "Aguardando" },
  { key: "em_transito", label: "Em trânsito" },
  { key: "entregue", label: "Entregues" },
  { key: "cancelado", label: "Cancelados" },
];

// Espelha o fluxo validado no backend: o select só oferece o que a API aceita,
// em vez de listar tudo e receber um 409 depois do clique.
const PROXIMOS = {
  criado: ["aguardando_coleta", "cancelado"],
  aguardando_coleta: ["em_transito", "cancelado", "criado"],
  em_transito: ["entregue", "cancelado", "aguardando_coleta"],
  entregue: ["em_transito"],
  cancelado: ["criado"],
};
const ROTULO = {
  criado: "Criado",
  aguardando_coleta: "Aguardando coleta",
  em_transito: "Em trânsito",
  entregue: "Entregue",
  cancelado: "Cancelado",
};

const VAZIO = {
  restaurant_id: "", restaurant_name: "", customer_name: "", customer_address: "",
  customer_phone: "", driver_id: "", driver_name: "", amount: 0, delivery_fee: 0,
  distance_km: 0, status: "criado", notes: "",
};

export default function Orders() {
  const qc = useQueryClient();
  const confirmar = useConfirm();
  const { isAdmin } = useAuth();
  const [aba, setAba] = useState("todos");
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [page, setPage] = useState(1);
  const [aberto, setAberto] = useState(false);
  const [form, setForm] = useState(VAZIO);
  const [editId, setEditId] = useState(null);

  useEffect(() => {
    const id = setTimeout(() => {
      setBuscaAplicada(busca);
      setPage(1);
    }, 300);
    return () => clearTimeout(id);
  }, [busca]);

  const { data, isLoading } = useQuery({
    queryKey: ["orders", aba, buscaAplicada, page],
    queryFn: () =>
      getList("/orders", { status: aba, search: buscaAplicada, page, page_size: 24 }),
    keepPreviousData: true,
    refetchInterval: 60_000,
  });
  const { data: restaurantes } = useQuery({
    queryKey: ["restaurants", "todos-select"],
    queryFn: () => getList("/restaurants", { page_size: 200 }),
  });
  const { data: entregadores } = useQuery({
    queryKey: ["drivers", "todos-select"],
    queryFn: () => getList("/drivers", { page_size: 200 }),
  });

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["orders"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    qc.invalidateQueries({ queryKey: ["drivers"] });
    qc.invalidateQueries({ queryKey: ["restaurants"] });
  };

  const salvar = useMutation({
    mutationFn: (p) => (editId ? api.put(`/orders/${editId}`, p) : api.post("/orders", p)),
    onSuccess: ({ data: o }) => {
      invalidar();
      toast.success(editId ? `Pedido ${o.code} atualizado` : `Pedido ${o.code} criado`);
      setAberto(false);
      setForm(VAZIO);
      setEditId(null);
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const abrirNovo = () => {
    setForm(VAZIO);
    setEditId(null);
    setAberto(true);
  };

  // Dados do cliente, valores e distância eram imutáveis depois de criar o
  // pedido: um endereço digitado errado só saía excluindo e refazendo.
  const abrirEdicao = (o) => {
    // Pedidos migrados podem ter só o nome do restaurante. Reatar pelo nome
    // evita abrir o formulário com o campo obrigatório vazio e sem explicação.
    const porNome = !o.restaurant_id
      ? restaurantes?.items?.find((r) => r.name === o.restaurant_name)
      : null;
    setForm({ ...VAZIO, ...o, restaurant_id: o.restaurant_id || porNome?.id || "" });
    setEditId(o.id);
    setAberto(true);
  };

  const mudarStatus = useMutation({
    mutationFn: ({ id, status }) => api.patch(`/orders/${id}/status`, { status }),
    onSuccess: ({ data: o }) => {
      invalidar();
      toast.success(
        o.status === "entregue"
          ? `Entrega registrada • repasse ${brl(o.driver_earning)}`
          : "Status atualizado",
      );
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const atribuir = useMutation({
    mutationFn: ({ id, driver_id }) => api.patch(`/orders/${id}/assign`, { driver_id }),
    onSuccess: () => {
      invalidar();
      toast.success("Entregador atribuído");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const excluir = useMutation({
    mutationFn: (id) => api.delete(`/orders/${id}`),
    onSuccess: () => {
      invalidar();
      toast.success("Pedido removido");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const itens = data?.items || [];

  return (
    <div className="space-y-6 animate-fade-up" data-testid="orders-page">
      <div className="flex flex-col lg:flex-row gap-3 lg:items-center justify-between">
        <div className="overflow-x-auto">
          <Tabs
            value={aba}
            onValueChange={(v) => {
              setAba(v);
              setPage(1);
            }}
          >
            <TabsList className="bg-slate-900 border border-slate-800">
              {ABAS.map((t) => (
                <TabsTrigger
                  key={t.key}
                  value={t.key}
                  data-testid={`order-tab-${t.key}`}
                  className="text-xs"
                >
                  {t.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
        <div className="flex gap-3 shrink-0">
          <div className="relative flex-1 lg:w-64">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500"
              aria-hidden="true"
            />
            <Input
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Código, cliente ou restaurante"
              aria-label="Buscar pedidos"
              data-testid="search-pedido-input"
              className="pl-9 bg-slate-900 border-slate-700 text-slate-100"
            />
          </div>
          <Button
            onClick={abrirNovo}
            data-testid="btn-novo-pedido"
            className="bg-primary hover:bg-orange-600 text-white gap-2 shrink-0"
          >
            <Plus className="w-4 h-4" /> Novo Pedido
          </Button>
        </div>
      </div>

      {isLoading ? (
        <Loading />
      ) : itens.length === 0 ? (
        <Panel>
          <EmptyState
            icon={Package}
            titulo="Nenhum pedido nesta categoria"
            descricao="Crie um pedido ou mude o filtro acima."
          />
        </Panel>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {itens.map((o, i) => (
              <Panel key={o.id} data-testid={`order-card-${i}`} className="p-5 space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-sm font-semibold text-primary">{o.code}</span>
                  <StatusBadge status={o.status} testid={`order-status-${i}`} />
                </div>

                <div className="space-y-2 text-sm">
                  <p className="flex items-center gap-2 text-slate-300">
                    <Store className="w-4 h-4 text-slate-500 shrink-0" aria-hidden="true" />
                    <span className="truncate">{o.restaurant_name}</span>
                  </p>
                  <p className="flex items-start gap-2 text-slate-300">
                    <MapPin className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" aria-hidden="true" />
                    <span className="min-w-0">
                      <span className="block truncate">{o.customer_name}</span>
                      <span className="block text-xs text-slate-500 truncate">
                        {o.customer_address || "Sem endereço"}
                      </span>
                    </span>
                  </p>
                  <p className="flex items-center gap-2 text-slate-300">
                    <Bike className="w-4 h-4 text-slate-500 shrink-0" aria-hidden="true" />
                    <span className="truncate">{o.driver_name || "Sem entregador"}</span>
                    {o.distance_km > 0 && (
                      <span className="ml-auto flex items-center gap-1 text-xs text-slate-500">
                        <Route className="w-3 h-3" aria-hidden="true" /> {o.distance_km} km
                      </span>
                    )}
                  </p>
                </div>

                <div className="flex items-end justify-between pt-1">
                  <div>
                    <p className="font-heading font-bold text-slate-100">{brl(o.amount)}</p>
                    <p className="text-[11px] text-slate-500">
                      taxa {brl(o.delivery_fee)} • {dataHora(o.created_at)}
                    </p>
                  </div>
                  {o.status === "entregue" && (
                    <div className="text-right">
                      <p className="text-[11px] text-slate-500">repasse / comissão</p>
                      <p className="text-xs font-semibold text-emerald-400">
                        {brl(o.driver_earning)} / {brl(o.platform_commission)}
                      </p>
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-800">
                  <Select
                    value={o.status}
                    onValueChange={(v) => mudarStatus.mutate({ id: o.id, status: v })}
                  >
                    <SelectTrigger
                      className="h-8 bg-slate-800 border-slate-700 text-xs"
                      data-testid={`order-status-select-${i}`}
                      aria-label={`Status do pedido ${o.code}`}
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={o.status} disabled>
                        {ROTULO[o.status]}
                      </SelectItem>
                      {(PROXIMOS[o.status] || []).map((s) => (
                        <SelectItem key={s} value={s}>
                          → {ROTULO[s]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Select
                    value={o.driver_id || ""}
                    onValueChange={(v) => atribuir.mutate({ id: o.id, driver_id: v })}
                    disabled={["entregue", "cancelado"].includes(o.status)}
                  >
                    <SelectTrigger
                      className="h-8 bg-slate-800 border-slate-700 text-xs"
                      data-testid={`order-driver-select-${i}`}
                      aria-label={`Entregador do pedido ${o.code}`}
                    >
                      <SelectValue placeholder="Atribuir" />
                    </SelectTrigger>
                    <SelectContent>
                      {(entregadores?.items || []).map((d) => (
                        <SelectItem key={d.id} value={d.id}>
                          {d.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex justify-end -mb-2">
                  <IconButton
                    icon={Pencil}
                    label={`Editar pedido ${o.code}`}
                    data-testid={`edit-order-${i}`}
                    onClick={() => abrirEdicao(o)}
                  />
                  {isAdmin && (
                    <IconButton
                      icon={Trash2}
                      label={`Excluir pedido ${o.code}`}
                      tone="hover:text-red-400"
                      data-testid={`delete-order-${i}`}
                      onClick={async () => {
                        const ok = await confirmar({
                          titulo: `Excluir ${o.code}?`,
                          descricao:
                            "Os lançamentos de repasse e comissão deste pedido serão estornados.",
                          confirmar: "Excluir",
                        });
                        if (ok) excluir.mutate(o.id);
                      }}
                    />
                  )}
                </div>
              </Panel>
            ))}
          </div>
          <Panel>
            <Pagination
              page={data.page}
              pages={data.pages}
              total={data.total}
              onChange={setPage}
              label="pedidos"
            />
          </Panel>
        </>
      )}

      <Dialog open={aberto} onOpenChange={setAberto}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100 max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading">
              {editId ? "Editar Pedido" : "Novo Pedido"}
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4 py-2">
            <div className="space-y-1.5">
              <Label>Restaurante *</Label>
              <Select
                value={form.restaurant_id}
                onValueChange={(v) => {
                  const r = restaurantes?.items.find((x) => x.id === v);
                  setForm({ ...form, restaurant_id: v, restaurant_name: r?.name || "" });
                }}
              >
                <SelectTrigger
                  className="bg-slate-800 border-slate-700"
                  data-testid="order-restaurant-select"
                >
                  <SelectValue placeholder="Selecione" />
                </SelectTrigger>
                <SelectContent>
                  {(restaurantes?.items || []).map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      {r.name}
                      {r.status !== "ativo" && (
                        <span className="ml-1.5 text-xs text-slate-500">
                          ({statusLabel(r.status)})
                        </span>
                      )}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Entregador</Label>
              <Select
                value={form.driver_id}
                onValueChange={(v) => {
                  const d = entregadores?.items.find((x) => x.id === v);
                  setForm({ ...form, driver_id: v, driver_name: d?.name || "" });
                }}
              >
                <SelectTrigger className="bg-slate-800 border-slate-700">
                  <SelectValue placeholder="Opcional" />
                </SelectTrigger>
                <SelectContent>
                  {(entregadores?.items || []).map((d) => (
                    <SelectItem key={d.id} value={d.id}>
                      {d.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="o-cliente">Cliente *</Label>
              <Input
                id="o-cliente"
                data-testid="order-customer-input"
                value={form.customer_name}
                onChange={(e) => setForm({ ...form, customer_name: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="o-tel">Telefone do cliente</Label>
              <Input
                id="o-tel"
                value={form.customer_phone}
                onChange={(e) => setForm({ ...form, customer_phone: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="o-end">Endereço de entrega</Label>
              <Input
                id="o-end"
                value={form.customer_address}
                onChange={(e) => setForm({ ...form, customer_address: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="o-valor">Valor do pedido (R$)</Label>
              <Input
                id="o-valor"
                type="number"
                min="0"
                step="0.01"
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: parseFloat(e.target.value) || 0 })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="o-taxa">Taxa de entrega (R$)</Label>
              <Input
                id="o-taxa"
                type="number"
                min="0"
                step="0.01"
                value={form.delivery_fee}
                onChange={(e) => setForm({ ...form, delivery_fee: parseFloat(e.target.value) || 0 })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="o-km">Distância (km)</Label>
              <Input
                id="o-km"
                type="number"
                min="0"
                step="0.1"
                value={form.distance_km}
                onChange={(e) => setForm({ ...form, distance_km: parseFloat(e.target.value) || 0 })}
                className="bg-slate-800 border-slate-700"
              />
              <p className="text-xs text-slate-500">
                Usada para calcular o repasse de contratos por quilômetro.
              </p>
            </div>
            {editId && (
              <div className="col-span-2 rounded-lg border border-slate-800 bg-slate-800/40 px-3 py-2">
                <p className="text-xs text-slate-400">
                  O status continua sendo alterado pelo seletor do cartão, para que o
                  lançamento de repasse e comissão acompanhe cada mudança.
                </p>
              </div>
            )}
          </div>
          {(!form.restaurant_id || !form.customer_name.trim()) && (
            <p className="text-xs text-amber-400" role="status" data-testid="order-form-hint">
              {!form.restaurant_id
                ? "Selecione o restaurante para salvar."
                : "Informe o nome do cliente para salvar."}
            </p>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAberto(false)} className="text-slate-400">
              Cancelar
            </Button>
            <Button
              onClick={() => salvar.mutate(form)}
              disabled={!form.restaurant_id || !form.customer_name.trim() || salvar.isPending}
              data-testid="save-order-button"
              className="bg-primary hover:bg-orange-600 text-white gap-2"
            >
              {salvar.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : editId ? (
                "Salvar alterações"
              ) : (
                <>
                  <DollarSign className="w-4 h-4" /> Criar Pedido
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
