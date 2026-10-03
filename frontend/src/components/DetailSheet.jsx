import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ClipboardList, Mail, MapPin, MessageSquare, Package, Phone, Plus, Star, Users, StickyNote,
} from "lucide-react";
import { api, apiError, brl, dataHora, getList } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState, Loading, Panel } from "@/components/Ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const ROTULO_CONTA = { corrente: "Corrente", poupanca: "Poupança" };
const ROTULO_PIX = {
  cpf: "CPF",
  celular: "Celular",
  email: "E-mail",
  aleatoria: "Aleatória",
};

const ICONE = {
  ligacao: Phone,
  whatsapp: MessageSquare,
  email: Mail,
  reuniao: Users,
  visita: MapPin,
  nota: StickyNote,
  tarefa: ClipboardList,
};

export function DetailSheet({ open, onOpenChange, type, entity }) {
  const qc = useQueryClient();
  const [tipo, setTipo] = useState("ligacao");
  const [texto, setTexto] = useState("");

  const filtro = type === "restaurante" ? "restaurant_id" : "driver_id";

  const { data: pedidos, isLoading: carregandoPedidos } = useQuery({
    queryKey: ["orders", type, entity?.id],
    queryFn: () => getList("/orders", { [filtro]: entity.id, page_size: 50 }),
    enabled: open && !!entity?.id,
  });

  // Linha do tempo real, vinda do servidor: interações registradas pela equipe
  // mais as alterações de cadastro. A versão anterior mostrava uma lista fixa de
  // documentos que não existia no banco e era igual para todo mundo.
  const { data: timeline, isLoading: carregandoTimeline } = useQuery({
    queryKey: ["timeline", type, entity?.id],
    queryFn: async () => (await api.get(`/timeline/${type}/${entity.id}`)).data,
    enabled: open && !!entity?.id,
  });

  const registrar = useMutation({
    mutationFn: () =>
      api.post("/activities", {
        kind: "interacao",
        type: tipo,
        title: texto.trim(),
        due_at: new Date().toISOString(),
        related_type: type,
        related_id: entity.id,
        related_name: entity.name,
        done: true,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["timeline", type, entity.id] });
      qc.invalidateQueries({ queryKey: ["activities"] });
      setTexto("");
      toast.success("Interação registrada");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  if (!entity) return null;

  const historico = pedidos?.items || [];
  const eventos = timeline?.eventos || [];
  const entregues = historico.filter((o) => o.status === "entregue");

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        className="bg-[#0C0D0F] border-slate-800 text-slate-100 w-full sm:max-w-lg overflow-y-auto"
        data-testid="detail-sheet"
      >
        <SheetHeader>
          <SheetTitle className="text-slate-50 font-heading flex items-center gap-3">
            {type === "entregador" && entity.photo ? (
              <img src={entity.photo} alt="" className="w-11 h-11 rounded-full object-cover" />
            ) : (
              <div className="w-11 h-11 rounded-full bg-primary/20 text-primary flex items-center justify-center font-bold shrink-0">
                {(entity.name || "?")
                  .split(" ")
                  .map((w) => w[0])
                  .slice(0, 2)
                  .join("")
                  .toUpperCase()}
              </div>
            )}
            <div className="min-w-0 text-left">
              <p className="truncate">{entity.name}</p>
              <p className="text-xs font-normal text-slate-500">
                {type === "restaurante"
                  ? entity.category
                  : (entity.vehicle_type || "").toUpperCase()}
              </p>
            </div>
          </SheetTitle>
        </SheetHeader>

        <div className="mt-6 space-y-6">
          <Panel className="p-4 space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-slate-500">Status</span>
              <StatusBadge status={entity.status} />
            </div>
            {entity.phone && (
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Telefone</span>
                <a href={`tel:${entity.phone}`} className="text-slate-200 hover:text-primary">
                  {entity.phone}
                </a>
              </div>
            )}
            {entity.email && (
              <div className="flex items-center justify-between gap-2">
                <span className="text-slate-500">E-mail</span>
                <a
                  href={`mailto:${entity.email}`}
                  className="text-slate-200 hover:text-primary truncate"
                >
                  {entity.email}
                </a>
              </div>
            )}
            {type === "restaurante" && (
              <>
                <div className="flex items-start justify-between gap-3">
                  <span className="text-slate-500 shrink-0">Endereço</span>
                  <span className="text-slate-200 text-right">{entity.address || "—"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">CNPJ</span>
                  <span className="text-slate-200 font-mono text-xs">{entity.cnpj || "—"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Comissão</span>
                  <span className="text-slate-200">{entity.commission_rate}%</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Comissão a receber</span>
                  <span className="text-emerald-400 font-semibold">
                    {brl(entity.commission_due)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Pedidos no mês / total</span>
                  <span className="text-slate-200">
                    {entity.orders_month ?? 0} / {entity.orders_total ?? 0}
                  </span>
                </div>
              </>
            )}
            {type === "entregador" && (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Avaliação</span>
                  <span className="text-amber-400 flex items-center gap-1">
                    <Star className="w-3.5 h-3.5 fill-amber-400" aria-hidden="true" />
                    {entity.rating}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Entregas concluídas</span>
                  <span className="text-slate-200">{entity.total_deliveries}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Saldo a receber</span>
                  <span className="text-emerald-400 font-semibold">{brl(entity.balance_due)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Já repassado</span>
                  <span className="text-slate-300">{brl(entity.paid_total)}</span>
                </div>
                {entity.cpf && (
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">CPF</span>
                    <span className="font-mono text-xs text-slate-200">{entity.cpf}</span>
                  </div>
                )}
              </>
            )}
          </Panel>

          {/* Dados de pagamento — é com eles que o repasse sai. Só aparecem
              para quem está autenticado no painel. */}
          {type === "entregador" && (entity.pix_key || entity.bank) && (
            <Panel className="p-4 space-y-2 text-sm">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Dados de pagamento
              </h4>
              {entity.bank && (
                <div className="flex items-center justify-between gap-2">
                  <span className="text-slate-500">Banco</span>
                  <span className="text-slate-200 text-right">{entity.bank}</span>
                </div>
              )}
              {entity.bank_agency && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Agência</span>
                  <span className="font-mono text-xs text-slate-200">{entity.bank_agency}</span>
                </div>
              )}
              {entity.bank_account && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Conta</span>
                  <span className="font-mono text-xs text-slate-200">
                    {entity.bank_account}
                    {entity.account_type && ` (${ROTULO_CONTA[entity.account_type] || ""})`}
                  </span>
                </div>
              )}
              {entity.pix_key && (
                <div className="flex items-start justify-between gap-2">
                  <span className="shrink-0 text-slate-500">
                    PIX{entity.pix_key_type ? ` (${ROTULO_PIX[entity.pix_key_type] || ""})` : ""}
                  </span>
                  <span className="break-all text-right font-mono text-xs text-keeta-light">
                    {entity.pix_key}
                  </span>
                </div>
              )}
            </Panel>
          )}

          {/* Registrar interação em um passo */}
          <div className="space-y-2">
            <Label className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Registrar interação
            </Label>
            <div className="flex gap-2">
              <Select value={tipo} onValueChange={setTipo}>
                <SelectTrigger
                  className="w-32 bg-slate-900 border-slate-800 text-xs shrink-0"
                  aria-label="Tipo de interação"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ligacao">Ligação</SelectItem>
                  <SelectItem value="whatsapp">WhatsApp</SelectItem>
                  <SelectItem value="email">E-mail</SelectItem>
                  <SelectItem value="reuniao">Reunião</SelectItem>
                  <SelectItem value="visita">Visita</SelectItem>
                  <SelectItem value="nota">Nota</SelectItem>
                </SelectContent>
              </Select>
              <Input
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && texto.trim()) registrar.mutate();
                }}
                placeholder="O que aconteceu?"
                aria-label="Descrição da interação"
                data-testid="detail-interaction-input"
                className="bg-slate-900 border-slate-800 text-sm"
              />
              <Button
                size="icon"
                onClick={() => registrar.mutate()}
                disabled={!texto.trim() || registrar.isPending}
                aria-label="Registrar interação"
                data-testid="detail-interaction-save"
                className="bg-primary hover:bg-orange-600 text-white shrink-0"
              >
                <Plus className="w-4 h-4" />
              </Button>
            </div>
          </div>

          <Tabs defaultValue="timeline">
            <TabsList className="bg-slate-900 border border-slate-800 w-full">
              <TabsTrigger value="timeline" className="flex-1 text-xs">
                Linha do tempo
              </TabsTrigger>
              <TabsTrigger value="pedidos" className="flex-1 text-xs">
                Pedidos ({historico.length})
              </TabsTrigger>
            </TabsList>

            <TabsContent value="timeline" className="mt-4">
              {carregandoTimeline ? (
                <Loading className="py-8" />
              ) : !eventos.length ? (
                <EmptyState
                  icon={ClipboardList}
                  titulo="Nada registrado ainda"
                  descricao="Use o campo acima para guardar o histórico de contato."
                />
              ) : (
                <ol className="space-y-3">
                  {eventos.map((ev) => {
                    const Icon = ICONE[ev.tipo] || ClipboardList;
                    const doSistema = ev.origem === "sistema";
                    return (
                      <li key={ev.id} className="flex gap-3" data-testid={`timeline-${ev.id}`}>
                        <div
                          className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${
                            doSistema ? "bg-slate-800 text-slate-500" : "bg-primary/15 text-primary"
                          }`}
                        >
                          <Icon className="w-3.5 h-3.5" aria-hidden="true" />
                        </div>
                        <div className="min-w-0 flex-1 pb-3 border-b border-slate-800/60">
                          <p className="text-sm text-slate-200 break-words">{ev.titulo}</p>
                          {typeof ev.detalhe === "string" && ev.detalhe && (
                            <p className="text-xs text-slate-500 mt-0.5">{ev.detalhe}</p>
                          )}
                          {doSistema && ev.detalhe && typeof ev.detalhe === "object" && (
                            <p className="text-xs text-slate-600 mt-0.5">
                              {Object.keys(ev.detalhe).slice(0, 4).join(", ") || "sem alterações"}
                            </p>
                          )}
                          <p className="text-[11px] text-slate-600 mt-1">
                            {dataHora(ev.at)}
                            {ev.autor ? ` • ${ev.autor}` : ""}
                          </p>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              )}
            </TabsContent>

            <TabsContent value="pedidos" className="mt-4">
              {carregandoPedidos ? (
                <Loading className="py-8" />
              ) : !historico.length ? (
                <EmptyState icon={Package} titulo="Nenhum pedido registrado" />
              ) : (
                <>
                  <p className="text-xs text-slate-500 mb-3">
                    {entregues.length} entregue(s) •{" "}
                    {brl(entregues.reduce((s, o) => s + (o.amount || 0), 0))} em valor
                  </p>
                  <ul className="space-y-2">
                    {historico.map((o) => (
                      <li
                        key={o.id}
                        className="flex items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-900 px-4 py-2.5"
                        data-testid={`history-row-${o.id}`}
                      >
                        <div className="min-w-0">
                          <p className="font-mono text-xs font-semibold text-primary">{o.code}</p>
                          <p className="text-xs text-slate-500 truncate">
                            {type === "restaurante" ? o.customer_name : o.restaurant_name}
                          </p>
                        </div>
                        <div className="text-right shrink-0">
                          <p className="text-sm text-slate-200">{brl(o.amount)}</p>
                          <StatusBadge status={o.status} />
                        </div>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </SheetContent>
    </Sheet>
  );
}
