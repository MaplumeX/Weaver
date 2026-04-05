import { test } from 'node:test'
import * as assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { ThinkingProcess } from '../components/chat/message/ThinkingProcess'
import type { ProcessEvent } from '../types/chat'

function event(
  id: string,
  type: string,
  timestamp: number,
  data: Record<string, unknown>,
): ProcessEvent {
  return { id, type, timestamp, data }
}

test('renders aggregated deep research thinking view with raw drilldown entry', () => {
  const events: ProcessEvent[] = [
    event('scope-approved', 'research_decision', 10, {
      decision_type: 'scope_approved',
    }),
    event('clarify-required', 'research_decision', 11, {
      decision_type: 'clarify_required',
      reason: 'Which aspects of the NIPS and CCF conflict should be prioritized?',
    }),
    event('plan', 'research_artifact_update', 20, {
      artifact_id: 'plan-1',
      artifact_type: 'outline',
      status: 'created',
      section_id: 'section-1',
      task_id: 'task-1',
      task_kind: 'section_research',
      summary: 'Generated 1 required section',
      stage: 'outline_gate',
      iteration: 1,
    }),
    event('task-search', 'research_task_update', 23, {
      task_id: 'task-1',
      section_id: 'section-1',
      task_kind: 'section_research',
      title: 'Supply chain resilience',
      status: 'in_progress',
      stage: 'search',
      iteration: 1,
    }),
    event('search-noise', 'search', 24, {
      query: 'ai chip supply chain',
    }),
    event('verify-passed', 'research_artifact_update', 33, {
      artifact_id: 'review-2',
      artifact_type: 'section_review',
      status: 'completed',
      task_id: 'task-1',
      section_id: 'section-1',
      task_kind: 'section_research',
      review_verdict: 'accept_section',
      summary: 'Coverage check passed',
      iteration: 2,
    }),
  ]

  const html = renderToStaticMarkup(
    React.createElement(ThinkingProcess, {
      events,
      isThinking: false,
      startedAt: 1000,
      completedAt: 4000,
    }),
  )

  assert.match(html, /Thought for 3s/)
  assert.match(html, /1 section/)
  assert.doesNotMatch(html, /steps/)
  assert.match(html, /Clarification required/)
  assert.match(html, /Which aspects of the NIPS and CCF conflict should be prioritized\?/)
  assert.match(html, /Section Research/)
  assert.match(html, /Supply chain resilience/)
  assert.match(html, /Original Stream Events/)
  assert.match(html, /full-fidelity events remain available for drilldown/)
  assert.match(html, /Default view collapses/)
  assert.doesNotMatch(html, /branch-1/)
  assert.doesNotMatch(html, /task-1/)
})
