from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.service import run_review
from app.api.routes.pull_requests import get_pull_request
from app.auth import get_current_user
from app.db.session import get_db
from app.models.repository import IndexStatus, Repository
from app.models.review import Finding, Review
from app.models.user import User
from app.schemas.review import FindingRead, ReviewDetail, ReviewSummary

router = APIRouter(prefix="/api/repositories", tags=["reviews"])


def _load_repository(repository_id: int, current_user: User, db: Session) -> Repository:
    repository = db.get(Repository, repository_id)
    if repository is None or repository.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repository


def _detail(review: Review, db: Session) -> ReviewDetail:
    findings = db.scalars(select(Finding).where(Finding.review_id == review.id)).all()
    return ReviewDetail(
        id=review.id,
        repository_id=review.repository_id,
        pr_number=review.pr_number,
        pr_title=review.pr_title,
        status=review.status.value,
        summary=review.summary,
        error=review.error,
        steps_used=review.steps_used,
        prompt_tokens=review.prompt_tokens,
        completion_tokens=review.completion_tokens,
        created_at=review.created_at,
        finished_at=review.finished_at,
        tool_calls=review.tool_calls or [],
        findings=[
            FindingRead(
                id=f.id,
                severity=f.severity,
                title=f.title,
                body=f.body,
                file_path=f.file_path,
                line=f.line,
                evidence=f.evidence,
            )
            for f in findings
        ],
    )


@router.post("/{repository_id}/pulls/{number}/review", response_model=ReviewDetail)
async def create_review(
    repository_id: int,
    number: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewDetail:
    """
    Runs the agent against a pull request and returns the finished review.

    Synchronous for now. Unlike indexing this is usually tens of seconds
    rather than minutes, so it fits inside a request; moving it onto the
    existing job queue is the natural next step if that stops being true.
    """
    repository = _load_repository(repository_id, current_user, db)
    if repository.index_status != IndexStatus.INDEXED:
        raise HTTPException(
            status_code=409,
            detail="Index this repository first; the agent needs it to investigate.",
        )

    pull_request = await get_pull_request(repository_id, number, current_user, db)
    review = run_review(repository, pull_request.model_dump(), current_user.access_token, db)
    return _detail(review, db)


@router.get("/{repository_id}/reviews", response_model=list[ReviewSummary])
def list_reviews(
    repository_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ReviewSummary]:
    _load_repository(repository_id, current_user, db)
    reviews = db.scalars(
        select(Review)
        .where(Review.repository_id == repository_id)
        .order_by(Review.created_at.desc())
        .limit(50)
    ).all()
    return [
        ReviewSummary(
            id=r.id,
            pr_number=r.pr_number,
            pr_title=r.pr_title,
            status=r.status.value,
            summary=r.summary,
            finding_count=db.scalar(
                select(func.count()).select_from(Finding).where(Finding.review_id == r.id)
            )
            or 0,
            created_at=r.created_at,
        )
        for r in reviews
    ]


@router.get("/{repository_id}/reviews/{review_id}", response_model=ReviewDetail)
def get_review(
    repository_id: int,
    review_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewDetail:
    _load_repository(repository_id, current_user, db)
    review = db.get(Review, review_id)
    if review is None or review.repository_id != repository_id:
        raise HTTPException(status_code=404, detail="Review not found")
    return _detail(review, db)
