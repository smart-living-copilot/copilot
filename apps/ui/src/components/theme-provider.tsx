'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

export type Theme = 'light' | 'dark' | 'system';
type ResolvedTheme = 'light' | 'dark';

interface ThemeContextValue {
  theme: Theme;
  resolvedTheme: ResolvedTheme;
  setForcedTheme: (theme: Theme | null) => void;
  setTheme: (theme: Theme) => void;
}

const STORAGE_KEY = 'theme';
const MEDIA_QUERY = '(prefers-color-scheme: dark)';

const ThemeContext = createContext<ThemeContextValue | null>(null);

function systemTheme(): ResolvedTheme {
  if (
    typeof window !== 'undefined' &&
    window.matchMedia?.(MEDIA_QUERY).matches
  ) {
    return 'dark';
  }
  return 'light';
}

function storedTheme(defaultTheme: Theme): Theme {
  if (typeof window === 'undefined') {
    return defaultTheme;
  }

  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return saved === 'light' || saved === 'dark' || saved === 'system'
      ? saved
      : defaultTheme;
  } catch {
    return defaultTheme;
  }
}

function applyTheme(resolvedTheme: ResolvedTheme) {
  document.documentElement.classList.toggle('dark', resolvedTheme === 'dark');
  document.documentElement.style.colorScheme = resolvedTheme;
}

export function ThemeProvider({
  children,
  defaultTheme = 'system',
}: {
  children: ReactNode;
  defaultTheme?: Theme;
}) {
  const [theme, setThemeState] = useState<Theme>(() =>
    storedTheme(defaultTheme),
  );
  const [forcedTheme, setForcedThemeState] = useState<Theme | null>(null);
  const [systemResolvedTheme, setSystemResolvedTheme] = useState<ResolvedTheme>(
    () => systemTheme(),
  );
  const effectiveTheme = forcedTheme ?? theme;
  const resolvedTheme =
    effectiveTheme === 'system' ? systemResolvedTheme : effectiveTheme;

  useEffect(() => {
    applyTheme(resolvedTheme);
  }, [resolvedTheme]);

  useEffect(() => {
    if (!window.matchMedia) {
      return;
    }

    const mediaQuery = window.matchMedia(MEDIA_QUERY);

    const handleSystemThemeChange = () => {
      setSystemResolvedTheme(systemTheme());
    };

    mediaQuery.addEventListener('change', handleSystemThemeChange);
    return () => {
      mediaQuery.removeEventListener('change', handleSystemThemeChange);
    };
  }, []);

  const setTheme = useCallback((nextTheme: Theme) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, nextTheme);
    } catch {
      // Theme persistence is best-effort in private or restricted contexts.
    }
    setThemeState(nextTheme);
  }, []);

  const setForcedTheme = useCallback((nextTheme: Theme | null) => {
    setForcedThemeState(nextTheme);
  }, []);

  const value = useMemo(
    () => ({
      theme: effectiveTheme,
      resolvedTheme,
      setForcedTheme,
      setTheme,
    }),
    [effectiveTheme, resolvedTheme, setForcedTheme, setTheme],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return context;
}
