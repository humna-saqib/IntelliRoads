import { useTheme, type Theme } from '../context/ThemeContext';

/**
 * Colours for Recharts and SVG drawings, which cannot read Tailwind classes.
 * They mirror the CSS tokens in index.css so charts match the page in both themes.
 */
export interface ChartPalette {
  grid: string;
  axis: string;
  cursor: string;
  ink: string;
  surface: string;
  ok: string;
  warn: string;
  bad: string;
  /** categorical series colours, in order */
  series: [string, string, string, string, string];
}

const PALETTES: Record<Theme, ChartPalette> = {
  light: {
    grid: '#e4e4e7',
    axis: '#71717a',
    cursor: 'rgba(24, 24, 27, 0.05)',
    ink: '#18181b',
    surface: '#ffffff',
    ok: '#16a34a',
    warn: '#d97706',
    bad: '#dc2626',
    series: ['#2563eb', '#0d9488', '#d97706', '#dc2626', '#7c3aed'],
  },
  dark: {
    grid: '#27272d',
    axis: '#8b8b95',
    cursor: 'rgba(244, 244, 245, 0.06)',
    ink: '#f4f4f5',
    surface: '#121215',
    ok: '#4ade80',
    warn: '#fbbf24',
    bad: '#f87171',
    series: ['#60a5fa', '#2dd4bf', '#fbbf24', '#f87171', '#a78bfa'],
  },
};

export function useChartTheme(): ChartPalette {
  const { theme } = useTheme();
  return PALETTES[theme];
}
