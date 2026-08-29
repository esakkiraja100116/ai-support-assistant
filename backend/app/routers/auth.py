from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import create_access_token
from app.db import get_db
from app.models import User
from app.schemas.auth import LoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    """Seeded usernames for the frontend's mock-login picker."""
    return list(db.scalars(select(User).order_by(User.username)))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown username")
    token = create_access_token(str(user.id), user.role)
    return TokenResponse(
        access_token=token, user_id=str(user.id), display_name=user.display_name, role=user.role
    )
