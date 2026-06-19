'use client';
// Aceternity-style bento grid — feature cards with hover glow + tilt.
import { motion } from 'framer-motion';
import { cn } from '../../lib/utils';

export function BentoGrid({
  className, children,
}: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        'grid auto-rows-[minmax(180px,_auto)] grid-cols-1 gap-4',
        'md:grid-cols-3',
        className,
      )}
    >
      {children}
    </div>
  );
}

export function BentoCard({
  className, title, description, icon, accent = 'astra', span,
}: {
  className?:    string;
  title:         string;
  description:   string;
  icon?:         React.ReactNode;
  accent?:       'astra' | 'emerald' | 'amber' | 'rose' | 'purple' | 'cyan';
  span?:         'col-2' | 'row-2' | 'col-2-row-2';
}) {
  const accents: Record<string, string> = {
    astra:   'from-astra-500/20 to-astra-600/0 ring-astra-500/30 hover:ring-astra-400/60',
    emerald: 'from-emerald-500/20 to-emerald-600/0 ring-emerald-500/30 hover:ring-emerald-400/60',
    amber:   'from-amber-500/20  to-amber-600/0  ring-amber-500/30  hover:ring-amber-400/60',
    rose:    'from-rose-500/20   to-rose-600/0   ring-rose-500/30   hover:ring-rose-400/60',
    purple:  'from-purple-500/20 to-purple-600/0 ring-purple-500/30 hover:ring-purple-400/60',
    cyan:    'from-cyan-500/20   to-cyan-600/0   ring-cyan-500/30   hover:ring-cyan-400/60',
  };
  const spans: Record<string, string> = {
    'col-2':         'md:col-span-2',
    'row-2':         'md:row-span-2',
    'col-2-row-2':   'md:col-span-2 md:row-span-2',
  };

  return (
    <motion.div
      whileHover={{ y: -4 }}
      transition={{ type: 'spring', stiffness: 300, damping: 25 }}
      className={cn(
        'group relative overflow-hidden rounded-xl p-5',
        'bg-gradient-to-br backdrop-blur-md',
        'ring-1 ring-inset transition-all duration-300',
        accents[accent],
        span ? spans[span] : '',
        className,
      )}
    >
      <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 bg-[radial-gradient(circle_at_var(--mx,_50%)_var(--my,_50%),_rgba(255,255,255,0.06),_transparent_40%)]" />
      <div className="relative z-10">
        {icon && <div className="mb-3 text-2xl">{icon}</div>}
        <h3 className="font-semibold text-lg mb-1.5 text-white">{title}</h3>
        <p className="text-sm text-slate-300 leading-relaxed">{description}</p>
      </div>
    </motion.div>
  );
}
