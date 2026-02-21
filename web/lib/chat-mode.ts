import type { components } from '@/lib/api-types'

export type SearchMode = components['schemas']['SearchMode']

export type CoreModeId = 'direct' | 'web' | 'agent' | 'ultra'
export type UiModeId = CoreModeId | 'mcp'

export function searchModeFromId(id: CoreModeId): SearchMode {
  switch (id) {
    case 'web':
      return { useWebSearch: true, useAgent: false, useDeepSearch: false }
    case 'agent':
      return { useWebSearch: false, useAgent: true, useDeepSearch: false }
    case 'ultra':
      return { useWebSearch: false, useAgent: true, useDeepSearch: true }
    case 'direct':
    default:
      return { useWebSearch: false, useAgent: false, useDeepSearch: false }
  }
}

export function normalizeSearchMode(mode: SearchMode): SearchMode {
  const safe: SearchMode = {
    useWebSearch: Boolean(mode?.useWebSearch),
    useAgent: Boolean(mode?.useAgent),
    useDeepSearch: Boolean(mode?.useDeepSearch),
  }

  // Keep semantics aligned with backend normalization: deep search requires agent.
  if (safe.useDeepSearch && !safe.useAgent) {
    safe.useDeepSearch = false
  }

  return safe
}

export function deriveUiModeId(mode: SearchMode, mcpMode: boolean): UiModeId {
  if (mcpMode) return 'mcp'

  const safe = normalizeSearchMode(mode)
  if (safe.useAgent && safe.useDeepSearch) return 'ultra'
  if (safe.useAgent) return 'agent'
  if (safe.useWebSearch) return 'web'
  return 'direct'
}

export function toNullableSearchMode(mode: SearchMode): SearchMode | null {
  const safe = normalizeSearchMode(mode)
  const anyEnabled = safe.useWebSearch || safe.useAgent || safe.useDeepSearch
  return anyEnabled ? safe : null
}

