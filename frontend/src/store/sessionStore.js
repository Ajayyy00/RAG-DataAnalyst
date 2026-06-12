import { create } from 'zustand'

export const useSessionStore = create((set) => ({
  sessions: [],
  activeSessionId: null,

  setSessions: (sessions) => set({ sessions }),

  setActiveSession: (id) => set({ activeSessionId: id }),

  addSession: (session) => set((s) => ({
    sessions: [session, ...s.sessions],
    activeSessionId: session.id,
  })),

  removeSession: (id) => set((s) => ({
    sessions: s.sessions.filter((sess) => sess.id !== id),
    activeSessionId: s.activeSessionId === id ? null : s.activeSessionId,
  })),

  updateSession: (id, updates) => set((s) => ({
    sessions: s.sessions.map((sess) => sess.id === id ? { ...sess, ...updates } : sess),
  })),
}))
