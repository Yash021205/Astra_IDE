// Runtime-relative WebSocket URLs so collab/terminal work on whatever domain
// the user is actually on (astraide.tech, the sslip host, localhost…), instead
// of a host baked in at build time.

export function collabWsUrl(): string {
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
  if (typeof window === 'undefined') return '';
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}`;
}
