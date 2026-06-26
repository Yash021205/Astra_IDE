'use client';
// Live presence bar (Google-Docs style): shows everyone currently in the
// workspace, their avatar/initial in their cursor colour, and which file each
// is viewing. Backed by a dedicated Yjs awareness room over the collab server
// (independent of the editor doc), so it works on every tab.

import { useEffect, useRef, useState } from 'react';
import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';
import { collabWsUrl } from '../lib/ws';

export interface Peer { name: string; color: string; file: string; avatar?: string | null; self?: boolean; }

const COLORS = ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];
function colorFor(name: string): string {
  let h = 0; for (const c of name) h = (h * 31 + c.charCodeAt(0)) & 0xffff;
  return COLORS[h % COLORS.length];
}

export function usePresence(room: string, username: string, file: string,
                            avatar?: string | null): Peer[] {
  const [peers, setPeers] = useState<Peer[]>([]);
  const provRef = useRef<WebsocketProvider | null>(null);

  useEffect(() => {
    const wsUrl = collabWsUrl();
    const ydoc = new Y.Doc();
    const provider = new WebsocketProvider(wsUrl, `presence-${room}`, ydoc);
    provRef.current = provider;
    const me = colorFor(username);
    provider.awareness.setLocalStateField('user',
      { name: username, color: me, file, avatar: avatar ?? null });

    const onChange = () => {
      const clientId = provider.awareness.clientID;
      const list: Peer[] = [];
      provider.awareness.getStates().forEach((st: any, id: number) => {
        if (st.user?.name) {
          list.push({ name: st.user.name, color: st.user.color || colorFor(st.user.name),
                      file: st.user.file || '', avatar: st.user.avatar, self: id === clientId });
        }
      });
      setPeers(list);
    };
    provider.awareness.on('change', onChange);
    onChange();
    return () => { provider.awareness.off('change', onChange); provider.destroy(); ydoc.destroy(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room, username]);

  // Broadcast the current file when it changes (without reconnecting).
  useEffect(() => {
    const p = provRef.current;
    if (p) p.awareness.setLocalStateField('user',
      { name: username, color: colorFor(username), file, avatar: avatar ?? null });
  }, [file, username, avatar]);

  return peers;
}

export default function PresenceBar({ peers }: { peers: Peer[] }) {
  if (peers.length === 0) return null;
  const shown = peers.slice(0, 6);
  return (
    <div className="flex items-center gap-1.5" aria-label={`${peers.length} people here`}>
      <div className="flex -space-x-1.5">
        {shown.map((p, i) => (
          <span key={p.name + i}
                title={`${p.name}${p.self ? ' (you)' : ''}${p.file ? ` — ${p.file}` : ''}`}
                className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-semibold
                           text-white ring-2 ring-surface overflow-hidden"
                style={{ backgroundColor: p.color }}>
            {p.avatar
              // eslint-disable-next-line @next/next/no-img-element
              ? <img src={p.avatar} alt="" className="w-full h-full object-cover" />
              : p.name[0]?.toUpperCase()}
          </span>
        ))}
      </div>
      <span className="text-[11px] text-faint hidden sm:inline">
        {peers.length === 1 ? 'only you' : `${peers.length} here`}
      </span>
    </div>
  );
}
