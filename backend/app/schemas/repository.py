from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.repository import IndexStatus


class RepositoryCreate(BaseModel):
    name: str
    github_url: str
    default_branch: str = "main"


class RepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    github_url: str
    default_branch: str
    index_status: IndexStatus
    indexed_at: datetime | None
    created_at: datetime
