import { test } from 'node:test'
import * as assert from 'node:assert/strict'

import {
  buildArtifactsFromSessionState,
  buildMessagesFromSessionState,
  buildPendingInterrupt,
  deriveSearchModeFromRoute,
  replaceSessionPreservingOrder,
  sortChatSessions,
} from '../lib/session-utils'

test('sortChatSessions keeps pinned sessions first and then sorts by updatedAt', () => {
  const sessions = sortChatSessions([
    { id: '2', title: 'b', date: '', createdAt: 1, updatedAt: 20, isPinned: false },
    { id: '1', title: 'a', date: '', createdAt: 1, updatedAt: 10, isPinned: true },
    { id: '3', title: 'c', date: '', createdAt: 1, updatedAt: 30, isPinned: false },
  ])

  assert.deepEqual(
    sessions.map((session) => session.id),
    ['1', '3', '2'],
  )
})

test('buildMessagesFromSessionState maps stored langchain message types back to chat roles', () => {
  const messages = buildMessagesFromSessionState(
    {
      messages: [
        { type: 'human', content: 'question' },
        { type: 'ai', content: 'answer' },
        { type: 'system', content: 'note' },
      ],
    },
    'session-1',
  )

  assert.deepEqual(
    messages.map((message) => ({ role: message.role, content: message.content })),
    [
      { role: 'user', content: 'question' },
      { role: 'assistant', content: 'answer' },
      { role: 'system', content: 'note' },
    ],
  )
})

test('buildArtifactsFromSessionState exposes final report as a report artifact', () => {
  const artifacts = buildArtifactsFromSessionState(
    {
      final_report: '# Report\n\nDone.',
    },
    'session-2',
  )

  assert.equal(artifacts.length, 1)
  assert.equal(artifacts[0]?.type, 'report')
  assert.match(artifacts[0]?.content || '', /Done\./)
})

test('buildPendingInterrupt restores scope review and binds it to the last assistant message', () => {
  const pending = buildPendingInterrupt(
    [
      {
        checkpoint: 'deepsearch_scope_review',
        content: 'Scope draft',
        instruction: 'Review the scope',
      },
    ],
    [
      { id: 'user-1', role: 'user', content: 'hello' },
      { id: 'assistant-1', role: 'assistant', content: 'scope response' },
    ],
  )

  assert.equal(pending?.kind, 'scope_review')
  assert.equal(pending?.messageId, 'assistant-1')
})

test('deriveSearchModeFromRoute maps backend route names to frontend mode keys', () => {
  assert.equal(deriveSearchModeFromRoute('deep'), 'deep')
  assert.equal(deriveSearchModeFromRoute('agent'), 'agent')
  assert.equal(deriveSearchModeFromRoute('web'), 'agent')
  assert.equal(deriveSearchModeFromRoute('direct'), 'agent')
  assert.equal(deriveSearchModeFromRoute('ultra'), 'deep')
})

test('replaceSessionPreservingOrder updates an existing session without moving it', () => {
  const sessions = replaceSessionPreservingOrder(
    [
      { id: '1', title: 'a', date: '', createdAt: 1, updatedAt: 10 },
      { id: '2', title: 'b', date: '', createdAt: 1, updatedAt: 20 },
      { id: '3', title: 'c', date: '', createdAt: 1, updatedAt: 30 },
    ],
    { id: '2', title: 'b2', date: '', createdAt: 1, updatedAt: 999 },
  )

  assert.deepEqual(
    sessions.map((session) => session.id),
    ['1', '2', '3'],
  )
  assert.equal(sessions[1]?.title, 'b2')
})
