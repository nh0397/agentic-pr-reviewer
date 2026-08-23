from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserRead

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


@router.get("/github/login")
def github_login() -> RedirectResponse:
    """
    Step 1 of OAuth: send the browser to GitHub's own login and consent
    screen. GitHub, not us, handles the username and password.
    """
    params = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_oauth_redirect_uri,
            "scope": "repo read:user",
        }
    )
    return RedirectResponse(f"{GITHUB_AUTHORIZE_URL}?{params}")


@router.get("/github/callback")
async def github_callback(code: str, request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    """
    Step 2 of OAuth: GitHub redirects here with a short lived `code`. We
    exchange it, server to server, for an access token, then use that token
    to ask GitHub who this is.
    """
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_oauth_redirect_uri,
            },
        )
        token_data = token_response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="GitHub did not return an access token")

        user_response = await client.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        github_user = user_response.json()

    user = db.scalar(select(User).where(User.github_id == github_user["id"]))
    if user is None:
        user = User(
            github_id=github_user["id"],
            username=github_user["login"],
            avatar_url=github_user.get("avatar_url"),
            access_token=access_token,
        )
        db.add(user)
    else:
        user.username = github_user["login"]
        user.avatar_url = github_user.get("avatar_url")
        user.access_token = access_token

    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    return RedirectResponse(settings.frontend_url)


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"status": "logged out"}
