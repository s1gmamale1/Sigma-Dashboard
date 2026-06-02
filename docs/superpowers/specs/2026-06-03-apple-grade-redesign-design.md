# Sigma Dashboard — Apple-grade Frontend Redesign (Design Spec)

**Date:** 2026-06-03 · **Status:** approved direction, pending spec review · **Branch:** `redesign/apple-grade-ui`

A full reimagining of the Sigma Dashboard frontend to Apple-grade UI/UX, grounded in the
`/apple-design` skill family (HIG: Clarity · Deference · Depth; Liquid Glass era). This doc is
the source of truth for the implementation plan.

---

## 1. Purpose

The current frontend (one 535-line `app.css`, React 18 + Vite + TS) is functional but reads as
"plain square boxes": flat 8px-radius surfaces, hairline borders, **zero motion**, generic type,
no loading states, and a live crash. This redesign transforms the *surface and behavior* — not the
data model or API — into a calm, premium, dual-theme dashboard with restrained spring motion.

## 2. Decisions locked (from brainstorming)

| Axis | Decision |
|---|---|
| Scope | **All 6 views + login**, one cohesive system |
| Depth | **Full reimagining** — rethink layout, components, IA where it earns it |
| Theme | **Both light & dark, equally flagship-quality** |
| Motion | **Restrained & premium** (utility surface: springs ≤300ms, no cinematic effects) |
| Shell / IA | **Focused Topbar** — floating glass bar, animated sliding segmented control, large collapsing title, bento Overview |
| Accent | **One: systemBlue** (`#007AFF` / `#0A84FF`); one-token swap for a brand color later |
| Charts | **Replace `recharts` with custom SVG bars** (fixes the live crash, drops a heavy dep) |
| CSS | **Modular files** (`tokens` / `base` / `components` / `views`) under the 500-line rule |

## 3. Non-negotiable Apple discipline (anti-slop guardrails)

These come straight from `apple-design/restraint-and-antislop.md`. Violating them is how "make it
Apple" goes wrong:

- **Glass = chrome only** (the topbar and any sheet). Content cards are **solid, quiet** surfaces.
  Never glass-on-glass; never text directly on a glass layer.
- **One accent** doing the pointing; everything else neutral + whitespace.
- **Hierarchy from type + space**, not boxes/borders/glow. When unsure, add space, not an element.
- **Dark mode = dimming, not inverting** — elevated surfaces step *lighter*.
- **Semantic tokens, never hardcoded hex** in components.
- **Motion budget = utility**: state/view transitions only, springs ≤300–400ms, animate
  `transform`/`opacity` only, full `prefers-reduced-motion` fallbacks. No scroll-jacking, no
  ambient/cinematic effects.
- The restraint pass: for every effect, "remove it — does the design lose *meaning* or just
  *decoration*?" If decoration, remove it.

## 4. Design system — tokens

All values are Apple-faithful (`apple-design-foundations` color + typography references).

### 4.1 Color (`tokens.css`)

Semantic, light-first with a dark dimming staircase. Labels are **alpha-modulated** off one base
color (not separate grays). P3 enhancement layered via `@supports`.

```css
:root, [data-theme="light"] {
  color-scheme: light;
  /* Labels (alpha off #3C3C43) */
  --label:            #000000;
  --label-secondary:  rgba(60,60,67,0.60);
  --label-tertiary:   rgba(60,60,67,0.30);
  --label-quaternary: rgba(60,60,67,0.18);
  /* Backgrounds */
  --bg:               #F2F2F7;   /* app canvas (grouped) */
  --surface:          #FFFFFF;   /* cards */
  --surface-2:        #F2F2F7;   /* nested/insets */
  /* Fills + separators */
  --fill:             rgba(120,120,128,0.20);
  --fill-2:           rgba(120,120,128,0.12);
  --separator:        rgba(60,60,67,0.29);
  /* Accent + status */
  --accent:           #007AFF;
  --success:          #248A3D;
  --warning:          #B25000;
  --danger:           #D70015;
  /* Glass (chrome only) */
  --glass-fill:       rgba(255,255,255,0.65);
  --glass-highlight:  rgba(255,255,255,0.60);
  --shadow-1:         0 1px 2px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.06);
  --shadow-float:     0 8px 32px rgba(0,0,0,0.12);
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --label:            #FFFFFF;
    --label-secondary:  rgba(235,235,245,0.60);
    --label-tertiary:   rgba(235,235,245,0.30);
    --label-quaternary: rgba(235,235,245,0.18);
    --bg:               #000000;   /* OLED base */
    --surface:          #1C1C1E;   /* elevated +1 */
    --surface-2:        #2C2C2E;   /* elevated +2 */
    --fill:             rgba(120,120,128,0.36);
    --fill-2:           rgba(118,118,128,0.24);
    --separator:        rgba(84,84,88,0.60);
    --accent:           #0A84FF;
    --success:          #30D158;
    --warning:          #FF9F0A;
    --danger:           #FF453A;
    --glass-fill:       rgba(28,28,30,0.65);
    --glass-highlight:  rgba(255,255,255,0.10);
    --shadow-1:         0 1px 2px rgba(0,0,0,0.30), 0 4px 16px rgba(0,0,0,0.40);
    --shadow-float:     0 8px 32px rgba(0,0,0,0.55);
  }
}

@supports (color: color(display-p3 1 1 1)) {
  :root { --accent: color(display-p3 0 0.478 1); }
  @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --accent: color(display-p3 0.04 0.52 1); } }
}

@media (prefers-contrast: more)        { :root { --label-secondary: rgba(60,60,67,0.80); --separator: rgba(60,60,67,0.55); } }
@media (prefers-reduced-transparency)  { :root { --glass-fill: var(--bg); } } /* opaque fallback */
```

### 4.2 Typography (`tokens.css` + `base.css`)

System SF stack; scale with size-specific tracking; **tabular numerals** for all numbers.

```css
:root {
  --font: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --type-large-title: 34px; --track-large-title: -0.016em;  /* weight 700, lh 41 */
  --type-title:       22px; --track-title:       -0.010em;  /* weight 600, lh 28 */
  --type-headline:    17px;                                  /* weight 600, lh 22 */
  --type-body:        17px;                                  /* weight 400, lh 22 */
  --type-callout:     16px;
  --type-subhead:     15px; --track-subhead:      0.004em;
  --type-footnote:    13px; --track-footnote:     0.025em;
  --type-caption:     12px; --track-caption:      0.05em;    /* eyebrows/labels, uppercase */
  --metric:           28px;                                  /* StatCard number, tabular */
}
.num, .metric, td.num, .money, time { font-variant-numeric: tabular-nums; }
body { font-family: var(--font); font-size: var(--type-body); line-height: 1.4; -webkit-font-smoothing: antialiased; }
```

Rules: never apply marketing/negative tracking to body (≤17px). Eyebrows use caption size,
uppercase, +0.05em, `--label-secondary`.

### 4.3 Space, radius, layout

- **8pt grid** (4pt half-steps). Tokens: `--sp-1:4 --sp-2:8 --sp-3:12 --sp-4:16 --sp-5:24 --sp-6:32 --sp-8:48`.
- **Radius:** `--r-card:18px --r-control:12px --r-tile:20px --r-pill:999px`.
- Content max-width `min(1200px, 100%)`, generous page padding (`--sp-6` desktop, `--sp-4` mobile).
- Bento on Overview only; other views use calm stacked sections / responsive card grids.

### 4.4 Materials — glass (chrome only)

```css
.glass {
  background: var(--glass-fill);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  box-shadow: inset 0 1px 0 var(--glass-highlight), var(--shadow-float);
}
@supports not (backdrop-filter: blur(1px)) { .glass { background: var(--bg); } }
```

### 4.5 Motion (`tokens.css`)

CSS `linear()` spring curves; transform/opacity only.

```css
:root {
  --spring-snappy:  linear(0,0.012,0.049,0.107,0.185,0.278,0.383,0.493,0.601,0.702,0.791,0.865,0.924,0.967,0.995,1.013,1.019,1.016,1.009,1.003,1);
  --dur-snappy: 280ms;     /* press, toggle, tab indicator */
  --spring-smooth: linear(0,0.0037,0.0142,0.031,0.0534,0.0804,0.1108,0.1438,0.1784,0.2135,0.2484,0.3145,0.3746,0.4283,0.4755,0.5562,0.6215,0.6726,0.7112,0.7735,0.8196,0.854,0.8793,0.9185,0.9458,0.9647,0.9779,0.9921,1);
  --dur-smooth: 400ms;     /* view crossfade, sheet, materialize */
  --ease-out: cubic-bezier(0.2,0.6,0.2,1);
}
@media (prefers-reduced-motion: reduce) {
  *,*::before,*::after { animation-duration:0.01ms!important; animation-iteration-count:1!important;
    transition-duration:0.01ms!important; scroll-behavior:auto!important; }
}
```

## 5. Architecture / file structure

**CSS** (`src/styles/`, imported from one `index.css`):
- `tokens.css` — color, type, space, radius, material, motion variables (the design system)
- `base.css` — resets, body, focus-visible, type utilities, `prefers-*` blocks
- `components.css` — shell, segmented control, cards, stat, pill, table, progress, skeleton, button, chart
- `views.css` — per-view grid/bento layouts

**New components** (`src/components/`), each small & single-purpose:
- `Shell.tsx` (extract the topbar/title/transition out of `App.tsx`)
- `SegmentedControl.tsx` — animated sliding indicator (measures active segment)
- `StatCard.tsx` — icon + label + tabular number + optional `CountUp`
- `Card.tsx` / `SectionHeader.tsx` — the quiet solid surface primitives
- `Skeleton.tsx` — content-shaped shimmer placeholders
- `BarChart.tsx` — custom SVG bars with spring grow-in (replaces recharts)
- `Avatar.tsx` — mono-initial chip for people
- `ChaseControl.tsx` — optimistic segmented chase-state control
- hooks: `useReducedMotion.ts`, `useCountUp.ts`

**No new heavy dependencies.** Remove `recharts`. Keep React, Vite, TanStack Query, lucide-react, zod.

## 6. Shell spec (Focused Topbar)

- **Floating glass bar**, inset (`--sp-4` from top/sides), `--r-pill`/`--r-card` rounded, `.glass`,
  `position: sticky`. Contains: brand mark + "Sigma Dashboard", the `SegmentedControl` (6 tabs), and
  topbar actions (date stepper, sign-out icon button).
- **SegmentedControl**: pill indicator translateX/scaleX-springs (`--spring-snappy`) to the active
  segment; segment shows icon + label (label hidden < 920px). Full keyboard + `role="tablist"`.
- **Large title** (`--type-large-title`) per active view, below the bar; **collapses** into the bar
  on scroll (IntersectionObserver/scroll-progress, reduced-motion → static).
- **Date control**: `‹ [date] ›` stepper wrapping the native `<input type=date>` (kept for a11y),
  styled as a segmented control; "Today" quick-reset.
- **View transition**: on tab change, outgoing view fades (120ms), incoming does opacity + 8px rise
  (`--spring-smooth`); reduced-motion → opacity only.

## 7. Per-view specs

### 7.1 Overview — bento home
- **Metric row:** 4 `StatCard`s (Shift records / Missing reports / At-risk goals / Stale topics) with
  `CountUp` on first load, tabular numerals, accent-tinted icon chip.
- **Tonight tile (wide):** roster rows (Avatar + name + StatusPill + in/out times + chase) — not a raw
  table; empty → calm `EmptyState`.
- **Weekly charge tile:** `BarChart` (UZS per person), grow-in reveal.
- **Goal-risk tile:** list of at-risk goals with title, deadline, animated progress fill.
- Tiles **materialize with 30ms stagger** on load (reduced-motion → no stagger, instant).

### 7.2 Attendance
- **Today:** person rows with optimistic `ChaseControl` (segmented none/needs-chase/chased/resolved),
  status pill, check-in/out (tabular), minutes-late, charge (UZS, tabular). Optimistic update via
  TanStack mutation with rollback on error.
- **History matrix:** sticky first column (person), date columns with status-dot + time; horizontal
  scroll preserved; hairline separators.
- **Weekly lates:** `BarChart` (lates vs charged, two series).
- **Weekly totals:** clean stat rows (late · charged · total UZS).

### 7.3 Reports
- **Daily reports:** quiet cards — person, topic, summary, extras; rating as ●●●○ / "3/4"; missing
  flagged with **color + icon + label** (never color alone).
- **Performance rank:** leaderboard rows with subtle position emphasis (1·2·3), avg rating, completion %.
- **Rating average:** `BarChart` (domain 0–4).

### 7.4 Goals
- Goal cards: title + StatusPill, animated progress, definition-list (owner/deadline/topic/nudge),
  latest log; **at-risk** = accent/danger-tinted left edge (not a heavy border).

### 7.5 Projects (condition)
- Topic cards: title, `#topic_id` chip, summary, **relative** last-activity ("2h ago"), open-items as
  a clean checklist; empty → "No open items".

### 7.6 Sheets
- Header card: spreadsheet title + configured name + primary **glass** import button (busy/disabled
  states), inline success-result and error banners.
- Per-tab preview: sticky header row, monospaced cells, ellipsis overflow, horizontal scroll.

### 7.7 Login
- Centered card on a calm field; app mark; username/password labels; error state; button busy state;
  subtle materialize-in on mount.

## 8. State spec (`apple-design-interaction`)

- **Loading:** content-shaped `Skeleton` shimmer (not spinners; spinners only > 1s genuine waits).
  Replaces today's blank-until-data.
- **Empty:** icon + message + (where relevant) a path forward.
- **Error:** icon + human message + retry affordance; the top-level `hasError` becomes a recoverable
  error card, not a dead end.
- **Optimistic:** chase-state changes apply instantly, roll back + toast/inline error on failure.
- **Feedback < 100ms:** every control has a press state (scale 0.97 / dim) via `--spring-snappy`.

## 9. Charts spec (custom SVG `BarChart.tsx`)

- Props: `data: {label, value, color?}[]`, optional `series` (2-series grouped), `max`, `format`.
- Render: responsive SVG, rounded-top bars, axis baseline + sparse gridlines in `--separator`,
  labels in `--label-secondary` caption type, tabular value tooltips on hover/focus.
- Reveal: bars grow from baseline via `transform: scaleY` (`--spring-smooth`), `transform-origin`
  bottom; reduced-motion → drawn instantly.
- Accessible: `role="img"` + `aria-label` summary; data also available as a visually-hidden table.

## 10. Live bug fix — React error #310

The running app at `:8000` crashes with minified React #310 inside `charts-*.js` (recharts).
Replacing recharts with `BarChart.tsx` (§9) removes the offending bundle and resolves the crash.
Verify post-change: load each view that previously charted (Overview, Attendance, Reports) with no
console error, in both StrictMode dev and production build.

## 11. Accessibility (preserve + extend)

- Keep: 44pt targets, `:focus-visible` rings, `prefers-reduced-motion`, `prefers-contrast`.
- Add: `prefers-reduced-transparency` opaque glass fallback; redundant (non-color-only) status
  encoding (icon/label + color); `role=tablist/tab` on the segmented control; visually-hidden chart
  data tables; maintain WCAG AA contrast (watch secondary-label-on-secondary-bg combos — use ≥18px or
  step up alpha).

## 12. Out of scope (v1 of redesign)

- No backend/API/data-model changes; no new views or features; no auth changes.
- No editing of attendance/reports by hand beyond the existing chase-state control.
- No charting library; no animation library; no component framework (shadcn etc.).

## 13. Acceptance criteria (definition of done)

1. All 6 views + login restyled to the new token system; both light & dark verified.
2. No `recharts`; custom `BarChart` renders all three chart spots; **no console errors** (the #310
   crash is gone) in dev StrictMode and prod build.
3. Floating glass topbar with animated sliding segmented control + collapsing large title + animated
   view transitions.
4. Skeleton loading, empty, error, and optimistic chase states all present.
5. Motion respects `prefers-reduced-motion`; glass respects `prefers-reduced-transparency`; contrast
   respects `prefers-contrast`; keyboard + focus fully operable; 44pt targets.
6. CSS split into modular files, each < 500 lines; no hardcoded hex in components (tokens only).
7. `npm run build` and `npm run lint` pass; `npm test` (vitest) passes; app serves correctly from
   FastAPI in production build.

## 14. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Removing recharts breaks a chart edge case | Custom `BarChart` covers all three current usages; keep API simple; test each |
| Sliding indicator measurement jitter on resize | ResizeObserver + measure on layout; reduced-motion path is static |
| Glass perf on low-end devices | Glass only on the single topbar; `@supports`/reduced-transparency fallbacks |
| Large-title collapse fighting scroll | Use passive scroll listener / IntersectionObserver; never `preventDefault` |
| Dual-theme contrast regressions | Verify AA on key combos in both themes during review |

## 15. Build sequence (for the plan)

1. Token layer + CSS module split + base utilities (no visual regressions yet).
2. Shared primitives: `Card`, `SectionHeader`, `StatCard`, `SegmentedControl`, `Skeleton`, `BarChart`,
   `Avatar`, hooks.
3. Shell (`Shell.tsx`) + topbar + view transition.
4. Views, one at a time, behind the new primitives: Overview → Attendance → Reports → Goals →
   Projects → Sheets → Login.
5. Remove recharts; verify #310 gone.
6. State polish (skeletons/empty/error/optimistic) + motion choreography.
7. A11y + dual-theme + build/lint/test verification.
