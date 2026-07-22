'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import type { Monaco } from '@monaco-editor/react';
import {
  ChevronRight, ChevronsDownUp, Folder, FolderOpen, FolderPlus, FilePlus,
  FileCode2, FileText, FileJson, FileTerminal, FileImage, Image as ImageIcon,
  GitBranch, RefreshCw, Save, Search, TerminalSquare, Trash2, Loader2, X, Check, Palette,
  PanelLeft, GripHorizontal, Upload, Copy,
} from 'lucide-react';

const Terminal = dynamic(() => import('./Terminal'), { ssr: false });

import {
  listFiles, readFile, writeFile, importRepo, makeDir, deletePath,
  searchWorkspace, rawFileUrl, uploadFiles, type WsFile, type SearchHit,
} from '../lib/api';
import { toast } from '../lib/toast';
import { cn } from '../lib/utils';
import Tooltip from './ui/Tooltip';
import ThemePicker from './ThemePicker';
import {
  applyEditorTheme, getSavedTheme, saveTheme, themeById, resolveMonacoName,
} from '../lib/editorThemes';

const MonacoEditor = dynamic(() => import('@monaco-editor/react'), { ssr: false });

// Extension -> Monaco language (syntax highlighting).
const EXT_LANG: Record<string, string> = {
  py: 'python', cpp: 'cpp', cc: 'cpp', h: 'cpp', hpp: 'cpp', c: 'c',
  js: 'javascript', mjs: 'javascript', jsx: 'javascript',
  ts: 'typescript', tsx: 'typescript',
  json: 'json', md: 'markdown', sh: 'shell', bash: 'shell',
  yml: 'yaml', yaml: 'yaml', html: 'html', css: 'css', scss: 'scss', go: 'go',
  rs: 'rust', java: 'java', sql: 'sql', toml: 'ini', txt: 'plaintext',
};

// Firebase/Glitch-style colour coding by extension. Each colour set is written
// as literal Tailwind classes so the JIT compiler keeps them.
const COLORS = {
  red:     { text: 'text-rose-400',    selBg: 'bg-rose-500/10',    border: 'border-rose-500'    },
  yellow:  { text: 'text-yellow-400',  selBg: 'bg-yellow-500/10',  border: 'border-yellow-500'  },
  sky:     { text: 'text-sky-400',     selBg: 'bg-sky-500/10',     border: 'border-sky-500'     },
  fuchsia: { text: 'text-fuchsia-400', selBg: 'bg-fuchsia-500/10', border: 'border-fuchsia-500' },
  orange:  { text: 'text-orange-400',  selBg: 'bg-orange-500/10',  border: 'border-orange-500'  },
  emerald: { text: 'text-emerald-400', selBg: 'bg-emerald-500/10', border: 'border-emerald-500' },
  cyan:    { text: 'text-cyan-400',    selBg: 'bg-cyan-500/10',    border: 'border-cyan-500'    },
  purple:  { text: 'text-purple-400',  selBg: 'bg-purple-500/10',  border: 'border-purple-500'  },
  slate:   { text: 'text-faint',       selBg: 'bg-slate-500/10',   border: 'border-slate-400'   },
};
type ColorKey = keyof typeof COLORS;
const EXT_COLOR: Record<string, ColorKey> = {
  json: 'red', js: 'yellow', mjs: 'yellow', jsx: 'yellow', ts: 'sky', tsx: 'sky',
  css: 'fuchsia', scss: 'fuchsia', html: 'orange', xml: 'orange',
  md: 'slate', txt: 'slate', lock: 'slate', gitignore: 'slate',
  py: 'emerald', sh: 'emerald', bash: 'emerald',
  go: 'cyan', rs: 'orange', java: 'red', c: 'sky', cpp: 'sky', h: 'sky',
  yml: 'purple', yaml: 'purple', toml: 'purple',
};

function extOf(path: string): string {
  const base = path.split('/').pop() ?? path;
  if (base.startsWith('.')) return base.slice(1).toLowerCase();   // .gitignore -> gitignore
  return base.includes('.') ? base.split('.').pop()!.toLowerCase() : '';
}
function colorOf(path: string) { return COLORS[EXT_COLOR[extOf(path)] ?? 'slate']; }
function langFor(path: string): string { return EXT_LANG[extOf(path)] ?? 'plaintext'; }

const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp', 'ico', 'avif']);
function isImage(path: string): boolean { return IMAGE_EXTS.has(extOf(path)); }

function FileIcon({ path }: { path: string }) {
  const e = extOf(path);
  const c = colorOf(path).text;
  if (isImage(path)) return <FileImage size={13} className="shrink-0 text-fuchsia-400" />;
  if (e === 'json') return <FileJson size={13} className={cn('shrink-0', c)} />;
  if (e === 'md' || e === 'txt') return <FileText size={13} className={cn('shrink-0', c)} />;
  if (e === 'sh' || e === 'bash') return <FileTerminal size={13} className={cn('shrink-0', c)} />;
  return <FileCode2 size={13} className={cn('shrink-0', c)} />;
}

// Render the filename with the extension portion coloured (Glitch style).
function FileName({ path }: { path: string }) {
  const base = path.split('/').pop() ?? path;
  const dot = base.lastIndexOf('.');
  const color = colorOf(path).text;
  if (dot <= 0) return <span className="truncate">{base}</span>;
  return (
    <span className="truncate">
      {base.slice(0, dot)}<span className={color}>{base.slice(dot)}</span>
    </span>
  );
}

type Prompt = { kind: 'file' | 'folder' | 'import' } | null;

interface FMProps {
  workspaceId: number;
  frozen?: boolean;
  onActiveFile?: (path: string | null) => void;
  /** Bump `.n` to request opening `.path` from outside (e.g. settings config). */
  openSignal?: { path: string; n: number };
  /** Reports whether the open file has unsaved edits (for the leave guard). */
  onDirtyChange?: (dirty: boolean) => void;
}

export default function FileManager({ workspaceId, frozen = false, onActiveFile, openSignal, onDirtyChange }: FMProps) {
  const [showTerminal, setShowTerminal] = useState(false);
  // Resizable panels (VS Code-style). Explorer collapses fully below a minimum;
  // terminal closes when dragged below a minimum.
  const [explorerW, setExplorerW] = useState(256);
  const [explorerCollapsed, setExplorerCollapsed] = useState(false);
  const [termH, setTermH] = useState(224);
  const drag = useRef<{ kind: 'x' | 'y'; startPos: number; startVal: number } | null>(null);

  useEffect(() => {
    function onMove(e: MouseEvent) {
      const d = drag.current; if (!d) return;
      if (d.kind === 'x') {
        const next = d.startVal + (e.clientX - d.startPos);
        if (next < 160) { setExplorerCollapsed(true); }
        else { setExplorerCollapsed(false); setExplorerW(Math.min(480, Math.max(190, next))); }
      } else {
        const next = d.startVal - (e.clientY - d.startPos);   // drag up = taller
        if (next < 64) { setShowTerminal(false); drag.current = null; }
        else { setTermH(Math.min(560, next)); }
      }
    }
    function onUp() { drag.current = null; document.body.style.userSelect = ''; document.body.style.cursor = ''; }
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
  }, []);

  function startDrag(kind: 'x' | 'y', e: React.MouseEvent) {
    drag.current = { kind, startPos: kind === 'x' ? e.clientX : e.clientY, startVal: kind === 'x' ? explorerW : termH };
    document.body.style.userSelect = 'none';
    document.body.style.cursor = kind === 'x' ? 'col-resize' : 'row-resize';
  }
  const [files, setFiles] = useState<WsFile[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [content, setContent] = useState('');
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [prompt, setPrompt] = useState<Prompt>(null);
  const [promptValue, setPromptValue] = useState('');
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved'>('idle');

  // Project search (VS Code-style).
  const [showSearch, setShowSearch] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchHit[]>([]);
  const [searching, setSearching] = useState(false);

  // Folder expand/collapse: collapsed paths tracked in a Set.
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const toggleFolder = (path: string) =>
    setCollapsed((prev) => { const n = new Set(prev); n.has(path) ? n.delete(path) : n.add(path); return n; });
  const collapseAll = () => setCollapsed(new Set(files.filter((f) => f.type === 'dir').map((f) => f.path)));
  const isHiddenByCollapse = (path: string): boolean => {
    const parts = path.split('/');
    for (let i = 1; i < parts.length; i++) {
      const ancestor = parts.slice(0, i).join('/');
      if (collapsed.has(ancestor)) return true;
    }
    return false;
  };

  // Editor theme (shared with the Collab editor via localStorage).
  const [themeId, setThemeId] = useState<string>(getSavedTheme);
  const [monacoTheme, setMonacoTheme] = useState<string>(() => resolveMonacoName(getSavedTheme()));
  const [showThemePicker, setShowThemePicker] = useState(false);
  const [monaco, setMonaco] = useState<Monaco | null>(null);

  async function refresh() {
    try { setFiles(await listFiles(workspaceId)); } catch { /* not fatal */ }
  }
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [workspaceId]);

  async function pickTheme(id: string) {
    setThemeId(id); saveTheme(id);
    if (monaco) setMonacoTheme(await applyEditorTheme(monaco, id));
    setShowThemePicker(false);
    toast.success('Theme applied', themeById(id).label);
  }

  // Surface unsaved-edit state to the workspace page (leave guard).
  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);

  // ── File upload (button + drag-drop) ──────────────────────────────────────
  const uploadRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  async function doUpload(files: FileList | File[]) {
    if (!files || (files as FileList).length === 0) return;
    if (frozen) { toast.error('Workspace is frozen', 'Unfreeze to upload.'); return; }
    setUploading(true);
    try {
      const saved = await uploadFiles(workspaceId, files);
      await refresh();
      toast.success('Uploaded', `${saved.length} file(s) added`);
    } catch (e: any) {
      toast.error('Upload failed', e?.response?.data?.detail || 'Error');
    } finally { setUploading(false); }
  }

  async function open(path: string) {
    setSel(path); setDirty(false); setSaveState('idle');
    onActiveFile?.(path);
    if (isImage(path)) { setContent(''); return; }   // images render from the raw URL
    try { setContent(await readFile(workspaceId, path)); }
    catch { setContent(''); toast.error('Cannot open file', path); }
  }

  // External open request (e.g. "open config file" from Settings).
  useEffect(() => {
    if (openSignal && openSignal.path) { refresh(); open(openSignal.path); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openSignal?.n]);
  async function save(silent = false) {
    if (!sel || isImage(sel)) return;
    setSaveState('saving');
    try {
      await writeFile(workspaceId, sel, content);
      setDirty(false); setSaveState('saved');
      if (!silent) toast.success('Saved', sel);
    } catch (e: any) {
      setSaveState('idle');
      toast.error('Save failed', e?.response?.data?.detail || 'Server error');
    }
  }

  // Auto-save: debounced write 1.2s after the last keystroke (no manual Save needed).
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!dirty || !sel || isImage(sel)) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => { save(true); }, 1200);
    return () => { if (saveTimer.current) clearTimeout(saveTimer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content, dirty, sel]);

  // Project search (debounced).
  useEffect(() => {
    if (!showSearch) return;
    const q = query.trim();
    if (q.length < 2) { setResults([]); return; }
    const id = setTimeout(async () => {
      setSearching(true);
      try { setResults(await searchWorkspace(workspaceId, q)); }
      catch { setResults([]); }
      setSearching(false);
    }, 300);
    return () => clearTimeout(id);
  }, [query, showSearch, workspaceId]);
  async function confirmPrompt() {
    const v = promptValue.trim();
    if (!v) return;
    setBusy(true);
    try {
      if (prompt?.kind === 'file')   { await writeFile(workspaceId, v, ''); await refresh(); await open(v); toast.success('File created', v); }
      else if (prompt?.kind === 'folder') { await makeDir(workspaceId, v); await refresh(); toast.success('Folder created', v); }
      else if (prompt?.kind === 'import') {
        toast.info('Cloning repository', 'This can take a few seconds');
        const r = await importRepo(workspaceId, v); await refresh();
        toast.success('Repository imported', `${r.file_count} files`);
      }
      setPrompt(null); setPromptValue('');
    } catch (e: any) { toast.error('Action failed', e?.response?.data?.detail || 'Server error'); }
    setBusy(false);
  }
  async function remove(path: string) {
    if (!confirm(`Delete "${path}"?`)) return;
    try {
      await deletePath(workspaceId, path);
      if (sel === path) { setSel(null); setContent(''); }
      await refresh(); toast.success('Deleted', path);
    } catch (e: any) { toast.error('Delete failed', e?.response?.data?.detail || 'Server error'); }
  }

  const promptLabel = useMemo(() => ({
    file:   { title: 'New file',   placeholder: 'src/main.py', hint: 'Path inside the workspace; folders are created automatically.' },
    folder: { title: 'New folder', placeholder: 'src/utils',   hint: 'Nested paths are allowed.' },
    import: { title: 'Import a public repository', placeholder: 'https://github.com/owner/repo', hint: 'GitHub, GitLab or Bitbucket over HTTPS. Replaces current workspace files.' },
  }), []);

  return (
    <div className="flex h-full bg-surface">
      {/* Collapsed explorer: thin reopen strip (VS Code-style) */}
      {explorerCollapsed && (
        <div className="w-9 border-r border-edge bg-raised/40 flex flex-col items-center py-2 shrink-0">
          <IconBtn title="Show explorer" onClick={() => { setExplorerCollapsed(false); setExplorerW(256); }}>
            <PanelLeft size={15} />
          </IconBtn>
        </div>
      )}

      {/* Explorer sidebar (resizable) */}
      <input ref={uploadRef} type="file" multiple className="hidden" aria-label="Upload files"
             onChange={(e) => { if (e.target.files) doUpload(e.target.files); e.target.value = ''; }} />
      <aside className={cn('relative border-r border-edge bg-raised/40 flex flex-col shrink-0 overflow-hidden', explorerCollapsed && 'hidden')}
             style={{ width: explorerW }}
             onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
             onDragLeave={() => setDragOver(false)}
             onDrop={(e) => { e.preventDefault(); setDragOver(false); if (e.dataTransfer.files?.length) doUpload(e.dataTransfer.files); }}>
        {dragOver && (
          <div className="absolute inset-0 z-20 grid place-items-center bg-astra-500/15 border-2 border-dashed border-astra-500 pointer-events-none">
            <span className="text-xs font-medium text-astra-700 dark:text-astra-200 inline-flex items-center gap-1.5">
              <Upload size={14} /> Drop to upload
            </span>
          </div>
        )}
        <div className="px-3 py-2 border-b border-edge flex items-center gap-1">
          <span className="t-overline text-faint flex-1">{showSearch ? 'Search' : 'Explorer'}</span>
          <IconBtn title="Search in project" onClick={() => setShowSearch((v) => !v)}>
            <Search size={13} className={showSearch ? 'text-astra-500' : ''} />
          </IconBtn>
          <IconBtn title="New file"   onClick={() => { setPrompt({ kind: 'file' }); setPromptValue(''); }}><FilePlus size={14} /></IconBtn>
          <IconBtn title="New folder" onClick={() => { setPrompt({ kind: 'folder' }); setPromptValue(''); }}><FolderPlus size={14} /></IconBtn>
          <IconBtn title="Upload files" onClick={() => uploadRef.current?.click()}>
            {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={14} />}
          </IconBtn>
          <IconBtn title="Import Git repository" onClick={() => { setPrompt({ kind: 'import' }); setPromptValue(''); }}><GitBranch size={14} /></IconBtn>
          <IconBtn title="Collapse all folders" onClick={collapseAll}><ChevronsDownUp size={13} /></IconBtn>
          <IconBtn title="Refresh" onClick={refresh}><RefreshCw size={13} /></IconBtn>
        </div>

        {/* Search panel */}
        {showSearch && (
          <div className="border-b border-edge p-2 space-y-2">
            <div className="relative">
              <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-faint" aria-hidden="true" />
              <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)}
                     placeholder="Search across files" aria-label="Search across files"
                     className="input-base pl-7 py-1.5 text-xs" />
            </div>
            <div className="max-h-[40vh] overflow-auto -mx-2">
              {searching && <p className="px-3 py-2 text-[11px] text-faint">Searching…</p>}
              {!searching && query.trim().length >= 2 && results.length === 0 &&
                <p className="px-3 py-2 text-[11px] text-faint">No matches.</p>}
              {results.map((r, i) => (
                <button key={`${r.path}:${r.line}:${i}`} type="button"
                        onClick={() => { setShowSearch(false); open(r.path); }}
                        className="w-full text-left px-3 py-1.5 hover:bg-raised border-l-2 border-transparent hover:border-astra-500">
                  <span className="flex items-center gap-1.5 text-[12px]">
                    <FileIcon path={r.path} />
                    <span className="truncate text-muted"><FileName path={r.path} /></span>
                    <span className="text-faint">:{r.line}</span>
                  </span>
                  <span className="block pl-5 text-[11px] font-mono text-faint truncate">{r.text}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        <div className={cn('flex-1 overflow-auto py-1 text-[13px]', showSearch && 'hidden')}>
          {files.length === 0 && (
            <div className="px-4 py-8 text-center">
              <p className="text-faint text-xs leading-relaxed">No files yet.<br />Create a file or import a Git repository.</p>
            </div>
          )}
          {files.map((f) => {
            if (isHiddenByCollapse(f.path)) return null;
            const selected = sel === f.path;
            const c = colorOf(f.path);
            const isDir = f.type === 'dir';
            const isOpen = isDir && !collapsed.has(f.path);
            return (
              <div key={f.path}
                   className={cn('group flex items-center gap-0.5 pr-1 border-l-2 transition-colors',
                     selected ? cn(c.selBg, c.border) : 'border-transparent hover:bg-raised')}
                   style={{ paddingLeft: 4 + (f.path.split('/').length - 1) * 14 }}>
                {/* Folder chevron toggle */}
                {isDir ? (
                  <button type="button" onClick={() => toggleFolder(f.path)}
                          title={isOpen ? 'Collapse' : 'Expand'}
                          className="p-0.5 rounded text-faint hover:text-muted shrink-0">
                    <ChevronRight size={12} className={cn('transition-transform', isOpen && 'rotate-90')} />
                  </button>
                ) : (
                  <span className="w-4 shrink-0" />
                )}
                <button type="button"
                        onClick={() => isDir ? toggleFolder(f.path) : open(f.path)}
                        title={f.path}
                        className="flex items-center gap-1.5 flex-1 min-w-0 py-1 text-left">
                  {isDir
                    ? (isOpen
                        ? <FolderOpen size={13} className="text-astra-500 shrink-0" />
                        : <Folder size={13} className="text-faint shrink-0" />)
                    : <FileIcon path={f.path} />}
                  {isDir
                    ? <span className={cn('truncate', isOpen ? 'text-ink font-medium' : 'text-muted')}>
                        {f.path.split('/').pop()}
                      </span>
                    : <span className={cn(selected ? 'text-ink font-medium' : 'text-muted')}>
                        <FileName path={f.path} />
                      </span>}
                </button>
                <button type="button" title={`Delete ${f.path}`} onClick={() => remove(f.path)}
                        className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-faint hover:text-rose-400">
                  <Trash2 size={12} />
                </button>
              </div>
            );
          })}
        </div>
      </aside>

      {/* Vertical resize handle between explorer and editor */}
      {!explorerCollapsed && (
        <div onMouseDown={(e) => startDrag('x', e)} title="Drag to resize · drag left to hide"
             className="w-1 shrink-0 cursor-col-resize bg-transparent hover:bg-astra-500/40 transition-colors" />
      )}

      {/* Editor pane */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="px-3 h-9 border-b border-edge flex items-center gap-3 text-xs bg-raised/40">
          {sel ? (
            <>
              <FileIcon path={sel} />
              <span className="text-muted truncate"><FileName path={sel} /></span>
              {!isImage(sel) && (
                <span className="text-[11px] text-faint inline-flex items-center gap-1">
                  {saveState === 'saving'
                    ? <><Loader2 size={10} className="animate-spin" /> saving</>
                    : dirty ? <span className="w-1.5 h-1.5 rounded-full bg-amber-400" title="Unsaved" />
                    : saveState === 'saved' ? <><Check size={11} className="text-emerald-500" /> saved</> : null}
                </span>
              )}
            </>
          ) : (
            <span className="text-faint">Select a file from the explorer</span>
          )}
          {frozen && <span className="chip border-amber-500/40 text-amber-600 dark:text-amber-400">read-only</span>}
          <div className="ml-auto flex items-center gap-1.5">
            <span className="text-[10px] text-faint hidden md:inline">auto-save on</span>
            <Tooltip content="Toggle terminal">
              <button type="button" onClick={() => setShowTerminal((v) => !v)}
                      aria-label="Toggle terminal"
                      className={cn('btn-ghost px-2 py-1 text-xs', showTerminal && 'text-astra-500')}>
                <TerminalSquare size={13} /> <span className="hidden lg:inline">Terminal</span>
              </button>
            </Tooltip>
            <Tooltip content="Editor theme">
              <button type="button" onClick={() => setShowThemePicker(true)}
                      aria-label="Editor theme"
                      className="btn-ghost px-2 py-1 text-xs">
                <Palette size={13} /> <span className="hidden lg:inline">{themeById(themeId).label}</span>
              </button>
            </Tooltip>
            {sel && !isImage(sel) && (
              <button type="button" onClick={() => save(false)} disabled={saveState === 'saving' || !dirty || frozen}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 text-white font-medium">
                {saveState === 'saving' ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} Save
              </button>
            )}
          </div>
        </div>

        {/* Editor area (shrinks when the terminal panel is open) */}
        <div className="flex-1 min-h-0 flex flex-col">
          {sel && (
            <div className="h-8 shrink-0 px-3 flex items-center gap-1.5 border-b border-edge bg-raised/40 text-xs">
              <span className="font-mono text-ink truncate" title={sel}>{sel}</span>
              <button type="button" title="Copy path"
                      onClick={() => {
                        try { navigator.clipboard?.writeText(sel); toast.success('Path copied', sel); }
                        catch { /* clipboard unavailable */ }
                      }}
                      className="ml-1 p-1 rounded text-faint hover:text-ink hover:bg-raised transition-colors">
                <Copy size={12} />
              </button>
            </div>
          )}
          <div className="flex-1 min-h-0">
          {sel && isImage(sel) ? (
            <div className="h-full overflow-auto grid place-items-center p-6 bg-[repeating-conic-gradient(theme(colors.slate.500/10%)_0%_25%,transparent_0%_50%)] bg-[length:24px_24px]">
              <div className="text-center">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={rawFileUrl(workspaceId, sel)} alt={sel}
                     className="max-w-full max-h-[70vh] rounded-lg shadow-pop border border-edge bg-surface" />
                <p className="mt-3 text-xs text-faint inline-flex items-center gap-1.5">
                  <ImageIcon size={12} /> {sel.split('/').pop()}
                </p>
              </div>
            </div>
          ) : sel ? (
            <MonacoEditor
              height="100%" theme={monacoTheme} path={sel} language={langFor(sel)} value={content}
              onMount={(_e, m) => { setMonaco(m); applyEditorTheme(m, themeId).then(setMonacoTheme).catch(() => {}); }}
              onChange={(v) => { setContent(v ?? ''); setDirty(true); setSaveState('idle'); }}
              options={{
                readOnly: frozen, automaticLayout: true,
                fontSize: 13.5, minimap: { enabled: false }, scrollBeyondLastLine: false, wordWrap: 'on',
                bracketPairColorization: { enabled: true },
                guides: { bracketPairs: true, indentation: true, highlightActiveIndentation: true },
                renderLineHighlight: 'all', smoothScrolling: true, fontLigatures: true,
                fontFamily: '"Source Code Pro", "JetBrains Mono", Menlo, Consolas, monospace',
                padding: { top: 10 },
              }}
            />
          ) : (
            <div className="h-full flex items-center justify-center">
              <div className="text-center max-w-sm">
                <Folder size={36} className="mx-auto text-edge-strong mb-3" />
                <p className="t-subtitle text-muted mb-1">Your project files</p>
                <p className="text-xs text-faint leading-relaxed">
                  Create files, organize folders, or bring an existing project in from GitHub.
                  Everything here is available to the Terminal and the Run pipeline.
                </p>
              </div>
            </div>
          )}
          </div>
        </div>

        {/* Integrated terminal (toggle from the toolbar) — resizable, drag the
            handle; drag below the minimum to close. */}
        {showTerminal && (
          <div className="border-t border-edge shrink-0 flex flex-col" style={{ height: termH }}>
            <div onMouseDown={(e) => startDrag('y', e)} title="Drag to resize · drag down to close"
                 className="h-1.5 shrink-0 cursor-row-resize flex items-center justify-center
                            bg-transparent hover:bg-astra-500/40 transition-colors group">
              <GripHorizontal size={12} className="text-faint group-hover:text-astra-500" />
            </div>
            <div className="flex-1 min-h-0">
              <Terminal workspaceId={workspaceId} />
            </div>
          </div>
        )}
      </div>

      {/* Inline prompt dialog */}
      {prompt && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-start justify-center pt-32 px-4"
             onClick={() => setPrompt(null)}>
          <div className="w-full max-w-md card p-4 shadow-pop" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="t-h3">{promptLabel[prompt.kind].title}</h3>
              <button type="button" onClick={() => setPrompt(null)} title="Close" aria-label="Close" className="btn-ghost p-1.5"><X size={14} /></button>
            </div>
            <input autoFocus value={promptValue} onChange={(e) => setPromptValue(e.target.value)}
                   onKeyDown={(e) => { if (e.key === 'Enter') confirmPrompt(); if (e.key === 'Escape') setPrompt(null); }}
                   placeholder={promptLabel[prompt.kind].placeholder} className="input-base font-mono" />
            <p className="text-[11px] text-faint mt-2">{promptLabel[prompt.kind].hint}</p>
            <div className="flex justify-end gap-2 mt-4">
              <button type="button" onClick={() => setPrompt(null)} className="btn-outline">Cancel</button>
              <button type="button" onClick={confirmPrompt} disabled={busy || !promptValue.trim()} className="btn-primary">
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} Confirm
              </button>
            </div>
          </div>
        </div>
      )}

      {showThemePicker && (
        <ThemePicker current={themeId} onPick={pickTheme} onClose={() => setShowThemePicker(false)} />
      )}
    </div>
  );
}

function IconBtn({ title, onClick, children }: { title: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <Tooltip content={title}>
      <button type="button" aria-label={title} onClick={onClick} className="btn-ghost p-1.5">{children}</button>
    </Tooltip>
  );
}
