export type KeyModifierSnapshot = {
  key: string
  ctrlKey: boolean
  metaKey: boolean
  altKey: boolean
  shiftKey: boolean
}

export type PlaywrightKeyboardAction =
  | { kind: 'type'; text: string }
  | { kind: 'press'; key: string }
  | { kind: 'ignore' }

const MODIFIER_KEYS = new Set(['Shift', 'Control', 'Alt', 'Meta'])

function normalizeSpecialKey(key: string): string {
  if (key === ' ') return 'Space'
  if (key === 'Esc') return 'Escape'
  return key
}

function isFunctionKey(key: string): boolean {
  // F1..F24 (Playwright supports many; be permissive).
  if (!key.startsWith('F')) return false
  const n = Number(key.slice(1))
  return Number.isInteger(n) && n > 0 && n <= 24
}

function buildModifiers(input: KeyModifierSnapshot): string[] {
  const modifiers: string[] = []
  if (input.ctrlKey) modifiers.push('Control')
  if (input.altKey) modifiers.push('Alt')
  if (input.shiftKey) modifiers.push('Shift')
  if (input.metaKey) modifiers.push('Meta')
  return modifiers
}

/**
 * Convert a KeyboardEvent-like snapshot into a Playwright keyboard action.
 *
 * - Printable characters => `keyboard.type(text)`
 * - Non-printables / chorded keys => `keyboard.press(key)`
 */
export function toPlaywrightKeyboardAction(input: KeyModifierSnapshot): PlaywrightKeyboardAction {
  const rawKey = typeof input?.key === 'string' ? input.key : ''
  const key = normalizeSpecialKey(rawKey)

  if (!key || key === 'Unidentified' || key === 'Dead') return { kind: 'ignore' }
  if (MODIFIER_KEYS.has(key)) return { kind: 'ignore' }

  // Avoid sending Ctrl/Cmd+V as a press; the paste event handler should send the text.
  if ((input.ctrlKey || input.metaKey) && key.toLowerCase() === 'v') return { kind: 'ignore' }

  const modifiers = buildModifiers(input)
  const hasChord = modifiers.length > 0

  if (hasChord) {
    const baseKey = key.length === 1 ? key.toUpperCase() : key
    return { kind: 'press', key: `${modifiers.join('+')}+${baseKey}` }
  }

  // Space is more reliable as a "press" than "type" for many sites (buttons/shortcuts).
  if (key === 'Space') return { kind: 'press', key: 'Space' }

  // Heuristic: one visible character => type.
  if (rawKey.length === 1) return { kind: 'type', text: rawKey }

  // Otherwise treat as a special key press.
  if (isFunctionKey(key)) return { kind: 'press', key }
  return { kind: 'press', key }
}

