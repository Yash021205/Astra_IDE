// Auth state (Zustand) — persists token + current user to localStorage so
// page refreshes don't log the user out.
//
// IMPORTANT: With Next.js SSR + Zustand `persist`, rehydration from
// localStorage happens AFTER the initial client render. Components that
// guard on `!token` must also check `hydrated` to avoid redirecting before
// the persisted state has loaded.

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { User } from './api';

interface AuthState {
  token:    string | null;
  user:     User | null;
  hydrated: boolean;
  setSession:   (token: string, user: User) => void;
  clearSession: () => void;
  setHydrated:  () => void;
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user:  null,
      hydrated: false,
      setHydrated:  () => set({ hydrated: true }),
      setSession:   (token, user) => set({ token, user }),
      clearSession: () => set({ token: null, user: null }),
    }),
    {
      name:    'astra-auth',
      storage: createJSONStorage(() => localStorage),
      // Only persist token + user (not the hydrated flag itself)
      partialize: (state) => ({ token: state.token, user: state.user }),
      onRehydrateStorage: () => (state) => {
        // Mark hydrated AFTER persisted state has been loaded into the store
        state?.setHydrated();
      },
    }
  )
);
