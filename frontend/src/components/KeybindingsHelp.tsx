'use client';
// Floating keybindings cheatsheet — opens on Ctrl/Cmd + K or by clicking the
// "?" button in the editor's status bar. Mirrors VS Code's keyboard reference.

import { useEffect } from 'react';
import { motion } from 'framer-motion';
import { Keyboard, X } from 'lucide-react';

const BINDINGS: Array<{ category: string; rows: Array<[string, string]> }> = [
  {
    category: 'Editing',
    rows: [
      ['Save (no-op — auto-synced)', 'Ctrl + S'],
      ['Comment line',               'Ctrl + /'],
      ['Comment block',              'Shift + Alt + A'],
      ['Move line up / down',        'Alt + ↑ / ↓'],
      ['Copy line up / down',        'Shift + Alt + ↑ / ↓'],
      ['Delete line',                'Ctrl + Shift + K'],
    ],
  },
  {
    category: 'Selection & cursor',
    rows: [
      ['Multi-cursor click',         'Alt + Click'],
      ['Add cursor above / below',   'Ctrl + Alt + ↑ / ↓'],
      ['Select next occurrence',     'Ctrl + D'],
      ['Select all occurrences',     'Ctrl + Shift + L'],
      ['Expand selection',           'Shift + Alt + →'],
      ['Shrink selection',           'Shift + Alt + ←'],
    ],
  },
  {
    category: 'Navigation',
    rows: [
      ['Go to line',                 'Ctrl + G'],
      ['Find',                       'Ctrl + F'],
      ['Find and replace',           'Ctrl + H'],
      ['Find next / previous',       'F3 / Shift + F3'],
      ['Indent / outdent',           'Ctrl + ] / Ctrl + ['],
      ['Format document',            'Shift + Alt + F'],
    ],
  },
  {
    category: 'Refactor & tools',
    rows: [
      ['Rename symbol',              'F2'],
      ['Trigger suggestions',        'Ctrl + Space'],
      ['Trigger parameter hints',    'Ctrl + Shift + Space'],
      ['Open keyboard shortcuts',    'Ctrl + K'],
      ['Run code',                   'Ctrl + Enter'],
    ],
  },
];

interface Props {
  open:    boolean;
  onClose: () => void;
}

export default function KeybindingsHelp({ open, onClose }: Props) {
  useEffect(() => {
    if (!open) return;
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onEsc);
    return () => window.removeEventListener('keydown', onEsc);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center px-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1,    opacity: 1 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-3xl max-h-[80vh] overflow-y-auto bg-slate-900 border border-slate-800 rounded-xl shadow-2xl"
      >
        <div className="sticky top-0 z-10 px-5 py-4 border-b border-slate-800 bg-slate-900/95 backdrop-blur flex items-center justify-between">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Keyboard size={18} className="text-astra-500" />
            Keyboard shortcuts
          </h2>
          <button onClick={onClose} type="button" aria-label="Close"
                  className="text-slate-400 hover:text-slate-100">
            <X size={18} />
          </button>
        </div>

        <div className="p-5 grid grid-cols-1 md:grid-cols-2 gap-6">
          {BINDINGS.map((group) => (
            <div key={group.category}>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                {group.category}
              </h3>
              <table className="w-full text-sm">
                <tbody>
                  {group.rows.map(([action, keys]) => (
                    <tr key={action} className="border-b border-slate-800/50 last:border-b-0">
                      <td className="py-1.5 text-slate-300">{action}</td>
                      <td className="py-1.5 text-right">
                        <span className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-xs font-mono text-astra-300">
                          {keys}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>

        <div className="px-5 py-3 border-t border-slate-800 bg-slate-900/60 text-xs text-slate-500">
          Press <kbd className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 font-mono">Esc</kbd> to close.
          On macOS, use <kbd className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 font-mono">⌘</kbd> instead of Ctrl.
        </div>
      </motion.div>
    </motion.div>
  );
}
