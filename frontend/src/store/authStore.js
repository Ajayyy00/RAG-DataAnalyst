import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// SECURITY: no JWT is ever stored here. Authentication state lives in HttpOnly
// cookies managed by the browser. We only persist non-sensitive profile data
// (name, role) for UX so the UI can render immediately on reload; the cookie is
// the source of truth and the backend re-validates every request.
export const useAuthStore = create(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,

      // Called after a successful login/me() — receives the user profile only.
      login: (user) => set({ user, isAuthenticated: true }),

      logout: () => {
        set({ user: null, isAuthenticated: false })
      },

      updateUser: (updates) => set((s) => ({ user: { ...s.user, ...updates } })),
    }),
    {
      name: 'hc-auth',
      partialize: (s) => ({ user: s.user, isAuthenticated: s.isAuthenticated }),
    }
  )
)
