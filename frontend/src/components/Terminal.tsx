'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Terminal as XTerm } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { Eraser, RotateCw, TerminalSquare } from 'lucide-react';
import '@xterm/xterm/css/xterm.css';

import { cn } from '../lib/utils';

/**
 * Interactive sandbox shell for a workspace. An xterm.js terminal bridged over
 * WebSocket to a real shell on the execution host, rooted in this workspace's
 * file tree (same files as the Explorer). Keystrokes are sent as {"i": data};
 * window resizes as {"r": [rows, cols]}.
 */

type ConnState = 'connecting' | 'connected' | 'closed' | 'error';

export default function Terminal({ workspaceId }: { workspaceId: number }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<XTerm | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [conn, setConn] = useState<ConnState>('connecting');
  const [epoch, setEpoch] = useState(0);          // bump to force reconnect

  const reconnect = useCallback(() => setEpoch((e) => e + 1), []);
  const clear = useCallback(() => termRef.current?.clear(), []);

  useEffect(() => {
    if (!hostRef.current) return;

    const term = new XTerm({
      fontFamily: '"JetBrains Mono", "Cascadia Code", ui-monospace, SFMono-Regular, Menlo, monospace',
      fontSize: 13,
      lineHeight: 1.35,
      allowTransparency: true,
      theme: {
        background: 'rgba(20, 30, 27, 0.35)',   // translucent so the glass shows through
        foreground: '#dbe5d8',
        cursor: '#9CB080',
        cursorAccent: '#1b2420',
        selectionBackground: '#2B5748',
        black: '#1e293b', brightBlack: '#475569',
        red: '#f87171',   brightRed: '#fca5a5',
        green: '#34d399', brightGreen: '#6ee7b7',
        yellow: '#fbbf24', brightYellow: '#fcd34d',
        blue: '#60a5fa',  brightBlue: '#93c5fd',
        magenta: '#c084fc', brightMagenta: '#d8b4fe',
        cyan: '#22d3ee',  brightCyan: '#67e8f9',
        white: '#e2e8f0', brightWhite: '#f8fafc',
      },
      cursorBlink: true,
      scrollback: 4000,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(hostRef.current);
    termRef.current = term;
    try { fit.fit(); } catch { /* not laid out yet */ }

    // token lives in the persisted auth store
    let token = '';
    try {
      const raw = window.localStorage.getItem('astra-auth');
      token = raw ? (JSON.parse(raw)?.state?.token ?? '') : '';
    } catch { /* ignore */ }

    // Connect to the terminal WS on the SAME origin the user is on (Caddy routes
    // /api/v1/* straight to the backend). In local dev (port 3000) fall back to
    // the Next.js /api proxy.
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const isDev = window.location.port === '3000' || window.location.hostname === 'localhost';
    const url = isDev
      ? `${proto}://${window.location.host}/api/workspaces/${workspaceId}/terminal?token=${encodeURIComponent(token)}`
      : `${proto}://${window.location.host}/api/v1/workspaces/${workspaceId}/terminal?token=${encodeURIComponent(token)}`;

    setConn('connecting');
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConn('connected');
      ws.send(JSON.stringify({ r: [term.rows, term.cols] }));
    };
    ws.onmessage = (e) => term.write(e.data);
    ws.onclose = () => setConn((c) => (c === 'error' ? c : 'closed'));
    ws.onerror = () => setConn('error');

    const dataSub = term.onData((d) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ i: d }));
    });

    const onResize = () => {
      try { fit.fit(); } catch { /* ignore */ }
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ r: [term.rows, term.cols] }));
    };
    window.addEventListener('resize', onResize);
    const t = setTimeout(onResize, 60);

    // Refit when the panel itself is resized (e.g. dragging the terminal height).
    const ro = new ResizeObserver(() => onResize());
    if (hostRef.current) ro.observe(hostRef.current);

    return () => {
      clearTimeout(t);
      ro.disconnect();
      window.removeEventListener('resize', onResize);
      dataSub.dispose();
      ws.close();
      term.dispose();
      termRef.current = null;
    };
  }, [workspaceId, epoch]);

  return (
    <div className="h-full flex flex-col bg-[#16211d]/55 backdrop-blur-2xl">
      {/* Terminal chrome */}
      <div className="h-9 px-3 flex items-center gap-3 border-b border-white/10 bg-white/5 select-none">
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-rose-500/80" />
          <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
        </div>
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <TerminalSquare size={13} className="text-astra-400" />
          <span className="font-medium text-slate-300">Sandbox shell</span>
          <span className="text-slate-600">/</span>
          <span className="font-mono">workspace-{workspaceId}</span>
        </div>
        <span className={cn(
          'text-[10px] px-2 py-0.5 rounded-full font-medium',
          conn === 'connected'  && 'bg-emerald-900/70 text-emerald-300',
          conn === 'connecting' && 'bg-amber-900/70 text-amber-300',
          (conn === 'closed' || conn === 'error') && 'bg-rose-900/70 text-rose-300',
        )}>
          {conn === 'connected' ? 'connected' : conn === 'connecting' ? 'connecting' : 'disconnected'}
        </span>
        <div className="ml-auto flex items-center gap-1">
          <button type="button" onClick={clear} title="Clear scrollback"
                  className="p-1.5 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800">
            <Eraser size={13} />
          </button>
          <button type="button" onClick={reconnect} title="Reconnect"
                  className="p-1.5 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800">
            <RotateCw size={13} />
          </button>
        </div>
      </div>

      {/* xterm mount */}
      <div ref={hostRef} className="flex-1 min-h-0 px-2 py-1.5" />

      {/* Footer hint */}
      <div className="h-6 px-3 flex items-center border-t border-white/10 bg-white/5 text-[10px] text-slate-400">
        Shell session is rooted in this workspace's files. The same tree is visible in the Files tab.
      </div>
    </div>
  );
}
