// Config de Tailwind v3.4.17 (la compila scripts/compilar_css.py).
//
// Los colores de la paleta salen de variables CSS (css/paleta.css, generado por
// scripts/generar_paleta.py): bg-slate-900 compila a rgb(var(--au-slate-900) / 1), así que
// sigue viéndose igual en el tema oscuro y cambia solo en el claro. Las opacidades
// (bg-slate-950/70) siguen funcionando por <alpha-value>.

const TONOS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];
const FAMILIAS = [
  'slate', 'gray', 'red', 'orange', 'amber', 'yellow', 'lime', 'green', 'emerald', 'teal',
  'cyan', 'sky', 'blue', 'indigo', 'violet', 'purple', 'fuchsia', 'pink', 'rose',
];

const variable = (nombre) => `rgb(var(--au-${nombre}) / <alpha-value>)`;
const familia = (nombre) => Object.fromEntries(TONOS.map((tono) => [tono, variable(`${nombre}-${tono}`)]));

module.exports = {
  content: [
    './src/aulento/web/static/**/*.{html,js}',
    '!./src/aulento/web/static/vendor/**',
  ],
  // Clases que se arman en tiempo de ejecución y el escaneo no ve:
  // el punto de color de cada plataforma (pantalla-courses.js: bg-${icono_color}-400).
  safelist: [
    { pattern: /^bg-(sky|emerald|amber|rose|indigo|purple|cyan|orange|green|blue)-400$/ },
  ],
  theme: {
    extend: {
      colors: {
        ...Object.fromEntries(FAMILIAS.map((nombre) => [nombre, familia(nombre)])),
        white: variable('blanco'),
        black: variable('negro'),
        // Alias semánticos para código nuevo: bg-superficie, text-texto-suave, border-borde...
        fondo: 'var(--au-fondo)',
        superficie: {
          DEFAULT: 'var(--au-superficie)',
          alta: 'var(--au-superficie-alta)',
          hundida: 'var(--au-superficie-hundida)',
        },
        borde: {
          DEFAULT: 'var(--au-borde)',
          fuerte: 'var(--au-borde-fuerte)',
        },
        texto: {
          DEFAULT: 'var(--au-texto)',
          titulo: 'var(--au-texto-titulo)',
          suave: 'var(--au-texto-suave)',
          tenue: 'var(--au-texto-tenue)',
        },
        primario: {
          DEFAULT: 'var(--au-primario)',
          texto: 'var(--au-primario-texto)',
          suave: 'var(--au-primario-suave)',
        },
      },
    },
  },
};
