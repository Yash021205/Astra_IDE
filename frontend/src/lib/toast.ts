// Minimal Zustand-based toast store. No external dependency.
// Used by `<Toaster />` (mounted once in the root layout) and the
// `toast.{success,error,info,warning}()` helpers.

import { create } from 'zustand';

export type ToastKind = 'success' | 'error' | 'info' | 'warning';

export interface Toast {
  id:        string;
  kind:      ToastKind;
  title:     string;
  message?:  string;
  duration?: number;   // ms, default 4000
}

interface ToastStore {
  items: Toast[];
  push:   (t: Omit<Toast, 'id'>) => void;
  remove: (id: string) => void;
}

export const useToastStore = create<ToastStore>((set, get) => ({
  items: [],
  push: (t) => {
    const id = Math.random().toString(36).slice(2, 10);
    const item: Toast = { id, duration: 4000, ...t };
    set((s) => ({ items: [...s.items, item] }));
    setTimeout(() => get().remove(id), item.duration);
  },
  remove: (id) => set((s) => ({ items: s.items.filter((t) => t.id !== id) })),
}));

// Convenience helpers
export const toast = {
  success: (title: string, message?: string) =>
    useToastStore.getState().push({ kind: 'success', title, message }),
  error: (title: string, message?: string) =>
    useToastStore.getState().push({ kind: 'error', title, message, duration: 6000 }),
  info: (title: string, message?: string) =>
    useToastStore.getState().push({ kind: 'info', title, message }),
  warning: (title: string, message?: string) =>
    useToastStore.getState().push({ kind: 'warning', title, message }),
};
