'use client';
import Sidebar from './Sidebar';

export { Avatar } from './AvatarInline';

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex">
      <a href="#main" className="skip-link">Skip to content</a>
      <div className="ambient" aria-hidden="true" />
      <Sidebar />
      <main id="main" className="flex-1 min-w-0">{children}</main>
    </div>
  );
}
