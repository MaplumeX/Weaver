/**
 * Centralized icon system for Weaver.
 *
 * Uses **Phosphor Icons** — slightly warmer strokes and better visual weight
 * at small sizes (a better fit for our UI density).
 *
 * Components import from this module instead of a raw icon library,
 * ensuring a consistent aesthetic across the app.
 *
 * Usage:
 *   import { Globe, Code, Copy } from '@/components/ui/icons'
 *   <Globe className="h-4 w-4" />
 */

import * as React from 'react'
import type { Icon, IconProps, IconWeight } from '@phosphor-icons/react'
import {
  // Navigation & arrows
  ArrowDown as PhArrowDown,
  ArrowRight as PhArrowRight,
  ArrowUp as PhArrowUp,
  CaretDown,
  CaretLeft,
  CaretRight,
  CaretUp,
  List,
  SidebarSimple,

  // Layout
  SquaresFour,
  Compass as PhCompass,
  FolderOpen as PhFolderOpen,
  ArrowsOut,
  ArrowsIn,
  Columns as PhColumns,
  House,

  // Actions
  Check as PhCheck,
  CheckCircle,
  ClipboardText,
  Copy as PhCopy,
  CursorClick as PhCursorClick,
  Download as PhDownload,
  ArrowSquareOut,
  Funnel,
  Link as PhLink,
  Plus as PhPlus,
  ArrowCounterClockwise,
  ArrowClockwise,
  ArrowUUpLeft,
  Trash,

  // Communication & chat
  ChatText,

  // Content types
  ChartBar,
  BookOpen as PhBookOpen,
  BookmarkSimple,
  Brain as PhBrain,
  Code as PhCode,
  Terminal,
  FileText as PhFileText,
  Image as PhImage,
  ListChecks as PhListChecks,
  Table as PhTable,
  TextAlignLeft as PhTextAlignLeft,

  // File
  File as PhFile,

  // Status
  WarningCircle,
  Warning,
  CircleNotch,
  WifiSlash,
  XCircle as PhXCircle,

  // Search & research
  Globe as PhGlobe,
  MagnifyingGlass,
  Sparkle,
  TrendUp,

  // Mode & config
  Robot,
  Monitor as PhMonitor,
  Plug as PhPlug,
  Rocket as PhRocket,
  Gear,
  Sliders,
  Wrench as PhWrench,
  GitBranch as PhGitBranch,

  // Edit & pen
  PencilLine as PhPencilLine,
  Pen,
  PenNib,

  // Audio & media
  Microphone,
  MicrophoneSlash,
  Play as PhPlay,
  Pause as PhPause,
  Square as PhSquare,
  SpeakerHigh,
  SpeakerSlash,
  Camera as PhCamera,
  Waveform,

  // Theme
  Moon as PhMoon,
  Sun as PhSun,

  // Pin/star
  Star as PhStar,

  // Close & cancel
  X as PhX,

  // Misc
  Bug as PhBug,
  Clock as PhClock,
  Eye as PhEye,
  Lock as PhLock,
  Paperclip as PhPaperclip,
  PaperPlaneRight,
  TestTube as PhTestTube,
  TextAlignJustify,
  DotsThree,
  DotsThreeVertical,
  Circle as PhCircle,

  // History
  ClockCounterClockwise,

  // Share
  ShareNetwork,

  // Notepad
  Notebook,

  // Faders / sliders
  SlidersHorizontal,
} from '@phosphor-icons/react'

type MakeIconOptions = {
  defaultWeight?: IconWeight
  defaultProps?: Partial<IconProps>
}

function makeWeaverIcon(IconComponent: Icon, options: MakeIconOptions = {}): Icon {
  // Default to `bold` for better legibility at our typical UI icon sizes (12–18px).
  // This also makes the visual switch from Lucide → Phosphor more noticeable.
  const defaultWeight: IconWeight = options.defaultWeight || 'bold'
  const defaultProps = options.defaultProps || {}
  const Wrapped = React.forwardRef<SVGSVGElement, IconProps>(({ weight, ...props }, ref) => {
    return (
      <IconComponent
        ref={ref}
        weight={weight || defaultWeight}
        {...defaultProps}
        {...props}
      />
    )
  })
  Wrapped.displayName = `WeaverIcon(${IconComponent.displayName || 'Icon'})`
  return Wrapped as unknown as Icon
}

// Navigation & arrows
export const ArrowDown = makeWeaverIcon(PhArrowDown)
export const ArrowRight = makeWeaverIcon(PhArrowRight)
export const ArrowUp = makeWeaverIcon(PhArrowUp)
export const ChevronDown = makeWeaverIcon(CaretDown)
export const ChevronLeft = makeWeaverIcon(CaretLeft)
export const ChevronRight = makeWeaverIcon(CaretRight)
export const ChevronUp = makeWeaverIcon(CaretUp)
export const Menu = makeWeaverIcon(List)
export const PanelRight = makeWeaverIcon(SidebarSimple, { defaultProps: { mirrored: true } })
export const PanelRightClose = makeWeaverIcon(SidebarSimple, { defaultProps: { mirrored: true } })
export const PanelRightOpen = makeWeaverIcon(SidebarSimple, { defaultProps: { mirrored: true } })
export const PanelLeftClose = makeWeaverIcon(SidebarSimple)
export const PanelLeftOpen = makeWeaverIcon(SidebarSimple)

// Layout & grid
export const LayoutGrid = makeWeaverIcon(SquaresFour)
export const Maximize2 = makeWeaverIcon(ArrowsOut)
export const Minimize2 = makeWeaverIcon(ArrowsIn)
export const Compass = makeWeaverIcon(PhCompass)
export const FolderOpen = makeWeaverIcon(PhFolderOpen)
export const Columns = makeWeaverIcon(PhColumns)
export const Home = makeWeaverIcon(House)

// Actions
export const CheckCircle2 = makeWeaverIcon(CheckCircle)
export const ClipboardCopy = makeWeaverIcon(ClipboardText)
export const ExternalLink = makeWeaverIcon(ArrowSquareOut)
export const Filter = makeWeaverIcon(Funnel)
export const RefreshCcw = makeWeaverIcon(ArrowCounterClockwise)
export const RefreshCw = makeWeaverIcon(ArrowClockwise)
export const RotateCcw = makeWeaverIcon(ArrowUUpLeft)
export const Trash2 = makeWeaverIcon(Trash)
export const Check = makeWeaverIcon(PhCheck)
export const Copy = makeWeaverIcon(PhCopy)
export const CursorClick = makeWeaverIcon(PhCursorClick)
export const Download = makeWeaverIcon(PhDownload)
export const Link = makeWeaverIcon(PhLink)
export const Plus = makeWeaverIcon(PhPlus)

// Communication & chat
export const MessageSquare = makeWeaverIcon(ChatText)
export const MessageSquarePlus = makeWeaverIcon(ChatText)

// Content types
export const BarChart = makeWeaverIcon(ChartBar)
export const BarChart3 = makeWeaverIcon(ChartBar)
export const BookmarkPlus = makeWeaverIcon(BookmarkSimple)
export const Code2 = makeWeaverIcon(Terminal)
export const BookOpen = makeWeaverIcon(PhBookOpen)
export const Brain = makeWeaverIcon(PhBrain)
export const Code = makeWeaverIcon(PhCode)
export const FileText = makeWeaverIcon(PhFileText)
export const Image = makeWeaverIcon(PhImage)
export const ImageIcon = makeWeaverIcon(PhImage)
export const ListChecks = makeWeaverIcon(PhListChecks)
export const Table = makeWeaverIcon(PhTable)
export const TextAlignLeft = makeWeaverIcon(PhTextAlignLeft)

// File
export const File = makeWeaverIcon(PhFile)
export const FileIcon = makeWeaverIcon(PhFile)

// Status
export const AlertCircle = makeWeaverIcon(WarningCircle)
export const AlertTriangle = makeWeaverIcon(Warning)
export const Loader2 = makeWeaverIcon(CircleNotch)
export const WifiOff = makeWeaverIcon(WifiSlash)
export const XCircle = makeWeaverIcon(PhXCircle)

// Search & research
export const Search = makeWeaverIcon(MagnifyingGlass)
export const Sparkles = makeWeaverIcon(Sparkle)
export const TrendingUp = makeWeaverIcon(TrendUp)
export const Globe = makeWeaverIcon(PhGlobe)

// Mode & config
export const Bot = makeWeaverIcon(Robot)
export const Settings = makeWeaverIcon(Gear)
export const Settings2 = makeWeaverIcon(Sliders)
export const Monitor = makeWeaverIcon(PhMonitor)
export const Plug = makeWeaverIcon(PhPlug)
export const Rocket = makeWeaverIcon(PhRocket)
export const Wrench = makeWeaverIcon(PhWrench)
export const GitBranch = makeWeaverIcon(PhGitBranch)

// Edit & pen
export const PenLine = makeWeaverIcon(Pen)
export const PenTool = makeWeaverIcon(PenNib)
export const PencilLine = makeWeaverIcon(PhPencilLine)

// Audio & media
export const Mic = makeWeaverIcon(Microphone)
export const MicOff = makeWeaverIcon(MicrophoneSlash)
export const Volume2 = makeWeaverIcon(SpeakerHigh)
export const VolumeX = makeWeaverIcon(SpeakerSlash)
export const AudioWaveform = makeWeaverIcon(Waveform)
export const AudioLines = makeWeaverIcon(Waveform)
export const Play = makeWeaverIcon(PhPlay)
export const Pause = makeWeaverIcon(PhPause)
export const Square = makeWeaverIcon(PhSquare)
export const Camera = makeWeaverIcon(PhCamera)

// Theme
export const Moon = makeWeaverIcon(PhMoon)
export const Sun = makeWeaverIcon(PhSun)

// Pin/star
export const Star = makeWeaverIcon(PhStar)
export const StarOff = makeWeaverIcon(PhStar, { defaultWeight: 'fill' })

// Close & cancel
export const X = makeWeaverIcon(PhX)

// Misc
export const Send = makeWeaverIcon(PaperPlaneRight)
export const WrapText = makeWeaverIcon(TextAlignJustify)
export const MoreHorizontal = makeWeaverIcon(DotsThree)
export const MoreVertical = makeWeaverIcon(DotsThreeVertical)
export const Bug = makeWeaverIcon(PhBug)
export const Clock = makeWeaverIcon(PhClock)
export const Eye = makeWeaverIcon(PhEye)
export const Lock = makeWeaverIcon(PhLock)
export const Paperclip = makeWeaverIcon(PhPaperclip)
export const TestTube = makeWeaverIcon(PhTestTube)
export const Circle = makeWeaverIcon(PhCircle)

// History
export const History = makeWeaverIcon(ClockCounterClockwise)

// Share
export const Share = makeWeaverIcon(ShareNetwork)

// Notepad
export const Notepad = makeWeaverIcon(Notebook)

// Faders / sliders
export const Faders = makeWeaverIcon(SlidersHorizontal)
