from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.session import get_db
from app.indexing.indexer import index_repository
from app.models.repository import IndexStatus, Repository
from app.models.user import User

router = APIRouter(prefix="/api/repositories", tags=["indexing"])


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
