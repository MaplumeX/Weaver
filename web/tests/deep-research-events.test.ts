import { test } from 'node:test'
import * as assert from 'node:assert/strict'

import { getDeepResearchAutoStatus } from '../hooks/useChatStream'
import {
  appendProcessEvent,
  createStreamingAssistantMessage,
  getRetainedProcessEvents,
} from '../lib/chat-stream-state'

test('maps research task updates to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_task_update', {
    status: 'in_progress',
    query: 'latest AI chip roadmap',
  })

  assert.equal(text, '多 Agent 调研：执行章节 · latest AI chip roadmap · 执行章节任务')
})

test('maps supervisor decisions to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_decision', {
    decision_type: 'synthesize',
  })

  assert.equal(text, '多 Agent 调研：supervisor 决定进入汇总阶段')
})

test('maps retry task updates to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_task_update', {
    status: 'in_progress',
    query: 'latest AI chip roadmap',
    attempt: 2,
  })

  assert.equal(text, '多 Agent 调研：重试章节 · latest AI chip roadmap · 执行章节任务')
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

test('maps resumed supervisor lifecycle to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_agent_start', {
    role: 'supervisor',
    resumed_from_checkpoint: true,
  })

  assert.equal(text, '多 Agent 调研：已确认范围，正在继续评估大纲并派发章节任务…')
})

test('maps verifier claim-check lifecycle to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_agent_start', {
    role: 'verifier',
    validation_stage: 'claim_check',
  })

  assert.equal(text, '多 Agent 调研：正在核对 claim 与 citation…')
})

test('maps section review artifact to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_artifact_update', {
    artifact_type: 'section_review',
    status: 'created',
    review_verdict: 'accept_section',
  })

  assert.equal(text, '多 Agent 调研：章节审查结果已更新')
})

test('maps final claim gate decision to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_decision', {
    decision_type: 'final_claim_gate_passed',
  })

  assert.equal(text, '多 Agent 调研：最终 claim gate 已通过')
})

test('continuation message keeps resumed process events in order', () => {
  let message = createStreamingAssistantMessage({ id: 'assistant-cont' })
  message = appendProcessEvent(
    message,
    'research_decision',
    { decision_type: 'scope_approved', resumed_from_checkpoint: true },
    100,
  )
    message = appendProcessEvent(
    message,
    'research_agent_start',
    { role: 'supervisor', resumed_from_checkpoint: true },
    110,
  )
  message = appendProcessEvent(
    message,
    'research_task_update',
    { status: 'ready', query: 'latest AI chip roadmap', resumed_from_checkpoint: true },
    120,
  )

  assert.deepEqual(
    (message.processEvents || []).map((event) => event.type),
    ['research_decision', 'research_agent_start', 'research_task_update'],
  )
})

test('retained process events keep early deep research phase anchors', () => {
  const baseEvents = [
    {
      id: 'scope-ready',
      type: 'research_decision',
      timestamp: 10,
      data: { decision_type: 'scope_ready' },
    },
    {
      id: 'planner-start',
      type: 'research_agent_start',
      timestamp: 20,
      data: { role: 'supervisor' },
    },
  ]

  const tailEvents = Array.from({ length: 80 }, (_, index) => ({
    id: `search-${index}`,
    type: 'search',
    timestamp: 100 + index,
    data: { query: `query-${index}` },
  }))

  const retained = getRetainedProcessEvents([...baseEvents, ...tailEvents])

  assert.ok(retained.some((event) => event.id === 'scope-ready'))
  assert.ok(retained.some((event) => event.id === 'planner-start'))
})

test('appendProcessEvent replaces repeated status events for the same semantic step', () => {
  let message = createStreamingAssistantMessage({ id: 'assistant-status' })

  message = appendProcessEvent(
    message,
    'status',
    { text: 'Preparing tools', step: 'agent' },
    100,
  )
  message = appendProcessEvent(
    message,
    'status',
    { text: 'Running agent (tool-calling)', step: 'agent' },
    110,
  )

  assert.equal(message.processEvents?.length, 1)
  assert.equal(message.processEvents?.[0]?.data?.step, 'agent')
  assert.equal(message.processEvents?.[0]?.data?.text, 'Running agent (tool-calling)')
})
