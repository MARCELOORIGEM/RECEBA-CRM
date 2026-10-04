import { useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowRight, BarChart3, Eye, EyeOff, Loader2, Lock, Mail, ShieldCheck, Truck, Users,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { MarcaComMascote } from "@/components/Keeta";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// As credenciais de demonstração ficavam impressas na tela de login em
// qualquer ambiente — inclusive no preview público, onde entregavam a senha do
// administrador. Agora dependem de uma variável de build.
const MOSTRAR_DEMO = process.env.REACT_APP_SHOW_DEMO_LOGIN === "true";

const DESTAQUES = [
  { icon: BarChart3, titulo: "Operação em números", texto: "Receita, margem e entregas do dia" },
  { icon: Users, titulo: "Funil comercial", texto: "Da prospecção ao contrato assinado" },
  { icon: Truck, titulo: "Entregas ao vivo", texto: "Status, rota e repasse automático" },
];

const PALAVRAS = ["A", "sua", "operação", "inteira"];

/* Três planos de profundidade. As fagulhas do fundo são menores, mais lentas,
   desfocadas e apagadas; as da frente, maiores e nítidas. É o que dá volume —
   um único plano subindo em linha reta lê como chuva invertida. */
const PLANOS = [
  { nome: "fundo", qtd: 16, tamanho: [1.5, 3], subida: [26, 38], desfoque: 1.4, opacidade: [0.1, 0.28] },
  { nome: "meio", qtd: 12, tamanho: [2.5, 5], subida: [17, 26], desfoque: 0.5, opacidade: [0.25, 0.5] },
  { nome: "frente", qtd: 7, tamanho: [4, 7.5], subida: [11, 17], desfoque: 0, opacidade: [0.45, 0.8] },
];

const entre = ([a, b]) => a + Math.random() * (b - a);

/** Sorteia as fagulhas uma única vez: recalcular a cada render faria as
 *  partículas saltarem de lugar no meio do voo. */
function useFagulhas() {
  return useMemo(
    () =>
      PLANOS.flatMap((plano, p) =>
        Array.from({ length: plano.qtd }, (_, i) => {
          // Uma em cada quatro é prata, como o letreiro do logo.
          const prata = Math.random() < 0.25;
          return {
            id: `${p}-${i}`,
            left: Math.random() * 100,
            // Começa em alturas diferentes para que a tela já nasça povoada.
            base: Math.random() * 40,
            tamanho: entre(plano.tamanho),
            subida: entre(plano.subida),
            balanco: 5 + Math.random() * 7,
            cintilacao: 2.5 + Math.random() * 4,
            atraso: -Math.random() * 40,
            desfoque: plano.desfoque,
            opacidade: entre(plano.opacidade),
            cor: prata ? "#D8DBE0" : "#F5A524",
            halo: prata ? "rgba(216,219,224,0.55)" : "rgba(245,165,36,0.85)",
          };
        }),
      ),
    [],
  );
}

export default function Login() {
  const { login, user, loading: verificando } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const cartao = useRef(null);
  const fagulhas = useFagulhas();

  useEffect(() => {
    document.title = "Entrar • Miliano CRM";
  }, []);

  /* O cartão inclina e o reflexo dourado segue o cursor.
     Os valores vão para variáveis CSS pelo ref, não para o state: a cada
     pixel de mouse o React re-renderizaria a tela inteira. */
  const moverBrilho = (e) => {
    const alvo = cartao.current;
    if (!alvo) return;
    const r = alvo.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width;
    const py = (e.clientY - r.top) / r.height;
    alvo.style.setProperty("--bx", `${px * 100}%`);
    alvo.style.setProperty("--by", `${py * 100}%`);
    alvo.style.setProperty("--rx", `${(0.5 - py) * 7}deg`);
    alvo.style.setProperty("--ry", `${(px - 0.5) * 9}deg`);
  };

  const soltarBrilho = () => {
    const alvo = cartao.current;
    if (!alvo) return;
    alvo.style.setProperty("--bx", "50%");
    alvo.style.setProperty("--by", "50%");
    alvo.style.setProperty("--rx", "0deg");
    alvo.style.setProperty("--ry", "0deg");
  };

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    const res = await login(email.trim(), password);
    setLoading(false);
    if (res.ok) {
      toast.success("Bem-vindo de volta!");
      navigate("/", { replace: true });
    } else {
      setError(res.error);
    }
  };

  const fill = (mode) => {
    const contas = {
      admin: [
        process.env.REACT_APP_DEMO_ADMIN_EMAIL || "",
        process.env.REACT_APP_DEMO_ADMIN_PASSWORD || "",
      ],
      gestor: [
        process.env.REACT_APP_DEMO_MANAGER_EMAIL || "",
        process.env.REACT_APP_DEMO_MANAGER_PASSWORD || "",
      ],
    };
    const [e, p] = contas[mode] || ["", ""];
    setEmail(e);
    setPassword(p);
  };

  if (!verificando && user) return <Navigate to="/" replace />;

  return (
    <div className="relative min-h-screen overflow-hidden bg-slate-950 text-slate-100">
      {/* ------------------------------------------------------ cenário */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        {/* Malha discreta, em prata, só para dar profundidade ao fundo. */}
        <div
          className="absolute inset-0 opacity-[0.05]"
          style={{
            backgroundImage:
              "linear-gradient(rgba(216,219,224,.9) 1px, transparent 1px), linear-gradient(90deg, rgba(216,219,224,.9) 1px, transparent 1px)",
            backgroundSize: "56px 56px",
            maskImage: "radial-gradient(ellipse at center, black 18%, transparent 74%)",
            WebkitMaskImage: "radial-gradient(ellipse at center, black 18%, transparent 74%)",
          }}
        />

        {/* Um sopro lento cruzando a tela, para o ar não ficar parado. */}
        <div
          className="absolute inset-y-0 left-0 w-1/3 animate-sopro"
          style={{
            animationDuration: "34s",
            background:
              "linear-gradient(90deg, transparent, rgba(245,165,36,0.05), transparent)",
          }}
        />

        {/* As fagulhas são o único movimento colorido do fundo: o brilho
            alaranjado que existia aqui lavava a área do logo e foi retirado.

            Três elementos aninhados por fagulha, porque os movimentos têm
            ritmos independentes e uma transform só não combina os três:
            subida (externo) · balanço lateral (meio) · cintilação (ponto). */}
        {fagulhas.map((f) => (
          <span
            key={f.id}
            className="absolute animate-subir will-change-transform"
            style={{
              left: `${f.left}%`,
              bottom: `${f.base}%`,
              animationDuration: `${f.subida}s`,
              animationDelay: `${f.atraso}s`,
            }}
          >
            <span
              className="block animate-balancar"
              style={{
                animationDuration: `${f.balanco}s`,
                animationDelay: `${f.atraso / 2}s`,
              }}
            >
              <span
                className="block rounded-full animate-cintilar"
                style={{
                  width: f.tamanho,
                  height: f.tamanho,
                  background: f.cor,
                  opacity: f.opacidade,
                  filter: f.desfoque ? `blur(${f.desfoque}px)` : undefined,
                  boxShadow: `0 0 ${f.tamanho * 2.5}px ${f.tamanho / 3}px ${f.halo}`,
                  animationDuration: `${f.cintilacao}s`,
                  animationDelay: `${f.atraso / 3}s`,
                }}
              />
            </span>
          </span>
        ))}
      </div>

      <div className="relative z-10 min-h-screen grid lg:grid-cols-2">
        {/* ------------------------------------------------ apresentação */}
        <section className="hidden lg:flex flex-col justify-between p-12 xl:p-16">
          <div className="animate-reveal-up">
            <MarcaComMascote tamanho="lg" brilho />
          </div>

          <div className="space-y-8 max-w-lg">
            <div className="space-y-4">
              <span
                className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary animate-reveal-up"
                style={{ animationDelay: "120ms" }}
              >
                <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
                CRM de operação logística
              </span>

              {/* Manchete entrando palavra a palavra. */}
              <h1 className="font-heading text-4xl xl:text-5xl font-extrabold leading-[1.08] tracking-tight">
                {PALAVRAS.map((palavra, i) => (
                  <span
                    key={palavra}
                    className="inline-block animate-reveal-up"
                    style={{ animationDelay: `${200 + i * 90}ms` }}
                  >
                    {palavra}&nbsp;
                  </span>
                ))}
                <span
                  className="inline-block texto-dourado animate-reveal-up"
                  style={{ animationDelay: "560ms" }}
                >
                  em uma tela só
                </span>
              </h1>

            </div>

            <ul className="space-y-3">
              {DESTAQUES.map(({ icon: Icon, titulo, texto }, i) => (
                <li
                  key={titulo}
                  className="group flex items-start gap-3 rounded-xl border border-slate-800/80 bg-slate-900/40 p-3.5 backdrop-blur-sm transition-all duration-300 hover:border-primary/40 hover:translate-x-1.5 animate-reveal-up"
                  style={{ animationDelay: `${760 + i * 110}ms` }}
                >
                  <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/12 text-primary transition-transform duration-300 group-hover:scale-110 group-hover:rotate-6">
                    <Icon className="h-[18px] w-[18px]" aria-hidden="true" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-slate-100">{titulo}</span>
                    <span className="block text-xs text-slate-500">{texto}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <p
            className="flex items-center gap-2 text-xs text-slate-600 animate-reveal-up"
            style={{ animationDelay: "1100ms" }}
          >
            <ShieldCheck className="h-4 w-4 text-primary/60" aria-hidden="true" />
            Sessão protegida — acesso restrito a contas autorizadas.
          </p>
        </section>

        {/* --------------------------------------------------- formulário */}
        <section
          className="flex items-center justify-center p-6 sm:p-12"
          style={{ perspective: "1400px" }}
        >
          <div
            ref={cartao}
            onMouseMove={moverBrilho}
            onMouseLeave={soltarBrilho}
            className="group/card relative w-full max-w-md animate-reveal-up"
            style={{
              animationDelay: "260ms",
              transform: "rotateX(var(--rx,0deg)) rotateY(var(--ry,0deg))",
              transformStyle: "preserve-3d",
              transition: "transform 380ms cubic-bezier(0.22, 1, 0.36, 1)",
            }}
          >
            {/* Fio de luz dando a volta na borda. O anel gira dentro de um
                contêiner recortado; a máscara interna deixa só a moldura. */}
            <div
              aria-hidden="true"
              className="pointer-events-none absolute -inset-px overflow-hidden rounded-2xl"
            >
              <div className="absolute left-1/2 top-1/2 h-[220%] w-[220%] -translate-x-1/2 -translate-y-1/2 animate-border-spin blur-[2px] bg-[conic-gradient(from_0deg,transparent_0deg,rgba(245,165,36,0.85)_30deg,transparent_78deg,transparent_180deg,rgba(216,219,224,0.4)_212deg,transparent_258deg)]" />
              <div className="absolute inset-px rounded-2xl bg-slate-950" />
            </div>

            <div className="relative rounded-2xl border border-slate-800/80 bg-slate-900/70 p-7 sm:p-9 shadow-2xl backdrop-blur-xl">
              {/* Reflexo que segue o cursor. */}
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 rounded-2xl opacity-0 transition-opacity duration-500 group-hover/card:opacity-100"
                style={{
                  background:
                    "radial-gradient(440px circle at var(--bx,50%) var(--by,50%), rgba(245,165,36,0.14), transparent 62%)",
                }}
              />

              <div className="relative">
                <div className="lg:hidden mb-7">
                  <MarcaComMascote tamanho="md" brilho />
                </div>

                <h2 className="font-heading text-2xl font-bold text-slate-50">Entrar no painel</h2>
                <p className="mt-1 text-sm text-slate-500">Acesse sua conta para continuar</p>

                <form onSubmit={submit} className="mt-7 space-y-5" data-testid="login-form">
                  <div
                    className="space-y-2 animate-reveal-up"
                    style={{ animationDelay: "420ms" }}
                  >
                    <Label htmlFor="email" className="text-slate-300">
                      E-mail
                    </Label>
                    <div className="group relative">
                      <Mail
                        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600 transition-all duration-300 group-focus-within:scale-110 group-focus-within:text-primary"
                        aria-hidden="true"
                      />
                      <Input
                        id="email"
                        type="email"
                        autoComplete="email"
                        data-testid="login-email-input"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="voce@empresa.com"
                        className="h-12 border-slate-700 bg-slate-950/60 pl-10 text-slate-100 transition-all duration-300 focus-visible:border-primary/50 focus-visible:ring-primary/40 focus-visible:shadow-[0_0_22px_-8px_rgba(245,165,36,0.8)]"
                        required
                      />
                    </div>
                  </div>

                  <div
                    className="space-y-2 animate-reveal-up"
                    style={{ animationDelay: "500ms" }}
                  >
                    <Label htmlFor="password" className="text-slate-300">
                      Senha
                    </Label>
                    <div className="group relative">
                      <Lock
                        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600 transition-all duration-300 group-focus-within:scale-110 group-focus-within:text-primary"
                        aria-hidden="true"
                      />
                      <Input
                        id="password"
                        type={show ? "text" : "password"}
                        autoComplete="current-password"
                        data-testid="login-password-input"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="••••••••"
                        className="h-12 border-slate-700 bg-slate-950/60 pl-10 pr-11 text-slate-100 transition-all duration-300 focus-visible:border-primary/50 focus-visible:ring-primary/40 focus-visible:shadow-[0_0_22px_-8px_rgba(245,165,36,0.8)]"
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShow((s) => !s)}
                        aria-label={show ? "Ocultar senha" : "Mostrar senha"}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 transition-colors hover:text-primary"
                        data-testid="login-toggle-password"
                      >
                        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  {error && (
                    <p
                      role="alert"
                      className="animate-reveal-up rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2.5 text-sm text-red-400"
                      data-testid="login-error"
                    >
                      {error}
                    </p>
                  )}

                  <div className="animate-reveal-up" style={{ animationDelay: "580ms" }}>
                    <Button
                      type="submit"
                      disabled={loading}
                      data-testid="login-submit-button"
                      className="group/btn relative h-12 w-full gap-2 overflow-hidden bg-[linear-gradient(110deg,#FFC15E,#F5A524,#DB8E0F,#F5A524,#FFC15E)] bg-[length:200%_100%] font-semibold text-slate-950 animate-gradient-x transition-all hover:shadow-[0_0_32px_-6px_rgba(245,165,36,0.75)] disabled:opacity-70"
                    >
                      {/* Lustro que atravessa o botão ao passar o mouse. */}
                      <span
                        aria-hidden="true"
                        className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/45 to-transparent transition-transform duration-700 group-hover/btn:translate-x-full"
                      />
                      {loading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <>
                          <span className="relative">Entrar</span>
                          <ArrowRight
                            className="relative h-4 w-4 transition-transform duration-300 group-hover/btn:translate-x-1.5"
                            aria-hidden="true"
                          />
                        </>
                      )}
                    </Button>
                  </div>
                </form>

                {/* Não há autoatendimento por e-mail de propósito: o
                    administrador gera um link de uso único na tela de
                    usuários e entrega pelo canal que a equipe já usa. */}
                <p className="mt-6 text-center text-xs text-slate-600" data-testid="login-esqueci">
                  Esqueceu a senha? Peça ao administrador um link de redefinição.
                </p>

                {MOSTRAR_DEMO && (
                  <div className="animate-reveal-up" style={{ animationDelay: "660ms" }}>
                    <div className="mt-7 flex items-center gap-2">
                      <div className="h-px flex-1 bg-slate-800" />
                      <span className="text-xs text-slate-600">Acesso rápido (demo)</span>
                      <div className="h-px flex-1 bg-slate-800" />
                    </div>
                    <div className="mt-4 grid grid-cols-2 gap-3">
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => fill("admin")}
                        data-testid="fill-admin-button"
                        className="border-slate-700 bg-slate-900/50 text-slate-200 transition-all hover:border-primary/40 hover:bg-slate-800 hover:-translate-y-0.5"
                      >
                        Admin
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => fill("gestor")}
                        data-testid="fill-gestor-button"
                        className="border-slate-700 bg-slate-900/50 text-slate-200 transition-all hover:border-primary/40 hover:bg-slate-800 hover:-translate-y-0.5"
                      >
                        Gestor
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
