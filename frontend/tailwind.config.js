/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        panel: 'var(--panel)',
        panel2: 'var(--panel2)',
        raise: 'var(--raise)',
        line: 'var(--line)',
        line2: 'var(--line-strong)',
        ink: 'var(--text)',
        dim: 'var(--dim)',
        faint: 'var(--faint)',
        accent: 'var(--accent)',
        good: 'var(--green)',
        warn: 'var(--amber)',
        crit: 'var(--red)',
        high: 'var(--orange)',
      },
      fontFamily: {
        display: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
};
