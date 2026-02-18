import assert from 'node:assert/strict'

import { parseSseFrame } from '../dist/sse.js'

function testParseSseFrame() {
  const frame =
    'id: 3\n' +
    'event: text\n' +
    'data: {"type":"text","data":{"content":"hi"}}\n' +
    '\n'

  const parsed = parseSseFrame(frame)
  assert.ok(parsed)
  assert.equal(parsed.id, 3)
  assert.equal(parsed.event, 'text')
  assert.deepEqual(parsed.data, { type: 'text', data: { content: 'hi' } })
}

testParseSseFrame()
console.log('sdk/typescript SSE parser: OK')

