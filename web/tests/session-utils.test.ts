import { test } from 'node:test'
import * as assert from 'node:assert/strict'
import * as sessionUtils from '../lib/session-utils'

import {
  buildArtifactsFromSessionState,
  buildChatSessionFromRemoteInfo,
  buildChatSnapshotFromRemote,
  mergeRemoteAndCachedHistory,
  resolveLoadedSessionSnapshot,
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
        checkpoint: 'deep_research_scope_review',
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
  assert.equal(deriveSearchModeFromRoute('ultra'), 'agent')
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

test('buildChatSessionFromRemoteInfo prefers explicit title/summary metadata from backend', () => {
  const session = buildChatSessionFromRemoteInfo({
    thread_id: 'thread_123',
    topic: 'fallback topic',
    title: 'Remote Title',
    summary: 'Remote Summary',
    status: 'running',
    route: 'agent',
    created_at: '2026-04-06T00:00:00Z',
    updated_at: '2026-04-06T00:01:00Z',
    is_pinned: true,
    tags: ['alpha'],
  })

  assert.equal(session.id, 'thread_123')
  assert.equal(session.title, 'Remote Title')
  assert.equal(session.summary, 'Remote Summary')
  assert.equal(session.isPinned, true)
  assert.deepEqual(session.tags, ['alpha'])
})

test('buildChatSnapshotFromRemote maps session snapshot payload to frontend state shape', () => {
  const snapshot = buildChatSnapshotFromRemote(
    {
      session: {
        thread_id: 'thread_123',
        title: 'Remote Title',
        status: 'interrupted',
        route: 'deep',
        created_at: '2026-04-06T00:00:00Z',
        updated_at: '2026-04-06T00:01:00Z',
        summary: 'Remote Summary',
        is_pinned: true,
        tags: ['alpha'],
      },
      messages: [
        {
          id: 'm1',
          role: 'assistant',
          content: 'hello',
          created_at: '2026-04-06T00:01:00Z',
        },
      ],
      pending_interrupt: { kind: 'scope_review', title: 'Review required' },
      can_resume: true,
    },
    'thread_123',
  )

  assert.equal(snapshot.sessionId, 'thread_123')
  assert.equal(snapshot.threadId, 'thread_123')
  assert.equal(snapshot.messages[0]?.role, 'assistant')
  assert.equal(snapshot.route, 'deep')
  assert.equal(snapshot.searchMode, 'deep')
  assert.equal(snapshot.status, 'interrupted')
  assert.equal(snapshot.canResume, true)
})

test('resolveLoadedSessionSnapshot falls back to cached local snapshot when remote snapshot is missing', () => {
  const fallback = {
    sessionId: 'thread_legacy',
    threadId: 'thread_legacy',
    messages: [{ id: 'm1', role: 'assistant' as const, content: 'cached message' }],
    artifacts: [],
    pendingInterrupt: null,
    currentStatus: '',
    route: 'agent' as const,
    searchMode: 'agent' as const,
    status: 'completed',
    canResume: false,
    updatedAt: 1,
    createdAt: 1,
  }

  const snapshot = resolveLoadedSessionSnapshot({
    remoteSnapshot: null,
    fallbackSnapshot: fallback,
    sessionId: 'thread_legacy',
  })

  assert.equal(snapshot?.messages[0]?.content, 'cached message')
  assert.equal(snapshot?.sessionId, 'thread_legacy')
})

test('mergeRemoteAndCachedHistory keeps cached sessions that are missing remotely', () => {
  const cached = [
    {
      id: 'thread_cached',
      title: 'Cached session',
      date: '',
      createdAt: 1,
      updatedAt: 20,
      threadId: 'thread_cached',
      source: 'cache' as const,
    },
  ]

  const merged = mergeRemoteAndCachedHistory([], cached)

  assert.equal(merged.length, 1)
  assert.equal(merged[0]?.id, 'thread_cached')
})

test('mergeRemoteAndCachedHistory prefers remote data for matching thread ids', () => {
  const cached = [
    {
      id: 'thread_same',
      title: 'Cached title',
      date: '',
      createdAt: 1,
      updatedAt: 10,
      threadId: 'thread_same',
      source: 'cache' as const,
    },
  ]
  const remote = [
    buildChatSessionFromRemoteInfo({
      thread_id: 'thread_same',
      title: 'Remote title',
      summary: 'Remote summary',
      status: 'running',
      route: 'agent',
      created_at: '2026-04-06T00:00:00Z',
      updated_at: '2026-04-06T00:01:00Z',
    }),
  ]

  const merged = mergeRemoteAndCachedHistory(remote, cached)

  assert.equal(merged.length, 1)
  assert.equal(merged[0]?.title, 'Remote title')
  assert.equal(merged[0]?.source, 'remote')
})

test('resolveRequestedSessionRestore suppresses stale session restore while clearing a chat', () => {
  assert.equal(typeof sessionUtils.resolveRequestedSessionRestore, 'function')

  const suppressed = sessionUtils.resolveRequestedSessionRestore({
    activeSessionId: null,
    requestedSessionId: 'thread_123',
    isHistoryLoading: false,
    clearingSessionId: 'thread_123',
  })

  assert.deepEqual(suppressed, {
    shouldOpen: false,
    nextClearingSessionId: 'thread_123',
  })

  const released = sessionUtils.resolveRequestedSessionRestore({
    activeSessionId: null,
    requestedSessionId: null,
    isHistoryLoading: false,
    clearingSessionId: 'thread_123',
  })

  assert.deepEqual(released, {
    shouldOpen: false,
    nextClearingSessionId: null,
  })

  const normalRestore = sessionUtils.resolveRequestedSessionRestore({
    activeSessionId: null,
    requestedSessionId: 'thread_456',
    isHistoryLoading: false,
    clearingSessionId: null,
  })

  assert.deepEqual(normalRestore, {
    shouldOpen: true,
    nextClearingSessionId: null,
  })
})
