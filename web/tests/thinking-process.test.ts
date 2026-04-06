import { test } from 'node:test'
import * as assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { ThinkingProcess } from '../components/chat/message/ThinkingProcess'

test('renders user-facing process header copy instead of legacy Thinking text', () => {
  const html = renderToStaticMarkup(
    React.createElement(ThinkingProcess, {
      isThinking: true,
      startedAt: Date.now() - 3000,
      tools: [
        {
          toolCallId: 'tool-1',
          toolName: 'browser_search',
          state: 'running',
          args: { query: 'agent observability' },
        },
      ],
      events: [
        {
          id: 'status-agent',
          type: 'status',
          timestamp: 10,
          data: { text: 'Running agent (tool-calling)', step: 'agent' },
        },
      ],
    }),
  )

  assert.match(html, /正在调用工具/)
  assert.doesNotMatch(html, /Thinking…/)
  assert.doesNotMatch(html, /Thought/)
})
