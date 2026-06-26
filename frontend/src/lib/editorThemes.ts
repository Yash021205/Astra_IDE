'use client';
// VS Code theme picker support, powered by `monaco-themes` (50+ community
// themes in Monaco format, the same definitions vscodethemes.com showcases).
// We curate a popular subset, lazy-load each theme's JSON, register it with
// Monaco, and persist the choice. Editors call applyTheme() on mount + on change.

import type { Monaco } from '@monaco-editor/react';

export interface ThemeDef {
  id: string;      // monaco-themes file name (without .json)
  label: string;
  type: 'dark' | 'light';
  file: string;    // JSON filename in monaco-themes/themes
}

// Curated, recognizable set (maps to the vscodethemes-style grid in the picker).
// "ASTRA Dark/Light" are Monaco built-ins so there's always an instant default.
export const EDITOR_THEMES: ThemeDef[] = [
  { id: 'astra-dark',  label: 'ASTRA Dark',    type: 'dark',  file: '' },
  { id: 'astra-light', label: 'ASTRA Light',   type: 'light', file: '' },
  { id: 'Dracula',          label: 'Dracula',          type: 'dark',  file: 'Dracula.json' },
  { id: 'GitHub Dark',      label: 'GitHub Dark',      type: 'dark',  file: 'GitHub Dark.json' },
  { id: 'GitHub Light',     label: 'GitHub Light',     type: 'light', file: 'GitHub Light.json' },
  { id: 'Monokai',          label: 'Monokai',          type: 'dark',  file: 'Monokai.json' },
  { id: 'Night Owl',        label: 'Night Owl',        type: 'dark',  file: 'Night Owl.json' },
  { id: 'Nord',             label: 'Nord',             type: 'dark',  file: 'Nord.json' },
  { id: 'One Dark Pro',     label: 'One Dark Pro',     type: 'dark',  file: 'Tomorrow-Night-Eighties.json' },
  { id: 'Solarized-dark',   label: 'Solarized Dark',   type: 'dark',  file: 'Solarized-dark.json' },
  { id: 'Solarized-light',  label: 'Solarized Light',  type: 'light', file: 'Solarized-light.json' },
  { id: 'Cobalt2',          label: 'Cobalt2',          type: 'dark',  file: 'Cobalt2.json' },
  { id: 'Tomorrow',         label: 'Tomorrow',         type: 'light', file: 'Tomorrow.json' },
  { id: 'Twilight',         label: 'Twilight',         type: 'dark',  file: 'Twilight.json' },
  { id: 'Oceanic Next',     label: 'Oceanic Next',     type: 'dark',  file: 'Oceanic Next.json' },
  { id: 'Xcode_default',    label: 'Xcode',            type: 'light', file: 'Xcode_default.json' },
  { id: 'Monoindustrial',   label: 'Monoindustrial',   type: 'dark',  file: 'Monoindustrial.json' },
  { id: 'Blackboard',       label: 'Blackboard',       type: 'dark',  file: 'Blackboard.json' },
];

const KEY = 'astra-editor-theme';
const _registered = new Set<string>(['astra-dark', 'astra-light']);

export function getSavedTheme(): string {
  if (typeof window === 'undefined') return 'astra-dark';
  return window.localStorage.getItem(KEY) || 'astra-dark';
}
export function saveTheme(id: string) {
  try { window.localStorage.setItem(KEY, id); } catch { /* ignore */ }
}
export function themeById(id: string): ThemeDef {
  return EDITOR_THEMES.find((t) => t.id === id) || EDITOR_THEMES[0];
}

/** Monaco theme id to pass to monaco.editor.setTheme / the <Editor theme> prop. */
export function resolveMonacoName(id: string): string {
  if (id === 'astra-dark') return 'vs-dark';
  if (id === 'astra-light') return 'vs';
  return id.replace(/[^a-zA-Z0-9_-]/g, '-');
}

/**
 * Lazy-load + register a monaco-themes theme, then apply it. Returns the Monaco
 * theme name actually set, so callers can keep the <Editor theme> prop in sync
 * (otherwise a re-render with a stale prop would reset the theme).
 */
export async function applyEditorTheme(monaco: Monaco, id: string): Promise<string> {
  const def = themeById(id);
  const name = resolveMonacoName(id);
  if (!_registered.has(id) && def.file) {
    try {
      const data = (await import(`monaco-themes/themes/${def.file}`)).default;
      monaco.editor.defineTheme(name, data as any);
      _registered.add(id);
    } catch {
      const fb = def.type === 'light' ? 'vs' : 'vs-dark';
      monaco.editor.setTheme(fb);
      return fb;
    }
  }
  monaco.editor.setTheme(name);
  return name;
}
