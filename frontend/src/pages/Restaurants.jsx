import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Pencil, Plus, Search, Store, Trash2 } from "lucide-react";
import { api, apiError, brl, getList } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { StatusBadge } from "@/components/StatusBadge";
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
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

const VAZIO = {
  name: "", category: "", contact_person: "", email: "", phone: "", cnpj: "",
  address: "", commission_rate: 15, status: "ativo", notes: "",
};

const CAMPOS_ENVIADOS = Object.keys(VAZIO);

export default function Restaurants() {
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

  // Filtro e busca passaram para o servidor: a tela não baixa mais a base
  // inteira para filtrar no navegador.
  useEffect(() => {
    const id = setTimeout(() => {
      setBuscaAplicada(busca);
      setPage(1);
    }, 300);
    return () => clearTimeout(id);
  }, [busca]);

  const { data, isLoading } = useQuery({
    queryKey: ["restaurants", buscaAplicada, status, page],
    queryFn: () => getList("/restaurants", { search: buscaAplicada, status, page, page_size: 20 }),
    keepPreviousData: true,
  });

  const salvar = useMutation({
    mutationFn: (p) => {
      const payload = Object.fromEntries(CAMPOS_ENVIADOS.map((k) => [k, p[k] ?? VAZIO[k]]));
      return editId ? api.put(`/restaurants/${editId}`, payload) : api.post("/restaurants", payload);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["restaurants"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success(editId ? "Restaurante atualizado" : "Restaurante cadastrado");
      setAberto(false);
      setForm(VAZIO);
      setEditId(null);
    },
    onError: (e) => toast.error(apiError(e, "Erro ao salvar restaurante")),
  });

  const excluir = useMutation({
    mutationFn: ({ id, force }) => api.delete(`/restaurants/${id}`, { params: { force } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["restaurants"] });
      toast.success("Restaurante removido");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const pedirExclusao = async (r) => {
    const ok = await confirmar({
      titulo: `Excluir ${r.name}?`,
      descricao:
        "Se houver pedidos no histórico, o sistema vai pedir confirmação extra. Considere mudar o status para 'inativo' em vez de excluir.",
      confirmar: "Excluir",
    });
    if (!ok) return;
    try {
      await excluir.mutateAsync({ id: r.id, force: false });
    } catch (e) {
      if (e?.response?.status !== 409) return;
      const forcar = await confirmar({
        titulo: "Excluir mesmo assim?",
        descricao: apiError(e),
        confirmar: "Excluir definitivamente",
      });
      if (forcar) excluir.mutate({ id: r.id, force: true });
    }
  };

  const itens = data?.items || [];

  return (
    <div className="space-y-6 animate-fade-up" data-testid="restaurants-page">
      <div className="flex flex-col sm:flex-row gap-3 sm:items-center justify-between">
        <div className="flex flex-1 gap-3">
          <div className="relative flex-1 max-w-xs">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500"
              aria-hidden="true"
            />
            <Input
              data-testid="search-restaurante-input"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar por nome, CNPJ ou contato"
              aria-label="Buscar restaurantes"
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
              data-testid="filter-restaurante-status"
              aria-label="Filtrar por status"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="todos">Todos os status</SelectItem>
              <SelectItem value="ativo">Ativo</SelectItem>
              <SelectItem value="em_analise">Em análise</SelectItem>
              <SelectItem value="suspenso">Suspenso</SelectItem>
              <SelectItem value="inativo">Inativo</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button
          onClick={() => {
            setForm(VAZIO);
            setEditId(null);
            setAberto(true);
          }}
          data-testid="btn-novo-restaurante"
          className="bg-primary hover:bg-orange-600 text-white gap-2"
        >
          <Plus className="w-4 h-4" /> Novo Restaurante
        </Button>
      </div>

      <Panel className="overflow-hidden">
        {isLoading ? (
          <Loading />
        ) : itens.length === 0 ? (
          <EmptyState
            icon={Store}
            titulo="Nenhum restaurante encontrado"
            descricao={
              buscaAplicada || status !== "todos"
                ? "Ajuste a busca ou o filtro de status."
                : "Cadastre o primeiro parceiro para começar a registrar pedidos."
            }
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="border-slate-800 hover:bg-transparent">
                    <TableHead className="text-slate-400">Nome</TableHead>
                    <TableHead className="text-slate-400">Categoria</TableHead>
                    <TableHead className="text-slate-400">Contato</TableHead>
                    <TableHead className="text-slate-400">Comissão</TableHead>
                    <TableHead className="text-slate-400">Pedidos/mês</TableHead>
                    <TableHead className="text-slate-400">A receber</TableHead>
                    <TableHead className="text-slate-400">Status</TableHead>
                    <TableHead className="text-slate-400 text-right">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {itens.map((r, i) => (
                    <TableRow
                      key={r.id}
                      className="border-slate-800 hover:bg-slate-800/40"
                      data-testid={`table-restaurante-row-${i}`}
                    >
                      <TableCell className="font-medium text-slate-100">
                        <button
                          onClick={() => setDetalhe(r)}
                          data-testid={`open-restaurante-detail-${i}`}
                          className="hover:text-primary transition-colors text-left"
                        >
                          {r.name}
                        </button>
                      </TableCell>
                      <TableCell className="text-slate-300">{r.category}</TableCell>
                      <TableCell className="text-slate-400">
                        <div>{r.contact_person || "—"}</div>
                        <div className="text-xs">{r.phone}</div>
                      </TableCell>
                      <TableCell className="text-slate-300">{r.commission_rate}%</TableCell>
                      <TableCell className="text-slate-300">{r.orders_month ?? 0}</TableCell>
                      <TableCell className="text-slate-300">{brl(r.commission_due)}</TableCell>
                      <TableCell>
                        <StatusBadge status={r.status} testid={`restaurante-status-${i}`} />
                      </TableCell>
                      <TableCell className="text-right whitespace-nowrap">
                        <IconButton
                          icon={Pencil}
                          label={`Editar ${r.name}`}
                          data-testid={`edit-restaurante-${i}`}
                          onClick={() => {
                            setForm({ ...VAZIO, ...r });
                            setEditId(r.id);
                            setAberto(true);
                          }}
                        />
                        {isAdmin && (
                          <IconButton
                            icon={Trash2}
                            label={`Excluir ${r.name}`}
                            tone="hover:text-red-400"
                            data-testid={`delete-restaurante-${i}`}
                            onClick={() => pedirExclusao(r)}
                          />
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <Pagination
              page={data.page}
              pages={data.pages}
              total={data.total}
              onChange={setPage}
              label="restaurantes"
            />
          </>
        )}
      </Panel>

      <Dialog open={aberto} onOpenChange={setAberto}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100 max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading">
              {editId ? "Editar Restaurante" : "Novo Restaurante"}
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4 py-2">
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="r-nome">Nome *</Label>
              <Input
                id="r-nome"
                data-testid="restaurante-name-input"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="r-cat">Categoria *</Label>
              <Input
                id="r-cat"
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
                placeholder="Hamburgueria, Pizzaria…"
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="r-cnpj">CNPJ</Label>
              <Input
                id="r-cnpj"
                value={form.cnpj}
                onChange={(e) => setForm({ ...form, cnpj: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="r-resp">Responsável</Label>
              <Input
                id="r-resp"
                value={form.contact_person}
                onChange={(e) => setForm({ ...form, contact_person: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="r-tel">Telefone</Label>
              <Input
                id="r-tel"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="r-email">E-mail</Label>
              <Input
                id="r-email"
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="r-end">Endereço</Label>
              <Input
                id="r-end"
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="r-com">Comissão (%)</Label>
              <Input
                id="r-com"
                type="number"
                min="0"
                max="100"
                step="0.5"
                value={form.commission_rate}
                onChange={(e) =>
                  setForm({ ...form, commission_rate: parseFloat(e.target.value) || 0 })
                }
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
                  <SelectItem value="ativo">Ativo</SelectItem>
                  <SelectItem value="em_analise">Em análise</SelectItem>
                  <SelectItem value="suspenso">Suspenso</SelectItem>
                  <SelectItem value="inativo">Inativo</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="r-obs">Observações</Label>
              <Textarea
                id="r-obs"
                rows={2}
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
              disabled={!form.name.trim() || !form.category.trim() || salvar.isPending}
              data-testid="save-restaurante-button"
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
        type="restaurante"
        entity={detalhe}
      />
    </div>
  );
}
