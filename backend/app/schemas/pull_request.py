from datetime import datetime

from pydantic import BaseModel


class PullRequestSummary(BaseModel):
    number: int
    title: str
    state: str
    author: str
    html_url: str
    created_at: datetime
    updated_at: datetime
    draft: bool


class ChangedFile(BaseModel):
    path: str
    status: str  # added / modified / removed / renamed
    additions: int
    deletions: int
    # GitHub omits the patch for binary files and very large diffs.
    patch: str | None = None


class PullRequestDetail(BaseModel):
    number: int
    title: str
    body: str | None
    state: str
    author: str
    html_url: str
    base_ref: str
    head_ref: str
    additions: int
    deletions: int
    changed_files: list[ChangedFile]
