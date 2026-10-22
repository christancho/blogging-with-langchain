import uuid
from datetime import datetime
from sqlalchemy import DDL, String, Integer, Text, DateTime, Float, Boolean, event, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from api.db import Base


class Job(Base):
    """Represents a blog generation job in the queue."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    tone: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_node: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs: Mapped[str | None] = mapped_column(Text, nullable=True)


# Postgres NOTIFY channel fired whenever the set of active jobs may have changed:
# a job is created or deleted, or its status / current_node changes. Log-only
# writes (the worker flushes Job.logs every 2s) deliberately do not fire it.
# GET /jobs/stream LISTENs here to push queue updates to the dashboard.
JOBS_CHANNEL = "jobs_changed"

# Production gets this from the alembic migration (d7e2a9c41f60); the listener
# below creates it for databases built with Base.metadata.create_all (tests).
JOBS_NOTIFY_FUNCTION_SQL = f"""
CREATE OR REPLACE FUNCTION notify_jobs_changed() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('{JOBS_CHANNEL}', '');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql
"""
JOBS_NOTIFY_TRIGGER_SQL = """
CREATE TRIGGER jobs_changed_notify
AFTER INSERT OR DELETE OR UPDATE OF status, current_node ON jobs
FOR EACH ROW EXECUTE FUNCTION notify_jobs_changed()
"""

event.listen(Job.__table__, "after_create", DDL(JOBS_NOTIFY_FUNCTION_SQL).execute_if(dialect="postgresql"))
event.listen(Job.__table__, "after_create", DDL(JOBS_NOTIFY_TRIGGER_SQL).execute_if(dialect="postgresql"))


class Settings(Base):
    """Single-row application settings table."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    default_tone: Mapped[str] = mapped_column(Text, nullable=False, default="informative and insightful")
    default_word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=3500)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    llm_temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    llm_model: Mapped[str] = mapped_column(Text, nullable=False, default="anthropic/claude-sonnet-4-5")
    auto_publish_to_ghost: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
