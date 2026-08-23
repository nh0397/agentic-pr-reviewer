from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.auth import get_current_user
from app.db.session import get_db
from app.indexing.indexer import index_repository
from app.models.code_graph import CodeFile, CodeSymbol, SymbolCall, SymbolType
from app.models.repository import IndexStatus, Repository
from app.models.user import User
from app.schemas.graph import (
    GraphEdge,
    GraphNode,
    GraphStats,
    LanguageBreakdown,
    RepositoryGraph,
)

router = APIRouter(prefix="/api/repositories", tags=["indexing"])

# The visualization is only readable up to a point, and a big repo can have
# thousands of edges. Past this we show a truncated graph rather than an
# unreadable hairball (or a huge response).
MAX_GRAPH_EDGES = 300


@router.post("/{repository_id}/index")
def trigger_indexing(
    repository_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Synchronous on purpose for now: the request blocks until indexing
    finishes. A real deployment would move this to a background job, since
    indexing a large repo can take well over a typical request timeout, but
    that's a deliberate later step once this pipeline itself is proven.
    """
    repository = db.get(Repository, repository_id)
    if repository is None or repository.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Repository not found")

    repository.index_status = IndexStatus.INDEXING
    db.commit()

    try:
        # The user's own GitHub token works for cloning both public and
        # private repos, so there's no need to track a separate "is this
        # repo private" flag just to decide whether to authenticate.
        result = index_repository(repository, current_user.access_token, db)
    except Exception as exc:
        repository.index_status = IndexStatus.FAILED
        db.commit()
        raise HTTPException(status_code=500, detail=f"Indexing failed: {exc}") from exc

    repository.index_status = IndexStatus.INDEXED
    repository.indexed_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "status": "indexed",
        "files_indexed": result.files_indexed,
        "symbols_found": result.symbols_found,
        "calls_found": result.calls_found,
    }


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
