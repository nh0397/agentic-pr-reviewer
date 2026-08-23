import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import auth, github, health, indexing, repositories
from app.config import get_settings
from app.db.session import engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Check the database once at startup and refuse to start without it.
    Otherwise the app boots "successfully" and then throws a long
    connection traceback on every single request, which buries the actual
    problem: Postgres isn't running.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        sys.exit(
            "\n"
            f"Cannot reach Postgres at {settings.database_url.rsplit('@', 1)[-1]}\n"
            "Start it first, from the project root:\n\n"
            "    docker compose up -d\n"
        )
    yield


app = FastAPI(title="Agentic PR Reviewer", version="0.1.0", lifespan=lifespan)

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
app.include_router(indexing.router)
