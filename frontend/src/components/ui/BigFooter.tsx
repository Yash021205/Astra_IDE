'use client';
// Aceternity-style footer: a giant translucent "ASTRA-IDE" wordmark sits as a
// background layer; the real footer line + links are layered cleanly in front
// (absolute wordmark, padded foreground — no fragile negative margins). Links
// shift color on hover.

import Link from 'next/link';
import { Github } from 'lucide-react';

export default function BigFooter() {
  return (
    <footer className="relative border-t border-edge bg-bg overflow-hidden">
      {/* Giant background wordmark, clipped at the bottom edge */}
      <div className="pointer-events-none select-none absolute inset-x-0 bottom-[-0.18em] flex justify-center">
        <span
          className="font-extrabold tracking-tighter leading-none text-transparent bg-clip-text
                     bg-gradient-to-b from-ink/[0.07] to-ink/[0.015]
                     text-[26vw] lg:text-[17rem]"
        >
          ASTRA-IDE
        </span>
      </div>

      {/* Foreground content */}
      <div className="relative z-10 max-w-6xl mx-auto px-6 pt-12 pb-44 sm:pb-56 flex flex-col items-center gap-4">
        <nav className="flex flex-wrap items-center justify-center gap-5 sm:gap-6 text-sm">
          <Link href="/dashboard" className="text-muted hover:text-astra-500 transition-colors">Workspaces</Link>
          <Link href="/clusters" className="text-muted hover:text-astra-600 dark:hover:text-astra-300 transition-colors">Clusters</Link>
          <Link href="/benchmarks" className="text-muted hover:text-blossom-500 dark:hover:text-blossom-300 transition-colors">Benchmarks</Link>
          <Link href="/platform" className="text-muted hover:text-astra-500 transition-colors">Platform</Link>
        </nav>
        <div className="text-xs text-faint flex items-center gap-2">
          <span className="hover:text-ink transition-colors">ASTRA-IDE</span>
          <span aria-hidden="true">&middot;</span>
          <span className="hover:text-ink transition-colors">2026</span>
          <span aria-hidden="true">&middot;</span>
          <a href="https://github.com/PrasannaMishra001/astra-ide"
             className="inline-flex items-center gap-1 hover:text-astra-500 transition-colors">
            <Github size={12} /> GitHub
          </a>
        </div>
      </div>
    </footer>
  );
}
