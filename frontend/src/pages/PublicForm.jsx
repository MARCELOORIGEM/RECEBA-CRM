import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { AlertCircle, CheckCircle2, Loader2, Send } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { TopoKeeta } from "@/components/Keeta";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

// Precisa bater com CAMPO_ISCA em backend/app/routers/public.py.
const CAMPO_ISCA = "_website";

const TIPO_HTML = {
  email: "email",
  telefone: "tel",
  numero: "number",
  data: "date",
  cpf: "text",
};

/** A opção "Outro" está escolhida quando existe texto livre no campo auxiliar. */
const ehOutro = (campo, valores) =>
  campo.allow_other && (valores[`${campo.key}__outro`] ?? "") !== "";

/**
 * Página pública do formulário.
 *
 * Fica fora da área autenticada: quem abre este link não tem conta e não deve
 * precisar de uma. Por isso o `api` é usado sem sessão e nada aqui expõe dados
 * internos — o backend devolve só título, descrição e campos.
 */
export default function PublicForm() {
  const { slug } = useParams();
  const [form, setForm] = useState(null);
  const [erroCarga, setErroCarga] = useState("");
  const [valores, setValores] = useState({});
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");
  const [sucesso, setSucesso] = useState("");
  // O backend recusa o envio sem o aceite quando há aviso de privacidade.
  const [aceite, setAceite] = useState(false);

  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const { data } = await api.get(`/public/forms/${slug}`);
        if (!vivo) return;
        setForm(data);
        document.title = `${data.title} • Miliano`;
      } catch (e) {
        if (vivo) setErroCarga(apiError(e, "Formulário indisponível."));
      }
    })();
    return () => {
      vivo = false;
    };
  }, [slug]);

  // Texto do aviso de privacidade, vindo da API (PRIVACIDADE_URL/_TEXTO no
  // ambiente). Vazio = instalação sem aviso, e aí não há o que aceitar.
  const aviso = form?.privacidade?.texto || "";

  const enviar = async (e) => {
    e.preventDefault();
    setEnviando(true);
    setErro("");
    try {
      // Os campos auxiliares do "Outro" são só da tela; o que vai para a API
      // é o valor final do campo.
      const respostas = Object.fromEntries(
        Object.entries(valores).filter(([k]) => !k.endsWith("__outro")),
      );
      if (aviso) respostas._consentimento = true;
      const { data } = await api.post(`/public/forms/${slug}`, { respostas });
      setSucesso(data.message);
    } catch (err) {
      setErro(apiError(err, "Não foi possível enviar. Tente novamente."));
    } finally {
      setEnviando(false);
    }
  };

  const Moldura = ({ children }) => (
    <div className="relative min-h-screen overflow-hidden bg-slate-950 text-slate-100">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute -top-40 left-1/2 h-[30rem] w-[30rem] -translate-x-1/2 rounded-full bg-keeta/15 blur-[130px] animate-pulse-glow" />
        <div className="absolute -bottom-44 right-0 h-[26rem] w-[26rem] rounded-full bg-keeta-yellow/10 blur-[130px] animate-pulse-glow" style={{ animationDelay: "-2s" }} />
      </div>
      <div className="relative z-10 mx-auto flex min-h-screen max-w-2xl flex-col px-5 py-10 sm:py-14">
        <header className="mb-6">
          <TopoKeeta />
        </header>
        {children}
        <footer className="mt-10 text-center text-xs text-slate-600">
          Miliano Business Solutions · Parceiro Oficial Keeta
        </footer>
      </div>
    </div>
  );

  if (erroCarga) {
    return (
      <Moldura>
        <div
          className="rounded-2xl border border-slate-800 bg-slate-900/70 p-8 text-center backdrop-blur-xl"
          data-testid="public-form-error"
        >
          <AlertCircle className="mx-auto mb-3 h-10 w-10 text-amber-500" aria-hidden="true" />
          <h1 className="font-heading text-xl font-bold text-slate-50">Formulário indisponível</h1>
          <p className="mt-2 text-sm text-slate-400">{erroCarga}</p>
        </div>
      </Moldura>
    );
  }

  if (!form) {
    return (
      <Moldura>
        <div className="flex justify-center py-20" role="status" aria-label="Carregando">
          <Loader2 className="h-7 w-7 animate-spin text-keeta-light" />
        </div>
      </Moldura>
    );
  }

  if (sucesso) {
    return (
      <Moldura>
        <div
          className="animate-fade-up rounded-2xl border border-keeta/30 bg-slate-900/70 p-8 text-center backdrop-blur-xl"
          data-testid="public-form-success"
        >
          <CheckCircle2 className="mx-auto mb-4 h-14 w-14 text-keeta-light" aria-hidden="true" />
          <h1 className="font-heading text-2xl font-bold text-slate-50">Tudo certo!</h1>
          <p className="mt-2 text-slate-400">{sucesso}</p>
        </div>
      </Moldura>
    );
  }

  return (
    <Moldura>
      <div
        className="animate-fade-up rounded-2xl border border-slate-800 bg-slate-900/70 p-6 sm:p-8 backdrop-blur-xl"
        data-testid="public-form"
      >
        <h1 className="font-heading text-2xl sm:text-3xl font-bold text-slate-50">{form.title}</h1>
        {form.description && (
          <p className="mt-2 text-sm leading-relaxed text-slate-400">{form.description}</p>
        )}

        <form onSubmit={enviar} className="mt-7 space-y-5">
          {form.fields.map((campo) => {
            const id = `campo-${campo.key}`;
            const comum = {
              id,
              required: campo.required,
              value: valores[campo.key] ?? "",
              onChange: (e) => setValores((v) => ({ ...v, [campo.key]: e.target.value })),
              placeholder: campo.placeholder || "",
              className: "bg-slate-950/60 border-slate-700 text-slate-100",
              "data-testid": `public-field-${campo.key}`,
            };

            return (
              <div key={campo.key} className="space-y-1.5">
                <Label htmlFor={id} className="text-slate-300">
                  {campo.label}
                  {campo.required && (
                    <span className="ml-1 text-keeta-light" aria-hidden="true">
                      *
                    </span>
                  )}
                </Label>

                {campo.type === "textarea" ? (
                  <Textarea {...comum} rows={3} />
                ) : campo.type === "escolha" ? (
                  /* Múltipla escolha com poucas opções: botões à mostra são
                     mais rápidos que abrir uma lista, ainda mais no celular. */
                  <div
                    role="radiogroup"
                    aria-label={campo.label}
                    data-testid={`public-field-${campo.key}`}
                    className="flex flex-wrap gap-2"
                  >
                    {(campo.options || []).map((o) => {
                      const marcada = valores[campo.key] === o;
                      return (
                        <button
                          key={o}
                          type="button"
                          role="radio"
                          aria-checked={marcada}
                          data-testid={`public-option-${campo.key}-${o}`}
                          onClick={() =>
                            setValores((x) => ({ ...x, [campo.key]: o, [`${campo.key}__outro`]: "" }))
                          }
                          className={`rounded-lg border px-4 py-2.5 text-sm transition-colors ${
                            marcada
                              ? "border-keeta bg-keeta/15 font-semibold text-keeta-light"
                              : "border-slate-700 bg-slate-950/60 text-slate-300 hover:border-slate-600"
                          }`}
                        >
                          {o}
                        </button>
                      );
                    })}

                    {/* "Outro:" com escrita livre, como no Google Forms. O que
                        a pessoa digita vira o valor do campo — uma lista de
                        bancos que não previsse o banco dela a deixaria sem
                        como responder. */}
                    {campo.allow_other && (
                      <div className="flex w-full items-center gap-2">
                        <button
                          type="button"
                          role="radio"
                          aria-checked={ehOutro(campo, valores)}
                          data-testid={`public-option-${campo.key}-outro`}
                          onClick={() =>
                            setValores((x) => ({ ...x, [campo.key]: "", [`${campo.key}__outro`]: " " }))
                          }
                          className={`shrink-0 rounded-lg border px-4 py-2.5 text-sm transition-colors ${
                            ehOutro(campo, valores)
                              ? "border-keeta bg-keeta/15 font-semibold text-keeta-light"
                              : "border-slate-700 bg-slate-950/60 text-slate-300 hover:border-slate-600"
                          }`}
                        >
                          Outro:
                        </button>
                        {ehOutro(campo, valores) && (
                          <Input
                            autoFocus
                            aria-label={`${campo.label} — outro`}
                            data-testid={`public-other-${campo.key}`}
                            value={(valores[`${campo.key}__outro`] || "").trimStart()}
                            onChange={(e) =>
                              setValores((x) => ({
                                ...x,
                                [`${campo.key}__outro`]: e.target.value || " ",
                                [campo.key]: e.target.value.trim(),
                              }))
                            }
                            className="h-11 border-slate-700 bg-slate-950/60 text-slate-100"
                          />
                        )}
                      </div>
                    )}
                  </div>
                ) : campo.type === "selecao" ? (
                  <Select
                    value={valores[campo.key] ?? ""}
                    onValueChange={(v) => setValores((x) => ({ ...x, [campo.key]: v }))}
                  >
                    <SelectTrigger
                      className="bg-slate-950/60 border-slate-700 text-slate-100"
                      data-testid={`public-field-${campo.key}`}
                      aria-label={campo.label}
                    >
                      <SelectValue placeholder="Selecione" />
                    </SelectTrigger>
                    <SelectContent>
                      {(campo.options || []).map((o) => (
                        <SelectItem key={o} value={o}>
                          {o}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : campo.type === "cpf" ? (
                  /* Teclado numérico no celular e só dígitos no valor — o
                     campo pede "11 números, sem pontos ou traços". */
                  <Input
                    {...comum}
                    type="text"
                    inputMode="numeric"
                    /* Sem `maxLength` no input: ele cortaria "529.982.247-25"
                       em 11 CARACTERES antes de a máscara tirar os pontos, e
                       sobrariam 9 dígitos. O corte acontece só depois. */
                    onChange={(e) =>
                      setValores((v) => ({
                        ...v,
                        [campo.key]: e.target.value.replace(/\D/g, "").slice(0, 11),
                      }))
                    }
                    className={`h-11 ${comum.className}`}
                  />
                ) : (
                  <Input
                    {...comum}
                    type={TIPO_HTML[campo.type] || "text"}
                    className={`h-11 ${comum.className}`}
                  />
                )}

                {campo.help && <p className="text-xs text-slate-600">{campo.help}</p>}
              </div>
            );
          })}

          {/* Isca: invisível e fora da ordem de tabulação. Pessoa nenhuma
              preenche; robô que varre o formulário preenche tudo. */}
          <div className="absolute left-[-9999px]" aria-hidden="true">
            <label htmlFor={CAMPO_ISCA}>Não preencha este campo</label>
            <input
              id={CAMPO_ISCA}
              name={CAMPO_ISCA}
              type="text"
              tabIndex={-1}
              autoComplete="off"
              value={valores[CAMPO_ISCA] ?? ""}
              onChange={(e) => setValores((v) => ({ ...v, [CAMPO_ISCA]: e.target.value }))}
            />
          </div>

          {aviso && (
            <label
              className="flex cursor-pointer gap-3 rounded-xl border border-slate-800 bg-slate-950/50 p-4 text-xs leading-relaxed text-slate-400"
              data-testid="public-form-consentimento"
            >
              <input
                type="checkbox"
                required
                checked={aceite}
                onChange={(e) => setAceite(e.target.checked)}
                data-testid="public-form-aceite"
                className="mt-0.5 h-4 w-4 shrink-0 accent-[#00A862]"
              />
              <span>
                {aviso}{" "}
                {form.privacidade?.url && (
                  <a
                    href={form.privacidade.url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-semibold text-keeta-light underline underline-offset-2"
                  >
                    Ler a política de privacidade
                  </a>
                )}
              </span>
            </label>
          )}

          {erro && (
            <p
              role="alert"
              className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2.5 text-sm text-red-400"
              data-testid="public-form-erro"
            >
              {erro}
            </p>
          )}

          <Button
            type="submit"
            disabled={enviando || (!!aviso && !aceite)}
            data-testid="public-form-submit"
            className="group h-12 w-full gap-2 bg-gradient-to-r from-keeta via-keeta-light to-keeta-yellow font-semibold text-slate-950 transition-all hover:shadow-[0_0_30px_-6px_rgba(0,168,98,0.65)]"
          >
            {enviando ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <>
                Enviar cadastro
                <Send className="h-4 w-4 transition-transform group-hover:translate-x-1" aria-hidden="true" />
              </>
            )}
          </Button>
        </form>
      </div>
    </Moldura>
  );
}
