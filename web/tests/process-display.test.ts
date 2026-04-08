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
      event('task-ready-1', 'research_task_update', 20, {
        task_id: 'task-1',
        section_id: 'section-1',
        task_kind: 'section_research',
        title: 'Supply chain resilience',
        status: 'ready',
        stage: 'planned',
      }),
      event('task-ready-2', 'research_task_update', 21, {
        task_id: 'task-2',
        section_id: 'section-2',
        task_kind: 'section_research',
        title: 'Packaging capacity',
        status: 'ready',
        stage: 'planned',
      }),
      event('task-search', 'research_task_update', 30, {
        task_id: 'task-1',
        section_id: 'section-1',
        task_kind: 'section_research',
        title: 'Supply chain resilience',
        status: 'in_progress',
        stage: 'search',
        iteration: 1,
      }),
      event('section-certified', 'research_artifact_update', 40, {
        artifact_id: 'cert-1',
        artifact_type: 'section_certification',
        status: 'completed',
        task_id: 'task-1',
        section_id: 'section-1',
        task_kind: 'section_research',
        title: 'Supply chain resilience',
        iteration: 1,
      }),
      event('task-search-2', 'research_task_update', 50, {
        task_id: 'task-2',
        section_id: 'section-2',
        task_kind: 'section_research',
        title: 'Packaging capacity',
        status: 'in_progress',
        stage: 'search',
        iteration: 1,
      }),
    ],
  })

  assert.equal(projection.summary.label, '正在检索资料')
  assert.deepEqual(projection.summary.metrics, ['1/2 章节完成'])
  assert.deepEqual(
    projection.details.map((item) => `${item.label}:${item.detail}`),
    ['Supply chain resilience:已完成', 'Packaging capacity:检索资料中'],
  )
})

test('keeps pre-research planning in chapter view without leaking technical iteration state', () => {
  const projection = projectProcessDisplay({
    isThinking: true,
    tools: [],
    events: [
      event('scope-approved', 'research_decision', 10, { decision_type: 'scope_approved' }),
      event('outline', 'research_artifact_update', 20, {
        artifact_id: 'outline-1',
        artifact_type: 'outline',
        status: 'created',
      }),
      event('task-ready-1', 'research_task_update', 30, {
        task_id: 'task-1',
        section_id: 'section-1',
        task_kind: 'section_research',
        title: 'Supply chain resilience',
        status: 'ready',
        stage: 'planned',
        iteration: 1,
      }),
      event('task-ready-2', 'research_task_update', 31, {
        task_id: 'task-2',
        section_id: 'section-2',
        task_kind: 'section_research',
        title: 'Packaging capacity',
        status: 'ready',
        stage: 'planned',
        iteration: 1,
      }),
    ],
  })

  assert.equal(projection.summary.label, '正在制定研究计划')
  assert.deepEqual(projection.summary.metrics, ['已规划 2 个章节'])
  assert.deepEqual(projection.details, [
    {
      id: 'pending-sections',
      label: '待开始章节',
      detail: '还有 2 个章节尚未开始',
    },
  ])
  assert.equal(
    buildProcessHeaderText({ projection, durationLabel: '12s' }),
    '正在制定研究计划 · 12s · 已规划 2 个章节',
  )
})
