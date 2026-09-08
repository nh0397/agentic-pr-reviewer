from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.session import get_db
from app.models.repository import Repository
from app.models.user import User
from app.schemas.pull_request import ChangedFile, PullRequestDetail, PullRequestSummary

router = APIRouter(prefix="/api/repositories", tags=["pull requests"])

GITHUB_API = "https://api.github.com"

# GitHub caps a single files listing at 300 files, and a diff that large is
# past the point where reviewing it as one unit is useful anyway.
MAX_CHANGED_FILES = 300


def _owner_and_name(repository: Repository) -> tuple[str, str]:
    """
    GitHub's API is addressed by owner/name, but we store the browser URL.
    Deriving it from the URL keeps a single source of truth rather than
    storing the same identity twice and letting the copies drift.
    """
    parts = [p for p in urlparse(repository.github_url).path.split("/") if p]
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail=f"Cannot parse owner/name from {repository.github_url}")
    return parts[0], parts[1].removesuffix(".git")


def _load_repository(repository_id: int, current_user: User, db: Session) -> Repository:
    repository = db.get(Repository, repository_id)
    if repository is None or repository.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repository


async def _github_get(url: str, token: str, params: dict | None = None):
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            params=params,
        )
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Not found on GitHub")
    if response.status_code == 403:
        # Distinguishable from a permissions problem by the message body,
        # but either way the caller can only wait or re-authorise.
        raise HTTPException(status_code=429, detail="GitHub rate limit or access denied")
    response.raise_for_status()
    return response.json()


@router.get("/{repository_id}/pulls", response_model=list[PullRequestSummary])
async def list_pull_requests(
    repository_id: int,
    state: str = "open",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PullRequestSummary]:
    repository = _load_repository(repository_id, current_user, db)
    owner, name = _owner_and_name(repository)

    payload = await _github_get(
        f"{GITHUB_API}/repos/{owner}/{name}/pulls",
        current_user.access_token,
        {"state": state, "sort": "updated", "direction": "desc", "per_page": 50},
    )

    return [
        PullRequestSummary(
            number=pr["number"],
            title=pr["title"],
            state=pr["state"],
            author=pr["user"]["login"],
            html_url=pr["html_url"],
            created_at=pr["created_at"],
            updated_at=pr["updated_at"],
            draft=pr.get("draft", False),
        )
        for pr in payload
    ]


@router.get("/{repository_id}/pulls/{number}", response_model=PullRequestDetail)
async def get_pull_request(
    repository_id: int,
    number: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PullRequestDetail:
    """The PR plus its changed files and patches, which is the raw material
    the review agent starts from."""
    repository = _load_repository(repository_id, current_user, db)
    owner, name = _owner_and_name(repository)
    token = current_user.access_token

    pr = await _github_get(f"{GITHUB_API}/repos/{owner}/{name}/pulls/{number}", token)
    files = await _github_get(
        f"{GITHUB_API}/repos/{owner}/{name}/pulls/{number}/files",
        token,
        {"per_page": MAX_CHANGED_FILES},
    )

    return PullRequestDetail(
        number=pr["number"],
        title=pr["title"],
        body=pr.get("body"),
        state=pr["state"],
        author=pr["user"]["login"],
        html_url=pr["html_url"],
        base_ref=pr["base"]["ref"],
        head_ref=pr["head"]["ref"],
        additions=pr.get("additions", 0),
        deletions=pr.get("deletions", 0),
        changed_files=[
            ChangedFile(
                path=f["filename"],
                status=f["status"],
                additions=f["additions"],
                deletions=f["deletions"],
                patch=f.get("patch"),
            )
            for f in files
        ],
    )
