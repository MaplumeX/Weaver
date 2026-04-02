import { test } from 'node:test'
import * as assert from 'node:assert/strict'

import { DEFAULT_MODEL } from '../lib/constants'
import { getModelAllowlist, resolveModelSelection } from '../lib/model-selection'

test('resolveModelSelection keeps a saved model when the backend still supports it', () => {
  const publicModels = {
    default: 'gpt-5',
    options: ['gpt-5', 'gpt-4o'],
  }

  assert.equal(resolveModelSelection('gpt-4o', publicModels), 'gpt-4o')
})

test('resolveModelSelection falls back to the backend default for unsupported saved models', () => {
  const publicModels = {
    default: 'gpt-5',
    options: ['gpt-5', 'gpt-4o'],
  }

  assert.equal(resolveModelSelection('deepseek-chat', publicModels), 'gpt-5')
})

test('resolveModelSelection falls back to the frontend default when public config is unavailable', () => {
  assert.equal(resolveModelSelection('', null), DEFAULT_MODEL)
})

test('getModelAllowlist trims and deduplicates backend model ids', () => {
  const allowlist = getModelAllowlist({
    default: 'gpt-5',
    options: [' gpt-5 ', 'gpt-5', 'gpt-4o'],
  })

  assert.deepEqual(Array.from(allowlist || []), ['gpt-5', 'gpt-4o'])
})
