import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, Float, func
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


class Settings(Base):
    """Single-row application settings table."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    default_tone: Mapped[str] = mapped_column(Text, nullable=False, default="informative and insightful")
    default_word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=3500)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    llm_temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    llm_model: Mapped[str] = mapped_column(Text, nullable=False, default="anthropic/claude-sonnet-4-5")
