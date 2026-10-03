import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertTriangle, Bike, Car, Loader2, Pencil, Plus, Search, Star, Trash2, Truck,
} from "lucide-react";
import { api, apiError, brl, getList } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { DetailSheet } from "@/components/DetailSheet";
import { EmptyState, IconButton, Loading, Pagination, Panel } from "@/components/Ui";
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

const VAZIO = {
  name: "", vehicle_type: "moto", phone: "", email: "", plate: "",
  status: "disponivel", rating: 5, photo: "", notes: "",
  // Dados de pagamento. Chegam pelo formulário de cadastro, mas precisam ser
  // editáveis aqui: um dígito errado na conta trava o repasse, e ninguém vai
  // pedir para a pessoa preencher o formulário de novo por causa disso.
  cpf: "", bank: "", bank_agency: "", bank_account: "",
  account_type: "", pix_key_type: "", pix_key: "",
};

const BANCOS = [
  "Banco do Brasil", "Bradesco", "Caixa Econômica Federal", "Itaú", "Santander",
  "Nubank", "Banco Inter", "C6 Bank", "PicPay", "Mercado Pago", "PagBank",
  "Banco PAN", "Sicredi", "Sicoob", "Outro",
];
const CAMPOS = Object.keys(VAZIO);

const ICONE_VEICULO = { moto: Truck, bike: Bike, carro: Car, van: Truck };
const ROTULO_VEICULO = { moto: "Moto", bike: "Bicicleta", carro: "Carro", van: "Van" };

export default function Drivers() {
  const qc = useQueryClient();
  const confirmar = useConfirm();
  const { isAdmin } = useAuth();
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [status, setStatus] = useState("todos");
  const [page, setPage] = useState(1);
  const [aberto, setAberto] = useState(false);
  const [form, setForm] = useState(VAZIO);
  const [editId, setEditId] = useState(null);
  const [detalhe, setDetalhe] = useState(null);

  useEffect(() => {
    const id = setTimeout(() => {
      setBuscaAplicada(busca);
      setPage(1);
    }, 300);
    return () => clearTimeout(id);
  }, [busca]);

  const { data, isLoading } = useQuery({
    queryKey: ["drivers", buscaAplicada, status, page],
    queryFn: () => getList("/drivers", { search: buscaAplicada, status, page, page_size: 24 }),
    keepPreviousData: true,
  });

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["drivers"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const salvar = useMutation({
    mutationFn: (p) => {
      const payload = Object.fromEntries(CAMPOS.map((k) => [k, p[k] ?? VAZIO[k]]));
      return editId ? api.put(`/drivers/${editId}`, payload) : api.post("/drivers", payload);
    },
    onSuccess: () => {
      invalidar();
      toast.success(editId ? "Entregador atualizado" : "Entregador cadastrado");
      setAberto(false);
      setForm(VAZIO);
      setEditId(null);
    },
    onError: (e) => toast.error(apiError(e, "Erro ao salvar entregador")),
  });

  // Endpoint dedicado: antes o status era mudado com um PUT do objeto inteiro,
  // que reenviava saldo e avaliação e podia sobrescrever o que o motor
  // financeiro tinha acabado de lançar.
  const mudarStatus = useMutation({
    mutationFn: ({ id, status: s }) => api.patch(`/drivers/${id}/status`, { status: s }),
    onSuccess: () => invalidar(),
    onError: (e) => toast.error(apiError(e)),
  });

  const excluir = useMutation({
    mutationFn: ({ id, force }) => api.delete(`/drivers/${id}`, { params: { force } }),
    onSuccess: () => {
      invalidar();
      toast.success("Entregador removido");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const pedirExclusao = async (d) => {
    const ok = await confirmar({
      titulo: `Excluir ${d.name}?`,
      descricao: "O cadastro sai da lista. O histórico de pedidos permanece.",
      confirmar: "Excluir",
    });
    if (!ok) return;
    try {
      await excluir.mutateAsync({ id: d.id, force: false });
    } catch (e) {
      if (e?.response?.status !== 409) return;
      const forcar = await confirmar({
        titulo: "Excluir com saldo em aberto?",
        descricao: apiError(e),
        confirmar: "Excluir mesmo assim",
      });
      if (forcar) excluir.mutate({ id: d.id, force: true });
    }
  };

  const iniciais = (n) =>
    (n || "?")
      .split(" ")
      .map((w) => w[0])
      .slice(0, 2)
      .join("")
      .toUpperCase();

  const itens = data?.items || [];

  return (
    <div className="space-y-6 animate-fade-up" data-testid="drivers-page">
      <div className="flex flex-col sm:flex-row gap-3 sm:items-center justify-between">
        <div className="flex flex-1 gap-3">
          <div className="relative flex-1 max-w-xs">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500"
              aria-hidden="true"
            />
            <Input
              data-testid="search-entregador-input"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar por nome, placa ou telefone"
              aria-label="Buscar entregadores"
              className="pl-9 bg-slate-900 border-slate-700 text-slate-100"
            />
          </div>
          <Select
            value={status}
            onValueChange={(v) => {
              setStatus(v);
              setPage(1);
            }}
          >
            <SelectTrigger
              className="w-40 bg-slate-900 border-slate-700 text-slate-100"
              data-testid="filter-entregador-status"
              aria-label="Filtrar por status"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="todos">Todos os status</SelectItem>
              <SelectItem value="disponivel">Disponível</SelectItem>
              <SelectItem value="em_entrega">Em entrega</SelectItem>
              <SelectItem value="offline">Offline</SelectItem>
              <SelectItem value="indisponivel">Indisponível</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button
          onClick={() => {
            setForm(VAZIO);
            setEditId(null);
            setAberto(true);
          }}
          data-testid="btn-novo-entregador"
          className="bg-primary hover:bg-orange-600 text-white gap-2"
        >
          <Plus className="w-4 h-4" /> Novo Entregador
        </Button>
      </div>

      {isLoading ? (
        <Loading />
      ) : itens.length === 0 ? (
        <Panel>
          <EmptyState
            icon={Bike}
            titulo="Nenhum entregador encontrado"
            descricao="Cadastre o time de entrega para atribuir pedidos e calcular repasses."
          />
        </Panel>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
            {itens.map((d, i) => {
              const VIcon = ICONE_VEICULO[d.vehicle_type] || Bike;
              return (
                <Panel
                  key={d.id}
                  data-testid={`driver-card-${i}`}
                  className="p-5 hover:border-slate-700 transition-colors"
                >
                  <div className="flex items-start gap-3">
                    {d.photo ? (
                      <img
                        src={d.photo}
                        alt=""
                        className="w-12 h-12 rounded-full object-cover shrink-0"
                      />
                    ) : (
                      <div className="w-12 h-12 rounded-full bg-primary/20 text-primary flex items-center justify-center font-bold shrink-0">
                        {iniciais(d.name)}
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <button
                        onClick={() => setDetalhe(d)}
                        data-testid={`open-driver-detail-${i}`}
                        className="font-semibold text-slate-100 hover:text-primary transition-colors truncate block max-w-full text-left"
                      >
                        {d.name}
                      </button>
                      <p className="text-xs text-slate-500 flex items-center gap-1.5 mt-0.5">
                        <VIcon className="w-3.5 h-3.5" aria-hidden="true" />
                        {ROTULO_VEICULO[d.vehicle_type] || d.vehicle_type}
                        {d.plate && ` • ${d.plate}`}
                      </p>
                    </div>
                    <span
                      className="flex items-center gap-1 text-amber-400 text-sm shrink-0"
                      aria-label={`Avaliação ${d.rating} de 5`}
                    >
                      <Star className="w-4 h-4 fill-amber-400" aria-hidden="true" /> {d.rating}
                    </span>
                  </div>

                  {!d.pix_key && !d.bank_account && (
                    <p
                      className="mt-3 flex items-center gap-1.5 rounded-lg border border-amber-500/25 bg-amber-500/10 px-2.5 py-1.5 text-[11px] text-amber-300"
                      data-testid={`driver-sem-pagamento-${i}`}
                    >
                      <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                      Sem dados de pagamento
                    </p>
                  )}

                  <div className="grid grid-cols-3 gap-2 mt-4">
                    <div className="rounded-lg bg-slate-800/50 p-3">
                      <p className="text-[11px] text-slate-500 uppercase">Entregas</p>
                      <p className="font-heading font-bold text-slate-100">{d.total_deliveries}</p>
                    </div>
                    <div className="rounded-lg bg-slate-800/50 p-3">
                      <p className="text-[11px] text-slate-500 uppercase">A receber</p>
                      <p className="font-heading font-bold text-emerald-400 text-sm">
                        {brl(d.balance_due)}
                      </p>
                    </div>
                    <div className="rounded-lg bg-slate-800/50 p-3">
                      <p className="text-[11px] text-slate-500 uppercase">Já pago</p>
                      <p className="font-heading font-bold text-slate-300 text-sm">
                        {brl(d.paid_total)}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center justify-between gap-2 mt-4">
                    <Select
                      value={d.status}
                      onValueChange={(v) => mudarStatus.mutate({ id: d.id, status: v })}
                    >
                      <SelectTrigger
                        className="w-40 h-8 bg-slate-800 border-slate-700 text-xs"
                        data-testid={`driver-status-select-${i}`}
                        aria-label={`Status de ${d.name}`}
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="disponivel">Disponível</SelectItem>
                        <SelectItem value="em_entrega">Em entrega</SelectItem>
                        <SelectItem value="offline">Offline</SelectItem>
                        <SelectItem value="indisponivel">Indisponível</SelectItem>
                      </SelectContent>
                    </Select>
                    <div className="flex">
                      <IconButton
                        icon={Pencil}
                        label={`Editar ${d.name}`}
                        data-testid={`edit-driver-${i}`}
                        onClick={() => {
                          setForm({ ...VAZIO, ...d });
                          setEditId(d.id);
                          setAberto(true);
                        }}
                      />
                      {isAdmin && (
                        <IconButton
                          icon={Trash2}
                          label={`Excluir ${d.name}`}
                          tone="hover:text-red-400"
                          data-testid={`delete-driver-${i}`}
                          onClick={() => pedirExclusao(d)}
                        />
                      )}
                    </div>
                  </div>
                </Panel>
              );
            })}
          </div>
          <Panel>
            <Pagination
              page={data.page}
              pages={data.pages}
              total={data.total}
              onChange={setPage}
              label="entregadores"
            />
          </Panel>
        </>
      )}

      <Dialog open={aberto} onOpenChange={setAberto}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100 max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading">
              {editId ? "Editar Entregador" : "Novo Entregador"}
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4 py-2">
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="d-nome">Nome *</Label>
              <Input
                id="d-nome"
                data-testid="driver-name-input"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Veículo</Label>
              <Select
                value={form.vehicle_type}
                onValueChange={(v) => setForm({ ...form, vehicle_type: v })}
              >
                <SelectTrigger className="bg-slate-800 border-slate-700">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="moto">Moto</SelectItem>
                  <SelectItem value="bike">Bicicleta</SelectItem>
                  <SelectItem value="carro">Carro</SelectItem>
                  <SelectItem value="van">Van</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="d-placa">Placa</Label>
              <Input
                id="d-placa"
                value={form.plate}
                onChange={(e) => setForm({ ...form, plate: e.target.value.toUpperCase() })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="d-tel">Telefone</Label>
              <Input
                id="d-tel"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="d-email">E-mail</Label>
              <Input
                id="d-email"
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="d-aval">Avaliação (0 a 5)</Label>
              <Input
                id="d-aval"
                type="number"
                min="0"
                max="5"
                step="0.1"
                value={form.rating}
                onChange={(e) => setForm({ ...form, rating: parseFloat(e.target.value) || 0 })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Status</Label>
              <Select value={form.status} onValueChange={(v) => setForm({ ...form, status: v })}>
                <SelectTrigger className="bg-slate-800 border-slate-700">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="disponivel">Disponível</SelectItem>
                  <SelectItem value="em_entrega">Em entrega</SelectItem>
                  <SelectItem value="offline">Offline</SelectItem>
                  <SelectItem value="indisponivel">Indisponível</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2 mt-2 border-t border-slate-800 pt-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Dados de pagamento
              </p>
              <p className="mt-0.5 text-[11px] text-slate-600">
                Usados no repasse. Vêm preenchidos quando o entregador se cadastra
                pelo formulário.
              </p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="d-cpf">CPF</Label>
              <Input
                id="d-cpf"
                inputMode="numeric"
                data-testid="driver-cpf-input"
                value={form.cpf}
                onChange={(e) =>
                  setForm({ ...form, cpf: e.target.value.replace(/\D/g, "").slice(0, 11) })
                }
                placeholder="00000000000"
                className="bg-slate-800 border-slate-700 font-mono"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Banco</Label>
              <Select
                value={form.bank}
                onValueChange={(v) => setForm({ ...form, bank: v })}
              >
                <SelectTrigger className="bg-slate-800 border-slate-700" data-testid="driver-bank">
                  <SelectValue placeholder="Selecione" />
                </SelectTrigger>
                <SelectContent>
                  {BANCOS.map((b) => (
                    <SelectItem key={b} value={b}>
                      {b}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="d-ag">Agência</Label>
              <Input
                id="d-ag"
                data-testid="driver-agency-input"
                value={form.bank_agency}
                onChange={(e) => setForm({ ...form, bank_agency: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="d-conta">Número da conta</Label>
              <Input
                id="d-conta"
                data-testid="driver-account-input"
                value={form.bank_account}
                onChange={(e) => setForm({ ...form, bank_account: e.target.value })}
                placeholder="12345678-9"
                className="bg-slate-800 border-slate-700 font-mono"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Tipo de conta</Label>
              <Select
                value={form.account_type}
                onValueChange={(v) => setForm({ ...form, account_type: v })}
              >
                <SelectTrigger className="bg-slate-800 border-slate-700">
                  <SelectValue placeholder="Selecione" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="corrente">Conta Corrente</SelectItem>
                  <SelectItem value="poupanca">Conta Poupança</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Tipo de chave PIX</Label>
              <Select
                value={form.pix_key_type}
                onValueChange={(v) => setForm({ ...form, pix_key_type: v })}
              >
                <SelectTrigger className="bg-slate-800 border-slate-700">
                  <SelectValue placeholder="Selecione" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="cpf">CPF</SelectItem>
                  <SelectItem value="celular">Celular</SelectItem>
                  <SelectItem value="email">E-mail</SelectItem>
                  <SelectItem value="aleatoria">Chave aleatória</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="d-pix">Chave PIX</Label>
              <Input
                id="d-pix"
                data-testid="driver-pix-input"
                value={form.pix_key}
                onChange={(e) => setForm({ ...form, pix_key: e.target.value })}
                className="bg-slate-800 border-slate-700 font-mono"
              />
            </div>

            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="d-obs">Observações</Label>
              <Textarea
                id="d-obs"
                rows={2}
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            {/* O saldo a receber deixou de ser digitável: ele é o resultado das
                entregas concluídas menos os repasses liquidados. */}
            <p className="col-span-2 text-xs text-slate-500">
              O saldo a receber é calculado pelas entregas e pelos repasses liquidados.
            </p>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAberto(false)} className="text-slate-400">
              Cancelar
            </Button>
            <Button
              onClick={() => salvar.mutate(form)}
              disabled={!form.name.trim() || salvar.isPending}
              data-testid="save-driver-button"
              className="bg-primary hover:bg-orange-600 text-white"
            >
              {salvar.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "Salvar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <DetailSheet
        open={!!detalhe}
        onOpenChange={(v) => !v && setDetalhe(null)}
        type="entregador"
        entity={detalhe}
      />
    </div>
  );
}
