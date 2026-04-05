import { test } from 'node:test'
import * as assert from 'node:assert/strict'

import { extractCitationNumber, splitInlineCitations } from '../lib/report-markdown'

test('extractCitationNumber returns numeric citation from bracket text', () => {
  assert.equal(extractCitationNumber('[12]'), '12')
  assert.equal(extractCitationNumber(' [3] '), '3')
  assert.equal(extractCitationNumber('[x]'), null)
})

test('splitInlineCitations separates text and citation tokens', () => {
  assert.deepEqual(splitInlineCitations('alpha [1] beta [2]'), [
    { type: 'text', value: 'alpha ' },
    { type: 'citation', value: '1' },
    { type: 'text', value: ' beta ' },
    { type: 'citation', value: '2' },
  ])
})
