import { test } from 'node:test'
import * as assert from 'node:assert/strict'

import { readStoredTheme, resolveAppliedTheme, writeStoredTheme } from '../lib/theme'

test('readStoredTheme returns a previously saved valid theme', () => {
  const storage = {
    getItem: (key: string) => (key === 'weaver-theme' ? 'dark' : null),
  }

  assert.equal(readStoredTheme('weaver-theme', 'system', storage), 'dark')
})

test('readStoredTheme falls back when storage contains an invalid theme value', () => {
  const storage = {
    getItem: () => 'solarized',
  }

  assert.equal(readStoredTheme('weaver-theme', 'system', storage), 'system')
})

test('writeStoredTheme persists the selected theme', () => {
  const writes: Array<[string, string]> = []
  const storage = {
    setItem: (key: string, value: string) => {
      writes.push([key, value])
    },
  }

  writeStoredTheme('weaver-theme', 'light', storage)

  assert.deepEqual(writes, [['weaver-theme', 'light']])
})

test('resolveAppliedTheme maps system mode using the current OS preference', () => {
  assert.equal(resolveAppliedTheme('system', true), 'dark')
  assert.equal(resolveAppliedTheme('system', false), 'light')
  assert.equal(resolveAppliedTheme('dark', false), 'dark')
})
