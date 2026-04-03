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
    event('branch-brief', 'research_artifact_update', 20, {
      artifact_id: 'brief-1',
      artifact_type: 'branch_brief',
      status: 'created',
      branch_id: 'branch-1',
      task_id: 'task-1',
      task_kind: 'branch_research',
      summary: 'Supply chain resilience',
      stage: 'planned',
      iteration: 1,
    }),
    event('generic-task', 'task_update', 21, {
      id: 'task-1',
      status: 'ready',
      title: 'duplicate task event',
    }),
    event('task-ready', 'research_task_update', 22, {
      task_id: 'task-1',
      branch_id: 'branch-1',
      task_kind: 'branch_research',
      title: 'Supply chain resilience',
      status: 'ready',
      stage: 'planned',
      iteration: 1,
    }),
    event('task-search', 'research_task_update', 23, {
      task_id: 'task-1',
      branch_id: 'branch-1',
      task_kind: 'branch_research',
      title: 'Supply chain resilience',
      status: 'in_progress',
      stage: 'search',
      iteration: 1,
      attempt: 1,
    }),
    event('search-chatter', 'search', 24, {
      query: 'ai chip supply chain',
    }),
    event('source', 'research_artifact_update', 25, {
      artifact_id: 'source-1',
      artifact_type: 'source_candidate',
      status: 'created',
      task_id: 'task-1',
      branch_id: 'branch-1',
      task_kind: 'branch_research',
      source_url: 'https://example.com/source-1',
      stage: 'search',
      iteration: 1,
    }),
    event('topology', 'deep_research_topology_update', 26, {}),
    event('verify-followup', 'research_artifact_update', 27, {
      artifact_id: 'verification-1',
      artifact_type: 'verification_result',
      status: 'completed',
      task_id: 'task-1',
      branch_id: 'branch-1',
      task_kind: 'branch_research',
      validation_stage: 'coverage_check',
      outcome: 'needs_follow_up',
      summary: 'Need more evidence',
      iteration: 1,
    }),
    event('retry-ready', 'research_task_update', 30, {
      task_id: 'task-1',
      branch_id: 'branch-1',
      task_kind: 'branch_research',
      title: 'Supply chain resilience',
      status: 'ready',
      stage: 'dispatch',
      iteration: 2,
      attempt: 2,
    }),
    event('retry-search', 'research_task_update', 31, {
      task_id: 'task-1',
      branch_id: 'branch-1',
      task_kind: 'branch_research',
      title: 'Supply chain resilience',
      status: 'in_progress',
      stage: 'search',
      iteration: 2,
      attempt: 2,
    }),
    event('synthesis', 'research_artifact_update', 32, {
      artifact_id: 'synthesis-1',
      artifact_type: 'branch_synthesis',
      status: 'created',
      task_id: 'task-1',
      branch_id: 'branch-1',
      task_kind: 'branch_research',
      stage: 'synthesize',
      citation_urls: ['https://example.com/source-1', 'https://example.com/source-2'],
      iteration: 2,
    }),
    event('verify-passed', 'research_artifact_update', 33, {
      artifact_id: 'verification-2',
      artifact_type: 'verification_result',
      status: 'completed',
      task_id: 'task-1',
      branch_id: 'branch-1',
      task_kind: 'branch_research',
      validation_stage: 'coverage_check',
      outcome: 'passed',
      summary: 'Coverage check passed',
      iteration: 2,
    }),
    event('outline', 'research_artifact_update', 34, {
      artifact_id: 'outline-1',
      artifact_type: 'outline',
      status: 'completed',
      branch_id: 'root-branch',
      section_count: 3,
      is_ready: true,
      iteration: 2,
    }),
    event('final-report', 'research_artifact_update', 35, {
      artifact_id: 'report-1',
      artifact_type: 'final_report',
      status: 'completed',
    }),
  ]

  const projection = projectDeepResearchTimeline(events)

  assert.ok(projection)
  assert.deepEqual(
    projection.phases.map((phase) => phase.key),
    ['intake', 'scope', 'planning', 'branch_research', 'verify', 'report'],
  )
  assert.ok(projection.headerMetrics.includes('6 phases'))
  assert.ok(projection.headerMetrics.includes('1 branch'))
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

  const branchPhase = projection.phases.find((phase) => phase.key === 'branch_research')
  assert.ok(branchPhase)
  assert.equal(branchPhase.branches.length, 1)
  assert.equal(branchPhase.branches[0]?.label, 'Supply chain resilience')
  assert.equal(branchPhase.branches[0]?.iterations.length, 2)
  assert.deepEqual(
    branchPhase.branches[0]?.iterations.map((item) => item.label),
    ['Iteration 1', 'Iteration 2'],
  )
  assert.ok(branchPhase.metrics.includes('2 iterations'))
})
