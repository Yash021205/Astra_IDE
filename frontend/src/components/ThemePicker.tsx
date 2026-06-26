'use client';
// VS Code theme picker — a modal grid (vscodethemes.com style) showing a tiny
// code preview per theme. Selecting one registers + applies it to every Monaco
// editor instance and persists the choice.

import { useEffect, useState } from 'react';
import { Check, Palette, Search, X } from 'lucide-react';
import { EDITOR_THEMES, type ThemeDef } from '../lib/editorThemes';
import { cn } from '../lib/utils';

// Compact representative palettes for the card previews: [bg, fg, keyword, string, comment].
const SWATCH: Record<string, string[]> = {
  'astra-dark':      ['#0b1220', '#e2e8f0', '#60a5fa', '#34d399', '#64748b'],
  'astra-light':     ['#ffffff', '#1e293b', '#2563eb', '#0d9488', '#94a3b8'],
  'Dracula':         ['#282a36', '#f8f8f2', '#ff79c6', '#f1fa8c', '#6272a4'],
  'GitHub Dark':     ['#0d1117', '#c9d1d9', '#ff7b72', '#a5d6ff', '#8b949e'],
  'GitHub Light':    ['#ffffff', '#24292e', '#d73a49', '#032f62', '#6a737d'],
  'Monokai':         ['#272822', '#f8f8f2', '#f92672', '#e6db74', '#75715e'],
  'Night Owl':       ['#011627', '#d6deeb', '#c792ea', '#ecc48d', '#637777'],
  'Nord':            ['#2e3440', '#d8dee9', '#81a1c1', '#a3be8c', '#616e88'],
  'One Dark Pro':    ['#282c34', '#abb2bf', '#c678dd', '#98c379', '#5c6370'],
  'Solarized-dark':  ['#002b36', '#839496', '#859900', '#2aa198', '#586e75'],
  'Solarized-light': ['#fdf6e3', '#657b83', '#859900', '#2aa198', '#93a1a1'],
  'Cobalt2':         ['#193549', '#ffffff', '# ff9d00', '#3ad900', '#0088ff'].map((c) => c.replace(' ', '')),
  'Tomorrow':        ['#ffffff', '#4d4d4c', '#8959a8', '#718c00', '#8e908c'],
  'Twilight':        ['#141414', '#f7f7f7', '#cda869', '#8f9d6a', '#5f5a60'],
  'Oceanic Next':    ['#1b2b34', '#d8dee9', '#c594c5', '#99c794', '#65737e'],
  'Xcode_default':   ['#ffffff', '#000000', '#aa0d91', '#c41a16', '#007400'],
  'Monoindustrial':  ['#222827', '#e6e1c4', '#bb80b3', '#a3a86d', '#7d8c93'],
  'Blackboard':      ['#0c1021', '#f8f8f8', '#fbde2d', '#61ce3c', '#aeaeae'],
};

function Preview({ id }: { id: string }) {
  const [bg, fg, kw, str, com] = SWATCH[id] ?? SWATCH['astra-dark'];
  return (
    <div className="rounded-md overflow-hidden border border-edge font-mono text-[10px] leading-[1.5]"
         style={{ background: bg, color: fg }} aria-hidden="true">
      <div className="px-2 py-1.5 space-y-0.5">
        <div><span style={{ color: com }}>// render</span></div>
        <div><span style={{ color: kw }}>const</span> n = <span style={{ color: str }}>&apos;astra&apos;</span>;</div>
        <div><span style={{ color: kw }}>function</span> run() {'{'}</div>
        <div className="pl-3">log(<span style={{ color: str }}>`hi ${'{'}n{'}'}`</span>)</div>
        <div>{'}'}</div>
      </div>
    </div>
  );
}

export default function ThemePicker({ current, onPick, onClose }: {
  current: string;
  onPick: (id: string) => void;
  onClose: () => void;
}) {
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState<'all' | 'dark' | 'light'>('all');

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const list = EDITOR_THEMES.filter((t) =>
    (filter === 'all' || t.type === filter) &&
    t.label.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="fixed inset-0 z-[60] bg-black/55 backdrop-blur-sm flex items-start justify-center p-4 sm:p-8 overflow-y-auto"
         role="dialog" aria-modal="true" aria-label="Choose editor theme" onClick={onClose}>
      <div className="w-full max-w-3xl card shadow-pop my-auto" onClick={(e) => e.stopPropagation()}>
        <div className="px-4 py-3 border-b border-edge flex items-center gap-3">
          <Palette size={16} className="text-astra-600 dark:text-astra-400" aria-hidden="true" />
          <h2 className="t-h3 flex-1">Editor theme</h2>
          <button type="button" onClick={onClose} title="Close" aria-label="Close" className="btn-ghost p-1.5">
            <X size={16} />
          </button>
        </div>

        <div className="px-4 py-3 flex items-center gap-2 border-b border-edge flex-wrap">
          <div className="relative flex-1 min-w-[12rem]">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" aria-hidden="true" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search themes"
                   aria-label="Search themes" className="input-base pl-8 py-1.5" />
          </div>
          {(['all', 'dark', 'light'] as const).map((f) => (
            <button key={f} type="button" onClick={() => setFilter(f)}
                    className={cn('px-2.5 py-1.5 rounded-lg border text-xs capitalize transition-colors',
                      filter === f ? 'border-astra-500 bg-astra-500/10 text-ink font-medium'
                                   : 'border-edge text-muted hover:border-edge-strong')}>
              {f}
            </button>
          ))}
        </div>

        <div className="p-4 grid grid-cols-2 sm:grid-cols-3 gap-3 max-h-[60vh] overflow-y-auto">
          {list.map((t: ThemeDef) => (
            <button key={t.id} type="button" onClick={() => onPick(t.id)}
                    className={cn('text-left rounded-lg border p-2 transition-all hover:-translate-y-0.5',
                      current === t.id ? 'border-astra-500 ring-2 ring-astra-500/30' : 'border-edge hover:border-edge-strong')}>
              <Preview id={t.id} />
              <div className="flex items-center gap-1.5 mt-2">
                <span className="t-body-sm font-medium truncate flex-1">{t.label}</span>
                {current === t.id && <Check size={13} className="text-astra-500 shrink-0" />}
                <span className="chip py-0 text-[9px]">{t.type}</span>
              </div>
            </button>
          ))}
          {list.length === 0 && (
            <p className="col-span-full text-center text-faint text-sm py-8">No themes match.</p>
          )}
        </div>
      </div>
    </div>
  );
}
