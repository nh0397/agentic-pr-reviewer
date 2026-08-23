from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    Reads the user id out of the signed session cookie set at login, then
    loads the matching row. Any route that depends on this is only reachable
    while logged in.
    """
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not logged in")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not logged in")

    return user
