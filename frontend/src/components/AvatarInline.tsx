'use client';

export function Avatar({ user, size = 24 }:
  { user: { username?: string; avatar_url?: string | null } | null; size?: number }) {
  if (user?.avatar_url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={user.avatar_url} alt="" width={size} height={size}
                className="rounded-full object-cover" style={{ width: size, height: size }} />;
  }
  return (
    <span className="rounded-full bg-astra-600 text-white font-semibold flex items-center justify-center"
          style={{ width: size, height: size, fontSize: size * 0.42 }} aria-hidden="true">
      {(user?.username?.[0] ?? '?').toUpperCase()}
    </span>
  );
}
