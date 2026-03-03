import { describe, expect, it } from 'vitest'

import { toPlaywrightKeyboardAction } from './keyboard'

describe('toPlaywrightKeyboardAction', () => {
  it('types printable characters (no modifiers)', () => {
    expect(
      toPlaywrightKeyboardAction({ key: 'a', ctrlKey: false, metaKey: false, altKey: false, shiftKey: false })
    ).toEqual({ kind: 'type', text: 'a' })
  })

  it('presses special keys like Enter', () => {
    expect(
      toPlaywrightKeyboardAction({ key: 'Enter', ctrlKey: false, metaKey: false, altKey: false, shiftKey: false })
    ).toEqual({ kind: 'press', key: 'Enter' })
  })

  it('presses arrow keys', () => {
    expect(
      toPlaywrightKeyboardAction({ key: 'ArrowLeft', ctrlKey: false, metaKey: false, altKey: false, shiftKey: false })
    ).toEqual({ kind: 'press', key: 'ArrowLeft' })
  })

  it('builds modifier chords for Control/Cmd', () => {
    expect(
      toPlaywrightKeyboardAction({ key: 'l', ctrlKey: true, metaKey: false, altKey: false, shiftKey: false })
    ).toEqual({ kind: 'press', key: 'Control+L' })
    expect(
      toPlaywrightKeyboardAction({ key: 'l', ctrlKey: false, metaKey: true, altKey: false, shiftKey: false })
    ).toEqual({ kind: 'press', key: 'Meta+L' })
  })

  it('ignores pure modifier keys', () => {
    expect(
      toPlaywrightKeyboardAction({ key: 'Shift', ctrlKey: false, metaKey: false, altKey: false, shiftKey: true })
    ).toEqual({ kind: 'ignore' })
  })

  it('does not send Control/Cmd+V as press (let paste handle)', () => {
    expect(
      toPlaywrightKeyboardAction({ key: 'v', ctrlKey: true, metaKey: false, altKey: false, shiftKey: false })
    ).toEqual({ kind: 'ignore' })
    expect(
      toPlaywrightKeyboardAction({ key: 'v', ctrlKey: false, metaKey: true, altKey: false, shiftKey: false })
    ).toEqual({ kind: 'ignore' })
  })
})

