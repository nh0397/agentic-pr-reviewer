from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.repository import Repository
from app.schemas.repository import RepositoryCreate, RepositoryRead

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


@router.get("", response_model=list[RepositoryRead])
def list_repositories(db: Session = Depends(get_db)) -> list[Repository]:
    return list(db.scalars(select(Repository).order_by(Repository.created_at.desc())))


@router.post("", response_model=RepositoryRead, status_code=201)
def create_repository(payload: RepositoryCreate, db: Session = Depends(get_db)) -> Repository:
    repository = Repository(
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
def get_repository(repository_id: int, db: Session = Depends(get_db)) -> Repository:
    repository = db.get(Repository, repository_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repository
