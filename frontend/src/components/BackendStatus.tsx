'use client';
import { useCallback, useEffect, useRef, useState } from 'react';

import Tooltip from './ui/Tooltip';
import { cn } from '../lib/utils';

/**
 * Live backend/VM reachability indicator.
 *
 * The UI is hosted separately from the backend (Vercel serves the frontend, the VM
 * runs the API, Kubernetes and the workspace pods). When the VM is stopped, the app
 * still loads perfectly but every API call fails, which is indistinguishable from a
 * bug. This dot makes that state obvious at a glance on every page.
 *
 * It polls the public `/api/v1/health` endpoint, which also reports whether the real
 * Kubernetes backing is live, so a green dot means "VM up AND cluster wired", not
 * merely "web process answered".
 */

type State = 'checking' | 'online' | 'degraded' | 'offline';

const POLL_MS = 20_000;
const TIMEOUT_MS = 6_000;

export default function BackendStatus({ className }: { className?: string }) {
  const [state, setState] = useState<State>('checking');
  const [detail, setDetail] = useState<string>('Checking backend…');
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const timer = useRef<ReturnType<typeof setInterval>>();

  const check = useCallback(async () => {
    const controller = new AbortController();
    const abort = setTimeout(() => controller.abort(), TIMEOUT_MS);
    try {
      // Note the path: the Next.js rewrite maps /api/:path* -> BACKEND_URL/api/v1/:path*,
      // so the client asks for /api/health and the backend receives /api/v1/health.
      // Using /api/v1/health here would double the prefix and 404 on Vercel (it only
      // appears to work on the VM because Caddy proxies /api/v1/* straight through).
      const res = await fetch('/api/health', {
        signal: controller.signal,
        cache: 'no-store',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = await res.json();
      if (body?.k8s) {
        setState('online');
        setDetail(`Backend online · cluster live · scheduler ${body.scheduler ?? 'n/a'}`);
      } else {
        // API is answering but the real cluster is not wired up (k3s down, or the
        // backend fell back to the simulator).
        setState('degraded');
        setDetail('Backend online · cluster not connected');
      }
    } catch {
      setState('offline');
      setDetail('Backend unreachable — start the VM to bring it back');
    } finally {
      clearTimeout(abort);
      setCheckedAt(new Date());
    }
  }, []);

  useEffect(() => {
    check();
    timer.current = setInterval(check, POLL_MS);
    const onFocus = () => check();
    window.addEventListener('focus', onFocus);
    return () => {
      clearInterval(timer.current);
      window.removeEventListener('focus', onFocus);
    };
  }, [check]);

  const dot: Record<State, string> = {
    checking: 'bg-amber-400',
    online:   'bg-emerald-500',
    degraded: 'bg-amber-500',
    offline:  'bg-rose-500',
  };
  const label: Record<State, string> = {
    checking: 'Checking',
    online:   'Online',
    degraded: 'Degraded',
    offline:  'Offline',
  };

  return (
    <Tooltip
      side="bottom"
      content={
        <span className="flex flex-col gap-0.5">
          <span>{detail}</span>
          {checkedAt && (
            <span className="text-faint font-normal">
              checked {checkedAt.toLocaleTimeString()}
            </span>
          )}
        </span>
      }
    >
      <button
        type="button"
        onClick={check}
        aria-label={`Backend status: ${label[state]}. Click to re-check.`}
        className={cn(
          'flex items-center gap-1.5 px-2 py-1.5 rounded-lg transition-colors',
          'hover:bg-ink/5 dark:hover:bg-white/10',
          className,
        )}
      >
        <span className="relative flex h-2 w-2">
          {state === 'online' && (
            <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
          )}
          <span className={cn('relative inline-flex h-2 w-2 rounded-full', dot[state])} />
        </span>
        <span className="hidden lg:inline text-xs text-muted">{label[state]}</span>
      </button>
    </Tooltip>
  );
}
