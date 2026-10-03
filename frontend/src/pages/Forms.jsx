import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowDown, ArrowUp, Check, ClipboardList, Copy, ExternalLink, Eye, FileInput,
  Loader2, Plus, RotateCcw, Trash2, X,
} from "lucide-react";
import { api, apiError, dataHora, getList } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { EmptyState, IconButton, Loading, MetricCard, Panel } from "@/components/Ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

const DESTINOS = [
  { valor: "lead", label: "Lead (funil comercial)" },
  { valor: "restaurante", label: "Restaurante" },
  { valor: "entregador", label: "Entregador" },
];

const TIPOS = [
  ["texto", "Texto"],
  ["email", "E-mail"],
  ["telefone", "Telefone"],
  ["cpf", "CPF"],
  ["numero", "Número"],
  ["data", "Data"],
  ["escolha", "Múltipla escolha"],
  ["selecao", "Lista suspensa"],
  ["textarea", "Texto longo"],
];

// Lista suspensa e múltipla escolha precisam de opções; o resto, não.
const TEM_OPCOES = new Set(["selecao", "escolha"]);

const CAMPO_NOVO = () => ({
  key: "",
  label: "",
  type: "texto",
  required: false,
  placeholder: "",
  help: "",
  options: [],
  allow_other: false,
});

const VAZIO = () => ({
  title: "",
  description: "",
  target: "entregador",
  success_message: "",
  active: true,
  fields: [{ ...CAMPO_NOVO(), key: "name", label: "Nome", required: true }],
});

/** Rótulo vira chave: "Nome do Restaurante" -> "nome_do_restaurante". */
const chaveDoRotulo = (rotulo) =>
  rotulo
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/^[^a-z]+/, "")
    .slice(0, 40) || "campo";

export default function Forms() {
  const qc = useQueryClient();
  const confirmar = useConfirm();
  const { isAdmin } = useAuth();
  const [aberto, setAberto] = useState(false);
  const [form, setForm] = useState(VAZIO);
  const [editId, setEditId] = useState(null);
  const [respostasDe, setRespostasDe] = useState(null);
  const [copiado, setCopiado] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["forms"],
    queryFn: () => getList("/forms", { page_size: 100 }),
  });

  /* Modelos padrão vêm do backend — mesma fonte da carga inicial. Duplicar as
     perguntas aqui em JavaScript faria os dois lados desandarem no primeiro
     ajuste que alguém fizesse de um lado só. */
  const { data: modelos } = useQuery({
    queryKey: ["form-templates"],
    queryFn: async () => (await api.get("/forms/templates")).data,
    staleTime: Infinity,
  });

  /** Cópia do modelo do destino. Sem clonar, editar um campo mexeria no cache. */
  const doModelo = (destino) => {
    const m = modelos?.[destino];
    if (!m) return { ...VAZIO(), target: destino };
    return {
      title: m.title,
      description: m.description,
      target: destino,
      success_message: m.success_message,
      active: true,
      fields: m.fields.map((c) => ({ ...c, options: [...(c.options || [])] })),
    };
  };

  const abrirNovo = () => {
    setForm(doModelo("entregador"));
    setEditId(null);
    setAberto(true);
  };

  // Pedido de exclusão (LGPD): a resposta guarda CPF, conta e chave PIX, e
  // apagar só o cadastro no CRM deixava essa cópia para trás.
  const excluirResposta = useMutation({
    mutationFn: ({ formId, id }) => api.delete(`/forms/${formId}/submissions/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["form-submissions"] });
      qc.invalidateQueries({ queryKey: ["forms"] });
      toast.success("Resposta removida");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const { data: respostas } = useQuery({
    queryKey: ["form-submissions", respostasDe?.id],
    queryFn: () => getList(`/forms/${respostasDe.id}/submissions`, { page_size: 100 }),
    enabled: !!respostasDe,
  });

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["forms"] });
    qc.invalidateQueries({ queryKey: ["restaurants"] });
    qc.invalidateQueries({ queryKey: ["drivers"] });
    qc.invalidateQueries({ queryKey: ["leads"] });
  };

  const salvar = useMutation({
    mutationFn: (p) => (editId ? api.put(`/forms/${editId}`, p) : api.post("/forms", p)),
    onSuccess: () => {
      invalidar();
      toast.success(editId ? "Formulário atualizado" : "Formulário criado");
      setAberto(false);
      setForm(VAZIO());
      setEditId(null);
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const alternar = useMutation({
    mutationFn: ({ id, active }) => api.patch(`/forms/${id}/active`, { active }),
    onSuccess: () => invalidar(),
    onError: (e) => toast.error(apiError(e)),
  });

  const excluir = useMutation({
    mutationFn: ({ id, force }) => api.delete(`/forms/${id}`, { params: force ? { force: true } : {} }),
    onSuccess: () => {
      invalidar();
      toast.success("Formulário removido");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  /**
   * Exclui o formulário, com a segunda confirmação quando há histórico.
   *
   * O 409 do backend é proteção contra engano, não um não definitivo: ele
   * existe para a pessoa parar e pensar. Sem este segundo passo, formulário
   * com resposta não saía da tela de jeito nenhum.
   */
  const excluirFormulario = async (f) => {
    const ok = await confirmar({
      titulo: `Excluir "${f.title}"?`,
      descricao: "O link para de funcionar imediatamente.",
      confirmar: "Excluir",
    });
    if (!ok) return;

    try {
      await excluir.mutateAsync({ id: f.id, force: false });
      return;
    } catch (e) {
      if (e?.response?.status !== 409) return;
    }

    const quantas = f.submissions_count || 0;
    const mesmoAssim = await confirmar({
      titulo: "Apagar também as respostas?",
      descricao:
        `Este formulário guarda ${quantas} resposta(s), com o que cada pessoa preencheu — ` +
        "CPF e dados bancários inclusive. Os cadastros já criados continuam no CRM; " +
        "só o histórico do formulário se perde, e não dá para desfazer.",
      confirmar: "Apagar tudo",
    });
    if (mesmoAssim) excluir.mutate({ id: f.id, force: true });
  };

  const linkDe = (slug) => `${window.location.origin}/f/${slug}`;

  const copiarLink = async (slug) => {
    try {
      await navigator.clipboard.writeText(linkDe(slug));
      setCopiado(slug);
      setTimeout(() => setCopiado(""), 2000);
      toast.success("Link copiado — já pode mandar no WhatsApp");
    } catch {
      toast.error("Não foi possível copiar automaticamente");
    }
  };

  // ------------------------------------------------------------ construtor
  const mudarCampo = (i, patch) =>
    setForm((f) => ({
      ...f,
      fields: f.fields.map((c, idx) => (idx === i ? { ...c, ...patch } : c)),
    }));

  const addCampo = (preset) => {
    setForm((f) => ({
      ...f,
      fields: [
        ...f.fields,
        preset
          ? { ...preset, options: [...(preset.options || [])] }
          : { ...CAMPO_NOVO(), key: `campo_${f.fields.length + 1}` },
      ],
    }));
  };

  /** Repõe as perguntas do modelo, mantendo o que já foi digitado no topo. */
  const aplicarModelo = async () => {
    const m = modelos?.[form.target];
    if (!m) return;
    if (form.fields.length) {
      const ok = await confirmar({
        titulo: "Repor as perguntas padrão?",
        descricao: "Os campos atuais deste formulário serão substituídos pelos do modelo.",
        confirmar: "Repor",
      });
      if (!ok) return;
    }
    setForm((f) => ({
      ...f,
      fields: m.fields.map((c) => ({ ...c, options: [...(c.options || [])] })),
      success_message: f.success_message || m.success_message,
    }));
  };

  const removerCampo = (i) =>
    setForm((f) => ({ ...f, fields: f.fields.filter((_, idx) => idx !== i) }));

  const moverCampo = (i, delta) =>
    setForm((f) => {
      const destino = i + delta;
      if (destino < 0 || destino >= f.fields.length) return f;
      const copia = [...f.fields];
      [copia[i], copia[destino]] = [copia[destino], copia[i]];
      return { ...f, fields: copia };
    });

  const usados = useMemo(() => new Set(form.fields.map((c) => c.key)), [form.fields]);
  // Perguntas do modelo que foram removidas — ficam à mão para repor uma a uma.
  const prontosDisponiveis = (modelos?.[form.target]?.fields || []).filter(
    (c) => !usados.has(c.key),
  );
  const temNome = usados.has("name");
  const rotulosOk = form.fields.every((c) => c.label.trim());
  const podeSalvar = form.title.trim() && temNome && rotulosOk && form.fields.length > 0;

  const itens = data?.items || [];
  const totalRespostas = itens.reduce((s, f) => s + (f.submissions_count || 0), 0);

  return (
    <div className="space-y-6 animate-fade-up" data-testid="forms-page">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-6">
        <MetricCard icon={FileInput} label="Formulários" value={itens.length} />
        <MetricCard
          icon={Check}
          label="Ativos"
          value={itens.filter((f) => f.active).length}
          tone="text-emerald-400"
        />
        <MetricCard
          icon={ClipboardList}
          label="Cadastros recebidos"
          value={totalRespostas}
          tone="text-primary"
        />
        <MetricCard
          icon={Eye}
          label="Mais usado"
          value={
            itens.length
              ? [...itens].sort((a, b) => (b.submissions_count || 0) - (a.submissions_count || 0))[0]
                  ?.submissions_count || 0
              : 0
          }
          hint={itens.length ? [...itens].sort((a, b) => (b.submissions_count || 0) - (a.submissions_count || 0))[0]?.title : ""}
        />
      </div>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="text-sm text-slate-500 max-w-2xl">
          Monte o formulário, copie o link e mande para quem vai se cadastrar. A resposta
          entra direto no CRM — restaurantes e entregadores chegam{" "}
          <strong className="text-slate-300">em análise</strong>, para a equipe conferir antes
          de ativar.
        </p>
        <Button
          onClick={abrirNovo}
          data-testid="btn-novo-formulario"
          className="bg-primary hover:bg-orange-600 text-slate-950 font-semibold gap-2"
        >
          <Plus className="w-4 h-4" /> Novo Formulário
        </Button>
      </div>

      {isLoading ? (
        <Loading />
      ) : itens.length === 0 ? (
        <Panel>
          <EmptyState
            icon={FileInput}
            titulo="Nenhum formulário criado"
            descricao="Um formulário público evita digitar cadastro por cadastro: quem quer entrar na rede preenche sozinho."
            acao={
              <Button
                onClick={abrirNovo}
                className="bg-primary hover:bg-orange-600 text-slate-950 font-semibold gap-2"
              >
                <Plus className="w-4 h-4" /> Criar o primeiro
              </Button>
            }
          />
        </Panel>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {itens.map((f, i) => (
            <Panel key={f.id} data-testid={`form-card-${i}`} className="p-5 space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold text-slate-100 truncate">{f.title}</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {DESTINOS.find((d) => d.valor === f.target)?.label} • {f.fields.length} campos
                    {" • "}
                    <span className="text-primary font-semibold">
                      {f.submissions_count || 0} recebido(s)
                    </span>
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Switch
                    checked={f.active}
                    onCheckedChange={(v) => alternar.mutate({ id: f.id, active: v })}
                    aria-label={`${f.active ? "Desativar" : "Ativar"} ${f.title}`}
                    data-testid={`toggle-form-${i}`}
                  />
                </div>
              </div>

              <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2">
                <code className="flex-1 min-w-0 truncate font-mono text-xs text-slate-400">
                  /f/{f.slug}
                </code>
                <IconButton
                  icon={copiado === f.slug ? Check : Copy}
                  label={`Copiar link de ${f.title}`}
                  tone={copiado === f.slug ? "text-emerald-400" : "hover:text-primary"}
                  data-testid={`copy-form-link-${i}`}
                  onClick={() => copiarLink(f.slug)}
                />
                <IconButton
                  icon={ExternalLink}
                  label={`Abrir ${f.title} em nova aba`}
                  data-testid={`open-form-${i}`}
                  onClick={() => window.open(linkDe(f.slug), "_blank", "noopener")}
                />
              </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setRespostasDe(f)}
                  data-testid={`view-submissions-${i}`}
                  className="border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800 gap-1.5 h-8"
                >
                  <ClipboardList className="w-3.5 h-3.5" /> Respostas
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setForm({ ...VAZIO(), ...f });
                    setEditId(f.id);
                    setAberto(true);
                  }}
                  data-testid={`edit-form-${i}`}
                  className="h-8 text-slate-400 hover:text-primary"
                >
                  Editar
                </Button>
                {isAdmin && (
                  <IconButton
                    icon={Trash2}
                    label={`Excluir ${f.title}`}
                    tone="hover:text-red-400"
                    data-testid={`delete-form-${i}`}
                    onClick={() => excluirFormulario(f)}
                  />
                )}
              </div>
            </Panel>
          ))}
        </div>
      )}

      {/* ----------------------------------------------------- construtor */}
      <Dialog open={aberto} onOpenChange={setAberto}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100 max-w-3xl max-h-[92vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading">
              {editId ? "Editar Formulário" : "Novo Formulário"}
            </DialogTitle>
            <DialogDescription className="text-slate-500">
              As perguntas já vêm no modelo padrão do sistema. Edite, remova,
              reordene ou acrescente o que quiser — nada aqui é fixo.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-5 py-2">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="sm:col-span-2 space-y-1.5">
                <Label htmlFor="fm-titulo">Título *</Label>
                <Input
                  id="fm-titulo"
                  data-testid="form-title-input"
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  placeholder="Cadastro de Restaurantes Parceiros"
                  className="bg-slate-800 border-slate-700"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Alimenta</Label>
                <Select
                  value={form.target}
                  // Em formulário novo, trocar o destino troca o modelo: quem
                  // muda para "entregador" quer as perguntas de entregador.
                  onValueChange={(v) => setForm(editId ? { ...form, target: v } : doModelo(v))}
                  disabled={!!editId}
                >
                  <SelectTrigger className="bg-slate-800 border-slate-700" data-testid="form-target">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DESTINOS.map((d) => (
                      <SelectItem key={d.valor} value={d.valor}>
                        {d.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {editId && (
                  <p className="text-[11px] text-slate-600">
                    O destino não muda depois que o formulário existe.
                  </p>
                )}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="fm-desc">Descrição</Label>
              <Textarea
                id="fm-desc"
                rows={2}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="Explique em uma frase para que serve o cadastro."
                className="bg-slate-800 border-slate-700"
              />
            </div>

            {/* Campos */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label>Campos do formulário</Label>
                <span className="text-xs text-slate-600">{form.fields.length} campo(s)</span>
              </div>

              {!temNome && (
                <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
                  Falta um campo com a chave <code className="font-mono">name</code>. É por ele
                  que o cadastro recebe um nome.
                </p>
              )}

              <div className="space-y-2">
                {form.fields.map((campo, i) => (
                  <div
                    key={i}
                    data-testid={`form-field-${i}`}
                    className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 space-y-3"
                  >
                    <div className="flex items-start gap-2">
                      <div className="flex flex-col gap-0.5 pt-1">
                        <IconButton
                          icon={ArrowUp}
                          label={`Mover "${campo.label || "campo"}" para cima`}
                          disabled={i === 0}
                          onClick={() => moverCampo(i, -1)}
                          className="h-6 w-6"
                        />
                        <IconButton
                          icon={ArrowDown}
                          label={`Mover "${campo.label || "campo"}" para baixo`}
                          disabled={i === form.fields.length - 1}
                          onClick={() => moverCampo(i, 1)}
                          className="h-6 w-6"
                        />
                      </div>

                      <div className="flex-1 grid grid-cols-1 sm:grid-cols-12 gap-2">
                        <div className="sm:col-span-5 space-y-1">
                          <Label className="text-[11px] text-slate-500">Rótulo *</Label>
                          <Input
                            value={campo.label}
                            data-testid={`field-label-${i}`}
                            onChange={(e) => {
                              const label = e.target.value;
                              // A chave acompanha o rótulo enquanto o usuário não
                              // a edita à mão — ninguém deveria precisar pensar
                              // em nome de variável para montar um formulário.
                              const auto = chaveDoRotulo(campo.label) === campo.key;
                              mudarCampo(i, auto ? { label, key: chaveDoRotulo(label) } : { label });
                            }}
                            className="h-9 bg-slate-800 border-slate-700"
                          />
                        </div>
                        <div className="sm:col-span-3 space-y-1">
                          <Label className="text-[11px] text-slate-500">Tipo</Label>
                          <Select
                            value={campo.type}
                            onValueChange={(v) => mudarCampo(i, { type: v })}
                          >
                            <SelectTrigger className="h-9 bg-slate-800 border-slate-700 text-xs">
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
                        <div className="sm:col-span-3 space-y-1">
                          <Label className="text-[11px] text-slate-500">Chave</Label>
                          <Input
                            value={campo.key}
                            onChange={(e) => mudarCampo(i, { key: e.target.value })}
                            className="h-9 bg-slate-800 border-slate-700 font-mono text-xs"
                          />
                        </div>
                        <div className="sm:col-span-1 flex items-end justify-end pb-1">
                          <IconButton
                            icon={X}
                            label={`Remover campo "${campo.label || i + 1}"`}
                            tone="hover:text-red-400"
                            data-testid={`remove-field-${i}`}
                            onClick={() => removerCampo(i)}
                          />
                        </div>
                      </div>
                    </div>

                    <div className="pl-8">
                      <Input
                        value={campo.help || ""}
                        onChange={(e) => mudarCampo(i, { help: e.target.value })}
                        placeholder="Instrução para quem preenche (opcional)"
                        aria-label={`Instrução de "${campo.label || "campo"}"`}
                        data-testid={`field-help-${i}`}
                        className="h-8 bg-slate-800 border-slate-700 text-xs"
                      />
                    </div>

                    <div className="flex flex-wrap items-center gap-4 pl-8">
                      <label className="flex items-center gap-2 text-xs text-slate-400">
                        <Switch
                          checked={campo.required}
                          onCheckedChange={(v) => mudarCampo(i, { required: v })}
                          aria-label={`Tornar "${campo.label || "campo"}" obrigatório`}
                        />
                        Obrigatório
                      </label>
                      {TEM_OPCOES.has(campo.type) && (
                        <label className="flex items-center gap-2 text-xs text-slate-400">
                          <Switch
                            checked={!!campo.allow_other}
                            onCheckedChange={(v) => mudarCampo(i, { allow_other: v })}
                            aria-label={`Permitir "Outro" em "${campo.label || "campo"}"`}
                          />
                          Permitir &ldquo;Outro&rdquo;
                        </label>
                      )}
                      {TEM_OPCOES.has(campo.type) && (
                        <div className="flex-1 min-w-[220px]">
                          <Input
                            value={(campo.options || []).join(", ")}
                            onChange={(e) =>
                              mudarCampo(i, {
                                options: e.target.value
                                  .split(",")
                                  .map((o) => o.trim())
                                  .filter(Boolean),
                              })
                            }
                            placeholder="Opções separadas por vírgula"
                            aria-label={`Opções de "${campo.label || "campo"}"`}
                            className="h-8 bg-slate-800 border-slate-700 text-xs"
                          />
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap gap-2 pt-1">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => addCampo(null)}
                  data-testid="add-field"
                  className="border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800 gap-1.5 h-8"
                >
                  <Plus className="w-3.5 h-3.5" /> Campo livre
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={aplicarModelo}
                  data-testid="apply-template"
                  className="h-8 gap-1.5 border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800"
                >
                  <RotateCcw className="w-3.5 h-3.5" /> Repor modelo padrão
                </Button>
                {prontosDisponiveis.map((p) => (
                  <Button
                    key={p.key}
                    size="sm"
                    variant="ghost"
                    onClick={() => addCampo(p)}
                    data-testid={`add-preset-${p.key}`}
                    className="h-8 border border-dashed border-slate-800 text-xs text-slate-400 hover:text-primary"
                  >
                    + {p.label}
                  </Button>
                ))}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="fm-ok">Mensagem depois do envio</Label>
              <Input
                id="fm-ok"
                value={form.success_message}
                onChange={(e) => setForm({ ...form, success_message: e.target.value })}
                placeholder="Recebemos seu cadastro! Em breve entramos em contato."
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
              disabled={!podeSalvar || salvar.isPending}
              data-testid="save-form-button"
              className="bg-primary hover:bg-orange-600 text-slate-950 font-semibold"
            >
              {salvar.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "Salvar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ------------------------------------------------------ respostas */}
      <Dialog open={!!respostasDe} onOpenChange={(v) => !v && setRespostasDe(null)}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100 max-w-4xl max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading">{respostasDe?.title}</DialogTitle>
            <DialogDescription className="text-slate-500">
              Cada resposta virou um cadastro no CRM.
            </DialogDescription>
          </DialogHeader>

          {!respostas ? (
            <Loading className="py-10" />
          ) : !respostas.items.length ? (
            <EmptyState
              icon={ClipboardList}
              titulo="Nenhuma resposta ainda"
              descricao="Compartilhe o link para começar a receber cadastros."
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="border-slate-800 hover:bg-transparent">
                    <TableHead className="text-slate-400">Cadastro</TableHead>
                    <TableHead className="text-slate-400">Respostas</TableHead>
                    <TableHead className="text-slate-400">Recebido</TableHead>
                    {isAdmin && <TableHead className="text-slate-400 text-right">Ações</TableHead>}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {respostas.items.map((s, i) => (
                    <TableRow
                      key={s.id}
                      className="border-slate-800 hover:bg-slate-800/40"
                      data-testid={`submission-row-${i}`}
                    >
                      <TableCell className="font-medium text-slate-100 align-top">
                        {s.record_name}
                      </TableCell>
                      <TableCell className="text-slate-400 text-xs">
                        <ul className="space-y-0.5">
                          {Object.entries(s.answers || {})
                            .filter(([, v]) => v !== "" && v !== null)
                            .map(([k, v]) => (
                              <li key={k}>
                                <span className="text-slate-600">{k}:</span> {String(v)}
                              </li>
                            ))}
                        </ul>
                      </TableCell>
                      <TableCell className="text-slate-400 text-xs align-top whitespace-nowrap">
                        {dataHora(s.created_at)}
                        {s.consentimento?.aceito && (
                          <p className="mt-1 text-[11px] text-emerald-600">
                            aviso de privacidade aceito
                          </p>
                        )}
                      </TableCell>
                      {isAdmin && (
                        <TableCell className="text-right align-top">
                          <IconButton
                            icon={Trash2}
                            label={`Excluir resposta de ${s.record_name}`}
                            tone="hover:text-red-400"
                            data-testid={`delete-submission-${i}`}
                            onClick={async () => {
                              const ok = await confirmar({
                                titulo: "Excluir esta resposta?",
                                descricao:
                                  `Apaga o que ${s.record_name} preencheu, incluindo CPF e dados ` +
                                  "bancários. O cadastro gerado no CRM continua — apague-o na " +
                                  "tela dele, se for o caso.",
                                confirmar: "Excluir",
                              });
                              if (ok) excluirResposta.mutate({ formId: respostasDe.id, id: s.id });
                            }}
                          />
                        </TableCell>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
