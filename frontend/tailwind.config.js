/** @type {import('tailwindcss').Config} */
module.exports = {
    // `overline` is a Tailwind utility; without this an app's own eyebrow-label class draws a line above the text.
    blocklist: ["overline"],
    darkMode: ["class"],
    content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "./public/index.html"
  ],
  theme: {
    extend: {
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)'
      },
      colors: {
        // ----------------------------------------------------------------
        // Identidade Miliano: grafite quente + dourado + prata.
        //
        // As rampas `slate` e `orange` do Tailwind são redefinidas de
        // propósito. A interface já usava essas classes em ~600 lugares;
        // renomear uma a uma seria churn puro, com risco de erro de digitação
        // e nenhum ganho. O tema troca o VALOR por trás do nome.
        //
        // Ou seja: `slate-*` aqui é o grafite da marca, não o azulado padrão
        // do Tailwind, e `orange-*` é o dourado do logo.
        // ----------------------------------------------------------------
        slate: {
          50: '#F7F7F8',
          100: '#EDEEF0',
          200: '#D7D9DD',
          300: '#B4B7BE',
          400: '#8B8F98',
          500: '#6B6F78',
          600: '#4E525A',
          700: '#363940',
          800: '#24262B',
          900: '#16171A',
          950: '#0C0D0F'
        },
        orange: {
          300: '#FFD28F',
          400: '#FFC15E',
          500: '#F5A524',
          600: '#DB8E0F',
          700: '#B0700A'
        },
        // Prata do letreiro, para realces e gradientes.
        silver: {
          DEFAULT: '#D8DBE0',
          light: '#F2F3F5',
          dark: '#9AA0A8'
        },
        gold: {
          DEFAULT: '#F5A524',
          light: '#FFC15E',
          glow: '#FFB84D',
          dark: '#C97F10'
        },
        // Parceria oficial Keeta: verde e amarelo da marca deles, usados só
        // onde a parceria aparece — o dourado segue sendo a cor do sistema.
        keeta: {
          DEFAULT: '#00A862',
          dark: '#00794A',
          light: '#3FCB8E',
          yellow: '#FFD400',
          'yellow-dark': '#E0B700'
        },

        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))'
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))'
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))'
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))'
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))'
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))'
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))'
        },
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        chart: {
          '1': 'hsl(var(--chart-1))',
          '2': 'hsl(var(--chart-2))',
          '3': 'hsl(var(--chart-3))',
          '4': 'hsl(var(--chart-4))',
          '5': 'hsl(var(--chart-5))'
        }
      },
      fontFamily: {
        script: ['Yellowtail', 'cursive']
      },
      backgroundImage: {
        // Cromado do letreiro: claro no topo, sombra no meio, brilho embaixo.
        'silver-sheen':
          'linear-gradient(180deg, #FFFFFF 0%, #D8DBE0 38%, #8B8F98 55%, #EDEEF0 78%, #B4B7BE 100%)',
        'gold-sheen':
          'linear-gradient(180deg, #FFD28F 0%, #F5A524 45%, #C97F10 70%, #FFC15E 100%)'
      },
      keyframes: {
        'accordion-down': {
          from: {
            height: '0'
          },
          to: {
            height: 'var(--radix-accordion-content-height)'
          }
        },
        'accordion-up': {
          from: {
            height: 'var(--radix-accordion-content-height)'
          },
          to: {
            height: '0'
          }
        },
        // Brilho que percorre o letreiro, como a luz no logo impresso.
        shine: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' }
        },
        'pulse-glow': {
          '0%, 100%': { opacity: '0.35' },
          '50%': { opacity: '0.75' }
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' }
        },
        'draw-arc': {
          from: { strokeDashoffset: '1000' },
          to: { strokeDashoffset: '0' }
        },
        // Manchas de luz que vagam pelo fundo, em ritmos diferentes para que
        // o conjunto nunca repita o mesmo desenho.
        'aurora-a': {
          '0%, 100%': { transform: 'translate3d(0,0,0) scale(1)' },
          '33%': { transform: 'translate3d(8%, 12%, 0) scale(1.18)' },
          '66%': { transform: 'translate3d(-6%, 6%, 0) scale(0.92)' }
        },
        'aurora-b': {
          '0%, 100%': { transform: 'translate3d(0,0,0) scale(1.05)' },
          '40%': { transform: 'translate3d(-12%, -8%, 0) scale(0.9)' },
          '75%': { transform: 'translate3d(6%, -14%, 0) scale(1.2)' }
        },
        // Fagulhas subindo, como brasa. Três movimentos independentes, em
        // elementos aninhados: uma transform só não consegue combinar subida,
        // balanço lateral e cintilação em ritmos diferentes.
        subir: {
          '0%': { transform: 'translateY(0)' },
          '100%': { transform: 'translateY(-108vh)' }
        },
        balancar: {
          '0%': { transform: 'translateX(-14px)' },
          '100%': { transform: 'translateX(14px)' }
        },
        cintilar: {
          '0%, 100%': { opacity: '0.15', transform: 'scale(0.75)' },
          '50%': { opacity: '1', transform: 'scale(1.15)' }
        },
        // Sopro lento que atravessa a tela, como poeira pegando a luz.
        sopro: {
          '0%': { transform: 'translateX(-30%)', opacity: '0' },
          '30%, 70%': { opacity: '0.5' },
          '100%': { transform: 'translateX(130%)', opacity: '0' }
        },
        // Fio de luz que dá a volta na borda do cartão.
        'border-spin': {
          from: { transform: 'rotate(0deg)' },
          to: { transform: 'rotate(360deg)' }
        },
        'reveal-up': {
          from: { opacity: '0', transform: 'translateY(18px)' },
          to: { opacity: '1', transform: 'translateY(0)' }
        },
        'gradient-x': {
          '0%, 100%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' }
        },
        'scan-line': {
          '0%': { transform: 'translateY(-100%)', opacity: '0' },
          '50%': { opacity: '0.6' },
          '100%': { transform: 'translateY(2400%)', opacity: '0' }
        }
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        shine: 'shine 6s linear infinite',
        'pulse-glow': 'pulse-glow 4s ease-in-out infinite',
        float: 'float 7s ease-in-out infinite',
        'draw-arc': 'draw-arc 1.6s ease-out forwards',
        'aurora-a': 'aurora-a 22s ease-in-out infinite',
        'aurora-b': 'aurora-b 28s ease-in-out infinite',
        subir: 'subir linear infinite',
        balancar: 'balancar ease-in-out infinite alternate',
        cintilar: 'cintilar ease-in-out infinite',
        sopro: 'sopro linear infinite',
        'border-spin': 'border-spin 8s linear infinite',
        'reveal-up': 'reveal-up 0.7s cubic-bezier(0.22, 1, 0.36, 1) both',
        'gradient-x': 'gradient-x 4s ease infinite',
        'scan-line': 'scan-line 9s ease-in-out infinite'
      }
    }
  },
  plugins: [require("tailwindcss-animate")],
};
