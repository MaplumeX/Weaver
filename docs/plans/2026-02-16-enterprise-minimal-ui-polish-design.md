# Enterprise Minimal UI Polish (Round 3) - Design

**Date:** 2026-02-16

## Context

Earlier UI rounds leaned on glass/gradient/glow. This round switches to an **enterprise minimal** direction: high readability, restrained accents, low visual noise, and predictable component hierarchy.

**Priority order (user):** Chat main UI > global components/styles > secondary pages.

## Goals

- Remove primary reliance on **gradients**, **glow**, and **glass/backdrop-blur**.
- Establish a consistent, token-driven **surface system** (background, panels, messages, dialogs) across light/dark.
- Tighten typography and spacing for long-form chat readability (line length, leading, code blocks).
- Reduce motion to subtle, purposeful feedback; avoid expensive blur effects.
- Maintain accessibility baselines: focus-visible rings, icon button labels, contrast.

## Non-Goals

- No new features or information architecture changes.
- No re-platforming UI primitives away from the current Radix/shadcn-style components.
- No brand redesign; keep a single calm accent color.

## Visual Direction

**Keywords:** crisp, quiet, confident, editorial spacing.

- Background: neutral, optionally with a subtle non-gradient texture.
- Surfaces: clear borders, light elevation, minimal shadows.
- Accent: one primary accent (blue) used sparingly for key actions and active states.
- Deliberate removal of: purple gradients, glow shadows, heavy blur.

## Token Strategy

Keep shadcn-compatible CSS variables in `web/app/globals.css`, but simplify:

- Remove gradient/glass/glow variables and utilities.
- Set `--primary` / `--ring` to the single accent for consistent focus/active cues.
- Ensure light/dark palettes keep contrast: readable body text, muted text still AA.

## Component Styling Rules

- Buttons: default primary action uses the single accent; secondary/outline are neutral.
- Dialogs/Overlays: solid overlay (no backdrop blur), bordered content, moderate shadow.
- Sidebar: neutral panel with clear active indicator (border + subtle background), no gradients.
- Messages: readable bubbles with subtle differentiation (user lightly tinted, assistant neutral).
- Inputs: flatter surfaces, precise focus rings, no scaling on focus.
- Code blocks: clean header (language + actions), no glassy blur.

## Motion & Performance

- Prefer `transition-colors` / `transition-shadow` only.
- Keep interaction feedback <= 200ms.
- Remove large `backdrop-filter` usage (especially on overlays, headers).

## Accessibility

- Maintain strong `:focus-visible` rings.
- Ensure icon-only buttons have `aria-label` (and `title` where helpful).
- Avoid hover-only actions being inaccessible on mobile; enable `group-focus-within` patterns.

## Scope (Primary Files)

- Tokens/styles: `web/app/globals.css`, `web/tailwind.config.js`
- Primitives: `web/components/ui/*` (button, dialog, select, input, popover, badge, etc.)
- Chat: `web/components/chat/*`
- Secondary pages: `web/components/views/Discover.tsx`, `web/components/views/Library.tsx`, `web/components/library/*`
- Legacy gradient pages: `web/app/not-found.tsx`

## Verification

Must pass:

- `pnpm -C web lint`
- `pnpm -C web exec tsc --noEmit`
- `pnpm -C web build`
