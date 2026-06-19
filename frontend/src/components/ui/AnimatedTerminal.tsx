'use client';
// Animated terminal — types out a scripted sequence of commands and outputs,
// like Aceternity's terminal demo but data-driven.

import { useEffect, useRef, useState } from 'react';
import { cn } from '../../lib/utils';

export interface TerminalLine {
  prompt?: string;            // e.g. "$" or ">"
  text:    string;            // the line to render
  delay?:  number;            // ms before this line starts
  speed?:  number;            // ms per char for typed lines
  kind?:   'cmd' | 'out' | 'ok' | 'warn' | 'err' | 'comment';
}

export default function AnimatedTerminal({
  lines, className, title = 'astra-ide@cloud', autoLoop = true,
}: {
  lines:     TerminalLine[];
  className?: string;
  title?:    string;
  autoLoop?: boolean;
}) {
  const [shown, setShown] = useState<TerminalLine[]>([]);
  const [typing, setTyping] = useState<string>('');
  const [cursor, setCursor] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (cursor >= lines.length) {
      if (autoLoop) {
        const t = setTimeout(() => {
          setShown([]);
          setTyping('');
          setCursor(0);
        }, 3000);
        return () => clearTimeout(t);
      }
      return;
    }
    const line = lines[cursor];
    const delay = line.delay ?? (line.kind === 'cmd' ? 400 : 200);
    const speed = line.speed ?? (line.kind === 'cmd' ? 30 : 8);

    const start = setTimeout(() => {
      let i = 0;
      setTyping('');
      const ticker = setInterval(() => {
        i += 1;
        setTyping(line.text.slice(0, i));
        if (i >= line.text.length) {
          clearInterval(ticker);
          setShown((s) => [...s, line]);
          setTyping('');
          setCursor((c) => c + 1);
        }
      }, speed);
    }, delay);
    return () => clearTimeout(start);
  }, [cursor, lines, autoLoop]);

  useEffect(() => {
    const el = containerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [shown, typing]);

  const colorFor = (kind?: TerminalLine['kind']) => {
    switch (kind) {
      case 'cmd':     return 'text-slate-100';
      case 'out':     return 'text-slate-300';
      case 'ok':      return 'text-emerald-400';
      case 'warn':    return 'text-amber-400';
      case 'err':     return 'text-rose-400';
      case 'comment': return 'text-slate-500 italic';
      default:        return 'text-slate-200';
    }
  };

  return (
    <div className={cn('rounded-xl border border-slate-800 bg-slate-950/80 shadow-2xl overflow-hidden font-mono text-[13px]', className)}>
      {/* Title bar with traffic-light dots */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-800 bg-slate-900/60">
        <span className="h-2.5 w-2.5 rounded-full bg-rose-500" />
        <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
        <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
        <span className="ml-3 text-xs text-slate-400">{title}</span>
      </div>

      {/* Output area */}
      <div ref={containerRef} className="p-4 h-[280px] overflow-y-auto leading-relaxed">
        {shown.map((line, idx) => (
          <div key={idx} className={cn('whitespace-pre-wrap', colorFor(line.kind))}>
            {line.prompt && <span className="text-astra-500 mr-2">{line.prompt}</span>}
            {line.text}
          </div>
        ))}
        {cursor < lines.length && (
          <div className={cn('whitespace-pre-wrap', colorFor(lines[cursor].kind))}>
            {lines[cursor].prompt && (
              <span className="text-astra-500 mr-2">{lines[cursor].prompt}</span>
            )}
            {typing}
            <span className="inline-block w-2 h-4 -mb-1 ml-0.5 bg-slate-100 animate-pulse" />
          </div>
        )}
      </div>
    </div>
  );
}
