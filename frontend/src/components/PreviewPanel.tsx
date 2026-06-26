'use client';
// Live preview (Vercel/StackBlitz style) for static sites in the workspace.
// Renders the workspace's index.html (or a chosen entry) in a sandboxed iframe,
// with reload / open-in-new-tab / close controls and a "ports" indicator.

import { useRef, useState } from 'react';
import { ExternalLink, RotateCw, X, Globe, ServerCog } from 'lucide-react';
import { previewUrl } from '../lib/api';
import { cn } from '../lib/utils';

export default function PreviewPanel({ workspaceId, onClose }:
  { workspaceId: number; onClose: () => void }) {
  const [entry, setEntry] = useState('index.html');
  const [nonce, setNonce] = useState(0);          // bump to reload the iframe
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const src = `${previewUrl(workspaceId, entry)}&_=${nonce}`;

  return (
    <div className="h-full flex flex-col bg-surface">
      <div className="h-9 px-3 flex items-center gap-2 border-b border-edge bg-raised/50">
        <Globe size={14} className="text-astra-600 dark:text-astra-400" aria-hidden="true" />
        <span className="text-xs font-medium">Preview</span>
        <input value={entry} onChange={(e) => setEntry(e.target.value)}
               aria-label="Preview entry file"
               className="ml-1 w-40 rounded-md border border-edge bg-surface px-2 py-0.5 text-[11px] font-mono" />
        <div className="ml-auto flex items-center gap-1">
          <button type="button" onClick={() => setNonce((n) => n + 1)} title="Reload" className="btn-ghost p-1.5"><RotateCw size={13} /></button>
          <a href={previewUrl(workspaceId, entry)} target="_blank" rel="noreferrer"
             title="Open in new tab" className="btn-ghost p-1.5"><ExternalLink size={13} /></a>
          <button type="button" onClick={onClose} title="Close preview" className="btn-ghost p-1.5"><X size={13} /></button>
        </div>
      </div>

      <div className="flex-1 min-h-0 bg-white">
        <iframe ref={iframeRef} key={nonce} src={src} title="Workspace preview"
                className="w-full h-full border-0"
                sandbox="allow-scripts allow-forms allow-popups allow-modals" />
      </div>

      <div className="h-7 px-3 flex items-center gap-3 border-t border-edge bg-raised/50 text-[10px] text-faint">
        <span className="inline-flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" /> serving static files
        </span>
        <span className="inline-flex items-center gap-1.5">
          <ServerCog size={11} /> port 3000 (proxied)
        </span>
        <span className="ml-auto truncate">Sandboxed: previewed code is isolated from the IDE.</span>
      </div>
    </div>
  );
}

export function PortsPanel({ workspaceId }: { workspaceId: number }) {
  return (
    <div className="card p-3">
      <div className="t-overline text-faint mb-2 flex items-center gap-1.5">
        <ServerCog size={12} /> Ports in use
      </div>
      <PortRow port={3000} label="preview (static)" href={previewUrl(workspaceId)} />
      <PortRow port={8000} label="workspace API" />
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
