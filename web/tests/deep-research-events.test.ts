import { test } from 'node:test'
import * as assert from 'node:assert/strict'

import { getDeepResearchAutoStatus } from '../hooks/useChatStream'

test('maps research task updates to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_task_update', {
    status: 'in_progress',
    query: 'latest AI chip roadmap',
  })

  assert.equal(text, '多 Agent 调研：执行任务 · latest AI chip roadmap')
})

test('maps coordinator decisions to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_decision', {
    decision_type: 'synthesize',
  })

  assert.equal(text, '多 Agent 调研：协调器决定进入汇总阶段')
})
