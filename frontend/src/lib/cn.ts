// Utility for conditional className merging (clsx + tailwind-merge).
// Used by every Aceternity-style component.
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
