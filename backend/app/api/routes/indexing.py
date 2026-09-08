from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.session import get_db
from app.indexing.queue import enqueue_job, queue_position
from app.models.code_graph import CodeFile, CodeSymbol, SymbolCall, SymbolType
from app.models.index_job import IndexJob, JobStatus
from app.models.repository import Repository
from app.models.user import User
from app.schemas.graph import (
    GraphEdge,
    GraphNode,
    GraphStats,
    IndexJobRead,
    LanguageBreakdown,
    RepositoryGraph,
)

router = APIRouter(prefix="/api/repositories", tags=["indexing"])

# The visualization is only readable up to a point, and a big repo can have
# thousands of edges. Past this we show a truncated graph rather than an
# unreadable hairball (or a huge response).
MAX_GRAPH_EDGES = 300


def _job_response(job: IndexJob, db: Session) -> IndexJobRead:
    return IndexJobRead(
        id=job.id,
        repository_id=job.repository_id,
        status=job.status.value,
        queue_position=queue_position(job, db),
        phase=job.phase,
        detail=job.detail,
        progress_current=job.progress_current,
        progress_total=job.progress_total,
        error=job.error,
        files_indexed=job.files_indexed,
        symbols_found=job.symbols_found,
        calls_found=job.calls_found,
    )


@router.post("/{repository_id}/index", response_model=IndexJobRead, status_code=202)
def trigger_indexing(
    repository_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IndexJobRead:
    """
    Queues the repository and returns immediately. Indexing clones the repo
    and embeds every symbol, which is far too slow to hold an HTTP request
    open for, and running several at once would only make each one slower.
    A single background worker drains the queue one repository at a time.
    """
    repository = db.get(Repository, repository_id)
    if repository is None or repository.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Repository not found")

    job = enqueue_job(repository_id, db)
    return _job_response(job, db)


@router.get("/{repository_id}/index", response_model=IndexJobRead | None)
def get_index_job(
    repository_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IndexJobRead | None:
    """Most recent job for this repository, which is what the UI polls."""
    repository = db.get(Repository, repository_id)
    if repository is None or repository.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Repository not found")

    job = db.scalar(
        select(IndexJob)
        .where(IndexJob.repository_id == repository_id)
        .order_by(IndexJob.created_at.desc())
        .limit(1)
    )
    return _job_response(job, db) if job else None


@router.get("/index/jobs", response_model=list[IndexJobRead])
def list_active_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[IndexJobRead]:
    """
    Every queued or running job for this user, so the dashboard can show
    the state of all repositories in one request instead of one per card.
    """
    repo_ids = select(Repository.id).where(Repository.user_id == current_user.id)
    jobs = db.scalars(
        select(IndexJob)
        .where(
            IndexJob.repository_id.in_(repo_ids),
            IndexJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
        .order_by(IndexJob.created_at)
    ).all()
    return [_job_response(job, db) for job in jobs]


@router.get("/{repository_id}/graph", response_model=RepositoryGraph)
def get_repository_graph(
    repository_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RepositoryGraph:
    """
    What indexing actually produced: counts, a language breakdown, and the
    call graph itself. Only symbols that participate in a call are returned
    as nodes; isolated symbols would be visual noise, and the counts already
    account for them.
    """
    repository = db.get(Repository, repository_id)
    if repository is None or repository.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Repository not found")

    file_ids = select(CodeFile.id).where(CodeFile.repository_id == repository_id)

    files_count = db.scalar(
        select(func.count()).select_from(CodeFile).where(CodeFile.repository_id == repository_id)
    )
    functions_count = db.scalar(
        select(func.count())
        .select_from(CodeSymbol)
        .where(CodeSymbol.file_id.in_(file_ids), CodeSymbol.symbol_type == SymbolType.FUNCTION)
    )
    classes_count = db.scalar(
        select(func.count())
        .select_from(CodeSymbol)
        .where(CodeSymbol.file_id.in_(file_ids), CodeSymbol.symbol_type == SymbolType.CLASS)
    )

    languages = [
        LanguageBreakdown(language=language, files=count)
        for language, count in db.execute(
            select(CodeFile.language, func.count())
            .where(CodeFile.repository_id == repository_id)
            .group_by(CodeFile.language)
            .order_by(func.count().desc())
        ).all()
    ]

    symbol_ids = select(CodeSymbol.id).where(CodeSymbol.file_id.in_(file_ids))
    edges_total = db.scalar(
        select(func.count())
        .select_from(SymbolCall)
        .where(SymbolCall.caller_id.in_(symbol_ids))
    )

    edge_rows = db.execute(
        select(SymbolCall.caller_id, SymbolCall.callee_id)
        .where(SymbolCall.caller_id.in_(symbol_ids))
        .limit(MAX_GRAPH_EDGES)
    ).all()

    connected_ids = {sid for edge in edge_rows for sid in edge}
    nodes: list[GraphNode] = []
    if connected_ids:
        nodes = [
            GraphNode(id=sid, name=name, symbol_type=symbol_type.value, path=path)
            for sid, name, symbol_type, path in db.execute(
                select(CodeSymbol.id, CodeSymbol.name, CodeSymbol.symbol_type, CodeFile.path)
                .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
                .where(CodeSymbol.id.in_(connected_ids))
            ).all()
        ]

    return RepositoryGraph(
        stats=GraphStats(
            files=files_count or 0,
            symbols=(functions_count or 0) + (classes_count or 0),
            functions=functions_count or 0,
            classes=classes_count or 0,
            edges=edges_total or 0,
            languages=languages,
        ),
        nodes=nodes,
        edges=[GraphEdge(source=caller, target=callee) for caller, callee in edge_rows],
    )
