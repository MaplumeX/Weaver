# Frontend UI Optimization (Round 2) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship a second round of UI polish (Chat-first) while preserving the existing glass + blue/purple gradient + subtle glow aesthetic, improving accessibility, and tightening motion/performance hygiene.

**Architecture:** Incremental changes focused on high-traffic Chat surfaces, then global primitives/styles, then a small set of secondary pages/dialogs. Avoid large refactors; prefer tokenized styling and targeted transitions.

**Tech Stack:** Next.js (App Router) + Tailwind CSS + Radix UI primitives + TypeScript strict + `next-themes` + `sonner` + `lucide-react`.

---

### Task 1: Make Message Action Bar Accessible (Mobile + Keyboard)

**Files:**
- Modify: `web/components/chat/MessageItem.tsx`

**Steps:**
1. Add `aria-label` + `title` for icon-only actions (Copy/Speak/Save/Edit).
2. Make the action bar appear on `focus-within` and be visible on mobile (avoid hover-only).
3. Adjust positioning so mobile actions do not overlap adjacent messages (responsive positioning inside bubble on small screens).

**Verify:**
- Run: `pnpm -C web exec tsc --noEmit`

---

### Task 2: Improve Message Typography + Readability

**Files:**
- Modify: `web/components/chat/MessageItem.tsx`

**Steps:**
1. Ensure long-form prose uses `text-pretty` and sensible leading/spacing.
2. Use `text-balance` for headings where present and avoid overly tight truncation.
3. Normalize link/inline-code styling so it reads well in both themes.

**Verify:**
- Run: `pnpm -C web lint`

---

### Task 3: Remove `transition-all` Hotspots in Message Surface

**Files:**
- Modify: `web/components/chat/MessageItem.tsx`
- Modify: `web/app/globals.css` (if shared classes need adjustment)

**Steps:**
1. Replace `transition-all` with targeted transitions (`transition-colors`, `transition-shadow`, `transition-opacity`, `transition-transform`) where needed.
2. Ensure interaction feedback stays <= 200ms.

**Verify:**
- Run: `pnpm -C web exec tsc --noEmit`

---

### Task 4: Fix CodeBlock Copy/Duplicate State Bug + A11y Labels

**Files:**
- Modify: `web/components/chat/message/CodeBlock.tsx`

**Steps:**
1. Remove duplicated `setCopied(true)` and duplicated timeout resets.
2. Add `aria-label` for Copy and Collapse icon buttons.
3. Ensure the collapse icon button triggers the same toggle as the header (keyboard-friendly).

**Verify:**
- Run: `pnpm -C web lint`

---

### Task 5: Tighten CodeBlock Transitions + Icon Button Sizing

**Files:**
- Modify: `web/components/chat/message/CodeBlock.tsx`

**Steps:**
1. Replace `transition-all` with targeted transitions.
2. Standardize icon button hit areas (prefer >= 32px) and keep visual weight consistent.

**Verify:**
- Run: `pnpm -C web exec tsc --noEmit`

---

### Task 6: Replace Layout Animation in Research Progress Styles

**Files:**
- Modify: `web/app/globals.css`

**Steps:**
1. Replace `.progress-bar-fill` width transition with a compositor-safe approach (e.g. `transform: scaleX(...)` + `transform-origin: left`).
2. Remove `transition-all` from `.research-card` and any similar shared classes in this block.

**Verify:**
- Run: `pnpm -C web build`

---

### Task 7: ArtifactsPanel Icon Buttons A11y + Transition Hygiene

**Files:**
- Modify: `web/components/chat/ArtifactsPanel.tsx`

**Steps:**
1. Add missing `aria-label` / `title` for icon-only buttons (collapse/expand/fullscreen/download).
2. Replace `transition-all` with targeted transitions; keep durations <= 200ms for interaction.

**Verify:**
- Run: `pnpm -C web lint`

---

### Task 8: Artifacts Fullscreen Overlay Consistency

**Files:**
- Modify: `web/components/chat/ArtifactsPanel.tsx`

**Steps:**
1. Align fullscreen overlay header styling with the global glass language (borders, background, button styles).
2. Ensure close button is clearly visible in both themes and keyboard-focusable.

**Verify:**
- Run: `pnpm -C web exec tsc --noEmit`

---

### Task 9: Scroll-To-Bottom Button Safe-Area + Faster Feedback

**Files:**
- Modify: `web/components/chat/ChatOverlays.tsx`
- Modify: `web/app/globals.css` (if new safe-area utility needed)

**Steps:**
1. Add safe-area-aware bottom offset for the floating button.
2. Reduce interaction feedback duration to <= 200ms; ensure only `opacity/transform` transitions.

**Verify:**
- Run: `pnpm -C web build`

---

### Task 10: Interrupt Banner Theming (Light/Dark) + Layout Polish

**Files:**
- Modify: `web/components/chat/ChatOverlays.tsx`

**Steps:**
1. Restyle banner to match glass theme (subtle surface + amber emphasis) and ensure dark mode contrast.
2. Keep actions aligned and consistent with the shared Button styles.

**Verify:**
- Run: `pnpm -C web lint`

---

### Task 11: Header Icon-Only Buttons A11y + Visual Consistency

**Files:**
- Modify: `web/components/chat/Header.tsx`

**Steps:**
1. Add missing `aria-label` where needed and ensure icon buttons have consistent sizing.
2. Align model Select trigger styling with the established Chat surface tokens.

**Verify:**
- Run: `pnpm -C web exec tsc --noEmit`

---

### Task 12: Sidebar Overlay Timing + Focus/Keyboard Usability

**Files:**
- Modify: `web/components/chat/Sidebar.tsx`
- Modify: `web/app/globals.css` (sidebar shared classes)

**Steps:**
1. Reduce mobile overlay transition from 500ms to <= 200ms and remove `transition-all` usage in `.sidebar-item`.
2. Make pin/delete affordances appear on `focus-within` as well as hover.

**Verify:**
- Run: `pnpm -C web build`

---

### Task 13: Button Primitive Transition Hygiene

**Files:**
- Modify: `web/components/ui/button.tsx`

**Steps:**
1. Replace base `transition-all` with targeted transitions.
2. Ensure disabled/loading states remain clear and do not animate layout.

**Verify:**
- Run: `pnpm -C web lint`

---

### Task 14: Button Loading Semantics

**Files:**
- Modify: `web/components/ui/button.tsx`

**Steps:**
1. Add `aria-busy` when `loading`.
2. Ensure spinner is decorative (`aria-hidden`) and does not break button width/spacing.

**Verify:**
- Run: `pnpm -C web exec tsc --noEmit`

---

### Task 15: Input Primitive Focus/Placeholder Polish

**Files:**
- Modify: `web/components/ui/input.tsx`

**Steps:**
1. Tighten placeholder contrast and focus ring behavior to match Chat surfaces.
2. Replace any broad transitions with targeted transitions.

**Verify:**
- Run: `pnpm -C web lint`

---

### Task 16: Card Typography Utilities

**Files:**
- Modify: `web/components/ui/card.tsx`

**Steps:**
1. Apply `text-balance` to titles where appropriate and `text-pretty` to descriptions (without changing DOM structure).
2. Keep the card as a neutral primitive; don’t bake in view-specific gradients.

**Verify:**
- Run: `pnpm -C web exec tsc --noEmit`

---

### Task 17: Fix Tailwind `pulse-glow` Keyframes (No Box-Shadow Animation)

**Files:**
- Modify: `web/tailwind.config.ts`

**Steps:**
1. Replace the `pulse-glow` keyframes from `box-shadow` animation to `opacity/transform` (compositor-safe).
2. Ensure `animate-pulse-glow` remains available and consistent with `web/app/globals.css`.

**Verify:**
- Run: `pnpm -C web build`

---

### Task 18: Reduced Motion + Remove Persistent `will-change`

**Files:**
- Modify: `web/app/globals.css`

**Steps:**
1. Ensure custom `.animate-*` utilities behave well under `prefers-reduced-motion`.
2. Remove `will-change` declarations that would persist beyond entrance animations.

**Verify:**
- Run: `pnpm -C web build`

---

### Task 19: Discover Page Type Safety + Visual Alignment

**Files:**
- Modify: `web/components/views/Discover.tsx`

**Steps:**
1. Remove `any` usage for template items and clean duplicate imports.
2. Align card transitions with the system (no `transition-all`, <= 200ms), and add `aria-label` for icon-only add button.

**Verify:**
- Run: `pnpm -C web lint`

---

### Task 20: Dialog/Modal Consistency (Export/Share/VersionHistory/Settings)

**Files:**
- Modify: `web/components/export/ExportDialog.tsx`
- Modify: `web/components/collaboration/ShareDialog.tsx`
- Modify: `web/components/collaboration/VersionHistory.tsx`
- Modify: `web/components/settings/SettingsDialog.tsx`

**Steps:**
1. Replace `transition-all` in selection cards with targeted transitions and <= 200ms feedback.
2. Add missing `aria-label` for close/copy/delete icon-only actions.
3. Ensure overlays/backdrop blur usage stays consistent with the glass theme.

**Verify (full suite):**
- Run: `pnpm -C web lint`
- Run: `pnpm -C web exec tsc --noEmit`
- Run: `pnpm -C web build`

