import type { Metadata } from "next"
import { GeistSans } from "geist/font/sans"
import { GeistMono } from "geist/font/mono"
import "./globals.css"
import "katex/dist/katex.min.css"
import { ThemeProvider } from "@/components/theme-provider"
import { I18nProvider } from "@/lib/i18n/i18n-context"
import { ChatErrorBoundary } from "@/components/ui/error-boundary"
import { cn } from "@/lib/utils"
import { Toaster } from "@/components/ui/sonner"
import { WebVitals } from "@/components/analytics/WebVitals"

export const metadata: Metadata = {
  title: {
    default: "Weaver - Deep Research AI Agent",
    template: "%s | Weaver AI",
  },
  description:
    "Enterprise-grade AI Agent platform powered by LangGraph. Deep research, code execution, browser automation, and multi-modal interaction.",
  keywords: [
    "AI Agent",
    "LangGraph",
    "Deep Research",
    "Code Execution",
    "Browser Automation",
    "LLM",
    "FastAPI",
    "Next.js",
  ],
  authors: [{ name: "Weaver Team" }],
  creator: "Weaver",
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL || "https://weaver-demo.vercel.app"
  ),
  openGraph: {
    type: "website",
    locale: "en_US",
    title: "Weaver - Deep Research AI Agent",
    description:
      "Enterprise-grade AI Agent platform with deep research, code execution, and browser automation.",
    siteName: "Weaver AI",
  },
  twitter: {
    card: "summary_large_image",
    title: "Weaver - Deep Research AI Agent",
    description:
      "Enterprise-grade AI Agent platform with deep research, code execution, and browser automation.",
  },
  icons: {
    icon: "/favicon.ico",
  },
  manifest: "/manifest.json",
  robots: {
    index: true,
    follow: true,
  },
}

export const viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0f172a" },
  ],
}


export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={cn(
        "min-h-dvh bg-background font-sans antialiased",
        GeistSans.variable,
        GeistMono.variable
      )}>
        {/* Skip-to-content link for keyboard/screen-reader users (WCAG 2.4.1) */}
        <a href="#main-content" className="skip-to-content">
          Skip to main content
        </a>
        <ThemeProvider
          defaultTheme="system"
          storageKey="weaver-theme"
          enableSystem
          enableColorScheme
        >
          <I18nProvider>
            <main id="main-content">
              <ChatErrorBoundary>
                {children}
              </ChatErrorBoundary>
            </main>
            <Toaster />
            <WebVitals />
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
