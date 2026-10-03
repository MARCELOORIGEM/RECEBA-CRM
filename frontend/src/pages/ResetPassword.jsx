import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Eye, EyeOff, KeyRound, Loader2, Lock } from "lucide-react";
import { api, apiError } from "@/lib/api";
import Logo from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const MINIMO = 8;

/** Força da senha, só para orientar quem está digitando. */
function medir(senha) {
  if (senha.length < MINIMO) return { nivel: 0, rotulo: "Curta demais", cor: "bg-red-500" };
  let pontos = 1;
  if (/[a-z]/.test(senha) && /[A-Z]/.test(senha)) pontos += 1;
  if (/\d/.test(senha)) pontos += 1;
  if (/[^A-Za-z0-9]/.test(senha)) pontos += 1;
  if (senha.length >= 14) pontos += 1;
  if (pontos <= 2) return { nivel: 1, rotulo: "Fraca", cor: "bg-red-500" };
  if (pontos === 3) return { nivel: 2, rotulo: "Razoável", cor: "bg-amber-500" };
  if (pontos === 4) return { nivel: 3, rotulo: "Boa", cor: "bg-lime-500" };
  return { nivel: 4, rotulo: "Forte", cor: "bg-emerald-500" };
}

/**
 * Tela do link de redefinição (`/redefinir-senha/:token`).
 *
 * Fica fora da área autenticada: quem chega aqui justamente não consegue
 * entrar. O token da URL é a credencial — o backend confere o hash dele, a
 * validade de 30 minutos e descarta o pedido no primeiro uso.
 */
export default function ResetPassword() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [senha, setSenha] = useState("");
  const [repetir, setRepetir] = useState("");
  const [ver, setVer] = useState(false);
  const [erro, setErro] = useState("");
  const [pronto, setPronto] = useState(false);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    document.title = "Criar nova senha • Miliano";
  }, []);

  const forca = medir(senha);
  const divergem = repetir !== "" && senha !== repetir;
  const podeEnviar = senha.length >= MINIMO && senha === repetir && !salvando;

  const enviar = async (e) => {
    e.preventDefault();
    setErro("");
    if (senha !== repetir) {
      setErro("As duas senhas precisam ser iguais.");
      return;
    }
    setSalvando(true);
    try {
      await api.post("/senha/redefinir", { token, nova_senha: senha });
      setPronto(true);
      // Tempo de ler a confirmação antes de cair no login.
      setTimeout(() => navigate("/login", { replace: true }), 2500);
    } catch (err) {
      setErro(apiError(err, "Não foi possível redefinir a senha."));
    } finally {
      setSalvando(false);
    }
  };

  const campo =
    "h-12 border-slate-700 bg-slate-950/60 pl-10 pr-11 text-slate-100 transition-all duration-300 focus-visible:border-primary/50 focus-visible:ring-primary/40";

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 px-5 py-12">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute -top-40 left-1/2 h-[32rem] w-[32rem] -translate-x-1/2 rounded-full bg-primary/10 blur-[140px] animate-pulse-glow" />
        <div className="absolute -bottom-40 right-10 h-[24rem] w-[24rem] rounded-full bg-primary/5 blur-[120px] animate-pulse-glow" style={{ animationDelay: "-2.5s" }} />
      </div>

      <div className="relative z-10 w-full max-w-md animate-reveal-up">
        <div className="mb-8 flex justify-center">
          <Logo tamanho="md" brilho />
        </div>

        <div className="rounded-2xl border border-slate-800/80 bg-slate-900/70 p-7 shadow-2xl backdrop-blur-xl sm:p-9">
          {pronto ? (
            <div className="text-center" data-testid="reset-sucesso">
              <CheckCircle2 className="mx-auto mb-4 h-14 w-14 text-emerald-500" aria-hidden="true" />
              <h1 className="font-heading text-2xl font-bold text-slate-50">Senha redefinida</h1>
              <p className="mt-2 text-sm text-slate-400">
                Já pode entrar com a nova senha. Levando você para o login…
              </p>
              <Link
                to="/login"
                className="mt-6 inline-flex items-center gap-2 text-sm font-semibold text-primary hover:underline"
              >
                Ir agora <ArrowLeft className="h-4 w-4 rotate-180" aria-hidden="true" />
              </Link>
            </div>
          ) : (
            <>
              <div className="mb-6 flex items-center gap-3">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-primary/30 bg-primary/10">
                  <KeyRound className="h-5 w-5 text-primary" aria-hidden="true" />
                </span>
                <div>
                  <h1 className="font-heading text-2xl font-bold text-slate-50">Criar nova senha</h1>
                  <p className="text-sm text-slate-500">Este link vale uma vez só.</p>
                </div>
              </div>

              <form onSubmit={enviar} className="space-y-5" data-testid="reset-form">
                <div className="space-y-2">
                  <Label htmlFor="senha" className="text-slate-300">
                    Nova senha
                  </Label>
                  <div className="group relative">
                    <Lock
                      className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600 transition-colors group-focus-within:text-primary"
                      aria-hidden="true"
                    />
                    <Input
                      id="senha"
                      type={ver ? "text" : "password"}
                      autoComplete="new-password"
                      data-testid="reset-senha"
                      value={senha}
                      onChange={(e) => setSenha(e.target.value)}
                      placeholder="Pelo menos 8 caracteres"
                      className={campo}
                      required
                      minLength={MINIMO}
                    />
                    <button
                      type="button"
                      onClick={() => setVer((v) => !v)}
                      aria-label={ver ? "Ocultar senha" : "Mostrar senha"}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 transition-colors hover:text-primary"
                    >
                      {ver ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>

                  {senha && (
                    <div className="flex items-center gap-2 pt-0.5">
                      <div className="flex h-1.5 flex-1 gap-1" aria-hidden="true">
                        {[0, 1, 2, 3].map((i) => (
                          <span
                            key={i}
                            className={`h-full flex-1 rounded-full transition-colors ${
                              i < forca.nivel ? forca.cor : "bg-slate-800"
                            }`}
                          />
                        ))}
                      </div>
                      <span className="w-20 text-right text-xs text-slate-500">{forca.rotulo}</span>
                    </div>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="repetir" className="text-slate-300">
                    Repita a senha
                  </Label>
                  <div className="group relative">
                    <Lock
                      className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600 transition-colors group-focus-within:text-primary"
                      aria-hidden="true"
                    />
                    <Input
                      id="repetir"
                      type={ver ? "text" : "password"}
                      autoComplete="new-password"
                      data-testid="reset-repetir"
                      value={repetir}
                      onChange={(e) => setRepetir(e.target.value)}
                      placeholder="••••••••"
                      className={campo}
                      required
                    />
                  </div>
                  {divergem && (
                    <p className="text-xs text-red-400">As duas senhas estão diferentes.</p>
                  )}
                </div>

                {erro && (
                  <p
                    role="alert"
                    className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2.5 text-sm text-red-400"
                    data-testid="reset-erro"
                  >
                    {erro}
                  </p>
                )}

                <Button
                  type="submit"
                  disabled={!podeEnviar}
                  data-testid="reset-submit"
                  className="h-12 w-full gap-2 bg-[linear-gradient(110deg,#FFC15E,#F5A524,#DB8E0F,#F5A524,#FFC15E)] bg-[length:200%_100%] font-semibold text-slate-950 animate-gradient-x transition-all hover:shadow-[0_0_32px_-6px_rgba(245,165,36,0.75)] disabled:opacity-60"
                >
                  {salvando ? <Loader2 className="h-4 w-4 animate-spin" /> : "Salvar nova senha"}
                </Button>
              </form>

              <Link
                to="/login"
                className="mt-6 flex items-center justify-center gap-2 text-sm text-slate-500 transition-colors hover:text-primary"
              >
                <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Voltar ao login
              </Link>
            </>
          )}
        </div>

        <p className="mt-6 text-center text-xs text-slate-600">
          Miliano Business Solutions · Parceiro Oficial Keeta
        </p>
      </div>
    </div>
  );
}
