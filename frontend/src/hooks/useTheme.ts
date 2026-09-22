import { useCallback, useEffect } from 'react';

import { useLocalStorage } from './useLocalStorage';

export type ThemeMode = 'dark' | 'light';

const STORAGE_KEY = 'it-dashboard:theme';

export function useTheme(): {
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;
} {
  const [theme, setTheme] = useLocalStorage<ThemeMode>(STORAGE_KEY, 'dark');

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'light') {
      root.classList.add('light');
    } else {
      root.classList.remove('light');
    }
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme(theme === 'dark' ? 'light' : 'dark');
  }, [theme, setTheme]);

  return { theme, setTheme, toggleTheme };
}
