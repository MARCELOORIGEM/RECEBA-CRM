/**
 * Marca Miliano Business Solutions — a arte oficial, não uma recriação.
 *
 * A imagem vem do PDF da marca ("LOGO MILIANO ILUMINADO (PRINCIPAL)", na pasta
 * `logo/`). O original é uma foto com o letreiro aceso sobre fundo preto
 * texturizado; o fundo foi retirado e virou transparência, mantendo o brilho
 * dourado como luz semitransparente. Por isso o logo foi feito para fundo
 * ESCURO — que é o do painel inteiro. Sobre branco, o prateado some.
 *
 * Arquivos em `frontend/public/`: WebP (leve) e PNG de reserva, ambos com
 * 1000 px de largura, o bastante para tela retina no maior tamanho.
 */

// Largura / altura da arte recortada. Reservar a proporção evita que a página
// pule quando a imagem termina de carregar.
const PROPORCAO = 1000 / 470;

const MASCARA = {
  WebkitMaskImage: "url(/miliano-logo.png)",
  maskImage: "url(/miliano-logo.png)",
};

// Altura em px por tamanho. A largura sai da proporção.
const ALTURAS = { sm: 44, md: 72, lg: 112, xl: 150 };

export function Logo({ tamanho = "md", brilho = false, className = "" }) {
  const altura = ALTURAS[tamanho] || ALTURAS.md;

  return (
    <span
      className={`relative inline-block shrink-0 ${className}`}
      style={{ height: altura, width: Math.round(altura * PROPORCAO) }}
    >
      <picture>
        <source srcSet="/miliano-logo.webp" type="image/webp" />
        <img
          src="/miliano-logo.png"
          alt="Miliano Business Solutions"
          width={1000}
          height={470}
          className="h-full w-full select-none object-contain"
          draggable="false"
        />
      </picture>
      {/* Faixa de luz passando pelo letreiro, recortada no formato do próprio
          logo (mask-image com a mesma imagem): ilumina só o desenho, nunca o
          fundo. Enfeite — respeita prefers-reduced-motion (index.css). */}
      {brilho && (
        <span
          aria-hidden="true"
          className="logo-brilho animate-shine absolute inset-0"
          style={MASCARA}
        />
      )}
    </span>
  );
}

export default Logo;
