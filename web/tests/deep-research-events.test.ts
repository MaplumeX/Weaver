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

  assert.equal(text, '多 Agent 调研：正在检索资料 · latest AI chip roadmap')
})

test('maps supervisor decisions to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_decision', {
    decision_type: 'synthesize',
  })

  assert.equal(text, '多 Agent 调研：正在生成最终答案')
})

test('maps retry task updates to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_task_update', {
    status: 'in_progress',
    query: 'latest AI chip roadmap',
    attempt: 2,
  })

  assert.equal(text, '多 Agent 调研：正在补充研究 · latest AI chip roadmap')
})

test('maps clarify lifecycle to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_agent_start', {
    role: 'clarify',
  })

  assert.equal(text, '多 Agent 调研：正在明确问题')
})

test('maps scope approval decisions to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_decision', {
    decision_type: 'scope_approved',
  })

  assert.equal(text, '多 Agent 调研：研究范围已确认')
})

test('maps scope draft artifact revisions to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_artifact_update', {
    artifact_type: 'scope_draft',
    status: 'revision_requested',
  })

  assert.equal(text, '多 Agent 调研：需要调整研究范围')
})

test('maps resumed supervisor lifecycle to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_agent_start', {
    role: 'supervisor',
    resumed_from_checkpoint: true,
  })

  assert.equal(text, '多 Agent 调研：正在制定研究计划')
})

test('maps verifier claim-check lifecycle to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_agent_start', {
    role: 'verifier',
    validation_stage: 'claim_check',
  })

  assert.equal(text, '多 Agent 调研：正在复核结论')
})

test('maps section review artifact to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_artifact_update', {
    artifact_type: 'section_review',
    status: 'created',
    review_verdict: 'accept_section',
    title: 'Supply chain resilience',
  })

  assert.equal(text, '多 Agent 调研：章节已通过复核 · Supply chain resilience')
})

test('maps final claim gate decision to readable auto status', () => {
  const text = getDeepResearchAutoStatus('research_decision', {
    decision_type: 'final_claim_gate_passed',
  })

  assert.equal(text, '多 Agent 调研：最终结论已复核')
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
