"""Runs a review and persists it, including the evidence trail."""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.agent.reviewer import review_pull_request
from app.agent.source import repository_source
from app.models.repository import Repository
from app.models.review import Finding, Review, ReviewStatus

logger = logging.getLogger("agent.service")


def run_review(
    repository: Repository,
    pull_request: dict[str, Any],
    access_token: str | None,
    db: Session,
) -> Review:
    review = Review(
        repository_id=repository.id,
        pr_number=pull_request["number"],
        pr_title=pull_request.get("title"),
        status=ReviewStatus.RUNNING,
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    logger.info(
        "reviewing %s PR #%s: %s",
        repository.name,
        pull_request["number"],
        pull_request.get("title"),
    )

    try:
        # One checkout for the whole review, so the read tools see real code.
        with repository_source(repository.github_url, access_token) as source:
            result = review_pull_request(repository.id, pull_request, db, source=source)
    except Exception as exc:
        logger.exception("review failed for PR #%s", pull_request["number"])
        db.rollback()
        review = db.get(Review, review.id)
        review.status = ReviewStatus.FAILED
        review.error = str(exc)[:2000]
        review.finished_at = datetime.now(timezone.utc)
        db.commit()
        return review

    review.status = ReviewStatus.SUCCEEDED
    review.summary = result.summary
    review.tool_calls = result.tool_calls
    review.steps_used = result.steps_used
    review.prompt_tokens = result.prompt_tokens
    review.completion_tokens = result.completion_tokens
    review.finished_at = datetime.now(timezone.utc)

    for finding in result.findings:
        db.add(
            Finding(
                review_id=review.id,
                severity=finding.severity,
                title=finding.title[:500],
                body=finding.body,
                file_path=finding.file,
                line=finding.line,
                evidence=finding.evidence,
            )
        )

    db.commit()
    db.refresh(review)
    logger.info(
        "review %d finished: %d finding(s) from %d tool call(s)",
        review.id,
        len(result.findings),
        len(result.tool_calls),
    )
    return review
