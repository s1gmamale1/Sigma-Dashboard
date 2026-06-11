from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

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


def migrate_report_rating(target: Engine) -> None:
    """The daily-report score moved from the 1–4 band int to a 0–100 percent
    (Abdul, 2026-06-12). Rebuild reports once if its CHECK still caps at 4,
    scaling legacy band ints ×25 (4→100, 3→75, 2→50, 1→25) so every historical
    row lands in the same leaderboard band under the new thresholds. Idempotent."""
    with target.connect() as conn:
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='reports'")
        ).scalar()
    if not ddl or "rating <= 4" not in ddl:
        return
    with target.begin() as conn:
        conn.execute(text("ALTER TABLE reports RENAME TO reports_old"))
        named_indexes = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND tbl_name='reports_old' AND sql IS NOT NULL"
            )
        ).all()
        for (index_name,) in named_indexes:
            conn.execute(text(f'DROP INDEX "{index_name}"'))
    Base.metadata.tables["reports"].create(target)
    with target.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO reports (id, person_id, report_date, summary, extras, rating,"
                " missing, source_topic, created_at, updated_at)"
                " SELECT id, person_id, report_date, summary, extras,"
                " CASE WHEN rating IS NULL THEN NULL ELSE rating * 25 END,"
                " missing, source_topic, created_at, updated_at"
                " FROM reports_old"
            )
        )
        conn.execute(text("DROP TABLE reports_old"))


def init_db() -> None:
    migrate_off_day(engine)
    migrate_report_rating(engine)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        seed_db(db)
        db.commit()


def seed_db(db: Session) -> None:
    if db.scalar(select(AttendancePolicy.id).limit(1)) is None:
        db.add(AttendancePolicy(charge_amount_uzs=0))

    for topic_id in SEEDED_TOPICS:
        if db.get(ProjectTopic, topic_id) is None:
            db.add(ProjectTopic(topic_id=topic_id, title=f"LMS Topic {topic_id}", active=True))

    if db.scalar(select(AuditLog.id).limit(1)) is None:
        db.add(
            AuditLog(
                actor="system",
                action="bootstrap",
                resource="database",
                detail_json='{"seeded": true}',
                created_at=utc_now(),
            )
        )

