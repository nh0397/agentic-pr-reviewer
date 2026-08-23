from datetime import datetime

from pydantic import BaseModel


class GithubRepoSummary(BaseModel):
    name: str
    full_name: str
    html_url: str
    default_branch: str
    private: bool
    description: str | None = None
    language: str | None = None
    stargazers_count: int = 0
    updated_at: datetime
