'use client'

import { useReducer, useCallback } from 'react'
import { STORAGE_KEYS, DEFAULT_MODEL } from '@/lib/constants'
import { searchModeFromId, type SearchMode } from '@/lib/chat-mode'

// Types
export type ChatView = 'dashboard' | 'discover' | 'library'

export type McpProviderId = 'filesystem' | 'memory'

export interface ChatUIState {
  sidebarOpen: boolean
  isArtifactsOpen: boolean
  showMobileArtifacts: boolean
  showScrollButton: boolean
  showSettings: boolean
  showBrowserViewer: boolean
  currentView: ChatView
  selectedModel: string
  searchMode: SearchMode
  mcpMode: boolean
  mcpProvider: McpProviderId
}

export type ChatUIAction =
  | { type: 'TOGGLE_SIDEBAR' }
  | { type: 'SET_SIDEBAR'; payload: boolean }
  | { type: 'TOGGLE_ARTIFACTS' }
  | { type: 'SET_MOBILE_ARTIFACTS'; payload: boolean }
  | { type: 'SET_SCROLL_BUTTON'; payload: boolean }
  | { type: 'SET_SETTINGS'; payload: boolean }
  | { type: 'SET_BROWSER_VIEWER'; payload: boolean }
  | { type: 'SET_VIEW'; payload: ChatView }
  | { type: 'SET_MODEL'; payload: string }
  | { type: 'SET_SEARCH_MODE'; payload: SearchMode }
  | { type: 'SET_MCP_MODE'; payload: boolean }
  | { type: 'SET_MCP_PROVIDER'; payload: McpProviderId }
  | { type: 'RESET_FOR_NEW_CHAT' }

// Initial state
const getInitialState = (): ChatUIState => {
  // Try to load model from localStorage (client-side only)
  let savedModel = DEFAULT_MODEL
  if (typeof window !== 'undefined') {
    const stored = localStorage.getItem(STORAGE_KEYS.MODEL)
    if (stored) savedModel = stored
  }

  return {
    sidebarOpen: true,
    isArtifactsOpen: true,
    showMobileArtifacts: false,
    showScrollButton: false,
    showSettings: false,
    showBrowserViewer: true,
    currentView: 'dashboard',
    selectedModel: savedModel,
    searchMode: searchModeFromId('direct'),
    mcpMode: false,
    mcpProvider: 'filesystem',
  }
}

// Reducer
function chatUIReducer(state: ChatUIState, action: ChatUIAction): ChatUIState {
  switch (action.type) {
    case 'TOGGLE_SIDEBAR':
      return { ...state, sidebarOpen: !state.sidebarOpen }
    case 'SET_SIDEBAR':
      return { ...state, sidebarOpen: action.payload }
    case 'TOGGLE_ARTIFACTS':
      return { ...state, isArtifactsOpen: !state.isArtifactsOpen }
    case 'SET_MOBILE_ARTIFACTS':
      return { ...state, showMobileArtifacts: action.payload }
    case 'SET_SCROLL_BUTTON':
      return { ...state, showScrollButton: action.payload }
    case 'SET_SETTINGS':
      return { ...state, showSettings: action.payload }
    case 'SET_BROWSER_VIEWER':
      return { ...state, showBrowserViewer: action.payload }
    case 'SET_VIEW':
      return { ...state, currentView: action.payload }
    case 'SET_MODEL':
      // Persist to localStorage
      if (typeof window !== 'undefined') {
        localStorage.setItem(STORAGE_KEYS.MODEL, action.payload)
      }
      return { ...state, selectedModel: action.payload }
    case 'SET_SEARCH_MODE':
      return { ...state, searchMode: action.payload }
    case 'SET_MCP_MODE':
      return { ...state, mcpMode: action.payload }
    case 'SET_MCP_PROVIDER':
      return { ...state, mcpProvider: action.payload }
    case 'RESET_FOR_NEW_CHAT':
      return {
        ...state,
        currentView: 'dashboard',
        searchMode: searchModeFromId('direct'),
        mcpMode: false,
        showScrollButton: false,
      }
    default:
      return state
  }
}

// Hook
export function useChatState() {
  const [state, dispatch] = useReducer(chatUIReducer, undefined, getInitialState)

  // Memoized action creators
  const toggleSidebar = useCallback(() => dispatch({ type: 'TOGGLE_SIDEBAR' }), [])
  const setSidebar = useCallback((open: boolean) => dispatch({ type: 'SET_SIDEBAR', payload: open }), [])
  const toggleArtifacts = useCallback(() => dispatch({ type: 'TOGGLE_ARTIFACTS' }), [])
  const setMobileArtifacts = useCallback((show: boolean) => dispatch({ type: 'SET_MOBILE_ARTIFACTS', payload: show }), [])
  const setScrollButton = useCallback((show: boolean) => dispatch({ type: 'SET_SCROLL_BUTTON', payload: show }), [])
  const setSettings = useCallback((show: boolean) => dispatch({ type: 'SET_SETTINGS', payload: show }), [])
  const setBrowserViewer = useCallback((show: boolean) => dispatch({ type: 'SET_BROWSER_VIEWER', payload: show }), [])
  const setView = useCallback((view: ChatView) => dispatch({ type: 'SET_VIEW', payload: view }), [])
  const setModel = useCallback((model: string) => dispatch({ type: 'SET_MODEL', payload: model }), [])
  const setSearchMode = useCallback((mode: SearchMode) => dispatch({ type: 'SET_SEARCH_MODE', payload: mode }), [])
  const setMcpMode = useCallback((enabled: boolean) => dispatch({ type: 'SET_MCP_MODE', payload: enabled }), [])
  const setMcpProvider = useCallback((provider: McpProviderId) => dispatch({ type: 'SET_MCP_PROVIDER', payload: provider }), [])
  const resetForNewChat = useCallback(() => dispatch({ type: 'RESET_FOR_NEW_CHAT' }), [])

  return {
    state,
    dispatch,
    // Action creators
    toggleSidebar,
    setSidebar,
    toggleArtifacts,
    setMobileArtifacts,
    setScrollButton,
    setSettings,
    setBrowserViewer,
    setView,
    setModel,
    setSearchMode,
    setMcpMode,
    setMcpProvider,
    resetForNewChat,
  }
}
