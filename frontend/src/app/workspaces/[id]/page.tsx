'use client';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import {
  getWorkspace,
  startWorkspace,
  stopWorkspace,
  type Workspace,
} from '../../../lib/api';
import { useAuth } from '../../../lib/auth';

// Editor is client-only (uses window)
const CollabEditor = dynamic(() => import('../../../components/CollabEditor'), { ssr: false });

export default function WorkspacePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { token, user, hydrated } = useAuth();
  const [ws, setWs] = useState<Workspace | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!hydrated) return;     // wait for persisted auth to load
    if (!token) {
      router.push('/login');
      return;
    }
    refresh();
  }, [token, hydrated]);

  async function refresh() {
    try {
      const id = Number(params.id);
      setWs(await getWorkspace(id));
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load workspace');
    }
  }

  if (error) {
    return (
      <main className="p-8">
        <p className="text-red-400">{error}</p>
        <Link href="/dashboard" className="text-astra-500">← Back</Link>
      </main>
    );
  }
  if (!ws || !user) {
    return <main className="p-8 text-slate-400">Loading…</main>;
  }

  return (
    <main className="h-screen flex flex-col">
      <header className="border-b border-slate-800 px-6 py-3 flex items-center gap-4 bg-slate-900">
        <Link href="/dashboard" className="text-astra-500 text-sm hover:underline">← Dashboard</Link>
        <h1 className="font-semibold">{ws.name}</h1>
        <span className="text-xs text-slate-500">{ws.language}</span>

        <span className={`text-[10px] px-1.5 py-0.5 rounded ${tierColor(ws.sandbox_tier)}`}>
          {ws.sandbox_tier}
        </span>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
          risk {ws.risk_score.toFixed(2)}
        </span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${statusColor(ws.status)}`}>
          {ws.status}
        </span>

        <div className="ml-auto flex gap-2 text-sm">
          {ws.status !== 'RUNNING' && (
            <button onClick={async () => { await startWorkspace(ws.id); refresh(); }}
                    className="px-3 py-1 rounded bg-emerald-700 hover:bg-emerald-600">Start</button>
          )}
          {ws.status === 'RUNNING' && (
            <button onClick={async () => { await stopWorkspace(ws.id); refresh(); }}
                    className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600">Stop</button>
          )}
        </div>
      </header>

      <section className="flex-1 min-h-0">
        <CollabEditor
          workspaceId={ws.id}
          room={ws.yjs_room}
          language={ws.language}
          initialCode={undefined}
          username={user.username}
          isOwner={ws.owner_id === user.id}
          status={ws.status}
          sandbox={ws.sandbox_tier}
        />
      </section>
    </main>
  );
}

function tierColor(tier: string): string {
  return {
    runc:        'bg-emerald-900 text-emerald-300',
    gvisor:      'bg-amber-900 text-amber-300',
    firecracker: 'bg-rose-900 text-rose-300',
  }[tier] || 'bg-slate-700';
}
function statusColor(status: string): string {
  return {
    PENDING:   'bg-slate-700',
    PREWARMED: 'bg-blue-700',
    RUNNING:   'bg-emerald-700',
    STOPPED:   'bg-slate-600',
    FAILED:    'bg-red-700',
    ARCHIVED:  'bg-slate-800',
  }[status] || 'bg-slate-700';
}
