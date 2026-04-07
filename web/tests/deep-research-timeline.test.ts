import { test } from 'node:test'
import * as assert from 'node:assert/strict'

import { projectDeepResearchTimeline } from '../lib/deep-research-timeline'
import type { ProcessEvent } from '../types/chat'

function event(
  id: string,
  type: string,
  timestamp: number,
  data: Record<string, unknown>,
): ProcessEvent {
  return { id, type, timestamp, data }
}

test('projects deep research events into stable phases and branch history', () => {
  const events: ProcessEvent[] = [
    event('scope-approved', 'research_decision', 10, {
      decision_type: 'scope_approved',
    }),
    event('clarify-required', 'research_decision', 11, {
      decision_type: 'clarify_required',
      reason: 'Which aspects of the NIPS and CCF conflict should be prioritized?',
    }),
    event('outline', 'research_artifact_update', 20, {
      artifact_id: 'outline-1',
      artifact_type: 'outline',
      status: 'created',
      section_id: 'section-1',
      task_id: 'task-1',
      task_kind: 'section_research',
      summary: 'Generated 1 required section',
      stage: 'outline_gate',
      iteration: 1,
    }),
    event('generic-task', 'task_update', 21, {
      id: 'task-1',
      status: 'ready',
      title: 'duplicate task event',
    }),
    event('task-ready', 'research_task_update', 22, {
      task_id: 'task-1',
      section_id: 'section-1',
      task_kind: 'section_research',
      title: 'Supply chain resilience',
      status: 'ready',
      stage: 'planned',
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
      attempt: 1,
    }),
    event('search-chatter', 'search', 24, {
      query: 'ai chip supply chain',
    }),
    event('bundle', 'research_artifact_update', 25, {
      artifact_id: 'bundle-1',
      artifact_type: 'evidence_bundle',
      status: 'created',
      task_id: 'task-1',
      section_id: 'section-1',
      task_kind: 'section_research',
      source_count: 1,
      source_urls: ['https://example.com/source-1'],
      stage: 'search',
      iteration: 1,
    }),
    event('topology', 'deep_research_topology_update', 26, {}),
    event('verify-followup', 'research_artifact_update', 27, {
      artifact_id: 'review-1',
      artifact_type: 'section_review',
      status: 'completed',
      task_id: 'task-1',
      section_id: 'section-1',
      task_kind: 'section_research',
      review_verdict: 'request_research',
      summary: 'Need more evidence',
      iteration: 1,
    }),
    event('retry-ready', 'research_task_update', 30, {
      task_id: 'task-1',
      section_id: 'section-1',
      task_kind: 'section_research',
      title: 'Supply chain resilience',
      status: 'ready',
      stage: 'dispatch',
      iteration: 2,
      attempt: 2,
    }),
    event('retry-search', 'research_task_update', 31, {
      task_id: 'task-1',
      section_id: 'section-1',
      task_kind: 'section_research',
      title: 'Supply chain resilience',
      status: 'in_progress',
      stage: 'search',
      iteration: 2,
      attempt: 2,
    }),
    event('section-draft', 'research_artifact_update', 32, {
      artifact_id: 'section-draft-1',
      artifact_type: 'section_draft',
      status: 'created',
      task_id: 'task-1',
      section_id: 'section-1',
      task_kind: 'section_research',
      stage: 'synthesize',
      source_urls: ['https://example.com/source-1', 'https://example.com/source-2'],
      title: 'Supply chain resilience',
      iteration: 2,
    }),
    event('section-certified', 'research_artifact_update', 33, {
      artifact_id: 'certification-1',
      artifact_type: 'section_certification',
      status: 'completed',
      task_id: 'task-1',
      section_id: 'section-1',
      task_kind: 'section_research',
      summary: 'Section certified',
      iteration: 2,
    }),
    event('final-report', 'research_artifact_update', 35, {
      artifact_id: 'report-1',
      artifact_type: 'final_report',
      status: 'completed',
    }),
    event('claim-gate', 'research_decision', 36, {
      decision_type: 'final_claim_gate_passed',
    }),
  ]

  const projection = projectDeepResearchTimeline(events)

  assert.ok(projection)
  assert.deepEqual(
    projection.phases.map((phase) => phase.key),
    ['intake', 'scope', 'outline', 'section_research', 'section_review', 'report', 'final_claim_gate'],
  )
  assert.ok(projection.headerMetrics.includes('7 phases'))
  assert.ok(projection.headerMetrics.includes('1 section'))
  assert.ok(projection.headerMetrics.includes('1 certified'))
  assert.ok(projection.headerMetrics.includes('2 sources'))
  assert.ok(projection.headerMetrics.includes('Iteration 2'))
  assert.equal(projection.suppressedEventCount, 3)

  const intakePhase = projection.phases.find((phase) => phase.key === 'intake')
  assert.ok(intakePhase)
  assert.equal(intakePhase.highlights[0]?.headline, 'Clarification required')
  assert.match(
    intakePhase.highlights[0]?.detail || '',
    /Which aspects of the NIPS and CCF conflict should be prioritized\?/,
  )

  const researchPhase = projection.phases.find((phase) => phase.key === 'section_research')
  assert.ok(researchPhase)
  assert.equal(researchPhase.sections.length, 1)
  assert.equal(researchPhase.sections[0]?.label, 'Supply chain resilience')
  assert.equal(researchPhase.sections[0]?.iterations.length, 2)
  assert.deepEqual(
    researchPhase.sections[0]?.iterations.map((item) => item.label),
    ['Iteration 1', 'Iteration 2'],
  )
  assert.ok(researchPhase.metrics.includes('2 iterations'))
  assert.ok(researchPhase.metrics.includes('2 sources'))

  const reviewPhase = projection.phases.find((phase) => phase.key === 'section_review')
  assert.ok(reviewPhase)
  assert.ok(reviewPhase.metrics.includes('1 certified'))
})

test('does not show section iteration metrics before section research actually starts', () => {
  const events: ProcessEvent[] = [
    event('scope-approved', 'research_decision', 10, {
      decision_type: 'scope_approved',
    }),
    event('outline', 'research_artifact_update', 20, {
      artifact_id: 'outline-1',
      artifact_type: 'outline',
      status: 'created',
      summary: 'Generated 2 required sections',
      iteration: 1,
    }),
    event('plan', 'research_artifact_update', 21, {
      artifact_id: 'plan-1',
      artifact_type: 'plan',
      status: 'completed',
      summary: 'Generated 2 section tasks',
      iteration: 1,
    }),
    event('task-ready-1', 'research_task_update', 22, {
      task_id: 'task-1',
      section_id: 'section-1',
      task_kind: 'section_research',
      title: 'Supply chain resilience',
      status: 'ready',
      stage: 'planned',
      iteration: 1,
    }),
    event('task-ready-2', 'research_task_update', 23, {
      task_id: 'task-2',
      section_id: 'section-2',
      task_kind: 'section_research',
      title: 'Packaging capacity',
      status: 'ready',
      stage: 'planned',
      iteration: 1,
    }),
  ]

  const projection = projectDeepResearchTimeline(events)

  assert.ok(projection)
  assert.ok(!projection.headerMetrics.some((metric) => metric.includes('section')))
  assert.ok(!projection.headerMetrics.some((metric) => metric.startsWith('Iteration ')))
  assert.ok(!projection.phases.some((phase) => phase.key === 'section_research'))
  assert.deepEqual(
    projection.phases.map((phase) => phase.key),
    ['scope', 'outline'],
  )
})
