/** @type {import('tailwindcss').Config} */

// Every colour comes from a CSS variable defined in src/index.css (:root = light, .dark = dark),
// stored as "r g b" so Tailwind opacity modifiers (bg-ink/10) keep working in both themes.
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  darkMode: 'class',
  content: ['./src/**/*.{ts,tsx}', './index.html'],
  theme: {
    extend: {
      colors: {
        page:       token('page'),        // app background
        surface:    token('surface'),     // cards, inputs, sidebar
        subtle:     token('subtle'),      // hover and selected fills
        line:       token('line'),        // hairline borders
        strong:     token('line-strong'), // emphasised borders, scrollbar
        ink:        token('ink'),         // primary text
        muted:      token('muted'),       // secondary text
        faint:      token('faint'),       // tertiary text, placeholders
        accent:     token('accent'),      // primary button fill
        'accent-fg': token('accent-fg'),  // text on the primary button
        brand:      token('brand'),
        ok:         token('ok'),
        warn:       token('warn'),
        bad:        token('bad'),
        info:       token('info'),
        'sig-red':    token('sig-red'),   // signal lamps (vivid in both themes)
        'sig-yellow': token('sig-yellow'),
        'sig-green':  token('sig-green'),
      },
      fontFamily: {
        sans: ['"Geist Variable"', 'ui-sans-serif', 'system-ui', '-apple-system', '"Segoe UI"', 'sans-serif'],
        mono: ['"Geist Mono Variable"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px rgb(var(--ink) / 0.04), 0 4px 16px -6px rgb(var(--ink) / 0.06)',
      },
      fontSize: {
        '2xs': ['11px', '16px'],
      },
    },
  },
  plugins: [],
}
