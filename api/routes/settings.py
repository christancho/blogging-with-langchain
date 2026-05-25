from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from api.db import get_db
from api.models import Settings
from api.auth import hash_password, require_auth

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    default_tone: str | None = None
    default_word_count: int | None = None


class PasswordChange(BaseModel):
    new_password: str
    confirm_password: str


def _row_to_dict(s: Settings) -> dict:
    return {"default_tone": s.default_tone, "default_word_count": s.default_word_count}


@router.get("")
async def get_settings(db: AsyncSession = Depends(get_db), _: str = Depends(require_auth)):
    """Return current default tone and word count."""
    result = await db.execute(select(Settings))
    return _row_to_dict(result.scalar_one())


@router.put("")
async def update_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Update default tone and/or word count."""
    result = await db.execute(select(Settings))
    s = result.scalar_one()
    if body.default_tone is not None:
        s.default_tone = body.default_tone
    if body.default_word_count is not None:
        s.default_word_count = body.default_word_count
    await db.commit()
    await db.refresh(s)
    return _row_to_dict(s)


@router.put("/password")
async def change_password(
    body: PasswordChange,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Change the UI password."""
    if body.new_password != body.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    result = await db.execute(select(Settings))
    s = result.scalar_one()
    s.password_hash = hash_password(body.new_password)
    await db.commit()
    return {"ok": True}
