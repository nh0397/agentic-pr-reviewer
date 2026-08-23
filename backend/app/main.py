from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import auth, github, health, repositories
from app.config import get_settings

settings = get_settings()

app = FastAPI(title="Agentic PR Reviewer", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Backs request.session, used to remember which user is logged in between
# requests via a signed cookie. "Signed" means the browser can see the
# cookie but cannot tamper with it without invalidating the signature.
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(github.router)
app.include_router(repositories.router)
