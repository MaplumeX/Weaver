import { test } from 'node:test'
import * as assert from 'node:assert/strict'

import { fetchSessionSnapshot, patchSession } from '../lib/session-api'

test('fetchSessionSnapshot requests the snapshot endpoint', async () => {
  let requested = ''
  globalThis.fetch = (async (input: string | URL) => {
    requested = String(input)
    return new Response(
      JSON.stringify({
        session: {
          thread_id: 'thread-1',
          title: 'hello',
          status: 'running',
          route: 'agent',
          created_at: '2026-04-06T00:00:00Z',
          updated_at: '2026-04-06T00:01:00Z',
        },
        messages: [],
        can_resume: false,
      }),
      { status: 200 },
    )
  }) as typeof fetch

  const snapshot = await fetchSessionSnapshot('thread-1')

  assert.match(requested, /\/api\/sessions\/thread-1\/snapshot$/)
  assert.equal(snapshot?.session.thread_id, 'thread-1')
})

test('patchSession sends a PATCH request with JSON body', async () => {
  const requests: Array<{ url: string; method: string; body: string }> = []

  globalThis.fetch = (async (input: string | URL, init?: RequestInit) => {
    requests.push({
      url: String(input),
      method: String(init?.method || 'GET'),
      body: String(init?.body || ''),
    })
    return new Response(
      JSON.stringify({
        thread_id: 'thread-1',
        title: 'Renamed',
        summary: '',
        status: 'running',
        route: 'agent',
        is_pinned: true,
        tags: [],
        created_at: '2026-04-06T00:00:00Z',
        updated_at: '2026-04-06T00:01:00Z',
      }),
      { status: 200 },
    )
  }) as typeof fetch

  const updated = await patchSession('thread-1', { title: 'Renamed', is_pinned: true })

  assert.equal(requests[0]?.method, 'PATCH')
  assert.match(requests[0]?.url || '', /\/api\/sessions\/thread-1$/)
  assert.match(requests[0]?.body || '', /"title":"Renamed"/)
  assert.equal(updated?.title, 'Renamed')
})
