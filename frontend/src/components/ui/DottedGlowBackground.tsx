'use client';
import { cn } from '../../lib/utils';

export default function DottedGlowBackground({
  children, className, dotColor = 'rgba(99,102,241,0.25)', glowColor = 'rgba(168,85,247,0.15)',
}: {
  children: React.ReactNode; className?: string;
  dotColor?: string; glowColor?: string;
}) {
  return (
    <div className={cn('relative overflow-hidden', className)}>
      <div className="absolute inset-0 pointer-events-none"
           style={{
             backgroundImage: `radial-gradient(${dotColor} 1px, transparent 1px)`,
             backgroundSize: '24px 24px',
           }} />
      <div className="absolute inset-0 pointer-events-none"
           style={{
             background: `radial-gradient(ellipse 60% 50% at 50% 50%, ${glowColor}, transparent 70%)`,
           }} />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
