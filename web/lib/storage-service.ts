import { STORAGE_KEYS } from '@/lib/constants'

export class StorageService {
  private static getItem<T>(key: string): T | null {
    if (typeof window === 'undefined') return null
    try {
      const item = window.localStorage.getItem(key)
      return item ? (JSON.parse(item) as T) : null
    } catch (error) {
      console.error(`Error reading from localStorage key "${key}":`, error)
      return null
    }
  }

  private static setItem<T>(key: string, value: T): void {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(key, JSON.stringify(value))
    } catch (error) {
      console.error(`Error writing to localStorage key "${key}":`, error)
    }
  }

  static getHistory<T>(): T[] {
    return this.getItem<T[]>(STORAGE_KEYS.HISTORY) || []
  }

  static saveHistory<T>(history: T[]): void {
    this.setItem(STORAGE_KEYS.HISTORY, history)
  }

  static getArtifacts<T>(): T[] {
    return this.getItem<T[]>(STORAGE_KEYS.ARTIFACTS) || []
  }

  static saveArtifacts<T>(artifacts: T[]): void {
    this.setItem(STORAGE_KEYS.ARTIFACTS, artifacts)
  }

  static getSessionMessages<T>(sessionId: string): T[] {
    return this.getItem<T[]>(`session_${sessionId}`) || []
  }

  static saveSessionMessages<T>(sessionId: string, messages: T[]): void {
    this.setItem(`session_${sessionId}`, messages)
  }

  static removeSessionMessages(sessionId: string): void {
    if (typeof window === 'undefined') return
    window.localStorage.removeItem(`session_${sessionId}`)
  }

  static getSessionSnapshot<T>(sessionId: string): T | null {
    return this.getItem<T>(`${STORAGE_KEYS.SESSION_SNAPSHOT_PREFIX}${sessionId}`)
  }

  static saveSessionSnapshot<T>(sessionId: string, snapshot: T): void {
    this.setItem(`${STORAGE_KEYS.SESSION_SNAPSHOT_PREFIX}${sessionId}`, snapshot)
  }

  static removeSessionSnapshot(sessionId: string): void {
    if (typeof window === 'undefined') return
    window.localStorage.removeItem(`${STORAGE_KEYS.SESSION_SNAPSHOT_PREFIX}${sessionId}`)
  }

  static clearAll(keysToKeep: string[] = []): void {
    if (typeof window === 'undefined') return
    // Simple clear, in a real app might need more logic to only clear app-specific keys
    // For now we iterate known keys or just clear all
    // Strategy: Clear known main keys and iterate to find sessions
    
    // 1. Get all session IDs first to clean them up if needed, but localStorage.clear() does it all.
    // However, we might want to keep some settings.
    
    // For now, let's just clear the specific app keys we manage
    this.saveHistory([])
    this.saveArtifacts([])
    // Also need to find and remove session_ keys. 
    // This is tricky without a list. We rely on the history list usually.
    // A robust way is to iterate all keys.
    Object.keys(window.localStorage).forEach(key => {
        if (
          key.startsWith('session_') ||
          key.startsWith(STORAGE_KEYS.SESSION_SNAPSHOT_PREFIX) ||
          key === STORAGE_KEYS.HISTORY ||
          key === STORAGE_KEYS.ARTIFACTS
        ) {
             if (!keysToKeep.includes(key)) {
                 window.localStorage.removeItem(key)
             }
        }
    })
  }
}
