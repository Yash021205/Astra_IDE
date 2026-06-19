'use client';
// Aceternity-style typewriter — letters appear one-by-one with a blinking caret.

import { useEffect, useState } from 'react';
import { cn } from '../../lib/utils';

export default function TypewriterEffect({
  text, className, speed = 40, onComplete,
}: {
  text:        string;
  className?:  string;
  speed?:      number;   // ms per character
  onComplete?: () => void;
}) {
  const [displayed, setDisplayed] = useState('');
  const [done, setDone] = useState(false);

  useEffect(() => {
    setDisplayed('');
    setDone(false);
    let i = 0;
    const interval = setInterval(() => {
      i += 1;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) {
        clearInterval(interval);
        setDone(true);
        onComplete?.();
      }
    }, speed);
    return () => clearInterval(interval);
  }, [text, speed, onComplete]);

  return (
    <span className={cn('inline-block', className)}>
      {displayed}
      <span
        className={cn(
          'inline-block w-[2px] ml-0.5 bg-current align-middle',
          'h-[1em]',
          done ? 'animate-pulse' : '',
        )}
      />
    </span>
  );
}
