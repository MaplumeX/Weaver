'use client'

import React, { createContext, useContext, useEffect, useState } from 'react'
import {
  DEFAULT_THEME,
  readStoredTheme,
  resolveAppliedTheme,
  Theme,
  writeStoredTheme,
} from '@/lib/theme'

interface ThemeProviderProps {
  children: React.ReactNode
  defaultTheme?: Theme
  storageKey?: string
}

interface ThemeProviderState {
  theme: Theme
  setTheme: (theme: Theme) => void
}

const initialState: ThemeProviderState = {
  theme: DEFAULT_THEME,
  setTheme: () => null,
}

const ThemeProviderContext = createContext<ThemeProviderState>(initialState)

export function ThemeProvider({
  children,
  defaultTheme = DEFAULT_THEME,
  storageKey = 'vite-ui-theme',
  ...props
}: ThemeProviderProps) {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window === 'undefined') return defaultTheme
    return readStoredTheme(storageKey, defaultTheme, window.localStorage)
  })

  useEffect(() => {
    const root = window.document.documentElement
    const appliedTheme = resolveAppliedTheme(
      theme,
      window.matchMedia('(prefers-color-scheme: dark)').matches,
    )
    root.classList.remove('light', 'dark')
    root.classList.add(appliedTheme)
  }, [theme])

  const value = {
    theme,
    setTheme: (theme: Theme) => {
      writeStoredTheme(
        storageKey,
        theme,
        typeof window === 'undefined' ? null : window.localStorage,
      )
      setThemeState(theme)
    },
  }

  return (
    <ThemeProviderContext.Provider {...props} value={value}>
      {children}
    </ThemeProviderContext.Provider>
  )
}

export const useTheme = () => {
  const context = useContext(ThemeProviderContext)

  if (context === undefined)
    throw new Error('useTheme must be used within a ThemeProvider')

  return context
}
