from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Base, engine, utc_now
from .models import AttendancePolicy, AuditLog, ProjectTopic

SEEDED_TOPICS = ("3", "5639", "9", "5631", "3569")


def init_db() -> None:
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

