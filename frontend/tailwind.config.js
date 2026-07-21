/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{ts,tsx}', './index.html'],
  theme: {
    extend: {
      colors: {
        primary: {
          50:  '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          800: '#1e293b',
          900: '#0f172a',
          950: '#020617',
        },
        accent: {
          50:  '#fffbeb',
          100: '#fef3c7',
          200: '#fde68a',
          300: '#fcd34d',
          400: '#fbbf24',
          500: '#f59e0b',
          600: '#d97706',
          700: '#b45309',
          800: '#92400e',
          900: '#78350f',
          950: '#451a03',
        },
        success: {
          400: '#4ade80',
          500: '#22c55e',
          600: '#16a34a',
        },
        warning: {
          400: '#fbbf24',
          500: '#f59e0b',
          600: '#d97706',
        },
        danger: {
          400: '#f87171',
          500: '#ef4444',
          600: '#dc2626',
        },
        surface: {
          950: '#030303',
          900: '#08080a',
          800: '#0e0e12',
          700: '#18181b',
          600: '#27272a',
          500: '#3f3f46',
        },
        neon: '#64748b',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-conic':  'conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))',
      },
      animation: {
        'pulse-slow':    'pulse 4s cubic-bezier(0.4,0,0.6,1) infinite',
        'glow-pulse':    'glow-pulse 2.5s ease-in-out infinite',
        'fade-in':       'fadeIn 0.3s ease-out',
        'slide-in':      'slideIn 0.3s ease-out',
        'spin-slow':     'spin 4s linear infinite',
      },
      keyframes: {
        'glow-pulse': {
          '0%, 100%': { boxShadow: '0 0 5px rgba(255,255,255,0.1)' },
          '50%':       { boxShadow: '0 0 15px rgba(255,255,255,0.2)' },
        },
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        slideIn: {
          from: { opacity: '0', transform: 'translateX(-12px)' },
          to:   { opacity: '1', transform: 'translateX(0)' },
        },
      },
      backdropBlur: {
        xs: '2px',
      },
      boxShadow: {
        'glow-green':  '0 0 15px rgba(34,197,94,0.25)',
        'glow-red':    '0 0 15px rgba(239,68,68,0.25)',
        'glow-yellow': '0 0 15px rgba(245,158,11,0.25)',
        'glow-cyan':   '0 0 15px rgba(148,163,184,0.2)',
        'glow-purple': '0 0 15px rgba(100,116,139,0.2)',
        'card':        '0 4px 20px -2px rgba(0,0,0,0.5), 0 2px 8px -1px rgba(0,0,0,0.3)',
        'card-hover':  '0 12px 24px -4px rgba(0,0,0,0.6), 0 4px 12px -2px rgba(0,0,0,0.4)',
      },
    },
  },
  plugins: [],
}
