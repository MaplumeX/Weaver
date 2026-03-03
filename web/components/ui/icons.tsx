/**
 * Centralized icon system for Weaver.
 *
 * Uses **Lucide** — clean, modern stroke-based icons standard across
 * shadcn/ui, Vercel, and the Next.js ecosystem.
 *
 * Components import from this module instead of a raw icon library,
 * ensuring a consistent aesthetic across the app.
 *
 * Usage:
 *   import { Globe, Code, Copy } from '@/components/ui/icons'
 *   <Globe className="h-4 w-4" />
 */

export {
  // Navigation & Arrows
  ArrowDown,
  ArrowRight,
  ArrowUp,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Menu,
  PanelRight,
  PanelRightClose,
  PanelRightOpen,
  PanelLeftClose,
  PanelLeftOpen,

  // Layout & Grid
  LayoutGrid,
  Compass,
  FolderOpen,
  Maximize2,
  Minimize2,
  Columns3 as Columns,
  House as Home,

  // Actions
  Check,
  CheckCircle2,
  ClipboardCopy,
  Copy,
  MousePointerClick as CursorClick,
  Download,
  ExternalLink,
  Filter,
  Link,
  Plus,
  RefreshCcw,
  RefreshCw,
  RotateCcw,
  Trash2,

  // Communication & Chat
  MessageSquare,
  MessageSquarePlus,

  // Content Types
  BarChart,
  BarChart3,
  BookOpen,
  BookmarkPlus,
  Brain,
  Code,
  SquareTerminal as Code2,
  FileText,
  Image,
  ImageIcon,
  ListChecks,
  Table,
  AlignLeft as TextAlignLeft,

  // File
  File,
  FileIcon,

  // Status
  AlertCircle,
  AlertTriangle,
  Loader2,
  WifiOff,
  XCircle,

  // Search & Research
  Globe,
  Search,
  Sparkles,
  TrendingUp,

  // Mode & Config
  Bot,
  Monitor,
  Plug,
  Rocket,
  Settings,
  Settings2,
  Wrench,
  GitBranch,

  // Edit & Pen
  PencilLine,
  PenLine,
  PenTool,

  // Audio & Media
  Mic,
  MicOff,
  Play,
  Pause,
  Square,
  Volume2,
  VolumeX,
  Camera,
  AudioWaveform,
  AudioLines,

  // Theme
  Moon,
  Sun,

  // Pin/Star
  Star,
  StarOff,

  // Close & Cancel
  X,

  // Misc
  Bug,
  Clock,
  Eye,
  Lock,
  Paperclip,
  SendHorizonal as Send,
  TestTube2 as TestTube,
  WrapText,
  MoreHorizontal,
  MoreVertical,
  Circle,

  // History
  History,

  // Share
  Share2 as Share,

  // Notepad
  NotebookPen as Notepad,

  // Faders / Sliders
  SlidersHorizontal as Faders,
} from 'lucide-react'
