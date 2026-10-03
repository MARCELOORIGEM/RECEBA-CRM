/**
 * Marca Miliano Business Solutions.
 *
 * Reproduz os três elementos do logo impresso: o arco dourado que envolve o
 * letreiro, "Miliano" em script cromado e a assinatura "BUSINESS SOLUTIONS"
 * com a divisão prata/dourado.
 *
 * O brilho que percorre o letreiro é enfeite e respeita
 * `prefers-reduced-motion` (regra global em index.css).
 */

// `recuo` é o quanto o letreiro entra por cima do arco: no logo original o
// arco envolve o "M", não fica ao lado dele.
// `espaco` separa a assinatura do letreiro. Nos tamanhos pequenos a descida
// da fonte script encosta em "BUSINESS SOLUTIONS" se a margem for negativa.
const TAMANHOS = {
  sm: { fonte: "text-2xl", assinatura: "text-[7px]", arco: 46, recuo: 26, espaco: "mt-1" },
  md: { fonte: "text-4xl", assinatura: "text-[9px]", arco: 70, recuo: 40, espaco: "mt-0.5" },
  lg: { fonte: "text-6xl", assinatura: "text-[11px]", arco: 104, recuo: 58, espaco: "-mt-1" },
  xl: { fonte: "text-7xl sm:text-8xl", assinatura: "text-xs", arco: 134, recuo: 74, espaco: "-mt-2" },
};

/** Arco dourado do logo — meia-lua aberta à direita, com brilho nas pontas. */
export function ArcoMiliano({ size = 48, className = "", style, animado = false }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      aria-hidden="true"
      className={className}
      style={style}
    >
      <defs>
        <linearGradient id="arco-dourado" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#FFD28F" />
          <stop offset="45%" stopColor="#F5A524" />
          <stop offset="100%" stopColor="#C97F10" />
        </linearGradient>
        <filter id="arco-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2.5" result="borrado" />
          <feMerge>
            <feMergeNode in="borrado" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <path
        d="M72 14 A42 42 0 1 0 84 74"
        stroke="url(#arco-dourado)"
        strokeWidth="5.5"
        strokeLinecap="round"
        filter="url(#arco-glow)"
        strokeDasharray={animado ? 1000 : undefined}
        className={animado ? "animate-draw-arc" : undefined}
      />
    </svg>
  );
}

export function Logo({ tamanho = "md", assinatura = true, brilho = false, className = "" }) {
  const t = TAMANHOS[tamanho] || TAMANHOS.md;

  return (
    <div className={`relative inline-block ${className}`}>
      <div className="relative min-w-0" style={{ paddingLeft: t.recuo }}>
        {/* O arco é centrado no LETREIRO, não no bloco inteiro. Centrado no
            bloco, ele descia e cruzava "BUSINESS SOLUTIONS". */}
        <div className="relative leading-none">
          {/* Sem z-index negativo: `-z-10` mandava o arco para trás do fundo
              do cartão e ele sumia sempre que o logo ficava sobre uma
              superfície preenchida. O letreiro sobe para z-10 em vez disso. */}
          <ArcoMiliano
            size={t.arco}
            animado={brilho}
            className="absolute top-1/2 -translate-y-1/2"
            style={{ left: -t.recuo }}
          />
          {/* A fonte script tem traço longo à direita; sem o padding ele é
              cortado pelo recorte do gradiente. */}
          <span
            className={`relative z-10 font-script ${t.fonte} texto-prata block leading-[1.25] pr-2`}
          >
            Miliano
          </span>
          {brilho && (
            <span
              aria-hidden="true"
              className={`font-script ${t.fonte} brilho-passante absolute inset-0 z-10 leading-[1.25] pr-2`}
            >
              Miliano
            </span>
          )}
        </div>

        {assinatura && (
          <p
            className={`relative z-10 ${t.assinatura} font-semibold tracking-[0.3em] uppercase whitespace-nowrap ${t.espaco} pl-1`}
          >
            <span className="text-silver-dark">Business </span>
            <span className="text-primary">Solutions</span>
          </p>
        )}
      </div>
    </div>
  );
}

export default Logo;
