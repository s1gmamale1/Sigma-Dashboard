# Review Fixes Implementation Plan (OFF DAY · Ops · Hardening)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the verified 2026-06-12 review fixes — OFF DAY end-to-end, launchd bring-up on :8001, and the P1 hardening batch — per `docs/superpowers/specs/2026-06-12-review-fixes-design.md`.

**Architecture:** FastAPI + SQLAlchemy (SQLite) backend at `backend/app/`, React/TS frontend at `frontend/`, pytest suite at `backend/tests/`. The Viper CLI client lives in a *different* repo: `/Users/aisigma/projects/SigmasDashboard/scripts/dashboard_client.py` (not a git repo). Live service is managed by launchd on macOS.

**Tech Stack:** Python 3.12+ (`.venv`), pydantic v2, SQLAlchemy 2 typed ORM, pytest, React 18 + Vite + TypeScript.

**Conventions:**
- Repo root: `/Users/aisigma/sigma-dashboard`. All commands run from there unless stated.
- Test command: `.venv/bin/python -m pytest backend/tests -q`
- Frontend check: `cd frontend && npm run build`
- Commit after each task. Tests must be green before each commit.

---

### Task 0: Baseline — confirm the suite is green before touching anything

- [ ] **Step 0.1: Run the full suite**

Run: `cd /Users/aisigma/sigma-dashboard && .venv/bin/python -m pytest backend/tests -q`
Expected: all pass (≈50+ tests). If anything fails, STOP and investigate before proceeding (systematic-debugging skill).

---

## WP1 — Ops bring-up (P0)

### Task 1: Canonicalize port :8001 in repo files

**Files:**
- Modify: `config/com.sigma.dashboard.plist` (port 8000→8001, add ThrottleInterval)
- Modify: `frontend/vite.config.ts:26` (proxy 8000→8001)
- Modify: `README.md:57` (uvicorn example port)

- [ ] **Step 1.1: plist — change port and add ThrottleInterval**

In `config/com.sigma.dashboard.plist`, change `<string>8000</string>` to `<string>8001</string>`, and add after the `</array>` of ProgramArguments:

```xml
  <key>ThrottleInterval</key>
  <integer>10</integer>
```

- [ ] **Step 1.2: vite proxy**

In `frontend/vite.config.ts` line 26, change:

```ts
      "/api": "http://127.0.0.1:8000"
```
to
```ts
      "/api": "http://127.0.0.1:8001"
```

- [ ] **Step 1.3: README**

In `README.md` line 57, change `--port 8000` to `--port 8001`. Search for any other `8000` references: `grep -rn "8000" README.md config/ frontend/vite.config.ts` — fix all hits.

- [ ] **Step 1.4: Verify no stale references**

Run: `grep -rn "8000" config/ frontend/vite.config.ts README.md`
Expected: no output.

- [ ] **Step 1.5: Commit**

```bash
git add config/com.sigma.dashboard.plist frontend/vite.config.ts README.md
git commit -m "fix(ops): canonicalize port 8001 (8000 is owned by netsbuilder); add launchd ThrottleInterval"
```

### Task 2: Live bring-up — pin DB path, install launchd unit, retire the manual process

This task changes live system state (no code). The dashboard will blip for a few seconds while launchd takes over.

- [ ] **Step 2.1: Pin the DB to an absolute path in the live `.env`** (the `.env` is gitignored — do NOT commit it)

```bash
cd /Users/aisigma/sigma-dashboard
grep -q SIGMA_DATABASE_URL .env || echo 'SIGMA_DATABASE_URL=sqlite:////Users/aisigma/sigma-dashboard/dashboard.db' >> .env
```

- [ ] **Step 2.2: Delete the stray empty DB**

```bash
[ -s backend/dashboard.db ] && echo "NOT EMPTY — STOP AND INVESTIGATE" || rm -f backend/dashboard.db
```
Expected: file removed (it was 0 bytes on 2026-06-12). If it is non-empty, stop.

- [ ] **Step 2.3: Install the plist and hand over from the manual process**

```bash
cp config/com.sigma.dashboard.plist ~/Library/LaunchAgents/
pkill -f "uvicorn backend.app.main:app" || true   # retire the manual :8001 process
launchctl load -w ~/Library/LaunchAgents/com.sigma.dashboard.plist
sleep 3
launchctl list | grep com.sigma.dashboard
```
Expected: a line with a PID and status 0.

- [ ] **Step 2.4: Verify HTTP + crash-respawn**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8001/        # expect 200 (frontend)
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8001/docs    # expect 200
PID=$(launchctl list | awk '/com.sigma.dashboard/{print $1}'); kill "$PID"; sleep 12
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8001/        # expect 200 again (KeepAlive)
```
Expected: 200 / 200 / 200. Also confirm the live DB is the root one: `sqlite3 dashboard.db "SELECT COUNT(*) FROM attendance_records;"` returns >0.

---

## WP2 — OFF DAY end-to-end (P0/P1)

### Task 3: `off_day` status in model, schema, and classifier

**Files:**
- Modify: `backend/app/models.py:9`
- Modify: `backend/app/schemas.py:7`
- Modify: `backend/app/services.py:83` (calculate_attendance_status)
- Test: `backend/tests/test_attendance_sheet.py`

- [ ] **Step 3.1: Write failing test** (append to `backend/tests/test_attendance_sheet.py`; it already has `make_db`, `TZ`, and imports for `AttendanceRecord`, `Person`, `select`, `date`):

```python
def test_explicit_off_day_status() -> None:
    from backend.app.services import calculate_attendance_status

    db = make_db()
    assert calculate_attendance_status(db, date(2026, 6, 7), None, "off_day") == ("off_day", 0)


def test_off_day_record_satisfies_check_constraint() -> None:
    from backend.app.services import get_or_create_person

    db = make_db()
    person = get_or_create_person(db, "oliver", "Oliver")
    db.add(
        AttendanceRecord(
            person_id=person.id, shift_date=date(2026, 6, 7), status="off_day", chase_state="none"
        )
    )
    db.commit()  # would raise IntegrityError if off_day is not in the CHECK constraint
```

- [ ] **Step 3.2: Run to verify failure**

Run: `.venv/bin/python -m pytest backend/tests/test_attendance_sheet.py -q -k off_day`
Expected: `test_explicit_off_day_status` fails (returns `("no_show", 0)`), `test_off_day_record...` fails with IntegrityError.

- [ ] **Step 3.3: Implement**

`backend/app/models.py:9`:
```python
ATTENDANCE_STATUSES = ("on_time", "late", "late_15", "no_show", "absent", "off_day")
```

`backend/app/schemas.py:7` (update the comment too — the set is no longer the 5 sheet values verbatim):
```python
# The HR sheet's 5 Status values, plus off_day (Viper writes the literal "OFF DAY"
# into the sheet for scheduled days off — Sundays and declared offs).
AttendanceStatus = Literal["on_time", "late", "late_15", "no_show", "absent", "off_day"]
```

`backend/app/services.py` — in `calculate_attendance_status`, insert before the `absent` check:
```python
    if explicit_status == "off_day":
        return "off_day", 0
```

- [ ] **Step 3.4: Run tests**

Run: `.venv/bin/python -m pytest backend/tests -q`
Expected: all pass (new tests pass because `make_db` creates fresh tables from the updated metadata).

- [ ] **Step 3.5: Commit**

```bash
git add backend/app/models.py backend/app/schemas.py backend/app/services.py backend/tests/test_attendance_sheet.py
git commit -m "feat(attendance): add first-class off_day status (model, schema, classifier)"
```

### Task 4: One-shot SQLite migration for the CHECK constraint

The live `dashboard.db` was created with the 5-value CHECK; SQLite cannot ALTER it. Rebuild once at bootstrap.

**Files:**
- Modify: `backend/app/bootstrap.py`
- Test: `backend/tests/test_migration.py` (create)

- [ ] **Step 4.1: Write failing test** — create `backend/tests/test_migration.py`:

```python
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from backend.app.bootstrap import migrate_off_day

# The pre-off_day DDL as SQLAlchemy generated it (5-value CHECK).
OLD_DDL = """
CREATE TABLE attendance_records (
    id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    shift_date DATE NOT NULL,
    check_in_at DATETIME,
    check_out_at DATETIME,
    status VARCHAR(24) NOT NULL,
    minutes_late INTEGER NOT NULL,
    chase_state VARCHAR(24) NOT NULL,
    notes TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_attendance_person_shift UNIQUE (person_id, shift_date),
    CONSTRAINT ck_attendance_status CHECK (status in ('on_time', 'late', 'late_15', 'no_show', 'absent')),
    CONSTRAINT ck_chase_state CHECK (chase_state in ('none', 'needs_chase', 'chased', 'resolved'))
)
"""


def _old_engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    with engine.begin() as conn:
        conn.execute(text(OLD_DDL))
        conn.execute(text("CREATE INDEX ix_attendance_records_person_id ON attendance_records (person_id)"))
        conn.execute(text("CREATE INDEX ix_attendance_records_shift_date ON attendance_records (shift_date)"))
        conn.execute(
            text(
                "INSERT INTO attendance_records (person_id, shift_date, status, minutes_late,"
                " chase_state, notes, created_at, updated_at)"
                " VALUES (1, '2026-06-01', 'no_show', 0, 'chased', 'kept', '2026-06-01', '2026-06-01')"
            )
        )
    return engine


def test_migrate_off_day_rebuilds_old_table() -> None:
    engine = _old_engine()
    migrate_off_day(engine)
    with engine.begin() as conn:
        # old row survived, admin fields intact
        row = conn.execute(
            text("SELECT status, chase_state, notes FROM attendance_records")
        ).one()
        assert tuple(row) == ("no_show", "chased", "kept")
        # off_day rows are now accepted
        conn.execute(
            text(
                "INSERT INTO attendance_records (person_id, shift_date, status, minutes_late,"
                " chase_state, created_at, updated_at)"
                " VALUES (1, '2026-06-07', 'off_day', 0, 'none', '2026-06-07', '2026-06-07')"
            )
        )


def test_migrate_off_day_is_idempotent() -> None:
    engine = _old_engine()
    migrate_off_day(engine)
    migrate_off_day(engine)  # second run must no-op without error
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM attendance_records")).scalar()
    assert count == 1
```

- [ ] **Step 4.2: Run to verify failure**

Run: `.venv/bin/python -m pytest backend/tests/test_migration.py -q`
Expected: ImportError — `migrate_off_day` does not exist.

- [ ] **Step 4.3: Implement** — in `backend/app/bootstrap.py`, add imports and the function, and call it first in `init_db`:

```python
from sqlalchemy import select, text
from sqlalchemy.engine import Engine

from .db import Base, engine, utc_now
from .models import AttendancePolicy, AuditLog, ProjectTopic

SEEDED_TOPICS = ("3", "5639", "9", "5631", "3569")


def migrate_off_day(target: Engine) -> None:
    """SQLite can't ALTER a CHECK constraint. If attendance_records predates the
    off_day status, rebuild it once (rename → drop named indexes → recreate from
    metadata → copy rows → drop old). Idempotent: no-ops when the DDL already
    mentions off_day or the table doesn't exist yet."""
    with target.connect() as conn:
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='attendance_records'")
        ).scalar()
    if not ddl or "off_day" in ddl:
        return
    with target.begin() as conn:
        conn.execute(text("ALTER TABLE attendance_records RENAME TO attendance_records_old"))
        named_indexes = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND tbl_name='attendance_records_old' AND sql IS NOT NULL"
            )
        ).all()
        for (index_name,) in named_indexes:
            conn.execute(text(f'DROP INDEX "{index_name}"'))
    Base.metadata.tables["attendance_records"].create(target)
    with target.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO attendance_records (id, person_id, shift_date, check_in_at,"
                " check_out_at, status, minutes_late, chase_state, notes, created_at, updated_at)"
                " SELECT id, person_id, shift_date, check_in_at, check_out_at, status,"
                " minutes_late, chase_state, notes, created_at, updated_at"
                " FROM attendance_records_old"
            )
        )
        conn.execute(text("DROP TABLE attendance_records_old"))


def init_db() -> None:
    migrate_off_day(engine)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        seed_db(db)
        db.commit()
```

(Keep the existing `seed_db` unchanged; keep the existing `from sqlalchemy.orm import Session` import.)

- [ ] **Step 4.4: Run tests**

Run: `.venv/bin/python -m pytest backend/tests -q`
Expected: all pass.

- [ ] **Step 4.5: Commit**

```bash
git add backend/app/bootstrap.py backend/tests/test_migration.py
git commit -m "feat(db): one-shot rebuild of attendance_records CHECK to admit off_day"
```

### Task 5: Importer — recognize OFF DAY cells and overwrite stale records (the P0)

**Files:**
- Modify: `backend/app/attendance_sheet.py` (`_upsert_row`, new `_is_off_day`)
- Test: `backend/tests/test_attendance_sheet.py`

- [ ] **Step 5.1: Write failing tests** (append to `backend/tests/test_attendance_sheet.py`):

```python
def test_off_day_cell_creates_off_day_record() -> None:
    db = make_db()
    grid = [row[:] for row in GRID]
    grid.append(["2026-06-03", "OFF DAY", "", "", "", "", ""])  # Oliver declared off
    apply_attendance_rows(db, parse_attendance_grid(grid), TZ)
    db.commit()

    record = db.scalar(
        select(AttendanceRecord)
        .join(Person)
        .where(Person.slug == "oliver", AttendanceRecord.shift_date == date(2026, 6, 3))
    )
    assert record is not None
    assert record.status == "off_day"
    assert record.check_in_at is None and record.check_out_at is None
    assert record.minutes_late == 0


def test_off_day_overwrites_stale_no_show() -> None:
    """P0 regression: a no_show imported earlier must be replaced when the same
    (person, date) cell is later declared OFF DAY — not silently kept."""
    db = make_db()
    apply_attendance_rows(db, parse_attendance_grid(GRID), TZ)
    db.commit()
    # Sam 2026-06-01 imported as no_show (from GRID). Admin had chased it.
    record = db.scalar(
        select(AttendanceRecord)
        .join(Person)
        .where(Person.slug == "sam", AttendanceRecord.shift_date == date(2026, 6, 1))
    )
    assert record.status == "no_show"
    record.chase_state = "chased"
    db.commit()

    resync = [row[:] for row in GRID]
    resync[3] = ["2026-06-01", "18:00", "", "On time", "OFF DAY", "", ""]  # Sam's day declared OFF
    apply_attendance_rows(db, parse_attendance_grid(resync), TZ)
    db.commit()

    db.refresh(record)
    assert record.status == "off_day"
    assert record.check_in_at is None
    assert record.chase_state == "chased"  # admin-owned fields preserved
```

- [ ] **Step 5.2: Run to verify failure**

Run: `.venv/bin/python -m pytest backend/tests/test_attendance_sheet.py -q -k "off_day_cell or overwrites_stale"`
Expected: both FAIL — record is None / status stays `no_show`.

- [ ] **Step 5.3: Implement** — in `backend/app/attendance_sheet.py` add after `_normalize_status`:

```python
OFF_DAY_TEXT = "off day"


def _is_off_day(arrival: str, status_text: str) -> bool:
    """Viper marks scheduled days off by writing the literal 'OFF DAY' into the
    arrival cell (per-person) or status cell; either marks the day off."""
    return _normalize_status(arrival) == OFF_DAY_TEXT or _normalize_status(status_text) == OFF_DAY_TEXT
```

and replace the top half of `_upsert_row` (everything before the `record = db.scalar(...)` lookup) with:

```python
def _upsert_row(db: Session, row: SheetAttendanceRow, tz: ZoneInfo) -> bool:
    person = get_or_create_person(db, row.slug, row.display_name)
    if _is_off_day(row.arrival, row.status_text):
        check_in: datetime | None = None
        check_out: datetime | None = None
        status, minutes_late = "off_day", 0
    else:
        check_in = _combine(row.shift_date, row.arrival, tz)
        check_out = _combine(row.shift_date, row.out, tz)
        if check_in and check_out and check_out < check_in:
            check_out = check_out + timedelta(days=1)  # shift crosses midnight (out ~03:00)
        classified = classify_sheet_row(db, row.shift_date, check_in, row.status_text)
        if classified is None:
            return False
        status, minutes_late = classified
```

(The remainder of `_upsert_row` — the record lookup, field assignment, `db.flush()`, `return True` — stays exactly as is.)

- [ ] **Step 5.4: Run tests**

Run: `.venv/bin/python -m pytest backend/tests -q`
Expected: all pass.

- [ ] **Step 5.5: Commit**

```bash
git add backend/app/attendance_sheet.py backend/tests/test_attendance_sheet.py
git commit -m "fix(import): OFF DAY cells upsert off_day records, overwriting stale no_show/late (P0)"
```

### Task 6: Importer — whole-team Sunday OFF DAY row

**Files:**
- Modify: `backend/app/attendance_sheet.py` (`parse_attendance_grid`)
- Test: `backend/tests/test_attendance_sheet.py`

- [ ] **Step 6.1: Write failing test** (append):

```python
def test_whole_team_sunday_off_day_row() -> None:
    """Viper writes 'OFF DAY' into col B and clears the rest of the row for a
    team-wide Sunday off. Every person must get an off_day record."""
    db = make_db()
    grid = [row[:] for row in GRID]
    grid.append(["2026-06-07", "OFF DAY", "", "", "", "", ""])
    rows = parse_attendance_grid(grid)

    sunday_rows = [r for r in rows if r.shift_date == date(2026, 6, 7)]
    assert sorted(r.slug for r in sunday_rows) == ["oliver", "sam"]

    apply_attendance_rows(db, rows, TZ)
    db.commit()
    statuses = {
        db.get(Person, r.person_id).slug: r.status
        for r in db.scalars(select(AttendanceRecord).where(AttendanceRecord.shift_date == date(2026, 6, 7)))
    }
    assert statuses == {"oliver": "off_day", "sam": "off_day"}
```

Note: this overlaps `test_off_day_cell_creates_off_day_record`'s grid shape — there, only Oliver's cell says OFF DAY *and Sam's columns are blank*, which is indistinguishable from a team-wide row. Update that earlier test so Sam has data on that day (making it a genuine per-person OFF), i.e. change its appended row to:

```python
    grid.append(["2026-06-03", "OFF DAY", "", "", "18:00", "", "On time"])
```

- [ ] **Step 6.2: Run to verify failure**

Run: `.venv/bin/python -m pytest backend/tests/test_attendance_sheet.py -q -k sunday`
Expected: FAIL — only `["oliver"]` gets a row (col B reads as Oliver's arrival; Sam's blanks drop).

- [ ] **Step 6.3: Implement** — in `parse_attendance_grid`, inside the `for raw in values[...]` loop, right after `if day is None: continue`, insert:

```python
        # Team-wide OFF DAY: Viper writes 'OFF DAY' in the first person's arrival
        # column (col B) and clears the rest of the row.
        if blocks:
            first_col = blocks[0][0]
            first_cell = str(raw[first_col]).strip() if first_col < len(raw) else ""
            other_cols = [
                c
                for col, _, _ in blocks
                for c in (col, col + 1, col + 2)
                if c != first_col
            ]
            others_blank = all(
                not (str(raw[c]).strip() if c < len(raw) else "") for c in other_cols
            )
            if _normalize_status(first_cell) == OFF_DAY_TEXT and others_blank:
                for col, slug, name in blocks:
                    rows.append(SheetAttendanceRow(slug, name, day, "OFF DAY", "", ""))
                continue
```

- [ ] **Step 6.4: Run tests**

Run: `.venv/bin/python -m pytest backend/tests -q`
Expected: all pass (including the updated per-person test).

- [ ] **Step 6.5: Commit**

```bash
git add backend/app/attendance_sheet.py backend/tests/test_attendance_sheet.py
git commit -m "fix(import): recognize whole-team Sunday OFF DAY rows for every person"
```

### Task 7: Exclude `off_day` from performance analytics

**Files:**
- Modify: `backend/app/services.py` (`compute_performance_rows`)
- Test: `backend/tests/test_attendance_sheet.py` (self-contained; avoids touching the large perf helpers)

- [ ] **Step 7.1: Write failing test** (append):

```python
def test_off_day_excluded_from_performance_metrics() -> None:
    from backend.app.services import compute_performance_rows, get_or_create_person

    db = make_db()
    person = get_or_create_person(db, "oliver", "Oliver")
    db.add(
        AttendanceRecord(
            person_id=person.id, shift_date=date(2026, 6, 1), status="on_time", chase_state="none"
        )
    )
    db.add(
        AttendanceRecord(
            person_id=person.id, shift_date=date(2026, 6, 7), status="off_day", chase_state="none"
        )
    )
    db.commit()

    rows = compute_performance_rows(db, date(2026, 6, 1), date(2026, 6, 7))
    metrics = next(m for p, m in rows if p.slug == "oliver")
    assert metrics["punctuality_rate"] == 100.0  # off_day must not dilute the denominator
    assert metrics["attendance_days"] == 1       # off_day is not an attendance day
```

- [ ] **Step 7.2: Run to verify failure**

Run: `.venv/bin/python -m pytest backend/tests/test_attendance_sheet.py -q -k performance_metrics`
Expected: FAIL — punctuality 50.0, attendance_days 2.

- [ ] **Step 7.3: Implement** — in `compute_performance_rows`, immediately after the `recs = list(db.scalars(select(AttendanceRecord)...))` block, add:

```python
        recs = [r for r in recs if r.status != "off_day"]  # off days are out of every HOW metric
```

- [ ] **Step 7.4: Run tests**

Run: `.venv/bin/python -m pytest backend/tests -q`
Expected: all pass.

- [ ] **Step 7.5: Commit**

```bash
git add backend/app/services.py backend/tests/test_attendance_sheet.py
git commit -m "fix(performance): exclude off_day records from punctuality/penalty/hours metrics"
```

### Task 8: Frontend — `off_day` rendering, fail-safe StatusPill, severity colors

**Files:**
- Modify: `frontend/src/lib/types.ts:1` (Status union)
- Modify: `frontend/src/components/StatusPill.tsx`
- Modify: `frontend/src/styles/components.css:378-388` (pill colors)

- [ ] **Step 8.1: types.ts**

```ts
export type Status = "on_time" | "late" | "late_15" | "no_show" | "absent" | "off_day";
```

- [ ] **Step 8.2: StatusPill — label + fail-open fix**

In `frontend/src/components/StatusPill.tsx`: add `off_day: "Off",` to the `labels` record (after `absent`), and change the render line so an unknown status can never produce a blank pill again:

```tsx
      {labels[value] ?? value}
```

- [ ] **Step 8.3: CSS — fix the inverted severity ramp + off_day style**

In `frontend/src/styles/components.css`, replace the `.pill-absent` and `.pill-no_show` blocks (lines ~378–385) with:

```css
.pill-absent {
  color: var(--warning);
  background: color-mix(in srgb, var(--warning) 16%, transparent);
}
.pill-no_show {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 22%, transparent);
}
.pill-off_day {
  color: var(--label-tertiary);
  background: var(--fill-2);
}
```

(`no_show` is the worst outcome → strongest danger; `absent` is an acknowledged absence → warning; `off_day` is calm/neutral. `pill-missing` stays as is.)

- [ ] **Step 8.4: Verify with the TypeScript build**

Run: `cd frontend && npm run build`
Expected: builds clean — `Status` is referenced by `AttendanceCell`/`Attendance` types, so a missed spot fails compilation.

- [ ] **Step 8.5: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/components/StatusPill.tsx frontend/src/styles/components.css
git commit -m "feat(frontend): render off_day as calm 'Off' pill; fail-safe StatusPill; fix severity colors"
```

---

## WP3 — P1 hardening

### Task 9: Constant-time secret comparison

**Files:**
- Modify: `backend/app/auth.py:19-25,58-66`
- Test: `backend/tests/test_auth.py` (create)

- [ ] **Step 9.1: Write failing-ish test** (behavioral lock — create `backend/tests/test_auth.py`):

```python
import pytest
from fastapi import HTTPException

from backend.app.auth import require_viper, verify_password
from backend.app.config import Settings


def make_settings(**overrides) -> Settings:
    values = {
        "jwt_secret": "unit-test-jwt-secret-0123456789",
        "viper_token": "unit-test-viper-token-0123456789",
        "admin_password": "correct-horse-battery",
        "admin_password_hash": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_verify_password_plaintext_fallback() -> None:
    settings = make_settings()
    assert verify_password(settings, "correct-horse-battery") is True
    assert verify_password(settings, "wrong") is False
    assert verify_password(make_settings(admin_password=None), "anything") is False


def test_require_viper_accepts_and_rejects() -> None:
    settings = make_settings()
    assert require_viper("unit-test-viper-token-0123456789", None, settings) == "viper"
    with pytest.raises(HTTPException):
        require_viper("wrong-token", None, settings)
    with pytest.raises(HTTPException):
        require_viper(None, None, settings)
```

- [ ] **Step 9.2: Run** — `.venv/bin/python -m pytest backend/tests/test_auth.py -q` — expected: PASS already (this locks behavior before the swap).

- [ ] **Step 9.3: Implement** — in `backend/app/auth.py` add `import secrets` at the top, then:

Line 25 (plaintext fallback) becomes:
```python
    return bool(
        settings.admin_password
        and secrets.compare_digest(password.encode("utf-8"), settings.admin_password.encode("utf-8"))
    )
```

Line 64 (viper token) becomes:
```python
    if not token or not secrets.compare_digest(
        token.encode("utf-8"), settings.viper_token.encode("utf-8")
    ):
```

- [ ] **Step 9.4: Run tests** — `.venv/bin/python -m pytest backend/tests -q` — expected: all pass.

- [ ] **Step 9.5: Commit**

```bash
git add backend/app/auth.py backend/tests/test_auth.py
git commit -m "fix(security): constant-time comparison for viper token and plaintext admin fallback"
```

### Task 10: Reject placeholder secrets at startup

**Files:**
- Modify: `backend/app/config.py` (add validator fn)
- Modify: `backend/app/main.py` (call in lifespan)
- Test: `backend/tests/test_auth.py`

- [ ] **Step 10.1: Write failing test** (append to `backend/tests/test_auth.py`):

```python
def test_placeholder_secrets_rejected() -> None:
    from backend.app.config import validate_runtime_secrets

    with pytest.raises(RuntimeError, match="SIGMA_JWT_SECRET"):
        validate_runtime_secrets(make_settings(jwt_secret="change-me-in-env-1234"))
    with pytest.raises(RuntimeError, match="SIGMA_VIPER_TOKEN"):
        validate_runtime_secrets(make_settings(viper_token="change-me-viper-token"))
    validate_runtime_secrets(make_settings())  # real-looking secrets pass
```

- [ ] **Step 10.2: Run to verify failure** — ImportError on `validate_runtime_secrets`.

- [ ] **Step 10.3: Implement** — append to `backend/app/config.py`:

```python
PLACEHOLDER_PREFIX = "change-me"


def validate_runtime_secrets(settings: Settings) -> None:
    """Refuse to boot with the shipped placeholder secrets — a missing .env would
    otherwise run with predictable JWT/Viper secrets that pass min_length."""
    bad = [
        name
        for name, value in (
            ("SIGMA_JWT_SECRET", settings.jwt_secret),
            ("SIGMA_VIPER_TOKEN", settings.viper_token),
        )
        if value.startswith(PLACEHOLDER_PREFIX)
    ]
    if bad:
        raise RuntimeError(f"placeholder secrets in use — set {', '.join(bad)} in .env")
```

In `backend/app/main.py`, import it (`from .config import get_settings, validate_runtime_secrets` — adjust the existing import line) and make the first lines of `lifespan`:

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_runtime_secrets(get_settings())
    init_db()
```

(Plain `TestClient(app)` without a `with` block does not run lifespan, so existing tests are unaffected; the live `.env` has real secrets.)

- [ ] **Step 10.4: Run tests** — `.venv/bin/python -m pytest backend/tests -q` — all pass.

- [ ] **Step 10.5: Commit**

```bash
git add backend/app/config.py backend/app/main.py backend/tests/test_auth.py
git commit -m "fix(security): refuse startup with placeholder JWT/Viper secrets"
```

### Task 11: Grade enum (server) + client choices (cross-repo)

**Files:**
- Modify: `backend/app/schemas.py:182`
- Modify: `backend/tests/test_performance.py` (lowercase grades → canonical)
- Modify (other repo, not git): `/Users/aisigma/projects/SigmasDashboard/scripts/dashboard_client.py:102`

- [ ] **Step 11.1: Write failing test** (append to `backend/tests/test_api_contract.py`, which has `client_with_db`):

```python
def test_viper_evaluation_rejects_noncanonical_grade() -> None:
    client = client_with_db()
    payload = {
        "person": {"slug": "abdul", "display_name": "Abdul"},
        "period_start": "2026-06-02",
        "period_end": "2026-06-07",
        "grade": "good",  # lowercase drift — must be rejected
    }
    response = client.post("/api/v1/viper/evaluation", json=payload)
    assert response.status_code == 422
    response = client.post("/api/v1/viper/evaluation", json={**payload, "grade": "Good"})
    assert response.status_code == 200
```

- [ ] **Step 11.2: Run to verify failure** — lowercase currently returns 200.

- [ ] **Step 11.3: Implement** — `backend/app/schemas.py:182`:

```python
    grade: Literal["Over", "Good", "Average", "Under"]
```

(`EvaluationOut.grade` stays `str` so any legacy rows still serialize.)

- [ ] **Step 11.4: Fix the tests that enshrined the drift** — in `backend/tests/test_performance.py`, the evaluation payloads/assertions use lowercase `"good"`/`"over"` (≈ lines 514, 550, 559, 567). Change payload grades to `"Good"`/`"Over"` and the assertions to match:

```python
        assert first.json()["data"]["grade"] == "Good"
        assert second.json()["data"]["grade"] == "Over"
        assert abdul_rows[0]["grade"] == "Over"
```

(Locate every lowercase grade with: `grep -n '"good"\|"over"\|"average"\|"under"' backend/tests/test_performance.py` and canonicalize all of them.)

- [ ] **Step 11.5: Client choices** — in `/Users/aisigma/projects/SigmasDashboard/scripts/dashboard_client.py` line 102, change:

```python
    pe.add_argument("--grade", required=True)
```
to
```python
    pe.add_argument("--grade", required=True, choices=["Over", "Good", "Average", "Under"])
```

- [ ] **Step 11.6: Run tests** — `.venv/bin/python -m pytest backend/tests -q` — all pass. Also sanity-check the client parses: `python3 /Users/aisigma/projects/SigmasDashboard/scripts/dashboard_client.py --help` exits 0.

- [ ] **Step 11.7: Commit** (sigma-dashboard only; the client repo is not git-tracked)

```bash
git add backend/app/schemas.py backend/tests/test_performance.py backend/tests/test_api_contract.py
git commit -m "fix(contract): grade is a closed enum (Over/Good/Average/Under); canonicalize test grades"
```

### Task 12: Server-side person allowlist for Viper writes

**Files:**
- Modify: `backend/app/services.py` (new error + `require_known_person`; swap into the 4 Viper upserts + goal owner)
- Modify: `backend/app/routes.py` (catch → 422 in the 5 viper endpoints)
- Modify: `backend/tests/test_api_contract.py` (existing tests post unknown slug "abdul")
- Test: `backend/tests/test_api_contract.py`

- [ ] **Step 12.1: Write failing test** (append to `backend/tests/test_api_contract.py`):

```python
def test_viper_rejects_unknown_person_slug() -> None:
    client = client_with_db()
    response = client.post(
        "/api/v1/viper/report",
        json={
            "person": {"slug": "olivr", "display_name": "Olivr"},  # typo slug
            "report_date": "2026-06-03",
            "summary": "did things",
        },
    )
    assert response.status_code == 422
    assert "olivr" in response.json()["error"]["message"]


def test_viper_goal_rejects_unknown_owner() -> None:
    client = client_with_db()
    response = client.post(
        "/api/v1/viper/goal",
        json={"slug": "hw-notion", "title": "Notion integration", "owner_slug": "olivr"},
    )
    assert response.status_code == 422
```

- [ ] **Step 12.2: Existing tests use slug "abdul" with no roster entry** — they will start failing once the allowlist lands. In `client_with_db()` in `backend/tests/test_api_contract.py`, seed the test roster right after `seed_db(session)`:

```python
    from backend.app.models import Person

    session.add(Person(slug="abdul", display_name="Abdul", active=True, sort_order=1))
    session.commit()
```

(Adjust the existing `seed_db(session); session.commit()` block to include this. Check the whole file for other slugs posted to `/viper/*` and seed them the same way. `backend/tests/test_performance.py` already creates its people directly — verify with `grep -n "viper/" backend/tests/test_performance.py` that every slug it posts is created first.)

- [ ] **Step 12.3: Run to verify failure** — new tests FAIL (unknown slugs are auto-created today).

- [ ] **Step 12.4: Implement** — in `backend/app/services.py`, after `get_or_create_person`, add:

```python
class UnknownPersonError(ValueError):
    """A Viper write referenced a person slug that is not in the roster."""


def require_known_person(db: Session, slug: str, display_name: str = "") -> Person:
    """Viper writes must reference an existing roster member — a typo'd slug must
    422, not silently spawn a phantom person. (The sheet importer keeps
    get_or_create_person: the sheet's name row is the roster source of truth.)"""
    person = db.scalar(select(Person).where(Person.slug == slug))
    if person is None:
        raise UnknownPersonError(f"unknown person slug: '{slug}'")
    if display_name and person.display_name != display_name:
        person.display_name = display_name
    return person
```

Swap the first line in each of `upsert_attendance`, `upsert_report`, `upsert_evaluation`, `create_feedback` from `get_or_create_person(...)` to:

```python
    person = require_known_person(db, payload.person.slug, payload.person.display_name)
```

And in `upsert_goal`, replace the owner lookup (lines ~139-142) with:

```python
    owner_id = None
    if payload.owner_slug:
        owner_id = require_known_person(db, payload.owner_slug).id
```

- [ ] **Step 12.5: Routes catch → 422** — in `backend/app/routes.py`, import the error (`from .services import ...` — add `UnknownPersonError` to the existing services import list), then wrap the service call in each of the five viper endpoints (`viper_attendance`, `viper_report`, `viper_goal`, `viper_evaluation`, `viper_feedback`) in the same pattern; e.g. `viper_report` becomes:

```python
    try:
        report = upsert_report(db, payload)
    except UnknownPersonError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    db.refresh(report)
    return ok({"id": report.id})
```

(Apply the identical try/except to the other four, preserving each endpoint's existing commit/refresh/return lines.)

- [ ] **Step 12.6: Run tests** — `.venv/bin/python -m pytest backend/tests -q` — all pass.

- [ ] **Step 12.7: Commit**

```bash
git add backend/app/services.py backend/app/routes.py backend/tests/test_api_contract.py
git commit -m "fix(contract): server-side person allowlist for Viper writes; unknown slug/owner -> 422"
```

### Task 13: Sanitize Google-Sheet endpoint error details

**Files:**
- Modify: `backend/app/routes.py:806,827` (and the equivalent in `/attendance/import-sheet` if it echoes `str(exc)` — check with `grep -n "str(exc)" backend/app/routes.py`)

- [ ] **Step 13.1: Implement directly** (low-risk message change; existing GoogleSheetError tests assert status codes, not message text — confirm with `grep -rn "GoogleSheetError\|google-sheet" backend/tests/`):

Add near the top of `backend/app/routes.py` (after the imports):

```python
import logging

logger = logging.getLogger("sigma.routes")
```

Then replace each sheet-endpoint `detail=str(exc)` (lines ~806 and ~827) with the logged generic form:

```python
    except GoogleSheetError as exc:
        logger.warning("google sheet operation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Sheet operation failed — see server logs",
        ) from exc
```

(The 409 at line ~599 keeps `str(exc)` — that ValueError is an app-authored duplicate-topic message, not an internal leak. `SheetSyncRun.error_message` stays detailed by design — admin-only ops trail.)

- [ ] **Step 13.2: Run tests** — `.venv/bin/python -m pytest backend/tests -q` — all pass (fix any test that asserted the old message text).

- [ ] **Step 13.3: Commit**

```bash
git add backend/app/routes.py
git commit -m "fix(security): log sheet errors server-side, return generic client message"
```

### Task 14: Minimal login rate limit (no new dependency)

**Files:**
- Create: `backend/app/ratelimit.py`
- Modify: `backend/app/routes.py` (login endpoint)
- Test: `backend/tests/test_auth.py`

- [ ] **Step 14.1: Write failing test** (append to `backend/tests/test_auth.py`):

```python
def test_login_rate_limited_after_five_attempts() -> None:
    from fastapi.testclient import TestClient

    from backend.app import ratelimit
    from backend.app.config import get_settings
    from backend.app.main import app

    app.dependency_overrides[get_settings] = lambda: make_settings()
    ratelimit.reset()
    try:
        client = TestClient(app)
        for _ in range(5):
            response = client.post(
                "/api/v1/auth/login", json={"username": "admin", "password": "wrong"}
            )
            assert response.status_code == 401
        response = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "wrong"}
        )
        assert response.status_code == 429
    finally:
        app.dependency_overrides.pop(get_settings, None)
        ratelimit.reset()
```

- [ ] **Step 14.2: Run to verify failure** — ImportError on `backend.app.ratelimit`.

- [ ] **Step 14.3: Implement** — create `backend/app/ratelimit.py`:

```python
"""Tiny in-process sliding-window rate limiter for the login endpoint.

One uvicorn process (launchd) → in-memory state is sufficient; revisit only if
the app ever runs multi-process (see WISHLIST: slowapi).
"""

import time
from collections import defaultdict, deque
from threading import Lock

WINDOW_SECONDS = 60.0
MAX_ATTEMPTS = 5

_attempts: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def allow(key: str) -> bool:
    """Record an attempt for `key`; False when the window budget is exhausted."""
    now = time.monotonic()
    with _lock:
        window = _attempts[key]
        while window and now - window[0] > WINDOW_SECONDS:
            window.popleft()
        if len(window) >= MAX_ATTEMPTS:
            return False
        window.append(now)
        return True


def reset() -> None:
    with _lock:
        _attempts.clear()
```

In `backend/app/routes.py`: add `Request` to the fastapi import (`from fastapi import APIRouter, Depends, HTTPException, Query, Request, status`), add `from . import ratelimit` to the local imports, and give `login` a request parameter + gate as its first lines:

```python
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Envelope:
    """Exchange an admin username + password for a bearer JWT.

    Returns `data.access_token` (send it as `Authorization: Bearer <token>`) and `data.expires_at`.
    """
    client_key = request.client.host if request.client else "unknown"
    if not ratelimit.allow(client_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts — try again in a minute",
        )
```

(The rest of `login` is unchanged.)

- [ ] **Step 14.4: Run tests** — `.venv/bin/python -m pytest backend/tests -q` — all pass.

- [ ] **Step 14.5: Commit**

```bash
git add backend/app/ratelimit.py backend/app/routes.py backend/tests/test_auth.py
git commit -m "feat(security): rate-limit /auth/login (5 attempts per minute per client)"
```

---

### Task 15: Final verification, live restart, wishlist promotions

- [ ] **Step 15.1: Full suite + frontend build**

```bash
cd /Users/aisigma/sigma-dashboard
.venv/bin/python -m pytest backend/tests -q
cd frontend && npm run build && cd ..
```
Expected: all green, build clean.

- [ ] **Step 15.2: Restart the live service on the new code and verify**

```bash
launchctl kickstart -k gui/$(id -u)/com.sigma.dashboard
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8001/      # 200
sqlite3 dashboard.db "SELECT sql FROM sqlite_master WHERE name='attendance_records';" | grep -c off_day  # 1 (migration ran)
sqlite3 dashboard.db "SELECT COUNT(*) FROM attendance_records;"       # unchanged row count (35 on 2026-06-12)
```

- [ ] **Step 15.3: Mark promoted wishlist items** — in `WISHLIST.md`, strike through each item implemented here and append `→ **fixed in <commit-area>** (2026-06-12)`; leave the deferred ones (Alembic, localStorage JWT, openapi.d.ts, composite render, goal-log idempotency, text caps, auth test gaps, client docstring) untouched.

- [ ] **Step 15.4: Commit**

```bash
git add WISHLIST.md
git commit -m "docs: mark 2026-06-12 review items fixed; keep deferred items parked"
```
