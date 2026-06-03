import os
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from api.db import get_db
from api.models import Settings
from api.auth import hash_password, require_auth

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    default_tone: str | None = None
    default_word_count: int | None = None
    llm_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    llm_model: str | None = None
    auto_publish_to_ghost: bool | None = None


class PasswordChange(BaseModel):
    new_password: str
    confirm_password: str


def _row_to_dict(s: Settings) -> dict:
    return {
        "default_tone": s.default_tone,
        "default_word_count": s.default_word_count,
        "llm_temperature": s.llm_temperature,
        "llm_model": s.llm_model,
        "auto_publish_to_ghost": s.auto_publish_to_ghost,
    }


@router.get("")
async def get_settings(db: AsyncSession = Depends(get_db), _: str = Depends(require_auth)):
    """Return current settings."""
    result = await db.execute(select(Settings))
    return _row_to_dict(result.scalar_one())


@router.put("")
async def update_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Update one or more settings fields."""
    result = await db.execute(select(Settings))
    s = result.scalar_one()
    if body.default_tone is not None:
        s.default_tone = body.default_tone
    if body.default_word_count is not None:
        s.default_word_count = body.default_word_count
    if body.llm_temperature is not None:
        s.llm_temperature = body.llm_temperature
    if body.llm_model is not None:
        s.llm_model = body.llm_model
    if body.auto_publish_to_ghost is not None:
        s.auto_publish_to_ghost = body.auto_publish_to_ghost
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


@router.get("/models")
async def list_models(_: str = Depends(require_auth)):
    """Proxy OpenRouter model list. Returns [{id, name}] sorted by name."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY not configured")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        models = sorted(
            [{"id": m["id"], "name": m.get("name", m["id"])} for m in data],
            key=lambda m: m["name"].lower(),
        )
        return models
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"OpenRouter error: {e.response.status_code}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Failed to reach OpenRouter: {e}")
