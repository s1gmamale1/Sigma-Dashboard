"""
Tests for the Performance tab: the composite-grade engine (services.compute_performance_rows)
and the new endpoints (GET /performance, /evaluations, /feedback; POST /viper/evaluation,
/viper/feedback).

Two layers:
  * Direct service tests build attendance/report/feedback rows in an in-memory DB and assert the
    output-anchored bands, the attendance penalty, the compensation cancel, the feedback ±1
    override + clamp, completion% over Mon–Sat work-days, and avg check-in/out + avg hours.
  * Route tests mint a real admin JWT (create_access_token) and send Viper writes with the real
    X-Viper-Token so require_admin / require_viper are exercised, plus the 401-without-token
    contract on every new endpoint.

Follows the conventions of test_attendance_policy.py (in-memory sqlite, Base.metadata.create_all,
seed_db) and test_projects.py (TestClient + StaticPool + dependency_overrides for get_db only).
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import create_access_token, require_admin, require_viper
from backend.app.bootstrap import seed_db
from backend.app.config import get_settings
from backend.app.db import Base, get_db
from backend.app.main import app
from backend.app.models import AttendanceRecord, Feedback, Person, Report
from backend.app.services import compute_performance_rows

TZ = ZoneInfo("Asia/Tashkent")


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------

def make_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_db(session)
    session.commit()
    return session


def add_person(db: Session, slug: str, name: str | None = None, sort: int = 1) -> Person:
    existing = db.scalar(select(Person).where(Person.slug == slug))
    if existing is not None:
        return existing
    person = Person(slug=slug, display_name=name or slug.title(), active=True, sort_order=sort)
    db.add(person)
    db.flush()
    return person


def add_report(
    db: Session,
    person: Person,
    day: date,
    rating: int | None = None,
    missing: bool = False,
    summary: str = "work",
) -> Report:
    report = Report(
        person_id=person.id,
        report_date=day,
        summary=summary,
        rating=rating,
        missing=missing,
    )
    db.add(report)
    db.flush()
    return report


def add_attendance(
    db: Session,
    person: Person,
    day: date,
    status: str,
    check_in: datetime | None = None,
    check_out: datetime | None = None,
    minutes_late: int = 0,
) -> AttendanceRecord:
    record = AttendanceRecord(
        person_id=person.id,
        shift_date=day,
        status=status,
        check_in_at=check_in,
        check_out_at=check_out,
        minutes_late=minutes_late,
    )
    db.add(record)
    db.flush()
    return record


def metrics_for(db: Session, person: Person, start: date, end: date) -> dict:
    """Pull the single person's metrics dict out of compute_performance_rows."""
    for row_person, metrics in compute_performance_rows(db, start, end):
        if row_person.id == person.id:
            return metrics
    raise AssertionError(f"person {person.slug} not present in performance rows")


# A full Mon–Sat work-week: 2026-06-01 (Mon) .. 2026-06-06 (Sat) -> 6 work-days.
WEEK_START = date(2026, 6, 1)
WEEK_END = date(2026, 6, 6)


# ---------------------------------------------------------------------------
# Output bands (WHAT-anchored composite grade)
# ---------------------------------------------------------------------------

class TestOutputBands:
    def _grade_for_avg_ratings(self, ratings: list[int]) -> str:
        db = make_db()
        person = add_person(db, "bander")
        for offset, rating in enumerate(ratings):
            add_report(db, person, date(2026, 6, 1 + offset), rating=rating)
        db.commit()
        return metrics_for(db, person, WEEK_START, WEEK_END)["composite_grade"]

    def test_avg_at_or_above_85_is_over(self):
        # mean(100, 90, 80) = 90 >= 85
        assert self._grade_for_avg_ratings([100, 90, 80]) == "Over"

    def test_avg_at_or_above_70_is_good(self):
        # mean(80, 75, 70) = 75 -> Good
        assert self._grade_for_avg_ratings([80, 75, 70]) == "Good"

    def test_avg_at_or_above_50_is_average(self):
        # mean(60, 55, 50) = 55 -> Average
        assert self._grade_for_avg_ratings([60, 55, 50]) == "Average"

    def test_avg_below_50_is_under(self):
        # mean(40, 30, 20) = 30 -> Under
        assert self._grade_for_avg_ratings([40, 30, 20]) == "Under"

    def test_band_boundary_85_is_over(self):
        # exactly 85 -> Over
        assert self._grade_for_avg_ratings([90, 80]) == "Over"

    def test_band_boundary_70_is_good(self):
        # exactly 70 -> Good
        assert self._grade_for_avg_ratings([75, 65]) == "Good"

    def test_no_reports_avg_none_is_under(self):
        db = make_db()
        person = add_person(db, "silent")
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        assert metrics["average_rating"] is None
        assert metrics["composite_grade"] == "Under"
        assert metrics["composite_score"] == 0


# ---------------------------------------------------------------------------
# Attendance penalty
# ---------------------------------------------------------------------------

class TestAttendancePenalty:
    def test_no_show_drops_two_bands_over_to_average(self):
        db = make_db()
        person = add_person(db, "noshow")
        # Over output (avg 100) ...
        for offset in range(3):
            add_report(db, person, date(2026, 6, 1 + offset), rating=100)
        # ... but a single no_show drops two bands: Over(3) - 2 = Average(1).
        add_attendance(db, person, date(2026, 6, 2), "no_show")
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        assert metrics["no_show_count"] == 1
        assert metrics["composite_grade"] == "Average"

    def test_two_lates_not_compensating_drops_one_band(self):
        db = make_db()
        person = add_person(db, "chronic")
        for offset in range(3):
            add_report(db, person, date(2026, 6, 1 + offset), rating=100)  # Over output
        # Two late arrivals, no overtime check-outs -> not compensating -> -1 band.
        add_attendance(
            db, person, date(2026, 6, 1), "late",
            check_in=datetime(2026, 6, 1, 18, 20, tzinfo=TZ), minutes_late=20,
        )
        add_attendance(
            db, person, date(2026, 6, 2), "late",
            check_in=datetime(2026, 6, 2, 18, 25, tzinfo=TZ), minutes_late=25,
        )
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        assert metrics["late_count"] == 2
        assert metrics["compensates"] is False
        # Over(3) - 1 = Good
        assert metrics["composite_grade"] == "Good"

    def test_single_late_does_not_penalize(self):
        db = make_db()
        person = add_person(db, "onelate")
        for offset in range(3):
            add_report(db, person, date(2026, 6, 1 + offset), rating=100)
        add_attendance(
            db, person, date(2026, 6, 1), "late",
            check_in=datetime(2026, 6, 1, 18, 20, tzinfo=TZ), minutes_late=20,
        )
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        # Only one late -> threshold (>=2) not met -> no penalty -> stays Over.
        assert metrics["composite_grade"] == "Over"


# ---------------------------------------------------------------------------
# Compensation cancels the chronic-late penalty
# ---------------------------------------------------------------------------

class TestCompensation:
    def test_late_but_overtime_compensates_cancels_penalty(self):
        db = make_db()
        person = add_person(db, "grinder")
        for offset in range(3):
            add_report(db, person, date(2026, 6, 1 + offset), rating=100)  # Over output
        # Two late check-ins (avg late ~22 min) but check-outs past 03:00 with big overtime
        # (avg OT ~75 min) -> compensates True -> chronic-late penalty cancelled.
        add_attendance(
            db, person, date(2026, 6, 1), "late",
            check_in=datetime(2026, 6, 1, 18, 20, tzinfo=TZ),
            check_out=datetime(2026, 6, 2, 4, 0, tzinfo=TZ),   # 04:00 -> 60 min OT
            minutes_late=20,
        )
        add_attendance(
            db, person, date(2026, 6, 2), "late",
            check_in=datetime(2026, 6, 2, 18, 25, tzinfo=TZ),
            check_out=datetime(2026, 6, 3, 4, 30, tzinfo=TZ),  # 04:30 -> 90 min OT
            minutes_late=25,
        )
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        assert metrics["compensates"] is True
        # Penalty cancelled -> stays Over.
        assert metrics["composite_grade"] == "Over"

    def test_overtime_below_late_does_not_compensate(self):
        db = make_db()
        person = add_person(db, "halfgrind")
        for offset in range(3):
            add_report(db, person, date(2026, 6, 1 + offset), rating=100)
        # avg late ~22 min but only ~10 min avg overtime -> ot < late -> not compensating.
        add_attendance(
            db, person, date(2026, 6, 1), "late",
            check_in=datetime(2026, 6, 1, 18, 20, tzinfo=TZ),
            check_out=datetime(2026, 6, 2, 3, 10, tzinfo=TZ),  # 03:10 -> 10 min OT
            minutes_late=20,
        )
        add_attendance(
            db, person, date(2026, 6, 2), "late",
            check_in=datetime(2026, 6, 2, 18, 25, tzinfo=TZ),
            check_out=datetime(2026, 6, 3, 3, 10, tzinfo=TZ),  # 03:10 -> 10 min OT
            minutes_late=25,
        )
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        assert metrics["compensates"] is False
        # Over(3) - 1 = Good (penalty applies)
        assert metrics["composite_grade"] == "Good"


# ---------------------------------------------------------------------------
# Feedback ±1 override + clamp
# ---------------------------------------------------------------------------

class TestFeedbackOverride:
    def test_latest_feedback_minus_one_shifts_band_down(self):
        db = make_db()
        person = add_person(db, "fb-down")
        for offset in range(3):
            add_report(db, person, date(2026, 6, 1 + offset), rating=100)  # Over output, clean attendance
        db.add(
            Feedback(person_id=person.id, feedback_date=date(2026, 6, 3), note="slipping", grade_adjustment=-1)
        )
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        # Over(3) - 1 = Good
        assert metrics["composite_grade"] == "Good"

    def test_latest_feedback_plus_one_shifts_band_up(self):
        db = make_db()
        person = add_person(db, "fb-up")
        # Good output (avg 75)
        for offset, rating in enumerate([80, 75, 70]):
            add_report(db, person, date(2026, 6, 1 + offset), rating=rating)
        db.add(
            Feedback(person_id=person.id, feedback_date=date(2026, 6, 3), note="great hustle", grade_adjustment=1)
        )
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        # Good(2) + 1 = Over(3)
        assert metrics["composite_grade"] == "Over"

    def test_only_latest_feedback_in_window_applies(self):
        db = make_db()
        person = add_person(db, "fb-latest")
        for offset in range(3):
            add_report(db, person, date(2026, 6, 1 + offset), rating=100)  # Over output
        # Older -1, newer +1; newest (by date then id) wins -> +1, clamped at Over.
        db.add(Feedback(person_id=person.id, feedback_date=date(2026, 6, 2), note="early", grade_adjustment=-1))
        db.add(Feedback(person_id=person.id, feedback_date=date(2026, 6, 4), note="recovered", grade_adjustment=1))
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        # +1 on Over clamps to Over (not a downgrade from the -1).
        assert metrics["composite_grade"] == "Over"

    def test_plus_one_clamps_at_over(self):
        db = make_db()
        person = add_person(db, "fb-clamp-hi")
        for offset in range(3):
            add_report(db, person, date(2026, 6, 1 + offset), rating=100)  # already Over(3)
        db.add(Feedback(person_id=person.id, feedback_date=date(2026, 6, 3), note="stellar", grade_adjustment=1))
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        assert metrics["composite_grade"] == "Over"
        assert metrics["composite_score"] == 100

    def test_minus_one_clamps_at_under(self):
        db = make_db()
        person = add_person(db, "fb-clamp-lo")
        for offset in range(3):
            add_report(db, person, date(2026, 6, 1 + offset), rating=25)  # already Under(0)
        db.add(Feedback(person_id=person.id, feedback_date=date(2026, 6, 3), note="worse", grade_adjustment=-1))
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        assert metrics["composite_grade"] == "Under"
        assert metrics["composite_score"] == 0

    def test_feedback_outside_window_is_ignored(self):
        db = make_db()
        person = add_person(db, "fb-out")
        for offset in range(3):
            add_report(db, person, date(2026, 6, 1 + offset), rating=100)  # Over output
        # Feedback dated after the window -> not applied.
        db.add(Feedback(person_id=person.id, feedback_date=date(2026, 6, 20), note="later", grade_adjustment=-1))
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        assert metrics["composite_grade"] == "Over"


# ---------------------------------------------------------------------------
# Completion % over Mon–Sat work-days
# ---------------------------------------------------------------------------

class TestCompletionRate:
    def test_full_week_all_reports_is_100(self):
        db = make_db()
        person = add_person(db, "complete")
        # 6 non-missing reports across the Mon–Sat window -> 6/6 = 100%.
        for offset in range(6):
            add_report(db, person, date(2026, 6, 1 + offset), rating=75)
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        assert metrics["report_completion_rate"] == 100.0

    def test_half_of_workdays_reported_is_fifty(self):
        db = make_db()
        person = add_person(db, "halfdone")
        # 3 non-missing reports / 6 work-days -> 50%.
        for offset in range(3):
            add_report(db, person, date(2026, 6, 1 + offset), rating=75)
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        assert metrics["report_completion_rate"] == 50.0

    def test_missing_reports_do_not_count_toward_completion(self):
        db = make_db()
        person = add_person(db, "missy")
        add_report(db, person, date(2026, 6, 1), rating=75)            # counts
        add_report(db, person, date(2026, 6, 2), missing=True)        # excluded
        add_report(db, person, date(2026, 6, 3), missing=True)        # excluded
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        # 1 non-missing / 6 work-days = 16.7%
        assert metrics["report_completion_rate"] == round(1 / 6 * 100, 1)
        assert metrics["missing_days"] == 2

    def test_sunday_excluded_from_workday_denominator(self):
        db = make_db()
        person = add_person(db, "sunday")
        # Window Mon 6/1 .. Sun 6/7 spans 7 calendar days but only 6 Mon–Sat work-days.
        for offset in range(6):
            add_report(db, person, date(2026, 6, 1 + offset), rating=75)
        db.commit()
        metrics = metrics_for(db, person, date(2026, 6, 1), date(2026, 6, 7))
        # 6 reports / 6 work-days (Sunday not counted) = 100%.
        assert metrics["report_completion_rate"] == 100.0


# ---------------------------------------------------------------------------
# avg check-in / check-out ("HH:MM") and avg hours
# ---------------------------------------------------------------------------

class TestAttendanceTimes:
    def test_avg_check_in_and_out_are_hh_mm(self):
        db = make_db()
        person = add_person(db, "timer")
        add_report(db, person, date(2026, 6, 1), rating=75)
        # Two days: 18:00 -> next-day 03:00, and 18:30 -> next-day 03:30.
        add_attendance(
            db, person, date(2026, 6, 1), "on_time",
            check_in=datetime(2026, 6, 1, 18, 0, tzinfo=TZ),
            check_out=datetime(2026, 6, 2, 3, 0, tzinfo=TZ),
        )
        add_attendance(
            db, person, date(2026, 6, 2), "on_time",
            check_in=datetime(2026, 6, 2, 18, 30, tzinfo=TZ),
            check_out=datetime(2026, 6, 3, 3, 30, tzinfo=TZ),
        )
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        # avg check-in = mean(18:00, 18:30) = 18:15; avg check-out = mean(03:00, 03:30) = 03:15.
        assert metrics["avg_check_in"] == "18:15"
        assert metrics["avg_check_out"] == "03:15"

    def test_avg_hours_about_nine_for_evening_to_3am_pair(self):
        db = make_db()
        person = add_person(db, "niner")
        add_report(db, person, date(2026, 6, 1), rating=75)
        # 18:00 -> next-day 03:20 == 9h20m -> ~9.3h; 18:00 -> 03:00 == 9h.
        add_attendance(
            db, person, date(2026, 6, 1), "on_time",
            check_in=datetime(2026, 6, 1, 18, 0, tzinfo=TZ),
            check_out=datetime(2026, 6, 2, 3, 20, tzinfo=TZ),
        )
        add_attendance(
            db, person, date(2026, 6, 2), "on_time",
            check_in=datetime(2026, 6, 2, 18, 0, tzinfo=TZ),
            check_out=datetime(2026, 6, 3, 3, 0, tzinfo=TZ),
        )
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        # mean(9.33, 9.0) = 9.17 -> rounds to 9.2; sanity-check it's ~9h.
        assert metrics["avg_hours"] is not None
        assert 9.0 <= metrics["avg_hours"] <= 9.5

    def test_no_timestamps_yields_none(self):
        db = make_db()
        person = add_person(db, "absentee")
        add_attendance(db, person, date(2026, 6, 1), "no_show")
        db.commit()
        metrics = metrics_for(db, person, WEEK_START, WEEK_END)
        assert metrics["avg_check_in"] is None
        assert metrics["avg_check_out"] is None
        assert metrics["avg_hours"] is None


# ---------------------------------------------------------------------------
# Leaderboard sort (best -> worst)
# ---------------------------------------------------------------------------

class TestLeaderboardSort:
    def test_rows_sorted_best_to_worst_by_composite_score(self):
        db = make_db()
        strong = add_person(db, "strong", sort=1)
        weak = add_person(db, "weak", sort=2)
        for offset in range(3):
            add_report(db, strong, date(2026, 6, 1 + offset), rating=100)  # Over
            add_report(db, weak, date(2026, 6, 1 + offset), rating=25)    # Under
        db.commit()
        rows = compute_performance_rows(db, WEEK_START, WEEK_END)
        ordered = [p.slug for p, _ in rows if p.slug in {"strong", "weak"}]
        assert ordered == ["strong", "weak"]


# ===========================================================================
# Route-level tests (real admin JWT + real X-Viper-Token)
# ===========================================================================

def _make_client() -> tuple[TestClient, Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_db(session)
    add_person(session, "abdul", "Abdul")
    session.commit()

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(require_viper, None)
    return TestClient(app), session


def _auth() -> dict[str, str]:
    settings = get_settings()
    token = create_access_token(settings, settings.admin_username)[0]
    return {"Authorization": f"Bearer {token}"}


def _viper() -> dict[str, str]:
    return {"X-Viper-Token": get_settings().viper_token}


def _eval_payload(period_start: str, period_end: str, grade: str, why: str) -> dict:
    return {
        "person": {"slug": "abdul", "display_name": "Abdul"},
        "period_start": period_start,
        "period_end": period_end,
        "grade": grade,
        "what": "shipped the dashboard",
        "how": "steady hours",
        "why": why,
    }


class TestPerformanceEndpoint:
    def test_get_performance_returns_rows(self):
        client, session = _make_client()
        person = add_person(session, "abdul", "Abdul")
        add_report(session, person, date(2026, 6, 1), rating=100)
        add_report(session, person, date(2026, 6, 2), rating=100)
        session.commit()

        resp = client.get("/api/v1/performance?from=2026-06-01&to=2026-06-06", headers=_auth())
        assert resp.status_code == 200
        rows = resp.json()["data"]
        row = next(r for r in rows if r["person"]["slug"] == "abdul")
        assert row["composite_grade"] == "Over"
        assert row["average_rating"] == 100.0
        assert row["avg_check_in"] is None  # no attendance rows
        assert isinstance(row["rating_trend"], list)
        assert row["rating_trend"][0]["date"] == "2026-06-01"


class TestEvaluationUpsert:
    def test_second_post_same_period_overwrites_single_row(self):
        client, session = _make_client()

        first = client.post(
            "/api/v1/viper/evaluation",
            headers=_viper(),
            json=_eval_payload("2026-06-01", "2026-06-06", "Good", "solid week"),
        )
        assert first.status_code == 200
        assert first.json()["data"]["grade"] == "Good"

        # Same (person, period) -> upsert overwrites grade/why, not a new row.
        second = client.post(
            "/api/v1/viper/evaluation",
            headers=_viper(),
            json=_eval_payload("2026-06-01", "2026-06-06", "Over", "even better"),
        )
        assert second.status_code == 200
        assert second.json()["data"]["grade"] == "Over"
        assert second.json()["data"]["id"] == first.json()["data"]["id"]

        # GET evaluations in the window returns exactly one row for this person.
        listing = client.get("/api/v1/evaluations?from=2026-06-01&to=2026-06-06", headers=_auth())
        assert listing.status_code == 200
        abdul_rows = [e for e in listing.json()["data"] if e["person"]["slug"] == "abdul"]
        assert len(abdul_rows) == 1
        assert abdul_rows[0]["grade"] == "Over"
        assert abdul_rows[0]["why"] == "even better"

    def test_different_period_creates_second_row(self):
        client, session = _make_client()
        client.post(
            "/api/v1/viper/evaluation",
            headers=_viper(),
            json=_eval_payload("2026-06-01", "2026-06-06", "Good", "week one"),
        )
        client.post(
            "/api/v1/viper/evaluation",
            headers=_viper(),
            json=_eval_payload("2026-06-08", "2026-06-13", "Over", "week two"),
        )
        listing = client.get("/api/v1/evaluations?from=2026-06-01&to=2026-06-13", headers=_auth())
        abdul_rows = [e for e in listing.json()["data"] if e["person"]["slug"] == "abdul"]
        assert len(abdul_rows) == 2
        # Newest period first.
        assert abdul_rows[0]["period_start"] == "2026-06-08"


class TestFeedbackEndpoint:
    def test_post_feedback_inserts_and_get_returns_in_window(self):
        client, session = _make_client()
        resp = client.post(
            "/api/v1/viper/feedback",
            headers=_viper(),
            json={
                "person": {"slug": "abdul", "display_name": "Abdul"},
                "feedback_date": "2026-06-03",
                "note": "great hustle this week",
                "source": "abdul",
                "grade_adjustment": 1,
            },
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["note"] == "great hustle this week"
        assert body["grade_adjustment"] == 1
        assert body["created_at"]  # naive-UTC string, present

        listing = client.get("/api/v1/feedback?from=2026-06-01&to=2026-06-06", headers=_auth())
        assert listing.status_code == 200
        notes = [f["note"] for f in listing.json()["data"] if f["person"]["slug"] == "abdul"]
        assert "great hustle this week" in notes

    def test_feedback_outside_window_not_returned(self):
        client, session = _make_client()
        client.post(
            "/api/v1/viper/feedback",
            headers=_viper(),
            json={
                "person": {"slug": "abdul", "display_name": "Abdul"},
                "feedback_date": "2026-07-01",
                "note": "out of window",
            },
        )
        listing = client.get("/api/v1/feedback?from=2026-06-01&to=2026-06-06", headers=_auth())
        assert all(f["note"] != "out of window" for f in listing.json()["data"])


# ---------------------------------------------------------------------------
# 401 without the right token on every new endpoint
# ---------------------------------------------------------------------------

class TestUnauthenticated:
    def test_get_performance_without_token_returns_401(self):
        client, _ = _make_client()
        resp = client.get("/api/v1/performance?from=2026-06-01&to=2026-06-06")
        assert resp.status_code == 401

    def test_get_evaluations_without_token_returns_401(self):
        client, _ = _make_client()
        resp = client.get("/api/v1/evaluations?from=2026-06-01&to=2026-06-06")
        assert resp.status_code == 401

    def test_get_feedback_without_token_returns_401(self):
        client, _ = _make_client()
        resp = client.get("/api/v1/feedback?from=2026-06-01&to=2026-06-06")
        assert resp.status_code == 401

    def test_post_viper_evaluation_without_token_returns_401(self):
        client, _ = _make_client()
        resp = client.post(
            "/api/v1/viper/evaluation",
            json=_eval_payload("2026-06-01", "2026-06-06", "Good", "no token"),
        )
        assert resp.status_code == 401

    def test_post_viper_feedback_without_token_returns_401(self):
        client, _ = _make_client()
        resp = client.post(
            "/api/v1/viper/feedback",
            json={
                "person": {"slug": "abdul", "display_name": "Abdul"},
                "feedback_date": "2026-06-03",
                "note": "no token",
            },
        )
        assert resp.status_code == 401

    def test_post_viper_evaluation_with_wrong_token_returns_401(self):
        client, _ = _make_client()
        resp = client.post(
            "/api/v1/viper/evaluation",
            headers={"X-Viper-Token": "totally-wrong-token"},
            json=_eval_payload("2026-06-01", "2026-06-06", "Good", "wrong token"),
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Regression: midnight-wraparound in overtime / avg check-out (review finding)
# ---------------------------------------------------------------------------

def test_early_leave_before_midnight_is_not_phantom_overtime() -> None:
    """A pre-midnight checkout (left early) must NOT register as overtime/compensation.
    Previously _minutes_of_day made a 23:00 checkout look like +20h overtime, falsely
    cancelling the chronic-late penalty and corrupting avg_check_out."""
    db = make_db()
    p = add_person(db, "early", "Early Leaver")
    for day in (date(2026, 6, 1), date(2026, 6, 2)):
        add_report(db, p, day, rating=100)
        add_attendance(
            db, p, day, "late_15",
            check_in=datetime(day.year, day.month, day.day, 18, 40, tzinfo=TZ),
            check_out=datetime(day.year, day.month, day.day, 23, 0, tzinfo=TZ),  # same-day = early
        )
    db.commit()
    m = metrics_for(db, p, WEEK_START, WEEK_END)
    assert m["avg_check_out"] == "23:00"          # not a wrapped/garbage time
    assert m["compensates"] is False              # leaving early is not compensation
    assert m["avg_hours"] == 4.3                  # 18:40 -> 23:00
    # avg 100 = Over(3), two lates without compensation -> -1 band = Good
    assert m["composite_grade"] == "Good"


def test_after_midnight_checkout_overtime_is_correct() -> None:
    """A normal post-03:00 checkout yields real overtime that compensates chronic lateness."""
    db = make_db()
    p = add_person(db, "comp", "Compensator")
    for day in (date(2026, 6, 1), date(2026, 6, 2)):
        add_report(db, p, day, rating=100)
        add_attendance(
            db, p, day, "late_15",
            check_in=datetime(day.year, day.month, day.day, 18, 40, tzinfo=TZ),       # 40 min late
            check_out=datetime(day.year, day.month, day.day + 1, 4, 30, tzinfo=TZ),   # 90 min overtime
        )
    db.commit()
    m = metrics_for(db, p, WEEK_START, WEEK_END)
    assert m["avg_check_out"] == "04:30"
    assert m["compensates"] is True               # overtime (90) >= lateness (40)
    assert m["composite_grade"] == "Over"         # penalty cancelled by compensation
