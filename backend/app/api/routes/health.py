from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    """
    Checks the database connection too, not just that the process is up.
    A process can be running while its database connection is broken, and
    that is the failure mode worth catching here.
    """
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
