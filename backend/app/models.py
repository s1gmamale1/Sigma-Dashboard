from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, TimestampMixin


ATTENDANCE_STATUSES = ("in", "late", "charged", "no_show", "excused")
CHARGE_REASONS = ("none", "late_after_grace", "second_late_week", "no_show", "manual_policy")
CHASE_STATES = ("none", "needs_chase", "chased", "resolved")
GOAL_STATUSES = ("active", "overdue", "done", "paused")
SYNC_STATUSES = ("success", "failed")


class Person(TimestampMixin, Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    attendance_records: Mapped[list["AttendanceRecord"]] = relationship(back_populates="person")
    reports: Mapped[list["Report"]] = relationship(back_populates="person")


class AttendancePolicy(TimestampMixin, Base):
    __tablename__ = "attendance_policy"

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_start_local: Mapped[str] = mapped_column(String(5), nullable=False, default="18:00")
    shift_end_local: Mapped[str] = mapped_column(String(5), nullable=False, default="03:00")
    grace_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    free_lates_per_week: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    week_start: Mapped[str] = mapped_column(String(16), nullable=False, default="monday")
    charge_amount_uzs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="UZS")


class AttendanceRecord(TimestampMixin, Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("person_id", "shift_date", name="uq_attendance_person_shift"),
        CheckConstraint(f"status in {ATTENDANCE_STATUSES}", name="ck_attendance_status"),
        CheckConstraint(f"charge_reason in {CHARGE_REASONS}", name="ck_charge_reason"),
        CheckConstraint(f"chase_state in {CHASE_STATES}", name="ck_chase_state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), nullable=False, index=True)
    shift_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    minutes_late: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    charged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    charge_amount_uzs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    charge_reason: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    chase_state: Mapped[str] = mapped_column(String(24), nullable=False, default="none")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    person: Mapped[Person] = relationship(back_populates="attendance_records")


class Report(TimestampMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("person_id", "report_date", name="uq_report_person_date"),
        CheckConstraint("rating is null or (rating >= 1 and rating <= 4)", name="ck_report_rating"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), nullable=False, index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    extras: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    missing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_topic: Mapped[str | None] = mapped_column(String(80), nullable=True)

    person: Mapped[Person] = relationship(back_populates="reports")


class Assignment(TimestampMixin, Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), nullable=False, index=True)
    assignment: Mapped[str] = mapped_column(Text, nullable=False)
    source_topic: Mapped[str] = mapped_column(String(80), nullable=False)
    since_date: Mapped[date] = mapped_column(Date, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Goal(TimestampMixin, Base):
    __tablename__ = "goals"
    __table_args__ = (
        CheckConstraint(f"status in {GOAL_STATUSES}", name="ck_goal_status"),
        CheckConstraint("progress_percent >= 0 and progress_percent <= 100", name="ck_goal_progress"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    owner_person_id: Mapped[int | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    topic_id: Mapped[str | None] = mapped_column(ForeignKey("project_topics.topic_id"), nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_nudge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    logs: Mapped[list["GoalLog"]] = relationship(back_populates="goal", cascade="all, delete-orphan")


class GoalLog(TimestampMixin, Base):
    __tablename__ = "goal_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    goal: Mapped[Goal] = relationship(back_populates="logs")


class ProjectTopic(TimestampMixin, Base):
    __tablename__ = "project_topics"

    topic_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(180), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProjectCondition(TimestampMixin, Base):
    __tablename__ = "project_conditions"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey("project_topics.topic_id"), unique=True, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    open_items_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class SheetSyncRun(TimestampMixin, Base):
    __tablename__ = "sheet_sync_runs"
    __table_args__ = (CheckConstraint(f"status in {SYNC_STATUSES}", name="ck_sheet_sync_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sync_type: Mapped[str] = mapped_column(String(32), nullable=False, default="attendance")
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource: Mapped[str] = mapped_column(String(120), nullable=False)
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

