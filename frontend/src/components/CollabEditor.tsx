'use client';
// Monaco-based collaborative editor with:
//   - Yjs CRDT sync over y-websocket (real-time, conflict-free)
//   - VS Code keybindings (Ctrl+S, Ctrl+/, multi-cursor, IntelliSense — Monaco built-in)
//   - Run button → POST /workspaces/:id/execute → output panel below editor
//   - Download button → save current buffer as a file
//   - Share button → open share modal
//   - Language picker → switches Monaco's tokenizer + theme
//   - Live presence list at the top right

import { useEffect, useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import type { editor } from 'monaco-editor';
import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';
import { MonacoBinding } from 'y-monaco';
import { Play, Download, Share2, Loader2, Settings2, Check, Palette } from 'lucide-react';
import type { Monaco } from '@monaco-editor/react';

import { executeCode, type ExecuteResponse } from '../lib/api';
import { collabWsUrl } from '../lib/ws';
import { cn } from '../lib/utils';
import { toast } from '../lib/toast';
import BottomPanel from './BottomPanel';
import ShareModal from './ShareModal';
import EditorStatusBar from './EditorStatusBar';
import KeybindingsHelp from './KeybindingsHelp';
import ThemePicker from './ThemePicker';
import {
  applyEditorTheme, getSavedTheme, saveTheme, themeById, resolveMonacoName,
} from '../lib/editorThemes';

// Editor preferences, persisted across sessions.
interface EditorPrefs { fontSize: number; minimap: boolean; wordWrap: boolean; }
const PREFS_KEY = 'astra-editor-prefs';
function loadPrefs(): EditorPrefs {
  if (typeof window === 'undefined') return { fontSize: 14, minimap: true, wordWrap: true };
  try { return { fontSize: 14, minimap: true, wordWrap: true, ...JSON.parse(localStorage.getItem(PREFS_KEY) || '{}') }; }
  catch { return { fontSize: 14, minimap: true, wordWrap: true }; }
}

const MonacoEditor = dynamic(() => import('@monaco-editor/react'), { ssr: false });

interface Props {
  workspaceId: number;
  room:        string;       // unique Yjs room ID
  language:    string;       // initial language
  initialCode?: string;
  username:    string;
  isOwner:     boolean;
  status?:     string;       // workspace status — shown in status bar
  sandbox?:    string;       // sandbox tier — shown in status bar
}

// Display name → Monaco's language ID (for syntax highlighting + keybindings)
const LANGUAGES = [
  { display: 'Python',     monaco: 'python',     ext: 'py'  },
  { display: 'C++',        monaco: 'cpp',        ext: 'cpp' },
  { display: 'JavaScript', monaco: 'javascript', ext: 'js'  },
  { display: 'TypeScript', monaco: 'typescript', ext: 'ts'  },
  { display: 'Bash',       monaco: 'shell',      ext: 'sh'  },
  { display: 'Java',       monaco: 'java',       ext: 'java' },
  { display: 'Go',         monaco: 'go',         ext: 'go'  },
  { display: 'Rust',       monaco: 'rust',       ext: 'rs'  },
  { display: 'JSON',       monaco: 'json',       ext: 'json' },
  { display: 'Markdown',   monaco: 'markdown',   ext: 'md'  },
];

// Languages our backend executor can actually run (others render but can't be "Run")
const EXECUTABLE = new Set(['python', 'cpp', 'javascript', 'shell']);

const USER_COLORS = ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899', '#14b8a6'];

function pickColor(name: string): string {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) & 0xffff;
  return USER_COLORS[h % USER_COLORS.length];
}

// Map Monaco language ID → backend executor language name
function executorLang(monacoLang: string): string {
  if (monacoLang === 'shell') return 'bash';
  return monacoLang;
}

// Map workspace-stored name → Monaco language ID (Monaco uses 'shell' for bash).
function toMonacoLang(workspaceLang: string): string {
  if (workspaceLang === 'bash' || workspaceLang === 'sh') return 'shell';
  if (workspaceLang === 'c++' || workspaceLang === 'cxx') return 'cpp';
  if (workspaceLang === 'js') return 'javascript';
  if (workspaceLang === 'ts') return 'typescript';
  if (workspaceLang === 'py') return 'python';
  return workspaceLang;
}

export default function CollabEditor({
  workspaceId, room, language, initialCode = '', username, isOwner,
  status = 'PENDING', sandbox = 'runc',
}: Props) {
  const [currentLang, setCurrentLang] = useState(toMonacoLang(language));
  const [peers, setPeers] = useState<{ name: string; color: string }[]>([]);
  const [cursorPos, setCursorPos] = useState({ line: 1, column: 1 });
  const [showHelp, setShowHelp] = useState(false);
  const [running, setRunning] = useState(false);
  const [output, setOutput] = useState<ExecuteResponse | null>(null);
  const [showShare, setShowShare] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [prefs, setPrefs] = useState<EditorPrefs>(loadPrefs);
  // Editor color theme (VS Code themes via monaco-themes), independent of the
  // app light/dark chrome. Kept in sync with the <Editor theme> prop.
  const [themeId, setThemeId] = useState<string>(getSavedTheme);
  const [monacoTheme, setMonacoTheme] = useState<string>(
    () => resolveMonacoName(getSavedTheme()));
  const [showThemePicker, setShowThemePicker] = useState(false);
  const monacoRef = useRef<Monaco | null>(null);

  async function pickTheme(id: string) {
    setThemeId(id); saveTheme(id);
    if (monacoRef.current) setMonacoTheme(await applyEditorTheme(monacoRef.current, id));
    setShowThemePicker(false);
    toast.success('Theme applied', themeById(id).label);
  }

  function updatePref<K extends keyof EditorPrefs>(k: K, v: EditorPrefs[K]) {
    const next = { ...prefs, [k]: v };
    setPrefs(next);
    try { localStorage.setItem(PREFS_KEY, JSON.stringify(next)); } catch { /* ignore */ }
  }

  const ydocRef     = useRef<Y.Doc | null>(null);
  const providerRef = useRef<WebsocketProvider | null>(null);
  const editorRef   = useRef<editor.IStandaloneCodeEditor | null>(null);
  const bindingRef  = useRef<MonacoBinding | null>(null);

  // ── Yjs sync ────────────────────────────────────────────────────────────
  useEffect(() => {
    const ydoc     = new Y.Doc();
    const wsUrl    = collabWsUrl();
    const provider = new WebsocketProvider(wsUrl, room, ydoc);
    const myColor  = pickColor(username);

    provider.awareness.setLocalStateField('user', { name: username, color: myColor });

    const onAwareness = () => {
      const states = Array.from(provider.awareness.getStates().values()) as
        Array<{ user?: { name: string; color: string } }>;
      setPeers(
        states
          .filter((s) => s.user?.name)
          .map((s) => ({ name: s.user!.name, color: s.user!.color || pickColor(s.user!.name) })),
      );
    };
    provider.awareness.on('change', onAwareness);
    onAwareness();

    ydocRef.current     = ydoc;
    providerRef.current = provider;

    return () => {
      provider.awareness.off('change', onAwareness);
      bindingRef.current?.destroy();
      provider.destroy();
      ydoc.destroy();
    };
  }, [room, username]);

  const onMount = (instance: editor.IStandaloneCodeEditor, monaco: Monaco) => {
    editorRef.current = instance;
    monacoRef.current = monaco;
    // Register + apply the saved VS Code theme, then sync the prop.
    applyEditorTheme(monaco, themeId).then(setMonacoTheme).catch(() => {});
    const ydoc     = ydocRef.current!;
    const provider = providerRef.current!;
    const ytext    = ydoc.getText('monaco');

    if (ytext.length === 0 && initialCode) {
      ytext.insert(0, initialCode);
    }

    bindingRef.current = new MonacoBinding(
      ytext, instance.getModel()!, new Set([instance]), provider.awareness,
    );

    // Track cursor position for the status bar
    instance.onDidChangeCursorPosition((e) => {
      setCursorPos({ line: e.position.lineNumber, column: e.position.column });
    });
  };

  // Ctrl/Cmd + K opens the keybindings help. Also listen to a custom event
  // dispatched by the command palette so "Show keyboard shortcuts" works there.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k' && !e.shiftKey) {
        e.preventDefault();
        setShowHelp((v) => !v);
      }
    };
    const onEvent = () => setShowHelp(true);
    window.addEventListener('keydown', onKey);
    window.addEventListener('astra:open-help', onEvent);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('astra:open-help', onEvent);
    };
  }, []);

  // ── Actions ──────────────────────────────────────────────────────────────
  async function onRun() {
    if (!editorRef.current) return;
    const code = editorRef.current.getValue();
    if (!code.trim()) {
      setOutput({
        language: currentLang, exit_code: 0, stdout: '', stderr: '(no code to run)',
        runtime_ms: 0, timeout: false, truncated: false,
      });
      return;
    }
    setRunning(true);
    try {
      const result = await executeCode(workspaceId, executorLang(currentLang), code);
      setOutput(result);
      if (result.timeout) {
        toast.warning('Timed out', `Execution exceeded the 5s limit.`);
      } else if (result.exit_code === 0) {
        toast.success('Run succeeded', `Finished in ${result.runtime_ms}ms`);
      } else {
        toast.error('Run failed', `Exit code ${result.exit_code}`);
      }
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'execute failed';
      setOutput({
        language: currentLang, exit_code: -1, stdout: '',
        stderr: msg,
        runtime_ms: 0, timeout: false, truncated: false,
      });
      toast.error('Could not run', msg);
    } finally {
      setRunning(false);
    }
  }

  function onDownload() {
    if (!editorRef.current) return;
    const code = editorRef.current.getValue();
    const lang = LANGUAGES.find((l) => l.monaco === currentLang);
    const filename = `astra-${room.slice(0, 8)}.${lang?.ext || 'txt'}`;
    const blob = new Blob([code], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    toast.success('Downloaded', filename);
  }

  const isExecutable = useMemo(() => EXECUTABLE.has(currentLang), [currentLang]);

  return (
    <div className="h-full flex flex-col bg-slate-950">
      {/* Toolbar */}
      <div className="px-3 py-2 text-xs flex flex-wrap items-center gap-2 border-b border-slate-800 bg-slate-900">
        {/* Language picker */}
        <select
          value={currentLang}
          onChange={(e) => setCurrentLang(e.target.value)}
          className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-slate-100 text-xs"
          title="Switch language for syntax highlighting + Run target"
        >
          {LANGUAGES.map((l) => (
            <option key={l.monaco} value={l.monaco}>{l.display}</option>
          ))}
        </select>

        {/* Run */}
        <button
          type="button"
          onClick={onRun}
          disabled={running || !isExecutable}
          className={cn(
            'inline-flex items-center gap-1.5 px-3 py-1 rounded font-medium',
            'bg-emerald-700 hover:bg-emerald-600 text-white',
            'disabled:bg-slate-700 disabled:text-slate-400 disabled:cursor-not-allowed',
          )}
          title={isExecutable ? 'Run (Ctrl+Enter equivalent)' : 'No backend executor for this language'}
        >
          {running
            ? <Loader2 size={13} className="animate-spin" />
            : <Play size={13} fill="currentColor" />}
          {running ? 'Running…' : 'Run'}
        </button>

        {/* Download */}
        <button
          type="button"
          onClick={onDownload}
          className="inline-flex items-center gap-1.5 px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 text-white font-medium"
          title="Download as file"
        >
          <Download size={13} /> Download
        </button>

        {/* Share */}
        {isOwner && (
          <button
            type="button"
            onClick={() => setShowShare(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded bg-astra-600 hover:bg-astra-700 text-white font-medium"
            title="Invite a collaborator"
          >
            <Share2 size={13} /> Share
          </button>
        )}

        {/* Editor settings */}
        <div className="relative">
          <button type="button" onClick={() => setShowSettings((v) => !v)}
                  aria-haspopup="true" aria-expanded={showSettings}
                  title="Editor settings"
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-700 hover:bg-slate-600 text-white">
            <Settings2 size={13} />
          </button>
          {showSettings && (
            <>
              <div aria-hidden="true" className="fixed inset-0 z-40" onClick={() => setShowSettings(false)} />
              <div
                   className="absolute left-0 top-full mt-1.5 z-50 w-56 rounded-lg border border-slate-700 bg-slate-900 p-2 shadow-xl text-slate-200">
                <div className="px-1 py-1 text-[11px] uppercase tracking-wider text-slate-500">Editor settings</div>
                <div className="flex items-center justify-between px-1 py-1.5">
                  <span className="text-xs">Font size</span>
                  <div className="inline-flex items-center gap-1">
                    {[12, 13, 14, 16, 18].map((s) => (
                      <button key={s} type="button" onClick={() => updatePref('fontSize', s)}
                              className={cn('w-6 h-6 rounded text-[11px]',
                                prefs.fontSize === s ? 'bg-astra-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700')}>
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
                <button type="button" onClick={() => updatePref('minimap', !prefs.minimap)}
                        className="w-full flex items-center justify-between px-1 py-1.5 text-xs hover:bg-slate-800 rounded">
                  <span>Minimap</span>
                  <span className={cn('w-4 h-4 rounded border flex items-center justify-center',
                    prefs.minimap ? 'bg-astra-600 border-astra-600' : 'border-slate-600')}>
                    {prefs.minimap && <Check size={11} className="text-white" />}
                  </span>
                </button>
                <button type="button" onClick={() => updatePref('wordWrap', !prefs.wordWrap)}
                        className="w-full flex items-center justify-between px-1 py-1.5 text-xs hover:bg-slate-800 rounded">
                  <span>Word wrap</span>
                  <span className={cn('w-4 h-4 rounded border flex items-center justify-center',
                    prefs.wordWrap ? 'bg-astra-600 border-astra-600' : 'border-slate-600')}>
                    {prefs.wordWrap && <Check size={11} className="text-white" />}
                  </span>
                </button>
                <div className="px-1 pt-1 text-[10px] text-slate-500">Use the Theme button for editor colors.</div>
              </div>
            </>
          )}
        </div>

        {/* Theme picker (VS Code themes) */}
        <button
          type="button"
          onClick={() => setShowThemePicker(true)}
          title="Editor theme (VS Code themes)"
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-700 hover:bg-slate-600 text-white"
        >
          <Palette size={13} /> <span className="hidden lg:inline">{themeById(themeId).label}</span>
        </button>

        <span className="text-slate-500 ml-2 hidden md:inline">room: <span className="font-mono">{room}</span></span>

        {/* Presence list */}
        <div className="ml-auto flex items-center gap-1.5">
          <span className="text-slate-400">
            {peers.length} editor{peers.length !== 1 ? 's' : ''} online
          </span>
          {peers.slice(0, 6).map((p) => (
            <span
              key={p.name}
              className="px-1.5 py-0.5 rounded text-[10px] font-medium text-white"
              style={{ backgroundColor: p.color }}
            >
              {p.name}
            </span>
          ))}
        </div>
      </div>

      {/* Editor */}
      <div className={cn('flex-1 min-h-0', output ? 'h-2/3' : '')}>
        <MonacoEditor
          height="100%"
          theme={monacoTheme}
          language={currentLang}
          onMount={onMount}
          options={{
            automaticLayout: true,
            fontSize: prefs.fontSize,
            minimap: { enabled: prefs.minimap, scale: 0.7 },
            scrollBeyondLastLine: false,
            wordWrap: prefs.wordWrap ? 'on' : 'off',
            tabSize: 4,
            insertSpaces: true,
            cursorBlinking: 'smooth',
            cursorSmoothCaretAnimation: 'on',
            smoothScrolling: true,
            bracketPairColorization: { enabled: true },
            guides: { bracketPairs: true, indentation: true, highlightActiveIndentation: true },
            renderLineHighlight: 'all',
            fontLigatures: true,
            fontFamily: '"JetBrains Mono", "Fira Code", "Cascadia Code", Menlo, Consolas, monospace',
            lineNumbers: 'on',
            formatOnPaste: true,
            formatOnType: true,
            suggestOnTriggerCharacters: true,
            quickSuggestions: true,
            // VS Code keybindings are the Monaco default: Ctrl+S, Ctrl+/, Ctrl+D,
            // multi-cursor with Alt+Click, Ctrl+F find/replace, F2 rename, etc.
          }}
        />
      </div>

      {/* VS Code-style tabbed bottom panel — output / problems / terminal */}
      {(output || running) && (
        <BottomPanel
          result={output}
          running={running}
          onClose={() => setOutput(null)}
          workspaceId={workspaceId}
          status={status}
          workspace={{
            name:     `ws-${workspaceId}`,
            language: currentLang,
            sandbox,
          }}
        />
      )}

      {/* VS Code-style status bar — always visible at the bottom */}
      <EditorStatusBar
        language={currentLang}
        line={cursorPos.line}
        column={cursorPos.column}
        peers={peers.length}
        status={status}
        sandbox={sandbox}
        onOpenHelp={() => setShowHelp(true)}
      />

      {/* Share modal — only mount when open */}
      {showShare && (
        <ShareModal
          workspaceId={workspaceId}
          onClose={() => setShowShare(false)}
        />
      )}

      {/* Keybindings cheatsheet (opens via Ctrl/Cmd+K or status bar "?") */}
      <KeybindingsHelp open={showHelp} onClose={() => setShowHelp(false)} />

      {/* VS Code theme picker */}
      {showThemePicker && (
        <ThemePicker current={themeId} onPick={pickTheme} onClose={() => setShowThemePicker(false)} />
      )}
    </div>
  );
}
