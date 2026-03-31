import { test } from 'node:test'
import * as assert from 'node:assert/strict'

import {
  buildInterruptResumePayload,
  getInterruptConversationMessage,
  getInterruptInputPlaceholder,
  normalizeInterruptReview,
} from '../lib/interrupt-review'

test('normalizes scope review interrupts into review metadata', () => {
  const review = normalizeInterruptReview({
    prompts: [
      {
        checkpoint: 'deepsearch_scope_review',
        instruction: 'Approve or revise the scope.',
        content: 'scope version 1',
        available_actions: ['approve_scope', 'revise_scope'],
      },
    ],
  })

  assert.ok(review)
  assert.equal(review?.kind, 'scope_review')
  assert.equal(review?.title, 'Review research scope')
  assert.equal(review?.content, 'scope version 1')
})

test('builds revise_scope payloads from scope review input', () => {
  const review = normalizeInterruptReview({
    prompts: [
      {
        checkpoint: 'deepsearch_scope_review',
        instruction: 'Approve or revise the scope.',
      },
    ],
  })

  assert.deepEqual(
    buildInterruptResumePayload(review!, 'revise_scope', 'Focus on supply chain'),
    {
      action: 'revise_scope',
      scope_feedback: 'Focus on supply chain',
    },
  )
})

test('builds clarify payloads from freeform answers', () => {
  const review = normalizeInterruptReview({
    prompts: [
      {
        checkpoint: 'deepsearch_clarify',
        message: 'What time range should the research cover?',
      },
    ],
  })

  assert.deepEqual(
    buildInterruptResumePayload(review!, 'answer_clarification', 'Only 2024 and 2025'),
    {
      clarify_answer: 'Only 2024 and 2025',
    },
  )
})

test('formats clarify interrupts as normal conversation prompts', () => {
  const review = normalizeInterruptReview({
    prompts: [
      {
        checkpoint: 'deepsearch_clarify',
        message: '你更关心整体趋势还是出行影响？',
      },
    ],
  })

  assert.equal(
    getInterruptConversationMessage(review, {
      prompts: [{ message: '你更关心整体趋势还是出行影响？' }],
    }),
    '你更关心整体趋势还是出行影响？',
  )
})

test('uses scope draft content as the in-chat review message', () => {
  const review = normalizeInterruptReview({
    prompts: [
      {
        checkpoint: 'deepsearch_scope_review',
        instruction: 'Approve or revise the scope.',
        content: '## 研究范围草案',
      },
    ],
  })

  assert.equal(getInterruptConversationMessage(review, { prompts: [] }), '## 研究范围草案')
})

test('provides conversation-style placeholders for clarify and scope revision', () => {
  const clarifyReview = normalizeInterruptReview({
    prompts: [{ checkpoint: 'deepsearch_clarify', message: '请补充目标' }],
  })
  const scopeReview = normalizeInterruptReview({
    prompts: [{ checkpoint: 'deepsearch_scope_review', content: 'scope draft' }],
  })

  assert.equal(getInterruptInputPlaceholder(clarifyReview), '继续补充你的研究目标、范围或约束')
  assert.equal(
    getInterruptInputPlaceholder(scopeReview, { revisionMode: true }),
    '继续告诉我你希望如何修改研究范围',
  )
})
