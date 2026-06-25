import './globals.css';
import type { Metadata, Viewport } from 'next';
import Toaster from '../components/Toaster';
import CommandPalette from '../components/CommandPalette';
import { THEME_BOOT_SCRIPT } from '../lib/theme';

export const metadata: Metadata = {
  metadataBase: new URL('https://astra-ide.local'),
  title: {
    default:  'ASTRA-IDE | Cloud IDE that schedules itself',
    template: '%s | ASTRA-IDE',
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
  themeColor:   '#2B5748',
  width:        'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Apply the saved theme before first paint (prevents light/dark flash). */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
        {/* Typography system (MongoDB-style: geometric sans + serif display +
            Source Code Pro for code). Loaded at runtime to keep Docker builds
            offline-safe. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,500;8..60,600;8..60,700&family=Source+Code+Pro:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-bg text-ink min-h-screen font-sans antialiased selection:bg-astra-600/30">
        {children}
        <Toaster />
        <CommandPalette />
      </body>
    </html>
  );
}
