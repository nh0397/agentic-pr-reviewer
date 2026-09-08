from datetime import datetime
from typing import Any

from pydantic import BaseModel


class FindingRead(BaseModel):
    id: int
    severity: str
    title: str
    body: str
    file_path: str | None = None
    line: int | None = None
    # Which tool results the agent based this on.
    evidence: str | None = None


class ReviewSummary(BaseModel):
    id: int
    pr_number: int
    pr_title: str | None
    status: str
    summary: str | None
    finding_count: int
    created_at: datetime


class ReviewDetail(BaseModel):
    id: int
    repository_id: int
    pr_number: int
    pr_title: str | None
    status: str
    summary: str | None
    error: str | None
    steps_used: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    created_at: datetime
    finished_at: datetime | None
    # The full investigation trail: every tool call and what it returned.
    tool_calls: list[Any]
    findings: list[FindingRead]
