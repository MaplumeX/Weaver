import { test } from 'node:test'
import * as assert from 'node:assert/strict'

import { buildProcessHeaderText, projectProcessDisplay } from '../lib/process-display'
import type { ProcessEvent, ToolInvocation } from '../types/chat'

function event(
  id: string,
  type: string,
  timestamp: number,
  data: Record<string, unknown>,
): ProcessEvent {
  return { id, type, timestamp, data }
}

test('collapses generic tool-calling chatter into one user-facing summary', () => {
  const tools: ToolInvocation[] = [
    {
      toolCallId: 'tool-1',
      toolName: 'browser_search',
      state: 'running',
      args: { query: 'agent observability' },
    },
  ]

  const projection = projectProcessDisplay({
    isThinking: true,
    tools,
    events: [
      event('init', 'status', 10, { text: 'Initializing research agent...', step: 'init' }),
      event('agent-thinking', 'thinking', 20, {
        text: '我会调用工具完成任务步骤，并记录关键过程。',
        node: 'agent',
      }),
      event('agent-status', 'status', 30, {
        text: 'Running agent (tool-calling)',
        step: 'agent',
      }),
      event('tool', 'tool', 40, { name: 'browser_search', status: 'running' }),
    ],
  })

  assert.equal(projection.summary.label, '正在调用工具')
  assert.deepEqual(
    projection.details.map((item) => item.label),
    ['分析问题', '调用工具'],
  )
  assert.equal(
    buildProcessHeaderText({ projection, durationLabel: '8s' }),
    '正在调用工具 · 8s · 1 个工具',
  )
})

test('projects deep research events into the same two-level display model', () => {
  const projection = projectProcessDisplay({
    isThinking: true,
    tools: [],
    events: [
      event('scope-approved', 'research_decision', 10, { decision_type: 'scope_approved' }),
      event('task-search', 'research_task_update', 20, {
        task_id: 'task-1',
        section_id: 'section-1',
        task_kind: 'section_research',
        title: 'Supply chain resilience',
        status: 'in_progress',
        stage: 'search',
        iteration: 1,
      }),
      event('section-draft', 'research_artifact_update', 30, {
        artifact_id: 'section-draft-1',
        artifact_type: 'section_draft',
        status: 'created',
        task_id: 'task-1',
        section_id: 'section-1',
        task_kind: 'section_research',
        title: 'Supply chain resilience',
        iteration: 1,
      }),
    ],
  })

  assert.equal(projection.summary.label, '正在检索资料')
  assert.ok(projection.summary.metrics.includes('1 section'))
  assert.deepEqual(
    projection.details.map((item) => item.label),
    ['研究范围', '检索资料', '汇总信息'],
  )
})
