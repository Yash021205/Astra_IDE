/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Semantic surfaces driven by CSS variables (globals.css) so the whole
        // app re-themes between light and dark with one class on <html>.
        bg:      'rgb(var(--c-bg) / <alpha-value>)',
        surface: 'rgb(var(--c-surface) / <alpha-value>)',
        raised:  'rgb(var(--c-raised) / <alpha-value>)',
        edge:    'rgb(var(--c-edge) / <alpha-value>)',
        'edge-strong': 'rgb(var(--c-edge-strong) / <alpha-value>)',
        ink:     'rgb(var(--c-ink) / <alpha-value>)',
        muted:   'rgb(var(--c-muted) / <alpha-value>)',
        faint:   'rgb(var(--c-faint) / <alpha-value>)',
        // Primary accent — sage→deep-green scale (9CB080 · 618764 · 2B5748 ·
        // 273338). Shared brand/action color across light + dark themes.
        astra: {
          50:  '#eef3ec',
          100: '#dbe7d6',
          200: '#c0d4b8',
          300: '#9CB080',   // sage
          400: '#7c9a72',
          500: '#618764',   // green
          600: '#4c6e54',
          700: '#2B5748',   // deep teal-green — primary on light
          800: '#244a3d',
          900: '#273338',   // dark slate
        },
        // Secondary accent — soft blush/petal pastels for highlights + gradients.
        blossom: {
          100: '#fff1e6',   // linen
          200: '#fde2e4',   // soft blush
          300: '#fad2e1',   // petal frost
          400: '#f4b8cf',
          500: '#e891ad',
          600: '#d96f93',
        },
      },
      fontFamily: {
        sans:  ['var(--font-sans)',  'Inter', 'system-ui', 'sans-serif'],
        serif: ['var(--font-serif)', 'Source Serif 4', 'Georgia', 'serif'],
        mono:  ['var(--font-mono)',  'Source Code Pro', 'JetBrains Mono', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px 0 rgb(0 0 0 / 0.04), 0 1px 6px -1px rgb(0 0 0 / 0.06)',
        pop:  '0 10px 38px -10px rgb(2 6 23 / 0.35), 0 10px 20px -15px rgb(2 6 23 / 0.2)',
      },
    },
  },
  plugins: [],
};
