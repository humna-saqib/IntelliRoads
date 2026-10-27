import { Moon, Sun } from 'lucide-react';
import { useTheme } from '../../context/ThemeContext';

/** Switches between the light and dark theme; the choice is remembered. */
export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const next = theme === 'dark' ? 'light' : 'dark';
  return (
    <button type="button" onClick={toggleTheme} className="btn btn-ghost btn-icon" aria-label={`Switch to ${next} theme`} title={`Switch to ${next} theme`}>
      {theme === 'dark' ? <Sun size={16} strokeWidth={1.75} /> : <Moon size={16} strokeWidth={1.75} />}
    </button>
  );
}
