import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class IndexJob(Base):
    """
    One queued request to index a repository.

    The queue lives in Postgres rather than in memory so that a restart
    does not silently lose work, and so the API can report queue position
    without the worker having to be asked.
    """

    __tablename__ = "index_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.QUEUED, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Incremented each time a worker picks the job up. A job interrupted by
    # a restart is requeued, so without a ceiling a job that dies every time
    # (a crash loop, or repeated reloads while editing) would retry forever
    # and never surface an error.
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Live progress, written as the job runs so the UI can show what is
    # happening instead of an indefinite spinner. `phase` drives the label,
    # and current/total drive a progress bar when the phase can be measured.
    phase: Mapped[str | None] = mapped_column(String(30), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(300), nullable=True)
    progress_current: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_total: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    files_indexed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbols_found: Mapped[int | None] = mapped_column(Integer, nullable=True)
    calls_found: Mapped[int | None] = mapped_column(Integer, nullable=True)
