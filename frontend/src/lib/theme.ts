'use client';
// App-wide light/dark theme. The chosen theme is persisted to localStorage and
// applied as a `dark` class on <html> (Tailwind darkMode: 'class'). A small
// inline script in layout.tsx applies it before first paint to avoid flashes.

import { useEffect, useState } from 'react';

export type Theme = 'light' | 'dark';
const KEY = 'astra-theme';

export function getTheme(): Theme {
  if (typeof window === 'undefined') return 'dark';
  const saved = window.localStorage.getItem(KEY);
  if (saved === 'light' || saved === 'dark') return saved;
  return 'dark';   // default to dark unless the user explicitly picks light
}

export function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark');
  window.localStorage.setItem(KEY, theme);
  // Let interested components (Monaco, xterm) react without a re-render chain.
  window.dispatchEvent(new CustomEvent('astra:theme', { detail: theme }));
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>('dark');

  useEffect(() => {
    setThemeState(getTheme());
    const onEvt = (e: Event) => setThemeState((e as CustomEvent).detail as Theme);
    window.addEventListener('astra:theme', onEvt);
    return () => window.removeEventListener('astra:theme', onEvt);
  }, []);

  const setTheme = (t: Theme) => { applyTheme(t); setThemeState(t); };
  return [theme, setTheme];
}

// Inline-script source for layout.tsx (runs before hydration; no flash).
export const THEME_BOOT_SCRIPT = `(function(){try{var t=localStorage.getItem('${KEY}');if(t!=='light'){document.documentElement.classList.add('dark');}}catch(e){document.documentElement.classList.add('dark');}})();`;
