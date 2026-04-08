/**
 * Browser visualization types for real-time browser viewing
 */

export interface BrowserScreenshot {
  id: string
  url: string                // Screenshot URL or base64 data URL
  pageUrl?: string           // The page being captured
  action?: string            // Action type: navigate, click, type, scroll, etc.
  tool?: string              // Tool name that captured the screenshot
  timestamp: number
  isLive?: boolean           // Whether this is from live screencast
}

export interface BrowserSession {
  threadId: string
  isActive: boolean
  currentUrl?: string
  screenshots: BrowserScreenshot[]
  cdpEndpoint?: string       // CDP endpoint for advanced streaming
  mode?: 'local' | 'e2b' | 'daytona'
}

export interface BrowserEvent {
  type: 'tool' | 'tool_screenshot' | 'tool_progress'
  event_id: string
  seq: number
  timestamp: number
  data: BrowserEventData
}

export interface BrowserEventData {
  tool?: string
  tool_id?: string
  phase?: string
  action?: string
  url?: string
  image?: string             // Base64 image data
  mime_type?: string
  filename?: string
  page_url?: string
  message?: string
  info?: string
  progress?: number
  status?: string
  success?: boolean
  duration_ms?: number
  error?: string
  args?: Record<string, unknown>
  payload?: Record<string, unknown>
}

export interface BrowserCapabilities {
  supportsCdp: boolean
  supportsScreencast: boolean
  supportsLiveView: boolean
  cdpEndpoint?: string
}
