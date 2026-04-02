export type Theme = 'dark' | 'light' | 'system'

export const DEFAULT_THEME: Theme = 'system'

function isTheme(value: string | null | undefined): value is Theme {
  return value === 'dark' || value === 'light' || value === 'system'
}

export function readStoredTheme(
  storageKey: string,
  fallbackTheme: Theme = DEFAULT_THEME,
  storage?: Pick<Storage, 'getItem'> | null,
): Theme {
  if (!storage) return fallbackTheme

  try {
    const storedTheme = storage.getItem(storageKey)
    return isTheme(storedTheme) ? storedTheme : fallbackTheme
  } catch (error) {
    console.error(`Error reading theme from localStorage key "${storageKey}":`, error)
    return fallbackTheme
  }
}

export function writeStoredTheme(
  storageKey: string,
  theme: Theme,
  storage?: Pick<Storage, 'setItem'> | null,
): void {
  if (!storage) return

  try {
    storage.setItem(storageKey, theme)
  } catch (error) {
    console.error(`Error writing theme to localStorage key "${storageKey}":`, error)
  }
}

export function resolveAppliedTheme(theme: Theme, prefersDark: boolean): 'dark' | 'light' {
  if (theme === 'system') {
    return prefersDark ? 'dark' : 'light'
  }

  return theme
}
