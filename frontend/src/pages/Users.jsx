import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Check, Copy, Eye, EyeOff, KeyRound, LayoutGrid, Loader2, Pencil, Plus, ShieldCheck, Sparkles,
  Trash2, UserCog, Users2,
} from "lucide-react";
import { api, apiError, dataHora } from "@/lib/api";
import { MODULOS, TODAS } from "@/lib/permissoes";
import { useAuth } from "@/context/AuthContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { EmptyState, IconButton, Loading, Panel } from "@/components/Ui";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

// Conta nova começa SEM tela nenhuma marcada: liberar é decisão consciente do
// administrador, não um padrão que esquece de restringir.
const VAZIO = { name: "", email: "", password: "", role: "manager", permissoes: [] };
const MIN_SENHA = 8;

// Sem caracteres que se confundem ao ditar ou ler no WhatsApp (0/O, 1/l/I).
const ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789";
const SIMBOLOS = "!@#$%&*";

function gerarSenha(tamanho = 14) {
  const sorteio = new Uint32Array(tamanho);
  crypto.getRandomValues(sorteio);
  const letras = Array.from(sorteio, (n) => ALFABETO[n % ALFABETO.length]);
  // Um símbolo e um número garantidos, em posições sorteadas: há sistema de
  // senha corporativo que recusa senha só de letras.
  const [p1, p2] = [sorteio[0] % tamanho, (sorteio[1] % (tamanho - 1)) + 1];
  letras[p1] = SIMBOLOS[sorteio[2] % SIMBOLOS.length];
  letras[p2 === p1 ? (p1 + 1) % tamanho : p2] = String(2 + (sorteio[3] % 8));
  return letras.join("");
}

async function copiarTexto(texto, rotulo) {
  try {
    await navigator.clipboard.writeText(texto);
    toast.success(`${rotulo} copiad${rotulo.endsWith("a") ? "a" : "o"}`);
    return true;
  } catch {
    // Área de transferência bloqueada (http sem TLS, permissão negada): o
    // valor fica visível na tela para seleção manual.
    toast.error("Copie manualmente.");
    return false;
  }
}

/** Resumo do acesso na tabela: "Tudo", "Nenhuma tela" ou os nomes. */
function ResumoAcesso({ u }) {
  if (u.role === "admin" || u.permissoes == null) {
    return (
      <span className="text-xs text-slate-300">
        {u.role === "admin" ? "Tudo (administrador)" : "Todas as telas"}
      </span>
    );
  }
  if (!u.modulos?.length) {
    return <span className="text-xs text-red-400">Nenhuma tela</span>;
  }
  const nomes = MODULOS.filter((m) => u.modulos.includes(m.chave)).map((m) => m.rotulo);
  return (
    <span className="text-xs text-slate-400" title={nomes.join(", ")}>
      {nomes.length <= 3 ? nomes.join(", ") : `${nomes.slice(0, 3).join(", ")} +${nomes.length - 3}`}
    </span>
  );
}

export default function Users() {
  const qc = useQueryClient();
  const confirmar = useConfirm();
  const { user: eu } = useAuth();
  const [aberto, setAberto] = useState(false);
  const [form, setForm] = useState(VAZIO);
  const [editId, setEditId] = useState(null);
  const [verSenha, setVerSenha] = useState(false);
  // Senha recém-definida, mostrada uma vez para o administrador entregar. O
  // banco guarda só o hash: depois de fechar esta janela, ninguém a recupera.
  const [senhaDefinida, setSenhaDefinida] = useState(null);
  // Link de redefinição recém-gerado. Mesmo princípio: só existe aqui.
  const [link, setLink] = useState(null);
  const [copiado, setCopiado] = useState(false);

  const { data: usuarios = [], isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: async () => (await api.get("/users")).data,
  });

  const fecharFormulario = () => {
    setAberto(false);
    setForm(VAZIO);
    setEditId(null);
    setVerSenha(false);
  };

  const salvar = useMutation({
    mutationFn: (p) => {
      const todas = p.permissoes.length === TODAS.length;
      if (!editId) {
        return api.post("/users", {
          name: p.name,
          email: p.email,
          password: p.password,
          role: p.role,
          // Todas marcadas = sem restrição (inclusive telas que surgirem).
          permissoes: p.role === "admin" || todas ? null : p.permissoes,
        });
      }
      const patch = { name: p.name, role: p.role };
      if (p.password) patch.password = p.password;
      if (p.role !== "admin") {
        if (todas) patch.todas_as_telas = true;
        else patch.permissoes = p.permissoes;
      }
      return api.put(`/users/${editId}`, patch);
    },
    onSuccess: (_r, p) => {
      qc.invalidateQueries({ queryKey: ["users"] });
      toast.success(editId ? "Usuário atualizado" : "Usuário criado");
      if (p.password) {
        setSenhaDefinida({ nome: p.name, email: p.email, senha: p.password, nova: !editId });
        setCopiado(false);
      }
      fecharFormulario();
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const alternarAtivo = useMutation({
    mutationFn: ({ id, active }) => api.put(`/users/${id}`, { active }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      toast.success("Acesso atualizado");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const gerarLink = useMutation({
    mutationFn: (id) => api.post(`/senha/link/${id}`),
    onSuccess: ({ data }) => {
      setLink(data);
      setCopiado(false);
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const excluir = useMutation({
    mutationFn: (id) => api.delete(`/users/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      toast.success("Usuário removido");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const alternarTela = (chave, marcado) =>
    setForm((f) => ({
      ...f,
      permissoes: marcado
        ? [...new Set([...f.permissoes, chave])]
        : f.permissoes.filter((c) => c !== chave),
    }));

  const senhaInvalida = form.password.length > 0 && form.password.length < MIN_SENHA;
  const podeSalvar =
    form.name.trim() &&
    (editId || (form.email.trim() && form.password.length >= MIN_SENHA)) &&
    !senhaInvalida;

  return (
    <div className="space-y-6 animate-fade-up" data-testid="users-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <p className="flex items-start gap-2 text-xs text-slate-500 max-w-xl">
          <ShieldCheck className="w-4 h-4 mt-0.5 shrink-0 text-emerald-500" aria-hidden="true" />
          Administradores veem e fazem tudo. Para cada gestor, você escolhe quais telas ele
          enxerga — o bloqueio vale também na API, não só no menu.
        </p>
        <Button
          onClick={() => {
            setForm(VAZIO);
            setEditId(null);
            setVerSenha(false);
            setAberto(true);
          }}
          data-testid="btn-novo-usuario"
          className="bg-primary hover:bg-orange-600 text-white gap-2"
        >
          <Plus className="w-4 h-4" /> Novo Usuário
        </Button>
      </div>

      <Panel className="overflow-hidden">
        {isLoading ? (
          <Loading />
        ) : !usuarios.length ? (
          <EmptyState icon={Users2} titulo="Nenhum usuário cadastrado" />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-slate-800 hover:bg-transparent">
                  <TableHead className="text-slate-400">Nome</TableHead>
                  <TableHead className="text-slate-400">E-mail</TableHead>
                  <TableHead className="text-slate-400">Perfil</TableHead>
                  <TableHead className="text-slate-400">Acesso</TableHead>
                  <TableHead className="text-slate-400">Último acesso</TableHead>
                  <TableHead className="text-slate-400">Ativo</TableHead>
                  <TableHead className="text-slate-400 text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {usuarios.map((u, i) => {
                  const souEu = u.id === eu?.id;
                  return (
                    <TableRow
                      key={u.id}
                      className="border-slate-800 hover:bg-slate-800/40"
                      data-testid={`user-row-${i}`}
                    >
                      <TableCell className="font-medium text-slate-100">
                        {u.name}
                        {souEu && <span className="ml-2 text-[11px] text-slate-500">(você)</span>}
                      </TableCell>
                      <TableCell className="text-slate-400">{u.email}</TableCell>
                      <TableCell>
                        <span
                          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${
                            u.role === "admin"
                              ? "bg-primary/15 text-primary border-primary/30"
                              : "bg-slate-500/15 text-slate-300 border-slate-500/30"
                          }`}
                        >
                          <UserCog className="w-3 h-3" aria-hidden="true" />
                          {u.role === "admin" ? "Administrador" : "Gestor"}
                        </span>
                      </TableCell>
                      <TableCell className="max-w-[14rem]">
                        <ResumoAcesso u={u} />
                      </TableCell>
                      <TableCell className="text-slate-400 text-xs">
                        {u.last_login_at ? dataHora(u.last_login_at) : "nunca entrou"}
                      </TableCell>
                      <TableCell>
                        <Switch
                          checked={u.active !== false}
                          disabled={souEu}
                          onCheckedChange={(v) => alternarAtivo.mutate({ id: u.id, active: v })}
                          aria-label={`${u.active === false ? "Ativar" : "Desativar"} acesso de ${u.name}`}
                          data-testid={`toggle-user-${i}`}
                        />
                      </TableCell>
                      <TableCell className="text-right whitespace-nowrap">
                        <IconButton
                          icon={Pencil}
                          label={`Editar ${u.name}, acesso e senha`}
                          data-testid={`edit-user-${i}`}
                          onClick={() => {
                            setForm({
                              name: u.name,
                              email: u.email,
                              password: "",
                              role: u.role,
                              // NULL no banco = todas as telas.
                              permissoes: u.permissoes == null ? TODAS : u.permissoes,
                            });
                            setEditId(u.id);
                            setVerSenha(false);
                            setAberto(true);
                          }}
                        />
                        <IconButton
                          icon={KeyRound}
                          label={`Gerar link para ${u.name} escolher a própria senha`}
                          disabled={gerarLink.isPending}
                          data-testid={`reset-user-${i}`}
                          onClick={async () => {
                            const ok = await confirmar({
                              titulo: `Gerar link de nova senha?`,
                              descricao: `${u.name} escolhe a própria senha pelo link. A senha atual continua valendo até ele ser usado.`,
                              confirmar: "Gerar link",
                            });
                            if (ok) gerarLink.mutate(u.id);
                          }}
                        />
                        <IconButton
                          icon={Trash2}
                          label={`Excluir ${u.name}`}
                          tone="hover:text-red-400"
                          disabled={souEu}
                          data-testid={`delete-user-${i}`}
                          onClick={async () => {
                            const ok = await confirmar({
                              titulo: `Excluir ${u.name}?`,
                              descricao: `${u.email} perde o acesso ao painel imediatamente.`,
                              confirmar: "Excluir",
                            });
                            if (ok) excluir.mutate(u.id);
                          }}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </Panel>

      {/* ------------------------------------------- senha recém-definida */}
      <Dialog open={!!senhaDefinida} onOpenChange={(v) => !v && setSenhaDefinida(null)}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-heading flex items-center gap-2">
              <KeyRound className="w-5 h-5 text-primary" aria-hidden="true" />
              {senhaDefinida?.nova ? "Usuário criado" : "Senha alterada"}
            </DialogTitle>
          </DialogHeader>
          {senhaDefinida && (
            <div className="space-y-4" data-testid="senha-definida-dialog">
              <p className="text-sm text-slate-400">
                Entregue estes dados a <strong className="text-slate-200">{senhaDefinida.nome}</strong>.
                {!senhaDefinida.nova && " Quem estava logado com a senha antiga já foi desconectado."}
              </p>
              <div className="space-y-2 rounded-xl border border-slate-800 bg-slate-950 p-4">
                <p className="text-xs text-slate-500">E-mail</p>
                <p className="font-mono text-sm text-slate-200 break-all">{senhaDefinida.email}</p>
                <p className="pt-2 text-xs text-slate-500">Senha</p>
                <div className="flex items-center gap-2">
                  <code
                    className="flex-1 break-all rounded-md bg-slate-900 px-3 py-2 font-mono text-base text-primary"
                    data-testid="senha-definida-valor"
                  >
                    {senhaDefinida.senha}
                  </code>
                  <Button
                    onClick={async () =>
                      setCopiado(
                        await copiarTexto(
                          `E-mail: ${senhaDefinida.email}\nSenha: ${senhaDefinida.senha}`,
                          "Acesso",
                        ),
                      )
                    }
                    className="bg-primary hover:bg-orange-600 text-white shrink-0 gap-2"
                  >
                    {copiado ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                    {copiado ? "Copiado" : "Copiar"}
                  </Button>
                </div>
              </div>
              <p className="text-xs text-slate-500">
                A senha aparece só agora: o sistema guarda apenas uma impressão dela, que não volta a
                ser senha. Se perder, defina outra em <strong>Editar</strong>.
              </p>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setSenhaDefinida(null)} className="border-slate-700">
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ------------------------------------------- link de redefinição */}
      <Dialog open={!!link} onOpenChange={(v) => !v && setLink(null)}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-heading flex items-center gap-2">
              <KeyRound className="w-5 h-5 text-primary" aria-hidden="true" />
              Link de nova senha
            </DialogTitle>
          </DialogHeader>
          {link && (
            <div className="space-y-4" data-testid="reset-link-dialog">
              <p className="text-sm text-slate-400">
                Envie para <strong className="text-slate-200">{link.usuario.nome}</strong> (
                {link.usuario.email}). Vale {link.expira_em_minutos} minutos e funciona uma vez só.
              </p>
              <div className="flex gap-2">
                <Input
                  readOnly
                  value={link.link}
                  onFocus={(e) => e.target.select()}
                  data-testid="reset-link-valor"
                  className="bg-slate-950 border-slate-700 text-slate-300 text-xs font-mono"
                />
                <Button
                  onClick={async () => setCopiado(await copiarTexto(link.link, "Link"))}
                  data-testid="reset-link-copiar"
                  className="bg-primary hover:bg-orange-600 text-white shrink-0 gap-2"
                >
                  {copiado ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  {copiado ? "Copiado" : "Copiar"}
                </Button>
              </div>
              <p className="text-xs text-slate-500">
                Este link não aparece de novo: o sistema guarda só a impressão dele. Se perder,
                gere outro — o anterior deixa de valer.
              </p>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setLink(null)} className="border-slate-700">
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ------------------------------------------- criar / editar */}
      <Dialog open={aberto} onOpenChange={(v) => (v ? setAberto(true) : fecharFormulario())}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100 max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="font-heading">
              {editId ? "Editar Usuário" : "Novo Usuário"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-5 py-2">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="u-nome">Nome *</Label>
                <Input
                  id="u-nome"
                  data-testid="user-name-input"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="bg-slate-800 border-slate-700"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="u-email">E-mail *</Label>
                <Input
                  id="u-email"
                  type="email"
                  disabled={!!editId}
                  data-testid="user-email-input"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="bg-slate-800 border-slate-700 disabled:opacity-60"
                />
                {editId && (
                  <p className="text-xs text-slate-500">O e-mail identifica a conta e não muda.</p>
                )}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="u-senha">
                {editId ? "Nova senha (deixe em branco para manter a atual)" : "Senha *"}
              </Label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Input
                    id="u-senha"
                    type={verSenha ? "text" : "password"}
                    autoComplete="new-password"
                    data-testid="user-password-input"
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    className="bg-slate-800 border-slate-700 pr-10 font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => setVerSenha((v) => !v)}
                    aria-label={verSenha ? "Esconder senha" : "Mostrar senha"}
                    data-testid="user-password-ver"
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-400 hover:text-slate-100"
                  >
                    {verSenha ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setForm({ ...form, password: gerarSenha() });
                    setVerSenha(true);
                  }}
                  data-testid="user-password-gerar"
                  className="border-slate-700 gap-1.5 shrink-0"
                >
                  <Sparkles className="h-4 w-4" /> Gerar
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={!form.password}
                  onClick={() => copiarTexto(form.password, "Senha")}
                  aria-label="Copiar senha"
                  className="border-slate-700 shrink-0 px-3"
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
              <p className={`text-xs ${senhaInvalida ? "text-red-400" : "text-slate-500"}`}>
                Mínimo de {MIN_SENHA} caracteres.
                {editId && " Ao trocar, quem estiver logado com a senha antiga é desconectado."}
              </p>
            </div>

            <div className="space-y-1.5">
              <Label>Perfil</Label>
              <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                <SelectTrigger className="bg-slate-800 border-slate-700" data-testid="user-role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="manager">Gestor — vê só as telas marcadas abaixo</SelectItem>
                  <SelectItem value="admin">Administrador — vê e controla tudo</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {form.role === "admin" ? (
              <p className="rounded-xl border border-primary/25 bg-primary/10 p-3 text-xs text-slate-300">
                Administrador vê todas as telas, gerencia usuários, chaves de API e auditoria.
              </p>
            ) : (
              <fieldset className="space-y-3" data-testid="user-permissoes">
                <div className="flex items-center justify-between gap-2">
                  <legend className="flex items-center gap-2 text-sm font-medium text-slate-200">
                    <LayoutGrid className="h-4 w-4 text-primary" aria-hidden="true" />
                    Telas que este usuário vê
                    <span className="text-xs font-normal text-slate-500">
                      ({form.permissoes.length} de {TODAS.length})
                    </span>
                  </legend>
                  <div className="flex gap-1">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setForm({ ...form, permissoes: TODAS })}
                      className="h-7 text-xs text-slate-300"
                    >
                      Marcar todas
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setForm({ ...form, permissoes: [] })}
                      className="h-7 text-xs text-slate-400"
                    >
                      Limpar
                    </Button>
                  </div>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {MODULOS.map((m) => {
                    const marcado = form.permissoes.includes(m.chave);
                    return (
                      <label
                        key={m.chave}
                        htmlFor={`perm-${m.chave}`}
                        className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors ${
                          marcado
                            ? "border-primary/40 bg-primary/10"
                            : "border-slate-800 bg-slate-950/40 hover:border-slate-700"
                        }`}
                      >
                        <Checkbox
                          id={`perm-${m.chave}`}
                          checked={marcado}
                          onCheckedChange={(v) => alternarTela(m.chave, v === true)}
                          data-testid={`perm-${m.chave}`}
                          className="mt-0.5"
                        />
                        <span>
                          <span className="block text-sm text-slate-100">{m.rotulo}</span>
                          <span className="block text-xs text-slate-500">{m.descricao}</span>
                        </span>
                      </label>
                    );
                  })}
                </div>
                {!form.permissoes.length && (
                  <p className="text-xs text-amber-400">
                    Sem nenhuma tela marcada, a conta entra mas não vê nada.
                  </p>
                )}
              </fieldset>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={fecharFormulario} className="text-slate-400">
              Cancelar
            </Button>
            <Button
              onClick={() => salvar.mutate(form)}
              disabled={!podeSalvar || salvar.isPending}
              data-testid="save-user-button"
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
