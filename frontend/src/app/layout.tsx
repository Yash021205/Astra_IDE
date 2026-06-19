import './globals.css';
import type { Metadata, Viewport } from 'next';
import Toaster from '../components/Toaster';
import CommandPalette from '../components/CommandPalette';

export const metadata: Metadata = {
  metadataBase: new URL('https://astra-ide.local'),
  title: {
    default:  'ASTRA-IDE — Cloud IDE that schedules itself',
    template: '%s — ASTRA-IDE',
  },
  description:
    'Adaptive Scheduling & Telemetry-driven Resource-aware Cloud IDE. ' +
    'DRL-PPO scheduling, eBPF observability, adaptive sandboxing, ' +
    'LSTM prewarming, multi-cluster federation, and Yjs CRDT collaboration.',
  applicationName: 'ASTRA-IDE',
  keywords: [
    'cloud IDE', 'DRL', 'PPO', 'reinforcement learning', 'eBPF',
    'kubernetes', 'monaco editor', 'yjs', 'crdt', 'sandboxing',
    'firecracker', 'gvisor', 'collaborative coding',
  ],
  authors: [{ name: 'Prasanna Mishra' }],
  creator:   'Prasanna Mishra',
  publisher: 'ASTRA-IDE',
  icons: {
    icon: [
      { url: '/logo.png',    type: 'image/png' },
      { url: '/favicon.png', type: 'image/png', sizes: '32x32' },
    ],
    apple: [
      { url: '/apple-touch-icon.png', sizes: '180x180', type: 'image/png' },
    ],
    shortcut: '/favicon.png',
  },
  openGraph: {
    type: 'website',
    title: 'ASTRA-IDE',
    description: 'The cloud IDE that schedules itself.',
    siteName: 'ASTRA-IDE',
    images: [{ url: '/og-image.png', width: 1200, height: 630, alt: 'ASTRA-IDE' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'ASTRA-IDE',
    description: 'The cloud IDE that schedules itself.',
    images: ['/og-image.png'],
  },
};

export const viewport: Viewport = {
  themeColor:   '#1d4ed8',
  width:        'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="bg-slate-950 text-slate-100 min-h-screen font-sans antialiased selection:bg-astra-600/40">
        {children}
        <Toaster />
        <CommandPalette />
      </body>
    </html>
  );
}
