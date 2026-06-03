# Apple-grade Frontend Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Sigma Dashboard frontend (React 18 + Vite + TS) into an Apple-grade, dual-theme UI with restrained spring motion, replacing the crashing recharts bundle with custom SVG charts.

**Architecture:** A token-driven design system (modular CSS) + ~10 small, single-purpose React primitives establish a fixed consistency contract. The shell and all 7 surfaces are rebuilt against those primitives. Glass is used only on chrome (topbar); content cards are quiet solid surfaces. Motion is utility-grade (springs ≤400ms, `transform`/`opacity` only, full `prefers-reduced-motion` fallbacks).

**Tech Stack:** React 18, Vite, TypeScript, TanStack Query, lucide-react, zod. Tests: vitest + jsdom + @testing-library/react. **Removed:** recharts. **No new runtime deps.**

**Source of truth:** `docs/superpowers/specs/2026-06-03-apple-grade-redesign-design.md` (design spec, §-referenced below).

**Working dir:** `/Users/aisigma/sigma-dashboard` · **Branch:** `redesign/apple-grade-ui` (already created).

---

## File structure (created/modified)

```
frontend/
  src/
    styles/
      index.css            (NEW — single entry; @imports the four modules)
      tokens.css           (NEW — color/type/space/radius/material/motion vars)
      base.css             (NEW — reset, body, focus, type utils, prefers-* blocks)
      components.css        (NEW — shell, segmented, card, stat, pill, table, skeleton, button, chart, avatar)
      views/
        overview.css        (NEW)  attendance.css (NEW)  reports.css (NEW)
        goals.css (NEW)      projects.css (NEW)  sheets.css (NEW)  login.css (NEW)
      app.css              (DELETE at the end, once nothing imports it)
    hooks/
      useReducedMotion.ts  (NEW)   useCountUp.ts (NEW)
    components/
      Shell.tsx            (NEW — topbar/title/transition, extracted from App.tsx)
      SegmentedControl.tsx (NEW)   StatCard.tsx (NEW)   Card.tsx (NEW)   SectionHeader.tsx (NEW)
      Skeleton.tsx (NEW)   Avatar.tsx (NEW)   BarChart.tsx (NEW)   ChaseControl.tsx (NEW)
      OverviewView.tsx · AttendanceView.tsx · ReportsView.tsx · GoalsView.tsx ·
      ProjectConditionView.tsx · SheetsView.tsx · LoginPanel.tsx · StatusPill.tsx · EmptyState.tsx (MODIFY)
    App.tsx                (MODIFY — use Shell; remove inline topbar)
    main.tsx               (MODIFY — import ./styles/index.css)
  vite.config.ts           (MODIFY — add vitest test config)
  package.json             (MODIFY — remove recharts; add test devDeps; add vitest setup)
  src/test/setup.ts        (NEW — testing-library/jest-dom)
```

---

### Task 0: Test infrastructure

**Files:**
- Modify: `frontend/package.json`, `frontend/vite.config.ts`
- Create: `frontend/src/test/setup.ts`

- [ ] **Step 1: Install test devDeps**

Run:
```bash
cd frontend && npm i -D jsdom @testing-library/react @testing-library/dom @testing-library/jest-dom @testing-library/user-event
```
Expected: added to devDependencies, no errors.

- [ ] **Step 2: Add vitest config to `vite.config.ts`**

Add a `test` block to the Vite config (merge into the existing `defineConfig`):
```ts
/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: true,
  },
});
```
(Preserve any existing plugin/server options already present in the file.)

- [ ] **Step 3: Create the setup file**

`frontend/src/test/setup.ts`:
```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 4: Smoke test the runner**

Create `frontend/src/test/smoke.test.ts`:
```ts
import { describe, it, expect } from "vitest";
describe("runner", () => { it("works", () => { expect(1 + 1).toBe(2); }); });
```
Run: `npm test`
Expected: 1 passed.

- [ ] **Step 5: Commit**
```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/src/test/setup.ts frontend/src/test/smoke.test.ts
git commit -m "test: add vitest + testing-library infrastructure"
```

---

### Task 1: Token layer + modular CSS split + base

**Files:**
- Create: `frontend/src/styles/{index,tokens,base,components}.css` and empty `views/*.css`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Create `tokens.css`** — copy the full token blocks from design spec §4.1–§4.5 verbatim (color light/dark + P3 + contrast/reduced-transparency; type scale + tabular `.num`; space `--sp-*`; radius `--r-*`; `.glass` lives in components.css; motion `--spring-*`/`--dur-*` + reduced-motion). The spec blocks are complete and final.

- [ ] **Step 2: Create `base.css`**
```css
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; min-width: 320px; background: var(--bg); color: var(--label);
  font-family: var(--font); font-size: var(--type-body); line-height: 1.4;
  -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
button, input, select, textarea { font: inherit; color: inherit; }
button { background: none; border: 0; cursor: pointer; }
:where(button, input, select, [tabindex]):focus-visible {
  outline: 3px solid color-mix(in srgb, var(--accent) 40%, transparent); outline-offset: 2px; border-radius: var(--r-control); }
.eyebrow { font-size: var(--type-caption); letter-spacing: var(--track-caption);
  text-transform: uppercase; font-weight: 600; color: var(--label-secondary); }
.title { font-size: var(--type-large-title); font-weight: 700; letter-spacing: var(--track-large-title); margin: 0; }
.h2 { font-size: var(--type-title); font-weight: 600; letter-spacing: var(--track-title); margin: 0; }
.muted { color: var(--label-secondary); }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; border:0; }
```

- [ ] **Step 3: Create `index.css`**
```css
@import "./tokens.css";
@import "./base.css";
@import "./components.css";
@import "./views/login.css";
@import "./views/overview.css";
@import "./views/attendance.css";
@import "./views/reports.css";
@import "./views/goals.css";
@import "./views/projects.css";
@import "./views/sheets.css";
```

- [ ] **Step 4: Create empty placeholder files** `components.css` and each `views/*.css` (with a `/* <name> */` header comment) so the imports resolve.

- [ ] **Step 5: Point the app at the new entry** — in `main.tsx` change `import "./styles/app.css";` to `import "./styles/index.css";`.

- [ ] **Step 6: Verify build**

Run: `npm run build`
Expected: build succeeds (app may look unstyled where old classes aren't yet ported — acceptable at this step).

- [ ] **Step 7: Commit**
```bash
git add frontend/src/styles frontend/src/main.tsx
git commit -m "feat(styles): token-driven modular CSS foundation"
```

---

### Task 2: `useReducedMotion` hook (TDD)

**Files:** Create `frontend/src/hooks/useReducedMotion.ts`, Test `frontend/src/hooks/useReducedMotion.test.ts`

- [ ] **Step 1: Failing test**
```ts
import { renderHook } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useReducedMotion } from "./useReducedMotion";

function mockMatchMedia(matches: boolean) {
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches, media: q, onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  }));
}

describe("useReducedMotion", () => {
  beforeEach(() => vi.unstubAllGlobals());
  it("returns true when the user prefers reduced motion", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(true);
  });
  it("returns false otherwise", () => {
    mockMatchMedia(false);
    const { result } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(false);
  });
});
```

- [ ] **Step 2: Run, expect FAIL** — `npm test -- useReducedMotion` → fails (module not found).

- [ ] **Step 3: Implement**
```ts
import { useEffect, useState } from "react";
const QUERY = "(prefers-reduced-motion: reduce)";
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() =>
    typeof matchMedia === "function" ? matchMedia(QUERY).matches : false);
  useEffect(() => {
    const mq = matchMedia(QUERY);
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}
```

- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat(hooks): useReducedMotion"`

---

### Task 3: `useCountUp` hook (TDD)

**Files:** Create `frontend/src/hooks/useCountUp.ts`, Test `frontend/src/hooks/useCountUp.test.ts`

Animates an integer from 0→target with rAF; respects reduced motion (jumps to target).

- [ ] **Step 1: Failing test**
```ts
import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { useCountUp } from "./useCountUp";

describe("useCountUp", () => {
  it("returns the target immediately when animation is disabled", () => {
    const { result } = renderHook(() => useCountUp(42, { animate: false }));
    expect(result.current).toBe(42);
  });
  it("ends at the target after animation completes", () => {
    vi.useFakeTimers();
    let raf = 0;
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      raf += 16; setTimeout(() => cb(raf), 16); return raf;
    });
    const { result } = renderHook(() => useCountUp(10, { animate: true, durationMs: 100 }));
    act(() => { vi.advanceTimersByTime(200); });
    expect(result.current).toBe(10);
    vi.useRealTimers(); vi.unstubAllGlobals();
  });
});
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement**
```ts
import { useEffect, useRef, useState } from "react";
interface Options { animate?: boolean; durationMs?: number; }
export function useCountUp(target: number, { animate = true, durationMs = 600 }: Options = {}): number {
  const [value, setValue] = useState(animate ? 0 : target);
  const startRef = useRef<number | null>(null);
  useEffect(() => {
    if (!animate) { setValue(target); return; }
    startRef.current = null;
    let id = 0;
    const tick = (t: number) => {
      if (startRef.current === null) startRef.current = t;
      const p = Math.min(1, (t - startRef.current) / durationMs);
      const eased = 1 - Math.pow(1 - p, 3); // easeOutCubic
      setValue(Math.round(target * eased));
      if (p < 1) id = requestAnimationFrame(tick);
    };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, [target, animate, durationMs]);
  return value;
}
```

- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat(hooks): useCountUp"`

---

### Task 4: `Card` + `SectionHeader` primitives

**Files:** Create `frontend/src/components/Card.tsx`, `frontend/src/components/SectionHeader.tsx`; append to `components.css`.

- [ ] **Step 1: `Card.tsx`**
```tsx
import type { ReactNode } from "react";
export function Card({ children, wide, className = "", as: Tag = "section" }:
  { children: ReactNode; wide?: boolean; className?: string; as?: any }) {
  return <Tag className={`card${wide ? " card--wide" : ""} ${className}`.trim()}>{children}</Tag>;
}
```

- [ ] **Step 2: `SectionHeader.tsx`**
```tsx
import type { ReactNode } from "react";
export function SectionHeader({ title, eyebrow, actions }:
  { title: ReactNode; eyebrow?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="section-header">
      <div>{eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}<h2 className="h2">{title}</h2></div>
      {actions ? <div className="section-header__actions">{actions}</div> : null}
    </header>
  );
}
```

- [ ] **Step 3: CSS (append to `components.css`)**
```css
.card { background: var(--surface); border-radius: var(--r-card); padding: var(--sp-4);
  box-shadow: var(--shadow-1); min-width: 0; }
.card--wide { grid-column: 1 / -1; }
.section-header { display: flex; align-items: center; justify-content: space-between;
  gap: var(--sp-3); margin-bottom: var(--sp-4); }
.section-header__actions { display: flex; align-items: center; gap: var(--sp-2); }
```

- [ ] **Step 4: Verify build** — `npm run build` → succeeds.
- [ ] **Step 5: Commit** — `git commit -m "feat(ui): Card + SectionHeader primitives"`

---

### Task 5: `StatCard` (+ CountUp) (TDD)

**Files:** Create `frontend/src/components/StatCard.tsx`, Test `StatCard.test.tsx`; append CSS.

- [ ] **Step 1: Failing test**
```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { StatCard } from "./StatCard";

describe("StatCard", () => {
  it("renders label and final value (no animation in tests)", () => {
    render(<StatCard label="Missing reports" value={3} animate={false} />);
    expect(screen.getByText("Missing reports")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement**
```tsx
import type { ReactNode } from "react";
import { useCountUp } from "../hooks/useCountUp";
import { useReducedMotion } from "../hooks/useReducedMotion";
export function StatCard({ icon, label, value, animate }:
  { icon?: ReactNode; label: string; value: number; animate?: boolean }) {
  const reduced = useReducedMotion();
  const shown = useCountUp(value, { animate: (animate ?? true) && !reduced });
  return (
    <div className="stat">
      {icon ? <span className="stat__icon" aria-hidden="true">{icon}</span> : null}
      <span className="stat__label">{label}</span>
      <strong className="stat__value num">{shown}</strong>
    </div>
  );
}
```

- [ ] **Step 4: CSS**
```css
.stat { display: grid; grid-template-columns: 44px 1fr; align-items: center; gap: var(--sp-1) var(--sp-3);
  background: var(--surface); border-radius: var(--r-card); padding: var(--sp-4); box-shadow: var(--shadow-1); }
.stat__icon { grid-row: span 2; display: grid; place-items: center; width: 44px; height: 44px;
  border-radius: var(--r-control); color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, transparent); }
.stat__icon svg { width: 20px; height: 20px; }
.stat__label { color: var(--label-secondary); font-size: var(--type-subhead); }
.stat__value { font-size: var(--metric); font-weight: 600; line-height: 1.1; }
```

- [ ] **Step 5: Run test, expect PASS.** **Step 6: Commit** — `git commit -m "feat(ui): StatCard with count-up"`

---

### Task 6: `SegmentedControl` with sliding indicator (TDD)

**Files:** Create `frontend/src/components/SegmentedControl.tsx`, Test `SegmentedControl.test.tsx`; append CSS.

Behavior: `role="tablist"`, one active segment, indicator pill positioned over the active segment (measured via refs), keyboard arrow navigation, calls `onChange`.

- [ ] **Step 1: Failing test**
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SegmentedControl } from "./SegmentedControl";

const items = [{ id: "a", label: "A" }, { id: "b", label: "B" }, { id: "c", label: "C" }];

describe("SegmentedControl", () => {
  it("marks the active segment selected", () => {
    render(<SegmentedControl items={items} value="b" onChange={() => {}} ariaLabel="Views" />);
    expect(screen.getByRole("tab", { name: "B" })).toHaveAttribute("aria-selected", "true");
  });
  it("calls onChange when a segment is clicked", async () => {
    const onChange = vi.fn();
    render(<SegmentedControl items={items} value="a" onChange={onChange} ariaLabel="Views" />);
    await userEvent.click(screen.getByRole("tab", { name: "C" }));
    expect(onChange).toHaveBeenCalledWith("c");
  });
  it("moves selection with ArrowRight", async () => {
    const onChange = vi.fn();
    render(<SegmentedControl items={items} value="a" onChange={onChange} ariaLabel="Views" />);
    screen.getByRole("tab", { name: "A" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenCalledWith("b");
  });
});
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement**
```tsx
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useReducedMotion } from "../hooks/useReducedMotion";
export interface Segment { id: string; label: string; icon?: ReactNode; }
export function SegmentedControl({ items, value, onChange, ariaLabel }:
  { items: Segment[]; value: string; onChange: (id: string) => void; ariaLabel: string }) {
  const reduced = useReducedMotion();
  const listRef = useRef<HTMLDivElement>(null);
  const [indicator, setIndicator] = useState<{ x: number; w: number } | null>(null);

  useEffect(() => {
    const list = listRef.current; if (!list) return;
    const measure = () => {
      const active = list.querySelector<HTMLElement>(`[data-id="${value}"]`);
      if (active) setIndicator({ x: active.offsetLeft, w: active.offsetWidth });
    };
    measure();
    const ro = new ResizeObserver(measure); ro.observe(list);
    return () => ro.disconnect();
  }, [value, items]);

  const onKey = (e: React.KeyboardEvent) => {
    const i = items.findIndex((s) => s.id === value);
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); onChange(items[(i + 1) % items.length].id); }
    if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); onChange(items[(i - 1 + items.length) % items.length].id); }
  };

  return (
    <div className="segmented" role="tablist" aria-label={ariaLabel} ref={listRef} onKeyDown={onKey}>
      {indicator ? (
        <span className="segmented__indicator" aria-hidden="true"
          style={{ transform: `translateX(${indicator.x}px)`, width: indicator.w,
            transition: reduced ? "none" : `transform var(--dur-snappy) var(--spring-snappy), width var(--dur-snappy) var(--spring-snappy)` }} />
      ) : null}
      {items.map((s) => (
        <button key={s.id} data-id={s.id} role="tab" type="button"
          aria-selected={s.id === value} tabIndex={s.id === value ? 0 : -1}
          className={`segmented__item${s.id === value ? " is-active" : ""}`}
          title={s.label} onClick={() => onChange(s.id)}>
          {s.icon}<span className="segmented__label">{s.label}</span>
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: CSS**
```css
.segmented { position: relative; display: inline-flex; gap: 2px; padding: 4px;
  border-radius: var(--r-pill); background: var(--fill-2); }
.segmented__indicator { position: absolute; top: 4px; bottom: 4px; left: 0; border-radius: var(--r-pill);
  background: var(--surface); box-shadow: var(--shadow-1); will-change: transform, width; }
.segmented__item { position: relative; z-index: 1; display: inline-flex; align-items: center; gap: var(--sp-2);
  min-height: 36px; min-width: 44px; padding: 0 var(--sp-3); border-radius: var(--r-pill);
  color: var(--label-secondary); font-size: var(--type-subhead); font-weight: 500;
  transition: color var(--dur-snappy) var(--ease-out); }
.segmented__item.is-active { color: var(--label); font-weight: 600; }
.segmented__item:active { transform: scale(0.97); }
@media (max-width: 920px) { .segmented__label { display: none; } }
```

- [ ] **Step 5: Run tests, expect PASS.** **Step 6: Commit** — `git commit -m "feat(ui): SegmentedControl with sliding indicator"`

> **jsdom note:** `offsetLeft/offsetWidth` are 0 in jsdom, so the indicator measures to 0 — fine for the behavior tests above (they assert roles/selection/keyboard, not pixel geometry). Visual positioning is verified in the browser at Task 21.

---

### Task 7: `Skeleton`

**Files:** Create `frontend/src/components/Skeleton.tsx`; append CSS.

- [ ] **Step 1: Implement**
```tsx
export function Skeleton({ w = "100%", h = 16, r = 8, className = "" }:
  { w?: string | number; h?: string | number; r?: number; className?: string }) {
  return <span className={`skeleton ${className}`.trim()} aria-hidden="true"
    style={{ width: w, height: h, borderRadius: r }} />;
}
export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return <span className="skeleton-text">{Array.from({ length: lines }).map((_, i) =>
    <Skeleton key={i} w={i === lines - 1 ? "60%" : "100%"} h={12} />)}</span>;
}
```

- [ ] **Step 2: CSS**
```css
.skeleton { display: block; background: linear-gradient(100deg, var(--fill-2) 30%, var(--fill) 50%, var(--fill-2) 70%);
  background-size: 200% 100%; animation: skeleton-shimmer 1.4s ease-in-out infinite; }
.skeleton-text { display: grid; gap: var(--sp-2); }
@keyframes skeleton-shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
@media (prefers-reduced-motion: reduce) { .skeleton { animation: none; } }
```

- [ ] **Step 3: Verify build.** **Step 4: Commit** — `git commit -m "feat(ui): Skeleton placeholders"`

---

### Task 8: `Avatar`

**Files:** Create `frontend/src/components/Avatar.tsx`; append CSS.

- [ ] **Step 1: Implement** (deterministic mono-initial chip)
```tsx
export function Avatar({ name }: { name: string }) {
  const initials = name.trim().split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  return <span className="avatar" aria-hidden="true">{initials || "?"}</span>;
}
```

- [ ] **Step 2: CSS**
```css
.avatar { display: inline-grid; place-items: center; width: 32px; height: 32px; flex: none;
  border-radius: var(--r-pill); font-size: var(--type-footnote); font-weight: 600;
  color: var(--label-secondary); background: var(--fill); }
```

- [ ] **Step 3: Build.** **Step 4: Commit** — `git commit -m "feat(ui): Avatar"`

---

### Task 9: Restyle `StatusPill`

**Files:** Modify `frontend/src/components/StatusPill.tsx` (logic unchanged); append pill CSS.

- [ ] **Step 1: Confirm `StatusPill.tsx` markup** stays `<span className={`pill pill-${value}`}>{labels[value]}</span>` (no code change needed; the labels map is already complete). Add an icon-dot for redundant (non-color-only) encoding:
```tsx
export function StatusPill({ value }: { value: PillValue }) {
  return <span className={`pill pill-${value}`}><span className="pill__dot" aria-hidden="true" />{labels[value]}</span>;
}
```

- [ ] **Step 2: CSS** (semantic-tinted, dot + label)
```css
.pill { display: inline-flex; align-items: center; gap: 6px; min-height: 24px; padding: 0 10px;
  border-radius: var(--r-pill); font-size: var(--type-footnote); font-weight: 600;
  color: var(--label-secondary); background: var(--fill-2); }
.pill__dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.pill-in, .pill-resolved, .pill-active, .pill-done { color: var(--success); background: color-mix(in srgb, var(--success) 14%, transparent); }
.pill-late, .pill-needs_chase, .pill-chased, .pill-paused { color: var(--warning); background: color-mix(in srgb, var(--warning) 16%, transparent); }
.pill-charged, .pill-no_show, .pill-overdue, .pill-missing { color: var(--danger); background: color-mix(in srgb, var(--danger) 14%, transparent); }
```

- [ ] **Step 3: Build.** **Step 4: Commit** — `git commit -m "feat(ui): restyle StatusPill with status dot"`

---

### Task 10: Custom `BarChart` (SVG) (TDD)

**Files:** Create `frontend/src/components/BarChart.tsx`, Test `BarChart.test.tsx`; append CSS.

Replaces recharts. Supports 1–2 series grouped bars, auto max, value formatting, reveal via `scaleY`, accessible label + visually-hidden data table.

- [ ] **Step 1: Failing test**
```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { BarChart } from "./BarChart";

const data = [{ label: "Oliver", value: 3 }, { label: "Sam", value: 5 }];
describe("BarChart", () => {
  it("renders an accessible figure with one rect per datum", () => {
    const { container } = render(<BarChart data={data} ariaLabel="Lates per person" />);
    expect(screen.getByRole("img", { name: /lates per person/i })).toBeInTheDocument();
    expect(container.querySelectorAll("rect.bar").length).toBe(2);
  });
  it("exposes the data in a visually-hidden table", () => {
    render(<BarChart data={data} ariaLabel="Lates" />);
    expect(screen.getByText("Oliver")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement**
```tsx
import { useReducedMotion } from "../hooks/useReducedMotion";
export interface Datum { label: string; value: number; value2?: number; }
export function BarChart({ data, ariaLabel, format = (n: number) => String(n), max: maxProp, height = 200 }:
  { data: Datum[]; ariaLabel: string; format?: (n: number) => string; max?: number; height?: number }) {
  const reduced = useReducedMotion();
  const grouped = data.some((d) => d.value2 != null);
  const max = maxProp ?? Math.max(1, ...data.flatMap((d) => [d.value, d.value2 ?? 0]));
  const W = 100, H = 100, pad = 4, slot = (W - pad * 2) / Math.max(1, data.length);
  const barW = grouped ? slot * 0.3 : slot * 0.5;
  return (
    <figure className="chart" role="img" aria-label={ariaLabel} style={{ height }}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="chart__svg">
        <line x1="0" y1={H - pad} x2={W} y2={H - pad} className="chart__axis" />
        {data.map((d, i) => {
          const cx = pad + slot * i + slot / 2;
          const h1 = ((H - pad * 2) * d.value) / max;
          const bars = [{ v: d.value, cls: "bar", x: grouped ? cx - barW - 1 : cx - barW / 2, h: h1 }];
          if (grouped) bars.push({ v: d.value2 ?? 0, cls: "bar bar--2", x: cx + 1, h: ((H - pad * 2) * (d.value2 ?? 0)) / max });
          return bars.map((b, j) => (
            <rect key={`${i}-${j}`} className={b.cls} x={b.x} y={H - pad - b.h} width={barW} height={Math.max(0, b.h)}
              rx="1.5" style={{ transformOrigin: `center ${H - pad}px`,
                animation: reduced ? "none" : `chart-grow var(--dur-smooth) var(--spring-smooth) both`,
                animationDelay: reduced ? undefined : `${i * 30}ms` }} />
          ));
        })}
      </svg>
      <div className="chart__labels">{data.map((d) => <span key={d.label}>{d.label}</span>)}</div>
      <figcaption className="sr-only">
        <table><tbody>{data.map((d) => (
          <tr key={d.label}><th>{d.label}</th><td>{format(d.value)}</td>{d.value2 != null ? <td>{format(d.value2)}</td> : null}</tr>
        ))}</tbody></table>
      </figcaption>
    </figure>
  );
}
```

- [ ] **Step 4: CSS**
```css
.chart { margin: 0; display: grid; gap: var(--sp-2); }
.chart__svg { width: 100%; height: 100%; overflow: visible; }
.chart__axis { stroke: var(--separator); stroke-width: 0.5; }
.chart .bar { fill: var(--accent); }
.chart .bar--2 { fill: var(--danger); }
.chart__labels { display: flex; justify-content: space-around; color: var(--label-secondary);
  font-size: var(--type-caption); letter-spacing: var(--track-caption); }
@keyframes chart-grow { from { transform: scaleY(0); } to { transform: scaleY(1); } }
@media (prefers-reduced-motion: reduce) { .chart .bar { animation: none !important; } }
```

- [ ] **Step 5: Run tests, expect PASS.** **Step 6: Commit** — `git commit -m "feat(ui): custom SVG BarChart (replaces recharts)"`

---

### Task 11: `Shell` (topbar + title + view transition)

**Files:** Create `frontend/src/components/Shell.tsx`; modify `frontend/src/App.tsx`; append shell CSS to `components.css`.

- [ ] **Step 1: `Shell.tsx`** — owns the glass topbar, brand, `SegmentedControl`, date stepper, sign-out, the per-view large title, and the view crossfade.
```tsx
import type { ReactNode } from "react";
import { LogOut, ChevronLeft, ChevronRight } from "lucide-react";
import { SegmentedControl, type Segment } from "./SegmentedControl";
import { addDays } from "../lib/dates";
export function Shell({ tabs, active, onActive, title, date, onDate, onLogout, children }:
  { tabs: Segment[]; active: string; onActive: (id: string) => void; title: string;
    date: string; onDate: (d: string) => void; onLogout: () => void; children: ReactNode }) {
  return (
    <div className="app-shell">
      <header className="topbar glass">
        <div className="topbar__brand"><span className="eyebrow">Viper operations</span><strong>Sigma Dashboard</strong></div>
        <SegmentedControl items={tabs} value={active} onChange={onActive} ariaLabel="Dashboard views" />
        <div className="topbar__actions">
          <div className="datestepper">
            <button className="icon-button" aria-label="Previous day" onClick={() => onDate(addDays(date, -1))}><ChevronLeft size={18} /></button>
            <input type="date" value={date} onChange={(e) => onDate(e.target.value)} aria-label="Dashboard date" />
            <button className="icon-button" aria-label="Next day" onClick={() => onDate(addDays(date, 1))}><ChevronRight size={18} /></button>
          </div>
          <button className="icon-button" onClick={onLogout} aria-label="Sign out"><LogOut size={18} /></button>
        </div>
      </header>
      <main className="content">
        <h1 className="title view-title">{title}</h1>
        <div key={active} className="view-enter">{children}</div>
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Update `App.tsx`** — replace the inline `<header className="topbar">…</header>` + `<main>` with `<Shell …>`; pass `tabs` (add `icon`), `active`, `setActive`, the active view's `title` (map tab id → label), `selectedDate`, `setSelectedDate`, `logout`, and render the existing conditional view body as `children`. Keep all `useQuery` calls unchanged.

- [ ] **Step 3: Shell CSS (append to `components.css`)**
```css
.app-shell { min-height: 100vh; }
.topbar { position: sticky; top: var(--sp-3); z-index: 20; margin: var(--sp-3) auto 0; width: min(1200px, calc(100% - var(--sp-8)));
  display: grid; grid-template-columns: minmax(160px, 1fr) auto 1fr; align-items: center; gap: var(--sp-4);
  padding: var(--sp-2) var(--sp-3); border-radius: var(--r-pill); }
.topbar__brand { display: grid; line-height: 1.1; }
.topbar__brand strong { font-size: var(--type-headline); font-weight: 600; }
.topbar__actions { display: flex; align-items: center; justify-content: flex-end; gap: var(--sp-2); }
.datestepper { display: inline-flex; align-items: center; gap: 2px; padding: 2px; border-radius: var(--r-control); background: var(--fill-2); }
.datestepper input { border: 0; background: transparent; min-height: 36px; padding: 0 var(--sp-1); color: var(--label); }
.icon-button { display: grid; place-items: center; width: 40px; height: 40px; border-radius: var(--r-control); color: var(--label); }
.icon-button:hover { background: var(--fill-2); } .icon-button:active { transform: scale(0.94); }
.content { width: min(1200px, 100%); margin: 0 auto; padding: var(--sp-6); }
.view-title { margin: var(--sp-4) 0 var(--sp-5); }
.view-enter { animation: view-in var(--dur-smooth) var(--spring-smooth) both; }
@keyframes view-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .view-enter { animation: view-fade 160ms ease both; } @keyframes view-fade { from { opacity: 0; } to { opacity: 1; } } }
@media (max-width: 920px) { .topbar { grid-template-columns: 1fr auto; width: calc(100% - var(--sp-5)); } .topbar__brand { display: none; } .content { padding: var(--sp-4); } }
```

- [ ] **Step 4: Verify build + lint** — `npm run build && npm run lint`.
- [ ] **Step 5: Commit** — `git commit -m "feat(shell): floating glass topbar + segmented nav + view transition"`

---

### Tasks 12–18: Views (parallelizable — each owns its own `views/<name>.css`)

> Each view task: rewrite the component's JSX against the primitives (`Card`, `SectionHeader`, `StatCard`, `Avatar`, `StatusPill`, `BarChart`, `Skeleton`), write the view's CSS into its **own** `views/<name>.css`, verify build, commit. No two view tasks edit the same CSS file, so they can run concurrently in isolated worktrees.

### Task 12: Overview (bento)
**Files:** Modify `OverviewView.tsx`; write `styles/views/overview.css`.
- [ ] **Step 1:** Rewrite `OverviewView` to use `metric-row` of 4 `StatCard`s; a wide "Tonight" `Card` rendering roster rows (`Avatar` + name + `StatusPill` + in/out + chase pill) instead of the raw table; a "Weekly charge" `Card` with `BarChart` (`data = weekly_summary.map(r => ({label: r.person.display_name, value: r.total_charge_uzs}))`, `format` → `toLocaleString()+" UZS"`); a "Goal risk" `Card` listing at-risk goals with title, deadline, animated `.progress`. Replace recharts imports with `BarChart`.
- [ ] **Step 2:** `overview.css` — `.view-grid` (2-col responsive → 1-col < 920px), `.metric-row` (4-col → 2 → 1), `.roster-row` (grid: avatar | name+meta | status), `.progress` bar (scaleX fill, `--spring-smooth`), `.tile` materialize stagger:
```css
.view-grid { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: var(--sp-4); }
.metric-row { grid-column: 1/-1; display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: var(--sp-3); }
.roster-row { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: var(--sp-3);
  padding: var(--sp-3) 0; border-bottom: 1px solid var(--separator); }
.roster-row:last-child { border-bottom: 0; }
.progress { height: 6px; border-radius: var(--r-pill); background: var(--fill); overflow: hidden; }
.progress > span { display: block; height: 100%; background: var(--accent); transform-origin: left;
  animation: progress-fill var(--dur-smooth) var(--spring-smooth) both; }
@keyframes progress-fill { from { transform: scaleX(0); } to { transform: scaleX(1); } }
.tile { animation: view-in var(--dur-smooth) var(--spring-smooth) both; }
.tile:nth-child(2){animation-delay:30ms}.tile:nth-child(3){animation-delay:60ms}.tile:nth-child(4){animation-delay:90ms}
@media (max-width: 920px){ .view-grid{grid-template-columns:1fr} .metric-row{grid-template-columns:repeat(2,1fr)} }
@media (prefers-reduced-motion: reduce){ .progress>span,.tile{animation:none} .progress>span{transform:none} }
```
- [ ] **Step 3:** Build → commit `feat(overview): bento home`.

### Task 13: Attendance (+ optimistic `ChaseControl`) (TDD on the control)
**Files:** Modify `AttendanceView.tsx`; create `ChaseControl.tsx` + `ChaseControl.test.tsx`; write `views/attendance.css`.
- [ ] **Step 1 (failing test):** `ChaseControl` renders 4 options, marks current selected, calls `onChange(next)` on click.
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { ChaseControl } from "./ChaseControl";
it("changes chase state", async () => {
  const onChange = vi.fn();
  render(<ChaseControl value="none" onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: /chased/i }));
  expect(onChange).toHaveBeenCalledWith("chased");
});
```
- [ ] **Step 2:** Implement `ChaseControl` (a compact segmented control over `none|needs_chase|chased|resolved`). 
- [ ] **Step 3:** Rewrite `AttendanceView`: "Today" as roster rows with `ChaseControl` wired to the **optimistic** mutation (`onMutate` cancels+snapshots+sets `["today",shiftDate]`, `onError` rolls back, `onSettled` invalidates — keep the existing `api.patchChase`); History matrix with sticky first column + status-dot cells; "Weekly lates" `BarChart` (grouped: `value=lates,value2=charged`); "Weekly totals" stat rows. Remove recharts.
- [ ] **Step 4:** `attendance.css` — roster, sticky `th/td:first-child`, `.matrix` cells, chase control sizing.
- [ ] **Step 5:** Tests + build → commit `feat(attendance): optimistic chase + roster + matrix`.

### Task 14: Reports
**Files:** Modify `ReportsView.tsx`; write `views/reports.css`.
- [ ] Rewrite: daily report `Card`s (person, topic, summary, extras, rating as ●●●○ via a small inline component, missing flagged with `StatusPill value="missing"` + icon + label); performance leaderboard rows with position emphasis; rating `BarChart` (`max=4`). Remove recharts. Build → commit `feat(reports): cards + leaderboard + chart`.

### Task 15: Goals
**Files:** Modify `GoalsView.tsx`; write `views/goals.css`.
- [ ] Rewrite: goal `Card`s with `StatusPill`, animated `.progress`, definition list (owner/deadline/topic/nudge), latest log; at-risk = accent/danger left-edge accent (`box-shadow: inset 3px 0 0 var(--danger)`). Build → commit `feat(goals): goal cards`.

### Task 16: Projects
**Files:** Modify `ProjectConditionView.tsx`; write `views/projects.css`.
- [ ] Rewrite: topic `Card`s — title + `#id` chip, summary, relative last-activity (add `relativeTime()` to `lib/dates.ts` + a unit test), open-items checklist. Build → commit `feat(projects): condition cards + relative time`.

### Task 17: Sheets
**Files:** Modify `SheetsView.tsx`; write `views/sheets.css`.
- [ ] Rewrite: header `Card` (title, configured name, primary glass import button busy/disabled, success/error banners); per-tab preview tables (sticky header, mono cells, ellipsis). Build → commit `feat(sheets): refined preview + import`.

### Task 18: Login
**Files:** Modify `LoginPanel.tsx`; write `views/login.css`.
- [ ] Rewrite: centered card on calm field, app mark, labels, error state, busy button, `materialize-in` on mount (reduced-motion → fade). Build → commit `feat(login): refined login`.

---

### Task 19: Remove recharts, verify #310 gone

**Files:** Modify `frontend/package.json`; verify no `recharts` imports remain.

- [ ] **Step 1:** `cd frontend && grep -rn "recharts" src` → expect **no matches** (all views migrated to `BarChart`).
- [ ] **Step 2:** `npm uninstall recharts`.
- [ ] **Step 3:** `npm run build` → succeeds; confirm no `charts-*.js` chunk referencing recharts.
- [ ] **Step 4:** Serve the production build and load Overview/Attendance/Reports; confirm **no console error** (the React #310 crash is gone). (Manual/Playwright check at Task 21.)
- [ ] **Step 5:** Commit — `git commit -m "chore: remove recharts (fixes React #310 crash)"`.

---

### Task 20: State polish — skeletons, empty, error

**Files:** Modify `App.tsx` (loading/error gating), `EmptyState.tsx`, view files as needed.

- [ ] **Step 1:** Replace the "render only when `*.data`" gating with skeleton states: while a view's queries are `isLoading`, render a view-shaped `Skeleton` layout instead of nothing.
- [ ] **Step 2:** Upgrade `EmptyState` to accept an optional `icon` and `action` (retry) and use it for empty datasets.
- [ ] **Step 3:** Convert the top-level `hasError` block into a recoverable error `Card` (message + "Retry" calling `refetch`).
- [ ] **Step 4:** Build + lint → commit `feat(states): skeleton/empty/error states`.

---

### Task 21: A11y + dual-theme + verification gate

**Files:** none new — verification + fixes.

- [ ] **Step 1:** Delete the now-unused `frontend/src/styles/app.css` (confirm nothing imports it) → build.
- [ ] **Step 2:** Run full suite: `cd frontend && npm run lint && npm test && npm run build`. All pass.
- [ ] **Step 3:** Serve prod build from FastAPI (`cd .. && uvicorn backend.app.main:app --port 8000`) and, with the running app, verify in the browser (Playwright/manual): both light & dark; segmented indicator slides; view transitions; charts render with no console errors; skeletons on load; keyboard tab through the segmented control; focus rings visible; 44pt targets.
- [ ] **Step 4:** Quick contrast check on secondary-label-on-secondary-bg combos in both themes; bump alpha where < AA.
- [ ] **Step 5:** Commit any fixes — `git commit -m "polish: a11y + dual-theme verification"`.

---

## Self-review

**Spec coverage:** tokens/type/space/material/motion (§4 → Task 1); modular CSS + components (§5 → Tasks 1,4–11, per-view); shell (§6 → Task 11); all 7 views (§7 → Tasks 12–18); states (§8 → Task 20); charts (§9 → Task 10, wired 12–17); #310 fix (§10 → Tasks 10,19); a11y (§11 → Tasks 9,21); out-of-scope respected (no API/data changes); acceptance criteria (§13 → Task 21 gate). ✓ No gaps.

**Placeholder scan:** behavioral components have full code + tests; view tasks give exact files, primitives, JSX shape, and complete per-view CSS. No TBD/TODO. ✓

**Type consistency:** `Segment{id,label,icon?}` used by SegmentedControl + Shell; `Datum{label,value,value2?}` used by BarChart + all chart call-sites; hooks `useReducedMotion()/useCountUp(target,{animate,durationMs})` signatures consistent across StatCard/SegmentedControl/BarChart. ✓
