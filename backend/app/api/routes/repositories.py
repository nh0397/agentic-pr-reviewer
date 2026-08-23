from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.session import get_db
from app.models.repository import Repository
from app.models.user import User
from app.schemas.repository import RepositoryCreate, RepositoryRead

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


@router.get("", response_model=list[RepositoryRead])
def list_repositories(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Repository]:
    return list(
        db.scalars(
            select(Repository)
            .where(Repository.user_id == current_user.id)
            .order_by(Repository.created_at.desc())
        )
    )


@router.post("", response_model=RepositoryRead, status_code=201)
def create_repository(
    payload: RepositoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Repository:
    repository = Repository(
        user_id=current_user.id,
        name=payload.name,
        github_url=payload.github_url,
        default_branch=payload.default_branch,
    )
    db.add(repository)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Repository already registered") from exc
    db.refresh(repository)
    return repository


@router.get("/{repository_id}", response_model=RepositoryRead)
def get_repository(
    repository_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Repository:
    repository = db.get(Repository, repository_id)
    if repository is None or repository.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repository
