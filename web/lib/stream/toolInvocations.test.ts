import { describe, expect, it } from 'vitest'

import type { ToolInvocation } from '@/types/chat'

import { applyToolStreamEvent } from './toolInvocations'

describe('applyToolStreamEvent', () => {
  it('upserts tool invocations by toolCallId', () => {
    const start = applyToolStreamEvent([], {
      toolCallId: 'run_1',
      name: 'tavily_search',
      status: 'running',
      query: 'weaver deep research',
    })

    expect(start).toHaveLength(1)
    expect(start[0]).toMatchObject({
      toolCallId: 'run_1',
      toolName: 'tavily_search',
      state: 'running',
      args: { query: 'weaver deep research' },
    } satisfies Partial<ToolInvocation>)

    const end = applyToolStreamEvent(start, {
      toolCallId: 'run_1',
      name: 'tavily_search',
      status: 'completed',
    })

    expect(end).toHaveLength(1)
    expect(end[0]?.state).toBe('completed')
  })
})
