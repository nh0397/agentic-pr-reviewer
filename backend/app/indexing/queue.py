import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import SessionLocal
from app.indexing.indexer import index_repository
from app.models.index_job import IndexJob, JobStatus
from app.models.repository import IndexStatus, Repository
from app.models.user import User

logger = logging.getLogger(__name__)

# How long the worker waits before looking for new work when the queue is
# empty. Short enough that a click feels immediate, long enough that an idle
# server is not busy-polling the database.
IDLE_POLL_SECONDS = 1.0

# How many times a job may be picked up before it is treated as broken.
# Only ever exceeded when a job is interrupted rather than finishing, since
# a job that runs to completion succeeds or fails on its first attempt.
MAX_ATTEMPTS = 3


def enqueue_job(repository_id: int, db) -> IndexJob:
    """
    Queue a repository for indexing, unless it is already waiting or in
    progress, in which case the existing job is returned. Without this,
    double-clicking Index would queue the same work twice.
    """
    existing = db.scalar(
        select(IndexJob)
        .where(
            IndexJob.repository_id == repository_id,
            IndexJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
        .order_by(IndexJob.created_at)
    )
    if existing is not None:
        return existing

    job = IndexJob(repository_id=repository_id)
    db.add(job)

    repository = db.get(Repository, repository_id)
    if repository is not None:
        repository.index_status = IndexStatus.INDEXING
    db.commit()
    db.refresh(job)
    return job


def queue_position(job: IndexJob, db) -> int:
    """0 means running or next up; 1 means one job ahead of it, and so on."""
    if job.status == JobStatus.RUNNING:
        return 0
    if job.status != JobStatus.QUEUED:
        return -1
    ahead = db.scalar(
        select(IndexJob)
        .where(IndexJob.status == JobStatus.RUNNING)
        .limit(1)
    )
    earlier_queued = len(
        db.scalars(
            select(IndexJob).where(
                IndexJob.status == JobStatus.QUEUED,
                IndexJob.created_at < job.created_at,
            )
        ).all()
    )
    return earlier_queued + (1 if ahead is not None else 0)


def _reset_orphaned_jobs() -> None:
    """
    The worker runs in this process, so anything left RUNNING belongs to a
    process that died (a crash, or just `--reload` restarting on a file
    save). Put those back in the queue instead of leaving them stuck.
    """
    with SessionLocal() as db:
        orphaned = db.scalars(
            select(IndexJob).where(IndexJob.status == JobStatus.RUNNING)
        ).all()
        if not orphaned:
            return

        requeued = 0
        for job in orphaned:
            if job.attempts >= MAX_ATTEMPTS:
                job.status = JobStatus.FAILED
                job.error = (
                    f"Interrupted {job.attempts} times without finishing. "
                    "The server most likely restarted while indexing was in progress."
                )
                job.finished_at = datetime.now(timezone.utc)
                repository = db.get(Repository, job.repository_id)
                if repository is not None:
                    repository.index_status = IndexStatus.FAILED
            else:
                job.status = JobStatus.QUEUED
                job.started_at = None
                requeued += 1

        logger.info(
            "Restart recovery: requeued %d job(s), gave up on %d",
            requeued,
            len(orphaned) - requeued,
        )
        db.commit()


def _claim_next_job() -> int | None:
    """
    Take the oldest queued job. SKIP LOCKED means that if this ever runs as
    more than one process, two workers cannot claim the same job.
    """
    with SessionLocal() as db:
        job = db.scalar(
            select(IndexJob)
            .where(IndexJob.status == JobStatus.QUEUED)
            .order_by(IndexJob.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return None
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.attempts += 1
        db.commit()
        return job.id


def _run_job(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(IndexJob, job_id)
        if job is None:
            return
        repository = db.get(Repository, job.repository_id)
        if repository is None:
            job.status = JobStatus.FAILED
            job.error = "Repository no longer exists"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

        owner = db.get(User, repository.user_id)
        token = owner.access_token if owner else None

        try:
            result = index_repository(repository, token, db)
        except Exception as exc:
            logger.exception("Indexing failed for repository %s", repository.id)
            db.rollback()
            job.status = JobStatus.FAILED
            job.error = str(exc)[:2000]
            job.finished_at = datetime.now(timezone.utc)
            repository.index_status = IndexStatus.FAILED
            db.commit()
            return

        job.status = JobStatus.SUCCEEDED
        job.files_indexed = result.files_indexed
        job.symbols_found = result.symbols_found
        job.calls_found = result.calls_found
        job.finished_at = datetime.now(timezone.utc)
        repository.index_status = IndexStatus.INDEXED
        repository.indexed_at = datetime.now(timezone.utc)
        db.commit()


async def worker_loop(stop_event: asyncio.Event) -> None:
    """
    Drains the queue one job at a time. Serial on purpose: indexing is CPU
    heavy (embeddings) and disk/network heavy (cloning), so running several
    at once would make each one slower rather than finishing sooner.

    The blocking work runs in a thread so the event loop, and therefore the
    rest of the API, stays responsive while a repository is being indexed.
    """
    await asyncio.to_thread(_reset_orphaned_jobs)

    while not stop_event.is_set():
        try:
            job_id = await asyncio.to_thread(_claim_next_job)
            if job_id is None:
                # Wake early if asked to stop, rather than always sleeping.
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=IDLE_POLL_SECONDS)
                except asyncio.TimeoutError:
                    pass
                continue
            await asyncio.to_thread(_run_job, job_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            # A failure here is in the queue machinery itself, not in one
            # job's indexing. Keep the worker alive, otherwise a single
            # transient database error would stop all future indexing.
            logger.exception("Index worker loop error")
            await asyncio.sleep(IDLE_POLL_SECONDS)
