// Time helpers. The backend stores naive UTC; older rows may arrive without a
// timezone suffix, which `new Date()` would parse as LOCAL time (the source of
// the "5h ago" bug in IST). parseUTC treats suffix-less timestamps as UTC.

export function parseUTC(iso: string): Date {
  if (!iso) return new Date(NaN);
  const hasTz = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso);
  return new Date(hasTz ? iso : iso + 'Z');
}

export function formatRel(iso: string): string {
  const t = parseUTC(iso).getTime();
  if (Number.isNaN(t)) return '';
  const diff = Date.now() - t;
  if (diff < 5_000)      return 'now';
  if (diff < 60_000)     return `${Math.floor(diff / 1000)}s ago`;
  if (diff < 3_600_000)  return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return parseUTC(iso).toLocaleString();
}
