from pydantic import BaseModel


class GithubRepoSummary(BaseModel):
    name: str
    full_name: str
    html_url: str
    default_branch: str
    private: bool
