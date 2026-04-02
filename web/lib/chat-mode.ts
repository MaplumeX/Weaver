export const CHAT_MODES = ['agent', 'deep'] as const

export type ChatMode = (typeof CHAT_MODES)[number]

export interface SearchModePayload {
  mode: ChatMode
}

export const DEFAULT_CHAT_MODE: ChatMode = 'agent'

export function normalizeChatMode(value?: string | null): ChatMode {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'deep') {
    return 'deep'
  }
  return 'agent'
}

export function isChatMode(value: unknown): value is ChatMode {
  return value === 'agent' || value === 'deep'
}

export function createSearchModePayload(mode?: string | null): SearchModePayload {
  return { mode: normalizeChatMode(mode) }
}
