# Performance Tab — Implementation Plan

> **For agentic workers:** the schema-sensitive backend (models + the composite-grade logic
> + endpoints) is authored by the lead and smoke-tested first; frontend + backend tests then
> fan out in parallel, followed by an adversarial review. Source spec:
> `~/projects/SigmasDashboard/docs/PERFORMANCE_TAB_PLAN.md`.

**Goal:** A dedicated **Performance** tab that strictly evaluates each person via WHAT (output)
/ HOW (work pattern) / WHY (verdict), combining daily reports, attendance, goals, Viper's weekly
evaluation, and Abdul's feedback.

**Architecture:** Enrich `GET /performance` to join attendance + compute a server-side composite
grade. Add two ingest-backed tables (`evaluations`, `feedback`) with Viper write endpoints + admin
read endpoints. New `PerformanceView` React tab (leaderboard + expandable WHAT/HOW/WHY detail +
period selector). Backend FastAPI+SQLite, frontend React/Vite/TanStack Query — same single service.

**Tech stack:** FastAPI · SQLAlchemy · Pydantic v2 · React 18 · TanStack Query · custom SVG charts.

## Locked decisions
1. **Composite grade** — output-anchored, attendance penalty-only, feedback ±1 band override.
2. **Default period** — current Mon–Sat work-week (6 work-days; completion% denominator = 6 in a
   full week, or count of Mon–Sat days in a custom window); also Month + Custom range.
3. **Verdict** — distilled (grade + one WHAT/HOW/WHY line) by default, expandable to full narrative.
4. **Feedback** — separate `feedback` table + `POST /viper/feedback`; per-person timeline under WHY;
   carries a structured `grade_adjustment ∈ {-1,0,+1}` so the override is computable.
5. **Charges** — dropped from the system (commit 191fa89); N/A on this tab.

---

## Backend

### Models (`backend/app/models.py`)
```python
class Evaluation(TimestampMixin, Base):
    __tablename__ = "evaluations"
    __table_args__ = (UniqueConstraint("person_id", "period_start", "period_end",
                                       name="uq_eval_person_period"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), nullable=False, index=True)
    period_start: Mapped[date]; period_end: Mapped[date]
    grade: Mapped[str] = mapped_column(String(24), nullable=False)   # under/average/good/over (free)
    what: Mapped[str] = mapped_column(Text); how: Mapped[str] = mapped_column(Text)
    why: Mapped[str] = mapped_column(Text)
    composite_score: Mapped[int | None]  # optional Viper-provided 0-100

class Feedback(TimestampMixin, Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), nullable=False, index=True)
    feedback_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(40), nullable=True)  # e.g. "abdul"
    grade_adjustment: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # -1/0/+1
```
Migration: additive `Base.metadata.create_all` (creates `evaluations`, `feedback`).

### Schemas (`backend/app/schemas.py`)
- `ViperEvaluationUpsert{person: ViperPersonRef, period_start, period_end, grade, what, how, why, composite_score?: int}`
- `EvaluationOut{id, person, period_start, period_end, grade, what, how, why, composite_score, updated_at}`
- `ViperFeedbackUpsert{person: ViperPersonRef, feedback_date, note, source?, grade_adjustment: int=0 (ge=-1,le=1)}`
- `FeedbackOut{id, person, feedback_date, note, source, grade_adjustment, created_at}`
- Enrich `PerformanceRow` — add: `avg_check_in: str|None` ("HH:MM"), `avg_check_out: str|None`,
  `on_time_count, late_count, late15_count, no_show_count, absent_count: int`, `compensates: bool`,
  `avg_hours: float|None`, `punctuality_rate: float`, `attendance_days: int`,
  `top_accomplishment: str|None`, `rating_trend: list[RatingPoint]`, `composite_grade: str`
  (Under/Average/Good/Over), `composite_score: int` (0-100). `RatingPoint{date, rating}`.

### Services (`backend/app/services.py`) — `compute_performance_rows(db, start, end)`
For each active person over `[start,end]`:
- reports → `average_rating` (mean of non-null), `missing_days`, `report_completion_rate`
  = round(non_missing / workdays * 100, 1) where `workdays = count of Mon–Sat in [start,end]` (≥1).
- attendance records → status counts; `punctuality_rate = on_time/total*100` (0 if none).
- `avg_check_in`/`avg_check_out` = mean minutes-of-day over records with that timestamp → "HH:MM".
- `avg_late_min` = mean over records of `max(0, checkin_min − 18:00)`; `avg_ot_min` = mean of
  `max(0, checkout_clock − 03:00)`; `compensates = avg_late_min > 0 and avg_ot_min >= avg_late_min`.
- `avg_hours` = mean of `(check_out_at − check_in_at)` hours over days with both (round 1).
- `top_accomplishment` = summary of highest-rated non-missing report (tie → latest); else None.
- `rating_trend` = [{date, rating} for non-missing reports asc].
- **composite grade:**
  ```
  band = 0(under) if avg is None else (3 if avg>=3.5 else 2 if avg>=2.5 else 1 if avg>=1.5 else 0)
  penalty = (2 if no_show_count>0 else 0) + (1 if (late+late15)>=2 and not compensates else 0)
  adj = grade_adjustment of the latest feedback in window (or 0)
  final = clamp(band - penalty + adj, 0, 3)
  composite_grade = ["Under","Average","Good","Over"][final];  composite_score = round(final/3*100)
  ```
- Sort leaderboard by `composite_score` desc, then `average_rating` desc (worst→best toggle = client).

### Routes (`backend/app/routes.py`)
- `GET /performance?from=&to=` — enriched rows (replaces current logic via `compute_performance_rows`).
- `POST /viper/evaluation` (require_viper) — upsert on (person, period_start, period_end) → `EvaluationOut`.
- `GET /evaluations?from=&to=` (require_admin) — evaluations overlapping window, latest per person.
- `POST /viper/feedback` (require_viper) — insert feedback → `FeedbackOut`.
- `GET /feedback?from=&to=` (require_admin) — feedback in window, newest first.
- New OpenAPI tag `Performance`; regen `openapi.json`; update `docs/API.md`.

### Backend tests (`backend/tests/test_performance.py`)
composite bands (under/avg/good/over), no_show → −2, chronic-late-no-comp → −1, compensates cancels
penalty, feedback +1/−1 override + clamp, completion% over Mon–Sat workdays, avg in/out + avg_hours,
evaluation upsert (same period overwrites), feedback insert + GET window, all endpoints 401 without token.

## Frontend

- **types.ts** — `RatingPoint`, extend `PerformanceRow` (above), `Evaluation`, `Feedback`.
- **api.ts** — `performance(token,from,to)` (already exists, now richer), `evaluations(token,from,to)`,
  `feedback(token,from,to)`.
- **dates.ts** — `monSatWeek(date)` → {from,to}; `monthRange(date)`; reuse `parseServerDate` for any times.
- **App.tsx** — add a `Performance` tab (icon `Gauge`/`TrendingUp`) between Reports and Goals; its own
  period state (default Mon–Sat week) driving the 3 queries; move the performance cards OUT of ReportsView.
- **PerformanceView.tsx** (NEW) — period selector (Week/Month/Custom from–to) + worst→best sort toggle;
  **leaderboard** rows (rank, composite grade pill, avg rating + sparkline trend, completion%, punctuality%,
  top accomplishment); click a row → **expand** WHAT/HOW/WHY detail panel.
- **Sparkline.tsx** (NEW) — tiny SVG line of `rating_trend` (reuse the finite-coercion guard from BarChart).
- **PerformanceDetail** (in PerformanceView) — WHAT (rating+sparkline, accomplishments, completion/missing),
  HOW (avg in/out, status counts, compensation flag, avg hours vs ~9h, punctuality trend), WHY (distilled
  eval grade + WHAT/HOW/WHY one-liners, **expand** to full narrative; feedback timeline newest-first).
- **ReportsView.tsx** — remove the "Performance rank" + "Rating average" cards (now their own tab).
- **CSS** — `views/performance.css` (leaderboard rows, grade pills reusing the pill palette, sparkline,
  detail grid, period selector); register in `styles/index.css`.
- Build clean (`tsc -b && vite build`); existing vitest stays green.

## Verification
- Backend smoke (TestClient against live db): every endpoint, composite-grade cases, upserts.
- Browser: Performance tab — leaderboard renders, expand shows WHAT/HOW/WHY, period selector refetches,
  sort toggle, zero console errors, timestamps correct (UTC-safe).
- Adversarial review: spec-compliance (4 decisions), backend correctness/security, frontend a11y, edge cases.
