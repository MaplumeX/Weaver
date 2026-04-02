import { test } from 'node:test'
import * as assert from 'node:assert/strict'

import { DEFAULT_MODEL } from '../lib/constants'
import { getConfiguredModelEntries, getModelAllowlist, resolveModelSelection } from '../lib/model-selection'

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

test('getConfiguredModelEntries only returns backend-configured models', () => {
  const entries = getConfiguredModelEntries({
    default: 'deepseek-v3-2-251201',
    options: ['deepseek-v3-2-251201', 'gpt-5'],
  })

  assert.deepEqual(entries, [
    { id: 'deepseek-v3-2-251201', name: 'deepseek-v3-2-251201', providerId: 'deepseek' },
    { id: 'gpt-5', name: 'GPT-5', providerId: 'openai' },
  ])
})

test('getConfiguredModelEntries falls back to the explicit current model when public config is unavailable', () => {
  const entries = getConfiguredModelEntries(null, ['claude-sonnet-4-5-20250514'])

  assert.deepEqual(entries, [
    { id: 'claude-sonnet-4-5-20250514', name: 'Claude Sonnet 4.5', providerId: 'anthropic' },
  ])
})
