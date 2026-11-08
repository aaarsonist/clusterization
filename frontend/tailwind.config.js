/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Wix Madefor Display"', 'sans-serif'],
        body: ['"Wix Madefor Text"', 'sans-serif'],
        sans: ['"Wix Madefor Text"', 'sans-serif'],
        heading: ['"Wix Madefor Display"', 'sans-serif'],
      },
      colors: {
        dusk: {
          paper: 'var(--dusk-paper)',
          subtle: 'var(--dusk-paper-subtle)',
          glass: 'var(--dusk-glass)',
          ink: 'var(--dusk-ink)',
          muted: 'var(--dusk-ink-muted)',
          rule: 'var(--dusk-rule)',
          periwinkle: 'var(--dusk-periwinkle)',
          'periwinkle-ink': 'var(--dusk-periwinkle-ink)',
          apricot: 'var(--dusk-apricot)',
          'apricot-ink': 'var(--dusk-apricot-ink)',
          sage: 'var(--dusk-sage)',
        },
        accent: {
          DEFAULT: 'var(--dusk-periwinkle)',
          hover: '#8695f7',
          light: '#b4beff',
          dark: '#5a6cf3',
        },
        primary: {
          DEFAULT: '#9ba8ff',
          50: '#f4f6ff',
          100: '#e8ecff',
          200: '#d4dcff',
          300: '#b4beff',
          400: '#9ba8ff',
          500: '#7b8cf9',
          600: '#5a6cf3',
          700: '#4856d8',
          800: '#3b47af',
          900: '#333e8a',
          950: '#12141a',
        },
        catIndigo: '#9ba8ff',
        catCrimson: '#f6a27e',
        catGold: '#e5c07b',
        catEmerald: '#81c79b',
        catSlate: '#8b92a4',
      },
      borderRadius: {
        'dusk-card': 'var(--dusk-radius-card)',
        'dusk-inner': 'var(--dusk-radius-inner)',
        'dusk-pill': 'var(--dusk-radius-pill)',
      },
      boxShadow: {
        'dusk-glass': 'var(--dusk-glass-hi), 0 12px 32px -8px rgba(0, 0, 0, 0.28)',
        'dusk-hi': 'var(--dusk-glass-hi)',
        'dusk-cta': 'inset 0 1px 0 rgba(255, 255, 255, 0.35), 0 4px 14px rgba(155, 168, 255, 0.2)',
      },
    },
  },
  plugins: [],
}
