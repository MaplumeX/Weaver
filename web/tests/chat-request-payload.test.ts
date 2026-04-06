import { test } from 'node:test'
import * as assert from 'node:assert/strict'

import { buildChatRequestPayload } from '../lib/chat-request'

test('buildChatRequestPayload includes thread_id for follow-up messages', () => {
  const payload = buildChatRequestPayload({
    messageHistory: [
      { role: 'user', content: 'hello' },
      { role: 'assistant', content: 'world' },
      { role: 'user', content: 'follow up' },
    ],
    model: 'deepseek-chat',
    searchMode: { mode: 'agent' },
    images: [],
    threadId: 'thread-existing',
  })

  assert.equal(payload.thread_id, 'thread-existing')
})
