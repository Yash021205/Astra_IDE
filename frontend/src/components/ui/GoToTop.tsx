'use client';
// Floating "scroll to top" button — appears after scrolling down a bit.

import { useEffect, useState } from 'react';
import { ArrowUp } from 'lucide-react';
import { cn } from '../../lib/utils';

export default function GoToTop() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const onScroll = () => setShow(window.scrollY > 400);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <button
      type="button"
      aria-label="Scroll to top"
      onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
      className={cn(
        'fixed bottom-6 right-6 z-50 grid place-items-center w-11 h-11 rounded-full',
        'bg-astra-600 dark:bg-astra-500 text-white dark:text-astra-900 shadow-pop',
        'transition-all duration-300 hover:scale-110',
        show ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4 pointer-events-none',
      )}
    >
      <ArrowUp size={18} />
    </button>
  );
}
