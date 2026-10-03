import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowDownCircle, ArrowUpCircle, CheckCircle2, Clock, FileText, Loader2, Plus,
  RotateCcw, Trash2, Wallet,
} from "lucide-react";
import { api, apiError, brl, dataBR, getList, hoje } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState, IconButton, Loading, MetricCard, Pagination, Panel } from "@/components/Ui";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const REGRA = {
  taxa_fixa: "Taxa fixa mensal",
  valor_km: "Valor por KM",
  comissao_entrega: "Comissão por entrega",
};

const CONTRATO_VAZIO = {
  party_type: "restaurante", party_id: "", party_name: "",
  rule_type: "comissao_entrega", value: 0, status: "ativo", notes: "",
};
const PAGAMENTO_VAZIO = () => ({
  creditor: "", creditor_type: "entregador", creditor_id: "", amount: 0,
  due_date: hoje(), method: "PIX", status: "pendente", notes: "",
});

export default function Contracts() {
  const qc = useQueryClient();
  const confirmar = useConfirm();
  const { isAdmin } = useAuth();
  const [filtroPagamento, setFiltroPagamento] = useState("todos");
  const [pagePag, setPagePag] = useState(1);
  const [abertoC, setAbertoC] = useState(false);
  const [abertoP, setAbertoP] = useState(false);
  const [formC, setFormC] = useState(CONTRATO_VAZIO);
  const [formP, setFormP] = useState(PAGAMENTO_VAZIO);
  const [editC, setEditC] = useState(null);

  const { data: contratos, isLoading: carregandoC } = useQuery({
    queryKey: ["contracts"],
    queryFn: () => getList("/contracts", { page_size: 100 }),
  });
  const { data: pagamentos, isLoading: carregandoP } = useQuery({
    queryKey: ["payments", filtroPagamento, pagePag],
    queryFn: () =>
      getList("/payments", { status: filtroPagamento, page: pagePag, page_size: 25 }),
    keepPreviousData: true,
  });
  const { data: restaurantes } = useQuery({
    queryKey: ["restaurants", "select"],
    queryFn: () => getList("/restaurants", { page_size: 200 }),
  });
  const { data: entregadores } = useQuery({
    queryKey: ["drivers", "select"],
    queryFn: () => getList("/drivers", { page_size: 200 }),
  });

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["payments"] });
    qc.invalidateQueries({ queryKey: ["contracts"] });
    qc.invalidateQueries({ queryKey: ["drivers"] });
    qc.invalidateQueries({ queryKey: ["restaurants"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const salvarC = useMutation({
    mutationFn: (p) => (editC ? api.put(`/contracts/${editC}`, p) : api.post("/contracts", p)),
    onSuccess: () => {
      invalidar();
      toast.success(editC ? "Contrato atualizado" : "Contrato criado");
      setAbertoC(false);
      setFormC(CONTRATO_VAZIO);
      setEditC(null);
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const excluirC = useMutation({
    mutationFn: (id) => api.delete(`/contracts/${id}`),
    onSuccess: () => {
      invalidar();
      toast.success("Contrato removido");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const salvarP = useMutation({
    mutationFn: (p) => api.post("/payments", p),
    onSuccess: () => {
      invalidar();
      toast.success("Pagamento registrado");
      setAbertoP(false);
      setFormP(PAGAMENTO_VAZIO());
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const liquidar = useMutation({
    mutationFn: (id) => api.post(`/payments/${id}/settle`),
    onSuccess: () => {
      invalidar();
      toast.success("Pagamento liquidado e saldo do credor atualizado");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const estornar = useMutation({
    mutationFn: (id) => api.post(`/payments/${id}/reopen`),
    onSuccess: () => {
      invalidar();
      toast.success("Liquidação estornada");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const excluirP = useMutation({
    mutationFn: (id) => api.delete(`/payments/${id}`),
    onSuccess: () => {
      invalidar();
      toast.success("Pagamento removido");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  // Totais vêm do servidor, sobre o filtro inteiro. Antes eram somados só com
  // os registros carregados na tela — e ignoravam o status, misturando pago
  // com pendente no mesmo número.
  const totais = pagamentos?.totals || {};
  const METRICAS = [
    {
      label: "Em aberto",
      value: (totais.pendente || 0) + (totais.atrasado || 0),
      icon: Clock,
      tone: "text-amber-400",
    },
    { label: "Atrasado", value: totais.atrasado || 0, icon: ArrowDownCircle, tone: "text-red-400" },
    { label: "Liquidado", value: totais.pago || 0, icon: CheckCircle2, tone: "text-emerald-400" },
    { label: "Total lançado", value: totais.geral || 0, icon: Wallet, tone: "text-slate-50" },
  ];

  const partes = formC.party_type === "restaurante" ? restaurantes?.items : entregadores?.items;
  const credores = formP.creditor_type === "restaurante" ? restaurantes?.items : entregadores?.items;

  const prefixo = (r) => (r === "comissao_entrega" ? "" : "R$ ");
  const sufixo = (r) =>
    r === "comissao_entrega" ? "%" : r === "valor_km" ? " /km" : " /mês";

  return (
    <div className="space-y-6 animate-fade-up" data-testid="contracts-page">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-6">
        {METRICAS.map((m) => (
          <MetricCard
            key={m.label}
            icon={m.icon}
            label={m.label}
            value={brl(m.value)}
            tone={m.tone}
          />
        ))}
      </div>

      <Tabs defaultValue="payments">
        <TabsList className="bg-slate-900 border border-slate-800">
          <TabsTrigger value="payments" data-testid="tab-payments">
            Controle de Pagamentos
          </TabsTrigger>
          <TabsTrigger value="contracts" data-testid="tab-contracts">
            Regras de Contrato
          </TabsTrigger>
        </TabsList>

        <TabsContent value="payments" className="mt-4 space-y-4">
          <div className="flex flex-wrap gap-3 justify-between items-center">
            <Select
              value={filtroPagamento}
              onValueChange={(v) => {
                setFiltroPagamento(v);
                setPagePag(1);
              }}
            >
              <SelectTrigger
                className="w-44 bg-slate-900 border-slate-700 text-slate-100"
                data-testid="filter-payment-status"
                aria-label="Filtrar pagamentos por status"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os status</SelectItem>
                <SelectItem value="pendente">Pendente</SelectItem>
                <SelectItem value="atrasado">Atrasado</SelectItem>
                <SelectItem value="pago">Pago</SelectItem>
                <SelectItem value="cancelado">Cancelado</SelectItem>
              </SelectContent>
            </Select>
            <Button
              onClick={() => {
                setFormP(PAGAMENTO_VAZIO());
                setAbertoP(true);
              }}
              data-testid="btn-novo-pagamento"
              className="bg-primary hover:bg-orange-600 text-white gap-2"
            >
              <Plus className="w-4 h-4" /> Novo Pagamento
            </Button>
          </div>

          <Panel className="overflow-hidden">
            {carregandoP ? (
              <Loading />
            ) : !pagamentos?.items?.length ? (
              <EmptyState
                icon={Wallet}
                titulo="Nenhum pagamento neste filtro"
                descricao="Registre os repasses a entregadores e as cobranças de comissão dos restaurantes."
              />
            ) : (
              <>
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-slate-800 hover:bg-transparent">
                        <TableHead className="text-slate-400">Credor</TableHead>
                        <TableHead className="text-slate-400">Tipo</TableHead>
                        <TableHead className="text-slate-400">Valor</TableHead>
                        <TableHead className="text-slate-400">Vencimento</TableHead>
                        <TableHead className="text-slate-400">Método</TableHead>
                        <TableHead className="text-slate-400">Status</TableHead>
                        <TableHead className="text-slate-400 text-right">Ações</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {pagamentos.items.map((p, i) => (
                        <TableRow
                          key={p.id}
                          className="border-slate-800 hover:bg-slate-800/40"
                          data-testid={`payment-row-${i}`}
                        >
                          <TableCell className="font-medium text-slate-100">{p.creditor}</TableCell>
                          <TableCell className="text-slate-400 capitalize">
                            {p.creditor_type}
                          </TableCell>
                          <TableCell className="text-slate-100 font-semibold">
                            {brl(p.amount)}
                          </TableCell>
                          <TableCell className="text-slate-300">{dataBR(p.due_date)}</TableCell>
                          <TableCell className="text-slate-300">{p.method}</TableCell>
                          <TableCell>
                            <StatusBadge status={p.status} testid={`payment-status-${i}`} />
                          </TableCell>
                          <TableCell className="text-right whitespace-nowrap">
                            {p.status === "pendente" || p.status === "atrasado" ? (
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={async () => {
                                  const ok = await confirmar({
                                    titulo: `Liquidar ${brl(p.amount)}?`,
                                    descricao: `Confirma o pagamento a ${p.creditor}? O saldo do credor será baixado.`,
                                    confirmar: "Confirmar pagamento",
                                    destrutivo: false,
                                  });
                                  if (ok) liquidar.mutate(p.id);
                                }}
                                disabled={liquidar.isPending}
                                data-testid={`btn-registrar-pagamento-${i}`}
                                className="text-emerald-400 hover:text-emerald-300 gap-1.5 h-8"
                              >
                                <CheckCircle2 className="w-4 h-4" /> Liquidar
                              </Button>
                            ) : p.status === "pago" && isAdmin ? (
                              <IconButton
                                icon={RotateCcw}
                                label={`Estornar pagamento de ${p.creditor}`}
                                data-testid={`reopen-payment-${i}`}
                                onClick={async () => {
                                  const ok = await confirmar({
                                    titulo: "Estornar liquidação?",
                                    descricao:
                                      "O valor volta a constar como pendente e o saldo do credor é restaurado.",
                                    confirmar: "Estornar",
                                  });
                                  if (ok) estornar.mutate(p.id);
                                }}
                              />
                            ) : null}
                            {isAdmin && (
                              <IconButton
                                icon={Trash2}
                                label={`Excluir pagamento de ${p.creditor}`}
                                tone="hover:text-red-400"
                                data-testid={`delete-payment-${i}`}
                                onClick={async () => {
                                  const ok = await confirmar({
                                    titulo: "Excluir lançamento?",
                                    descricao: `${p.creditor} — ${brl(p.amount)}. Esta ação não pode ser desfeita.`,
                                    confirmar: "Excluir",
                                  });
                                  if (ok) excluirP.mutate(p.id);
                                }}
                              />
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                <Pagination
                  page={pagamentos.page}
                  pages={pagamentos.pages}
                  total={pagamentos.total}
                  onChange={setPagePag}
                  label="lançamentos"
                />
              </>
            )}
          </Panel>
        </TabsContent>

        <TabsContent value="contracts" className="mt-4 space-y-4">
          <div className="flex justify-end">
            <Button
              onClick={() => {
                setFormC(CONTRATO_VAZIO);
                setEditC(null);
                setAbertoC(true);
              }}
              data-testid="btn-novo-contrato"
              className="bg-primary hover:bg-orange-600 text-white gap-2"
            >
              <Plus className="w-4 h-4" /> Novo Contrato
            </Button>
          </div>

          {carregandoC ? (
            <Loading />
          ) : !contratos?.items?.length ? (
            <Panel>
              <EmptyState
                icon={FileText}
                titulo="Nenhum contrato cadastrado"
                descricao="A regra do contrato define quanto o entregador recebe por entrega e quanto a Miliano cobra do restaurante."
              />
            </Panel>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {contratos.items.map((c, i) => (
                <Panel key={c.id} data-testid={`contract-card-${i}`} className="p-5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-semibold text-slate-100 truncate">{c.party_name}</p>
                      <p className="text-xs text-slate-500 capitalize">{c.party_type}</p>
                    </div>
                    <StatusBadge status={c.status} />
                  </div>
                  <div className="mt-4 pt-4 border-t border-slate-800">
                    <p className="text-xs text-slate-500 uppercase tracking-wider">
                      {REGRA[c.rule_type]}
                    </p>
                    <p className="font-heading text-2xl font-bold text-primary mt-1">
                      {prefixo(c.rule_type)}
                      {c.value}
                      {sufixo(c.rule_type)}
                    </p>
                  </div>
                  <div className="flex justify-end gap-1 mt-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setFormC({ ...CONTRATO_VAZIO, ...c });
                        setEditC(c.id);
                        setAbertoC(true);
                      }}
                      data-testid={`edit-contract-${i}`}
                      className="h-8 text-xs text-slate-400 hover:text-primary"
                    >
                      Editar
                    </Button>
                    {isAdmin && (
                      <IconButton
                        icon={Trash2}
                        label={`Excluir contrato de ${c.party_name}`}
                        tone="hover:text-red-400"
                        data-testid={`delete-contract-${i}`}
                        onClick={async () => {
                          const ok = await confirmar({
                            titulo: `Excluir contrato de ${c.party_name}?`,
                            descricao:
                              "Novas entregas passarão a usar a regra padrão até que outro contrato seja criado.",
                            confirmar: "Excluir",
                          });
                          if (ok) excluirC.mutate(c.id);
                        }}
                      />
                    )}
                  </div>
                </Panel>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Pagamento */}
      <Dialog open={abertoP} onOpenChange={setAbertoP}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-heading">Novo Pagamento</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4 py-2">
            <div className="space-y-1.5">
              <Label>Tipo de credor</Label>
              <Select
                value={formP.creditor_type}
                onValueChange={(v) =>
                  setFormP({ ...formP, creditor_type: v, creditor_id: "", creditor: "" })
                }
              >
                <SelectTrigger className="bg-slate-800 border-slate-700">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="entregador">Entregador</SelectItem>
                  <SelectItem value="restaurante">Restaurante</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Credor *</Label>
              <Select
                value={formP.creditor_id}
                onValueChange={(v) => {
                  const alvo = credores?.find((x) => x.id === v);
                  setFormP({
                    ...formP,
                    creditor_id: v,
                    creditor: alvo?.name || "",
                    amount:
                      formP.creditor_type === "entregador"
                        ? alvo?.balance_due || formP.amount
                        : alvo?.commission_due || formP.amount,
                  });
                }}
              >
                <SelectTrigger
                  className="bg-slate-800 border-slate-700"
                  data-testid="payment-creditor-select"
                >
                  <SelectValue placeholder="Selecione" />
                </SelectTrigger>
                <SelectContent>
                  {(credores || []).map((x) => (
                    <SelectItem key={x.id} value={x.id}>
                      {x.name}
                      {formP.creditor_type === "entregador" && x.balance_due > 0
                        ? ` — deve ${brl(x.balance_due)}`
                        : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="p-valor">Valor (R$) *</Label>
              <Input
                id="p-valor"
                type="number"
                min="0.01"
                step="0.01"
                data-testid="payment-amount-input"
                value={formP.amount}
                onChange={(e) => setFormP({ ...formP, amount: parseFloat(e.target.value) || 0 })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="p-venc">Vencimento</Label>
              <Input
                id="p-venc"
                type="date"
                value={formP.due_date}
                onChange={(e) => setFormP({ ...formP, due_date: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Método</Label>
              <Select value={formP.method} onValueChange={(v) => setFormP({ ...formP, method: v })}>
                <SelectTrigger className="bg-slate-800 border-slate-700">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="PIX">PIX</SelectItem>
                  <SelectItem value="Transferência">Transferência</SelectItem>
                  <SelectItem value="Dinheiro">Dinheiro</SelectItem>
                  <SelectItem value="Boleto">Boleto</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Status</Label>
              <Select value={formP.status} onValueChange={(v) => setFormP({ ...formP, status: v })}>
                <SelectTrigger className="bg-slate-800 border-slate-700">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="pendente">Pendente</SelectItem>
                  <SelectItem value="atrasado">Atrasado</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="p-obs">Observações</Label>
              <Textarea
                id="p-obs"
                rows={2}
                value={formP.notes}
                onChange={(e) => setFormP({ ...formP, notes: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAbertoP(false)} className="text-slate-400">
              Cancelar
            </Button>
            <Button
              onClick={() => salvarP.mutate(formP)}
              disabled={!formP.creditor || formP.amount <= 0 || salvarP.isPending}
              data-testid="save-payment-button"
              className="bg-primary hover:bg-orange-600 text-white"
            >
              {salvarP.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "Salvar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Contrato */}
      <Dialog open={abertoC} onOpenChange={setAbertoC}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-heading">
              {editC ? "Editar Contrato" : "Novo Contrato"}
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4 py-2">
            <div className="space-y-1.5">
              <Label>Tipo de parte</Label>
              <Select
                value={formC.party_type}
                onValueChange={(v) =>
                  setFormC({ ...formC, party_type: v, party_id: "", party_name: "" })
                }
              >
                <SelectTrigger className="bg-slate-800 border-slate-700">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="restaurante">Restaurante</SelectItem>
                  <SelectItem value="entregador">Entregador</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Parte *</Label>
              <Select
                value={formC.party_id}
                onValueChange={(v) => {
                  const alvo = partes?.find((x) => x.id === v);
                  setFormC({ ...formC, party_id: v, party_name: alvo?.name || "" });
                }}
              >
                <SelectTrigger
                  className="bg-slate-800 border-slate-700"
                  data-testid="contract-party-select"
                >
                  <SelectValue placeholder="Selecione" />
                </SelectTrigger>
                <SelectContent>
                  {(partes || []).map((x) => (
                    <SelectItem key={x.id} value={x.id}>
                      {x.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Regra</Label>
              <Select
                value={formC.rule_type}
                onValueChange={(v) => setFormC({ ...formC, rule_type: v })}
              >
                <SelectTrigger className="bg-slate-800 border-slate-700">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="comissao_entrega">Comissão por entrega (%)</SelectItem>
                  <SelectItem value="valor_km">Valor por KM (R$)</SelectItem>
                  <SelectItem value="taxa_fixa">Taxa fixa mensal (R$)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="c-valor">
                Valor {formC.rule_type === "comissao_entrega" ? "(%)" : "(R$)"}
              </Label>
              <Input
                id="c-valor"
                type="number"
                min="0"
                max={formC.rule_type === "comissao_entrega" ? 100 : undefined}
                step="0.01"
                data-testid="contract-value-input"
                value={formC.value}
                onChange={(e) => setFormC({ ...formC, value: parseFloat(e.target.value) || 0 })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Status</Label>
              <Select value={formC.status} onValueChange={(v) => setFormC({ ...formC, status: v })}>
                <SelectTrigger className="bg-slate-800 border-slate-700">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ativo">Ativo</SelectItem>
                  <SelectItem value="suspenso">Suspenso</SelectItem>
                  <SelectItem value="encerrado">Encerrado</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="c-obs">Observações</Label>
              <Textarea
                id="c-obs"
                rows={2}
                value={formC.notes}
                onChange={(e) => setFormC({ ...formC, notes: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAbertoC(false)} className="text-slate-400">
              Cancelar
            </Button>
            <Button
              onClick={() => salvarC.mutate(formC)}
              disabled={!formC.party_name || salvarC.isPending}
              data-testid="save-contract-button"
              className="bg-primary hover:bg-orange-600 text-white"
            >
              {salvarC.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "Salvar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
