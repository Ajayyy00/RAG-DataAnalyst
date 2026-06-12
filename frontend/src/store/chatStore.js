import { create } from 'zustand'

export const useChatStore = create((set, get) => ({
  messages: [],
  isStreaming: false,
  streamingStep: '',
  activeResult: null,

  addUserMessage: (content) => set((s) => ({
    messages: [...s.messages, {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    }]
  })),

  addAssistantMessage: (result) => set((s) => ({
    messages: [...s.messages, {
      id: crypto.randomUUID(),
      role: 'assistant',
      timestamp: new Date().toISOString(),
      ...result,
    }],
    isStreaming: false,
    streamingStep: '',
  })),

  setStreaming: (isStreaming, step = '') => set({ isStreaming, streamingStep: step }),

  setActiveResult: (result) => set({ activeResult: result }),

  clearMessages: () => set({ messages: [], activeResult: null }),

  loadMessages: (messages) => set({ messages }),
}))
