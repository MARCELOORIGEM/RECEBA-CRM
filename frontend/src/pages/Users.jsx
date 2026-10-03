import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Check, Copy, KeyRound, Loader2, Pencil, Plus, ShieldCheck, Trash2, UserCog, Users2,
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
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

const VAZIO = { name: "", email: "", password: "", role: "manager" };
const MIN_SENHA = 8;

export default function Users() {
  const qc = useQueryClient();
  const confirmar = useConfirm();
  const { user: eu } = useAuth();
  const [aberto, setAberto] = useState(false);
  const [form, setForm] = useState(VAZIO);
  const [editId, setEditId] = useState(null);
  // Link de redefinição recém-gerado. Só existe aqui, nesta tela, até fechar:
  // o backend guarda apenas o hash do token e não sabe mais devolvê-lo.
  const [link, setLink] = useState(null);
  const [copiado, setCopiado] = useState(false);

  const { data: usuarios = [], isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: async () => (await api.get("/users")).data,
  });

  const salvar = useMutation({
    mutationFn: (p) => {
      if (!editId) return api.post("/users", p);
      const patch = { name: p.name, role: p.role };
      if (p.password) patch.password = p.password;
      return api.put(`/users/${editId}`, patch);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      toast.success(editId ? "Usuário atualizado" : "Usuário criado");
      setAberto(false);
      setForm(VAZIO);
      setEditId(null);
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

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(link.link);
      setCopiado(true);
      toast.success("Link copiado");
    } catch {
      // Área de transferência bloqueada (http sem TLS, permissão negada): o
      // link fica visível na tela para seleção manual.
      toast.error("Copie o link manualmente.");
    }
  };

  const excluir = useMutation({
    mutationFn: (id) => api.delete(`/users/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      toast.success("Usuário removido");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const senhaInvalida =
    (!editId || form.password) && form.password.length > 0 && form.password.length < MIN_SENHA;
  const podeSalvar =
    form.name.trim() &&
    (editId || (form.email.trim() && form.password.length >= MIN_SENHA)) &&
    !senhaInvalida;

  return (
    <div className="space-y-6 animate-fade-up" data-testid="users-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <p className="flex items-start gap-2 text-xs text-slate-500 max-w-xl">
          <ShieldCheck className="w-4 h-4 mt-0.5 shrink-0 text-emerald-500" aria-hidden="true" />
          Administradores podem excluir cadastros, gerar chaves de API e ver a auditoria. Gestores
          operam o dia a dia sem acesso a essas ações.
        </p>
        <Button
          onClick={() => {
            setForm(VAZIO);
            setEditId(null);
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
                          label={`Editar ${u.name}`}
                          data-testid={`edit-user-${i}`}
                          onClick={() => {
                            setForm({ name: u.name, email: u.email, password: "", role: u.role });
                            setEditId(u.id);
                            setAberto(true);
                          }}
                        />
                        <IconButton
                          icon={KeyRound}
                          label={`Gerar link de nova senha para ${u.name}`}
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
                  onClick={copiar}
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

      <Dialog open={aberto} onOpenChange={setAberto}>
        <DialogContent className="bg-slate-900 border-slate-800 text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-heading">
              {editId ? "Editar Usuário" : "Novo Usuário"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
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
            <div className="space-y-1.5">
              <Label htmlFor="u-senha">
                {editId ? "Nova senha (deixe em branco para manter)" : "Senha *"}
              </Label>
              <Input
                id="u-senha"
                type="password"
                data-testid="user-password-input"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="bg-slate-800 border-slate-700"
              />
              <p className={`text-xs ${senhaInvalida ? "text-red-400" : "text-slate-500"}`}>
                Mínimo de {MIN_SENHA} caracteres.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label>Perfil</Label>
              <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                <SelectTrigger className="bg-slate-800 border-slate-700" data-testid="user-role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="manager">Gestor operacional</SelectItem>
                  <SelectItem value="admin">Administrador</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAberto(false)} className="text-slate-400">
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
