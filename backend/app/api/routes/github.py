import httpx
from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.models.user import User
from app.schemas.github import GithubRepoSummary

router = APIRouter(prefix="/api/github", tags=["github"])


@router.get("/repos", response_model=list[GithubRepoSummary])
async def list_my_github_repos(current_user: User = Depends(get_current_user)) -> list[dict]:
    """
    Lists the logged-in user's own GitHub repositories, using their stored
    access token. This is what lets the frontend show a picker instead of
    the user typing a repo URL by hand.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.github.com/user/repos",
            headers={"Authorization": f"Bearer {current_user.access_token}"},
            params={"sort": "updated", "per_page": 50},
        )
        response.raise_for_status()
        return response.json()
