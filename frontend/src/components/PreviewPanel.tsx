'use client';
// Live preview for the workspace. Two modes:
//   Files       - serve the workspace's static files (index.html etc.) directly.
//   Live server - reverse-proxy a dev server the user started inside the container
//                 (e.g. `python -m http.server 8080`) on a chosen/detected port.

import { useEffect, useRef, useState } from 'react';
import { ExternalLink, RotateCw, X, Globe, ServerCog, Radio, FileCode } from 'lucide-react';
import { previewUrl, proxyUrl, getWorkspacePorts } from '../lib/api';
import { cn } from '../lib/utils';

type Mode = 'static' | 'live';

export default function PreviewPanel({ workspaceId, onClose }:
  { workspaceId: number; onClose: () => void }) {
  const [mode, setMode] = useState<Mode>('static');
  const [entry, setEntry] = useState('index.html');
  const [port, setPort] = useState(3000);
  const [detected, setDetected] = useState<number[]>([]);
  const [nonce, setNonce] = useState(0);          // bump to reload the iframe
  const iframeRef = useRef<HTMLIFrameElement>(null);

  async function refreshPorts() {
    try {
      const ports = await getWorkspacePorts(workspaceId);
      setDetected(ports);
      if (ports.length && !ports.includes(port)) setPort(ports[0]);
    } catch { setDetected([]); }
  }
  useEffect(() => { refreshPorts(); /* eslint-disable-next-line */ }, [workspaceId]);

  const base = mode === 'live'
    ? proxyUrl(workspaceId, port, entry === 'index.html' ? '' : entry)
    : previewUrl(workspaceId, entry);
  const src = `${base}${base.includes('?') ? '&' : '?'}_=${nonce}`;
  const openHref = mode === 'live' ? proxyUrl(workspaceId, port, '') : previewUrl(workspaceId, entry);

  return (
    <div className="h-full flex flex-col bg-surface">
      <div className="h-9 px-3 flex items-center gap-2 border-b border-edge bg-raised/50">
        <Globe size={14} className="text-astra-600 dark:text-astra-400" aria-hidden="true" />
        <span className="text-xs font-medium">Preview</span>

        {/* Static files vs live dev-server proxy */}
        <div className="ml-1 inline-flex rounded-md border border-edge overflow-hidden text-[11px]">
          <button type="button" onClick={() => setMode('static')}
                  className={cn('px-2 py-0.5 inline-flex items-center gap-1',
                    mode === 'static' ? 'bg-astra-600 text-white' : 'text-faint hover:bg-raised')}>
            <FileCode size={11} /> Files
          </button>
          <button type="button" onClick={() => setMode('live')}
                  className={cn('px-2 py-0.5 inline-flex items-center gap-1',
                    mode === 'live' ? 'bg-astra-600 text-white' : 'text-faint hover:bg-raised')}>
            <Radio size={11} /> Live server
          </button>
        </div>

        {mode === 'live' ? (
          <div className="inline-flex items-center gap-1">
            <span className="text-[11px] text-faint">port</span>
            {detected.length > 0 ? (
              <select value={port} onChange={(e) => setPort(Number(e.target.value))}
                      aria-label="Preview port"
                      className="rounded-md border border-edge bg-surface px-1.5 py-0.5 text-[11px] font-mono">
                {detected.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            ) : (
              <input type="number" value={port} onChange={(e) => setPort(Number(e.target.value) || port)}
                     aria-label="Preview port"
                     className="w-16 rounded-md border border-edge bg-surface px-1.5 py-0.5 text-[11px] font-mono" />
            )}
            <button type="button" onClick={refreshPorts} title="Detect ports" className="btn-ghost p-1"><RotateCw size={11} /></button>
          </div>
        ) : (
          <input value={entry} onChange={(e) => setEntry(e.target.value)}
                 aria-label="Preview entry file"
                 className="ml-1 w-40 rounded-md border border-edge bg-surface px-2 py-0.5 text-[11px] font-mono" />
        )}

        <div className="ml-auto flex items-center gap-1">
          <button type="button" onClick={() => setNonce((n) => n + 1)} title="Reload" className="btn-ghost p-1.5"><RotateCw size={13} /></button>
          <a href={openHref} target="_blank" rel="noreferrer" title="Open in new tab" className="btn-ghost p-1.5"><ExternalLink size={13} /></a>
          <button type="button" onClick={onClose} title="Close preview" className="btn-ghost p-1.5"><X size={13} /></button>
        </div>
      </div>

      <div className="flex-1 min-h-0 bg-white">
        <iframe ref={iframeRef} key={`${mode}-${port}-${nonce}`} src={src} title="Workspace preview"
                className="w-full h-full border-0"
                sandbox="allow-scripts allow-forms allow-popups allow-modals" />
      </div>

      <div className="h-7 px-3 flex items-center gap-3 border-t border-edge bg-raised/50 text-[10px] text-faint">
        <span className="inline-flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          {mode === 'live' ? `proxying port ${port}` : 'serving static files'}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <ServerCog size={11} /> {detected.length ? `detected: ${detected.join(', ')}` : 'no dev server detected'}
        </span>
        <span className="ml-auto truncate">Sandboxed: previewed code is isolated from the IDE.</span>
      </div>
    </div>
  );
}

export function PortsPanel({ workspaceId }: { workspaceId: number }) {
  const [ports, setPorts] = useState<number[]>([]);
  useEffect(() => { getWorkspacePorts(workspaceId).then(setPorts).catch(() => setPorts([])); }, [workspaceId]);
  return (
    <div className="card p-3">
      <div className="t-overline text-faint mb-2 flex items-center gap-1.5">
        <ServerCog size={12} /> Ports in use
      </div>
      {ports.length === 0 ? (
        <p className="text-xs text-faint py-1">
          No dev server detected. Start one in the terminal, e.g.{' '}
          <code className="font-mono text-[11px]">python -m http.server 8080</code>.
        </p>
      ) : ports.map((p) => <PortRow key={p} port={p} label="dev server" href={proxyUrl(workspaceId, p, '')} />)}
    </div>
  );
}

function PortRow({ port, label, href }: { port: number; label: string; href?: string }) {
  return (
    <div className={cn('flex items-center gap-2 py-1.5 text-xs')}>
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
      <span className="font-mono text-ink">{port}</span>
      <span className="text-faint flex-1 truncate">{label}</span>
      {href && (
        <a href={href} target="_blank" rel="noreferrer" className="text-astra-600 dark:text-astra-400 hover:underline inline-flex items-center gap-1">
          open <ExternalLink size={10} />
        </a>
      )}
    </div>
  );
}
