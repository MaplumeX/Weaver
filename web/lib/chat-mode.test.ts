import { describe, expect, it } from 'vitest'

import {
  deriveUiModeId,
  normalizeSearchMode,
  searchModeFromId,
  toNullableSearchMode,
} from './chat-mode'

describe('chat-mode helpers', () => {
  it('builds canonical SearchMode objects from mode ids', () => {
    expect(searchModeFromId('direct')).toEqual({
      useWebSearch: false,
      useAgent: false,
      useDeepSearch: false,
    })
    expect(searchModeFromId('web')).toEqual({
      useWebSearch: true,
      useAgent: false,
      useDeepSearch: false,
    })
    expect(searchModeFromId('agent')).toEqual({
      useWebSearch: false,
      useAgent: true,
      useDeepSearch: false,
    })
    expect(searchModeFromId('ultra')).toEqual({
      useWebSearch: false,
      useAgent: true,
      useDeepSearch: true,
    })
  })

  it('normalizes invalid combinations (deep requires agent)', () => {
    expect(
      normalizeSearchMode({ useWebSearch: false, useAgent: false, useDeepSearch: true }),
    ).toEqual({
      useWebSearch: false,
      useAgent: false,
      useDeepSearch: false,
    })
  })

  it('derives UI mode id from SearchMode + MCP toggle', () => {
    expect(deriveUiModeId(searchModeFromId('direct'), false)).toBe('direct')
    expect(deriveUiModeId(searchModeFromId('web'), false)).toBe('web')
    expect(deriveUiModeId(searchModeFromId('agent'), false)).toBe('agent')
    expect(deriveUiModeId(searchModeFromId('ultra'), false)).toBe('ultra')
    expect(deriveUiModeId(searchModeFromId('agent'), true)).toBe('mcp')
  })

  it('sends null search_mode when all flags are false', () => {
    expect(toNullableSearchMode(searchModeFromId('direct'))).toBeNull()
    expect(toNullableSearchMode(searchModeFromId('web'))).toEqual(searchModeFromId('web'))
  })
})

