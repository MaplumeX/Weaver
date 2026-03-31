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

test('maps retry task updates to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_task_update', {
    status: 'in_progress',
    query: 'latest AI chip roadmap',
    attempt: 2,
  })

  assert.equal(text, '多 Agent 调研：重试任务 · latest AI chip roadmap')
})

test('maps clarify lifecycle to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_agent_start', {
    role: 'clarify',
  })

  assert.equal(text, '多 Agent 调研：正在澄清研究目标与约束…')
})

test('maps scope approval decisions to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_decision', {
    decision_type: 'scope_approved',
  })

  assert.equal(text, '多 Agent 调研：研究范围已确认，开始正式规划')
})

test('maps scope draft artifact revisions to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_artifact_update', {
    artifact_type: 'scope_draft',
    status: 'revision_requested',
  })

  assert.equal(text, '多 Agent 调研：已收到范围修改意见，正在重写草案')
})
