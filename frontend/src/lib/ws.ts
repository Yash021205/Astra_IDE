// Runtime-relative WebSocket URLs so collab/terminal work on whatever domain
// the user is actually on (astraide.tech, the sslip host, localhost…), instead
// of a host baked in at build time.
//
// NEXT_PUBLIC_WS_HOST is an explicit override for split deployments where the UI
// and the WebSocket backend live on different hosts — e.g. the frontend on Vercel
// while the terminal, collab relay and workspace pods stay on the VM. Vercel
// cannot proxy long-lived WebSockets, so when it is set both WS endpoints point
// straight at the VM origin (e.g. "wss://34-14-181-224.sslip.io"). When it is
// unset, behaviour is exactly the same-host logic the single-VM deploy relies on.

const WS_HOST = process.env.NEXT_PUBLIC_WS_HOST;

export function collabWsUrl(): string {
  if (WS_HOST) return `${WS_HOST}/collab`;
  if (typeof window === 'undefined') return 'ws://localhost:1234';
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  // In production Caddy routes /collab/* to the collab server (prefix stripped).
  // In local dev the collab server is on :1234 directly.
  if (window.location.port === '3000' || window.location.hostname === 'localhost') {
    return process.env.NEXT_PUBLIC_COLLAB_WS_URL || 'ws://localhost:1234';
  }
  return `${proto}://${window.location.host}/collab`;
}

export function backendWsBase(): string {
  if (WS_HOST) return WS_HOST;
  if (typeof window === 'undefined') return '';
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}`;
}
