// Utility helpers used by all UI components.
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** Merge Tailwind classes with conflict resolution — the standard Aceternity helper. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
