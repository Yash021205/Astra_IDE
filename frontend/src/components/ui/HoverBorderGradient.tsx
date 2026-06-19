'use client';
// Aceternity-style button with an animated conic-gradient border on hover.

import { cn } from '../../lib/utils';

export default function HoverBorderGradient({
  children, className, containerClassName, as: Tag = 'button', ...rest
}: {
  children:            React.ReactNode;
  className?:          string;    // inner pill classes
  containerClassName?: string;    // outer wrapper classes (Aceternity API)
  as?:                 React.ElementType;
  [k: string]: unknown;
}) {
  return (
    <Tag
      {...rest}
      className={cn(
        'group relative inline-flex items-center justify-center overflow-hidden rounded-full p-[1.5px]',
        'transition-all duration-300',
        containerClassName,
      )}
    >
      <span
        className="absolute inset-0 rounded-full opacity-60 transition-opacity duration-500 group-hover:opacity-100"
        style={{
          background: 'conic-gradient(from 0deg, #3b82f6, #a855f7, #ec4899, #3b82f6)',
          animation:  'spin 6s linear infinite',
        }}
      />
      <span className={cn(
        'relative z-10 inline-flex items-center justify-center gap-2 rounded-full bg-slate-950 px-5 py-2.5 text-sm font-medium text-white',
        className,
      )}>
        {children}
      </span>
    </Tag>
  );
}
