import asyncio
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.indexing.indexer import index_repository
from app.models.code_graph import CodeFile
from app.models.index_job import IndexJob, JobStatus
from app.models.repository import IndexStatus, Repository
from app.models.user import User

logger = logging.getLogger("indexing.queue")

# How long the worker waits before looking for new work when the queue is
# empty. Short enough that a click feels immediate, long enough that an idle
# server is not busy-polling the database.
IDLE_POLL_SECONDS = 1.0

# How many times a job may be picked up before it is treated as broken.
# Only ever exceeded when a job is interrupted rather than finishing, since
# a job that runs to completion succeeds or fails on its first attempt.
MAX_ATTEMPTS = 3

# Postgres advisory lock id. Claiming a job and running it both happen while
# holding this, so only one worker anywhere indexes at a time, not merely one
# per process. Without it, a second backend (a stray `uvicorn`, or more than
# one deployed instance) would index concurrently and the one-at-a-time
# guarantee would quietly not hold. Postgres drops the lock automatically if
# the session ends, so a crashed worker does not wedge the queue.
WORKER_LOCK_KEY = 8412771  # arbitrary, just needs to be unique to this app


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
    repository = db.get(Repository, repository_id)
    name = repository.name if repository else f"id={repository_id}"

    if existing is not None:
        logger.info(
            "already %s as job %d, not queueing again: %s",
            existing.status.value,
            existing.id,
            name,
        )
        return existing

    job = IndexJob(repository_id=repository_id)
    db.add(job)
    if repository is not None:
        repository.index_status = IndexStatus.INDEXING
    db.commit()
    db.refresh(job)
    logger.info("queued job %d for %s (position %d)", job.id, name, queue_position(job, db))
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


def _reconcile_stuck_repositories() -> None:
    """
    A repository marked INDEXING with no queued or running job would show a
    spinner forever, since nothing is left to move it on. Put it back to a
    truthful state: INDEXED if an index exists for it, otherwise NOT_INDEXED.
    """
    with SessionLocal() as db:
        active_repo_ids = select(IndexJob.repository_id).where(
            IndexJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])
        )
        stuck = db.scalars(
            select(Repository).where(
                Repository.index_status == IndexStatus.INDEXING,
                Repository.id.notin_(active_repo_ids),
            )
        ).all()
        if not stuck:
            return

        for repository in stuck:
            has_index = db.scalar(
                select(CodeFile.id).where(CodeFile.repository_id == repository.id).limit(1)
            )
            repository.index_status = (
                IndexStatus.INDEXED if has_index else IndexStatus.NOT_INDEXED
            )
            logger.info(
                "reset %s from indexing to %s (no active job)",
                repository.name,
                repository.index_status.value,
            )
        db.commit()


def _claim_next_job(db) -> int | None:
    """
    Take the oldest queued job. SKIP LOCKED means two workers racing here
    cannot claim the same row even before the advisory lock is considered.
    """
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


def _claim_and_run_one() -> str:
    """
    One turn of the worker: take the global lock, run at most one job, then
    release. Returns what happened so the loop knows whether to sleep.
    """
    with SessionLocal() as db:
        acquired = db.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": WORKER_LOCK_KEY}
        ).scalar()
        if not acquired:
            return "busy_elsewhere"
        try:
            job_id = _claim_next_job(db)
            if job_id is None:
                return "empty"
            _run_job(job_id, db)
            return "ran"
        finally:
            db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": WORKER_LOCK_KEY})
            db.commit()


def _run_job(job_id: int, db) -> None:
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

    logger.info(
        "starting job %d for %s (attempt %d of %d)",
        job.id,
        repository.name,
        job.attempts,
        MAX_ATTEMPTS,
    )
    started = time.monotonic()

    def record_progress(phase: str, detail: str, current=None, total=None) -> None:
        # A short, separate session on purpose: the indexing session has a
        # long transaction open, so writing progress through it would not be
        # visible to the API until indexing committed, which is exactly when
        # the progress stops being useful.
        try:
            with SessionLocal() as progress_db:
                progress_db.query(IndexJob).filter(IndexJob.id == job_id).update(
                    {
                        "phase": phase,
                        "detail": detail[:300],
                        "progress_current": current,
                        "progress_total": total,
                    }
                )
                progress_db.commit()
        except Exception:
            # Progress reporting must never take the job down with it.
            logger.warning("could not record progress for job %d", job_id, exc_info=True)

    try:
        result = index_repository(repository, token, db, on_progress=record_progress)
    except Exception as exc:
        logger.exception("job %d FAILED for %s: %s", job.id, repository.name, exc)
        db.rollback()
        db.refresh(job)
        job.status = JobStatus.FAILED
        job.error = str(exc)[:2000]
        job.finished_at = datetime.now(timezone.utc)
        repository.index_status = IndexStatus.FAILED
        db.commit()
        return

    # Re-read after the progress writes above, which changed the row from a
    # different session; without this the stale in-session copy would undo
    # them and could clobber the status we are about to set.
    db.refresh(job)
    job.status = JobStatus.SUCCEEDED
    job.files_indexed = result.files_indexed
    job.symbols_found = result.symbols_found
    job.calls_found = result.calls_found
    job.phase = None
    job.detail = None
    job.progress_current = None
    job.progress_total = None
    job.finished_at = datetime.now(timezone.utc)
    repository.index_status = IndexStatus.INDEXED
    repository.indexed_at = datetime.now(timezone.utc)
    db.commit()

    remaining = len(
        db.scalars(select(IndexJob).where(IndexJob.status == JobStatus.QUEUED)).all()
    )
    logger.info(
        "job %d SUCCEEDED for %s in %.1fs; %d job(s) left in queue",
        job.id,
        repository.name,
        time.monotonic() - started,
        remaining,
    )


async def worker_loop(stop_event: asyncio.Event) -> None:
    """
    Drains the queue one job at a time. Serial on purpose: indexing is CPU
    heavy (embeddings) and disk/network heavy (cloning), so running several
    at once would make each one slower rather than finishing sooner.

    The blocking work runs in a thread so the event loop, and therefore the
    rest of the API, stays responsive while a repository is being indexed.
    """
    logger.info("index worker started, draining queue one repository at a time")
    await asyncio.to_thread(_reset_orphaned_jobs)
    await asyncio.to_thread(_reconcile_stuck_repositories)

    while not stop_event.is_set():
        try:
            outcome = await asyncio.to_thread(_claim_and_run_one)
            if outcome == "ran":
                continue  # go straight for the next job, no need to wait
            # Nothing to do, or another process is holding the worker lock.
            # Wake early if asked to stop, rather than always sleeping.
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=IDLE_POLL_SECONDS)
            except asyncio.TimeoutError:
                pass
        except asyncio.CancelledError:
            raise
        except Exception:
            # A failure here is in the queue machinery itself, not in one
            # job's indexing. Keep the worker alive, otherwise a single
            # transient database error would stop all future indexing.
            logger.exception("Index worker loop error")
            await asyncio.sleep(IDLE_POLL_SECONDS)
