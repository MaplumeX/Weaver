export const CHAT_MODES = ['agent', 'deep'] as const

export type ChatMode = (typeof CHAT_MODES)[number]

export interface SearchModePayload {
  mode: ChatMode
}

export const DEFAULT_CHAT_MODE: ChatMode = 'agent'

const DEEP_MODE_ALIASES = new Set(['deep', 'ultra', 'deep_agent', 'deep-agent'])

export function normalizeChatMode(value?: string | null): ChatMode {
  const normalized = String(value || '').trim().toLowerCase()
  if (DEEP_MODE_ALIASES.has(normalized)) {
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
