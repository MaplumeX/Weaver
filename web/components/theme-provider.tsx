'use client'

import { ThemeProvider as NextThemesProvider, useTheme as useNextTheme } from 'next-themes'
import type { ThemeProviderProps as NextThemesProviderProps } from 'next-themes'

export type ThemeProviderProps = NextThemesProviderProps

export function ThemeProvider({ children, ...props }: ThemeProviderProps) {
  return (
    <NextThemesProvider attribute="class" {...props}>
      {children}
    </NextThemesProvider>
  )
}

export const useTheme = useNextTheme
