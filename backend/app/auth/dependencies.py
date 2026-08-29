import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.db import get_db
from app.models import Role, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_error
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise credentials_error from exc

    user = db.get(User, user_id)
    if user is None:
        raise credentials_error
    return user


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """The one dependency allowed to see data across all users - every other
    endpoint scopes queries to current_user.id. Checked against the live
    DB-loaded role (not the JWT's role claim), so a demoted admin loses
    access immediately rather than waiting out the token's lifetime."""
    if current_user.role != Role.ADMINISTRATOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return current_user
