import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Eye, EyeOff, KeyRound, Loader2, UserCog } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const MIN_SENHA = 8;

/**
 * Conta do próprio usuário.
 *
 * Trocar a senha só existia na gestão de usuários, restrita ao administrador:
 * um gestor ficava preso à senha com que foi cadastrado, sem forma de trocá-la.
 */
export function AccountDialog({ open, onOpenChange }) {
  const { user, setUser } = useAuth();
  const [nome, setNome] = useState("");
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [confirma, setConfirma] = useState("");
  const [mostrar, setMostrar] = useState(false);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    if (open) {
      setNome(user?.name || "");
      setAtual("");
      setNova("");
      setConfirma("");
      setMostrar(false);
    }
  }, [open, user?.name]);

  const salvarNome = async () => {
    setSalvando(true);
    try {
      const { data } = await api.put("/auth/me", { name: nome.trim() });
      setUser(data);
      toast.success("Nome atualizado");
      onOpenChange(false);
    } catch (e) {
      toast.error(apiError(e));
    } finally {
      setSalvando(false);
    }
  };

  const trocarSenha = async () => {
    setSalvando(true);
    try {
      await api.post("/auth/password", { current_password: atual, new_password: nova });
      toast.success("Senha alterada. Use a nova no próximo acesso.");
      onOpenChange(false);
    } catch (e) {
      toast.error(apiError(e));
    } finally {
      setSalvando(false);
    }
  };

  const curta = nova.length > 0 && nova.length < MIN_SENHA;
  const divergem = confirma.length > 0 && nova !== confirma;
  const podeTrocar = atual && nova.length >= MIN_SENHA && nova === confirma;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-slate-900 border-slate-800 text-slate-100">
        <DialogHeader>
          <DialogTitle className="font-heading">Minha conta</DialogTitle>
          <DialogDescription className="text-slate-500">
            {user?.email} — {user?.role === "admin" ? "Administrador" : "Gestor"}
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="senha">
          <TabsList className="bg-slate-800 border border-slate-700 w-full">
            <TabsTrigger value="senha" className="flex-1 text-xs gap-1.5" data-testid="tab-senha">
              <KeyRound className="w-3.5 h-3.5" aria-hidden="true" /> Senha
            </TabsTrigger>
            <TabsTrigger value="perfil" className="flex-1 text-xs gap-1.5" data-testid="tab-perfil">
              <UserCog className="w-3.5 h-3.5" aria-hidden="true" /> Perfil
            </TabsTrigger>
          </TabsList>

          <TabsContent value="senha" className="mt-4 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="senha-atual">Senha atual</Label>
              <Input
                id="senha-atual"
                type="password"
                autoComplete="current-password"
                data-testid="senha-atual-input"
                value={atual}
                onChange={(e) => setAtual(e.target.value)}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="senha-nova">Nova senha</Label>
              <div className="relative">
                <Input
                  id="senha-nova"
                  type={mostrar ? "text" : "password"}
                  autoComplete="new-password"
                  data-testid="senha-nova-input"
                  value={nova}
                  onChange={(e) => setNova(e.target.value)}
                  className="bg-slate-800 border-slate-700 pr-10"
                />
                <button
                  type="button"
                  onClick={() => setMostrar((m) => !m)}
                  aria-label={mostrar ? "Ocultar senha" : "Mostrar senha"}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
                >
                  {mostrar ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <p className={`text-xs ${curta ? "text-red-400" : "text-slate-500"}`}>
                Mínimo de {MIN_SENHA} caracteres.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="senha-confirma">Repita a nova senha</Label>
              <Input
                id="senha-confirma"
                type={mostrar ? "text" : "password"}
                autoComplete="new-password"
                data-testid="senha-confirma-input"
                value={confirma}
                onChange={(e) => setConfirma(e.target.value)}
                className="bg-slate-800 border-slate-700"
              />
              {divergem && <p className="text-xs text-red-400">As senhas não coincidem.</p>}
            </div>
            <DialogFooter>
              <Button variant="ghost" onClick={() => onOpenChange(false)} className="text-slate-400">
                Cancelar
              </Button>
              <Button
                onClick={trocarSenha}
                disabled={!podeTrocar || salvando}
                data-testid="salvar-senha-button"
                className="bg-primary hover:bg-orange-600 text-white"
              >
                {salvando ? <Loader2 className="w-4 h-4 animate-spin" /> : "Trocar senha"}
              </Button>
            </DialogFooter>
          </TabsContent>

          <TabsContent value="perfil" className="mt-4 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="perfil-nome">Nome exibido</Label>
              <Input
                id="perfil-nome"
                data-testid="perfil-nome-input"
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <p className="text-xs text-slate-500">
              O e-mail identifica a conta e só um administrador pode alterá-lo.
            </p>
            <DialogFooter>
              <Button variant="ghost" onClick={() => onOpenChange(false)} className="text-slate-400">
                Cancelar
              </Button>
              <Button
                onClick={salvarNome}
                disabled={!nome.trim() || nome.trim() === user?.name || salvando}
                data-testid="salvar-perfil-button"
                className="bg-primary hover:bg-orange-600 text-white"
              >
                {salvando ? <Loader2 className="w-4 h-4 animate-spin" /> : "Salvar"}
              </Button>
            </DialogFooter>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
