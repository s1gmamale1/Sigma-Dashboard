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
