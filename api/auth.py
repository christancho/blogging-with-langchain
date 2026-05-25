import os
from datetime import datetime, timedelta, timezone
import bcrypt
from jose import jwt, JWTError
from fastapi import Cookie, HTTPException

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a plain-text password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_token(subject: str = "user", expires_delta: timedelta = timedelta(days=7)) -> str:
    """Create a signed JWT with the given subject and expiry."""
    expire = datetime.now(timezone.utc) + expires_delta
    return jwt.encode({"sub": subject, "exp": expire}, os.environ["JWT_SECRET"], algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises JWTError if invalid or expired."""
    return jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[ALGORITHM])


def require_auth(access_token: str | None = Cookie(default=None)) -> str:
    """FastAPI dependency that validates the JWT cookie and returns the subject."""
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(access_token)
        return payload["sub"]
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
