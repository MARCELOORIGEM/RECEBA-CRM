import { useState } from "react";
import { BadgeCheck, Bike, Zap } from "lucide-react";
import { Logo } from "@/components/Logo";

/* Mascote da Keeta. É arte da marca deles, então entra como arquivo de imagem
   em `frontend/public/` — não como desenho feito aqui.

   Tenta as extensões comuns em sequência: quem salva o arquivo não deveria
   precisar acertar png contra jpg. Esgotadas as opções, o componente some em
   silêncio, em vez de deixar um ícone de imagem quebrada na tela. */
const ARQUIVOS_MASCOTE = [
  "/keeta-mascote.png",
  "/keeta-mascote.webp",
  "/keeta-mascote.jpg",
  "/keeta-mascote.jpeg",
  "/keeta-mascote.svg",
];

export function MascoteKeeta({ altura = 64, className = "" }) {
  const [tentativa, setTentativa] = useState(0);
  if (tentativa >= ARQUIVOS_MASCOTE.length) return null;
  return (
    <img
      key={ARQUIVOS_MASCOTE[tentativa]}
      src={ARQUIVOS_MASCOTE[tentativa]}
      alt="Mascote Keeta"
      style={{ height: altura }}
      onError={() => setTentativa((t) => t + 1)}
      className={`w-auto shrink-0 select-none object-contain ${className}`}
      draggable="false"
    />
  );
}

/**
 * Parceria oficial Keeta.
 *
 * O verde e o amarelo aparecem SÓ aqui: o dourado continua sendo a cor do
 * sistema. Misturar as duas paletas pela interface inteira apagaria as duas.
 */

/** Marca Keeta em texto — a fonte é a do sistema, com o peso do wordmark. */
export function MarcaKeeta({ className = "" }) {
  return (
    <span className={`font-heading font-extrabold tracking-tight ${className}`}>Keeta</span>
  );
}

/** Selo compacto, para a barra do topo. */
export function SeloKeeta({ className = "" }) {
  return (
    <span
      className={`items-center gap-2 rounded-full border border-keeta/30 bg-keeta/10 px-3 py-1.5 ${className}`}
      data-testid="selo-keeta"
    >
      <BadgeCheck className="h-3.5 w-3.5 shrink-0 text-keeta-light" aria-hidden="true" />
      <span className="whitespace-nowrap text-[11px] font-semibold text-slate-300">
        Parceiro Oficial
      </span>
      <MarcaKeeta className="text-sm text-keeta-light" />
    </span>
  );
}

/**
 * Faixa da parceria, no mesmo espírito do banner impresso: fundo escuro,
 * curvas verdes e amarelas à direita, Miliano à esquerda e Keeta do outro lado
 * de um divisor.
 */
export function FaixaKeeta({ className = "" }) {
  return (
    <div
      className={`relative overflow-hidden rounded-xl border border-slate-800 bg-slate-900 ${className}`}
      data-testid="faixa-keeta"
    >
      {/* Curvas da marca. Ficam à direita para não passar por cima do texto. */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute -right-24 -top-32 h-80 w-80 rounded-full bg-keeta/20 blur-3xl" />
        <div className="absolute -bottom-28 right-10 h-64 w-64 rounded-full bg-keeta-yellow/15 blur-3xl" />
        <svg
          className="absolute right-0 top-0 h-full w-1/2 opacity-70"
          viewBox="0 0 400 200"
          preserveAspectRatio="none"
          fill="none"
        >
          <path d="M180 -40 C 300 40, 300 160, 200 240" stroke="#00A862" strokeWidth="26" opacity="0.35" />
          <path d="M240 -40 C 360 40, 360 160, 260 240" stroke="#FFD400" strokeWidth="18" opacity="0.3" />
        </svg>
      </div>

      <div className="relative flex flex-wrap items-center gap-x-6 gap-y-4 p-5 pb-0 sm:p-6 sm:pb-0">
        <Logo tamanho="sm" />

        <div className="hidden h-12 w-px bg-slate-700 sm:block" />

        <div className="flex min-w-0 items-center gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
              Parceiro Oficial
            </p>
            <MarcaKeeta className="text-3xl text-keeta-light" />
          </div>
          <MascoteKeeta altura={104} className="-mb-1 self-end" />
        </div>

        <ul className="ml-auto mb-5 flex flex-wrap items-center gap-2 sm:mb-6">
          <li className="flex items-center gap-1.5 rounded-lg border border-keeta/25 bg-keeta/10 px-3 py-1.5 text-xs text-slate-300">
            <Bike className="h-3.5 w-3.5 text-keeta-light" aria-hidden="true" />
            Entregas integradas
          </li>
          <li className="flex items-center gap-1.5 rounded-lg border border-keeta-yellow/25 bg-keeta-yellow/10 px-3 py-1.5 text-xs text-slate-300">
            <Zap className="h-3.5 w-3.5 text-keeta-yellow" aria-hidden="true" />
            Repasse automático
          </li>
          <li className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs text-slate-300">
            <BadgeCheck className="h-3.5 w-3.5 text-keeta-light" aria-hidden="true" />
            Credenciamento oficial
          </li>
        </ul>
      </div>
    </div>
  );
}

/** Cabeçalho do formulário público, nas cores da parceria. */
export function TopoKeeta() {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-slate-800 bg-slate-900">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute -right-20 -top-24 h-64 w-64 rounded-full bg-keeta/25 blur-3xl" />
        <div className="absolute -bottom-24 -left-16 h-56 w-56 rounded-full bg-keeta-yellow/15 blur-3xl" />
      </div>
      <div className="relative flex flex-col items-center gap-4 px-6 py-7">
        <div className="flex items-center gap-4">
          <Logo tamanho="md" brilho />
          <div className="h-12 w-px bg-slate-700" aria-hidden="true" />
          <MascoteKeeta altura={92} />
        </div>
        <div className="flex items-center gap-2 rounded-full border border-keeta/30 bg-keeta/10 px-4 py-1.5">
          <BadgeCheck className="h-4 w-4 text-keeta-light" aria-hidden="true" />
          <span className="text-xs font-semibold text-slate-300">Parceiro Oficial</span>
          <MarcaKeeta className="text-base text-keeta-light" />
        </div>
      </div>
      {/* Fita verde-amarela fechando o cabeçalho. */}
      <div
        aria-hidden="true"
        className="h-1.5 bg-gradient-to-r from-keeta via-keeta-yellow to-keeta"
      />
    </div>
  );
}
