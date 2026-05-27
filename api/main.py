import logging
import os
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from api.db import get_db, AsyncSessionLocal
from api.models import Settings
from api.auth import hash_password, verify_password, create_token, require_auth
from api.routes import settings as settings_router
from api.routes import jobs as jobs_router

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger("api.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Seed settings and start background worker on startup."""
    try:
        _log.info("STARTUP [1/3] seeding settings...")
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Settings))
            if not result.scalar_one_or_none():
                initial_password = os.environ.get("UI_PASSWORD", "changeme")
                db.add(Settings(password_hash=hash_password(initial_password)))
                await db.commit()
        _log.info("STARTUP [1/3] settings seeded")

        if os.environ.get("ENV") != "test":
            _log.info("STARTUP [2/3] importing worker module...")
            from api.worker import start_worker
            _log.info("STARTUP [2/3] starting background worker...")
            start_worker()
            _log.info("STARTUP [2/3] background worker started")

        _log.info("STARTUP [3/3] complete — app ready")
    except Exception:
        _log.error("STARTUP FAILED:\n" + traceback.format_exc())
        raise
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("WEB_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(settings_router.router)
app.include_router(jobs_router.router)


class LoginRequest(BaseModel):
    password: str


@app.post("/auth/login")
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """Validate password and set JWT HttpOnly cookie."""
    result = await db.execute(select(Settings))
    settings = result.scalar_one()
    if not verify_password(body.password, settings.password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")
    token = create_token()
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=os.environ.get("ENV") == "production",
        samesite="none" if os.environ.get("ENV") == "production" else "lax",
        max_age=7 * 24 * 60 * 60,
    )
    return {"ok": True}


@app.post("/auth/logout")
async def logout(response: Response):
    """Clear the JWT cookie."""
    response.delete_cookie("access_token")
    return {"ok": True}


@app.get("/auth/me")
async def me(_: str = Depends(require_auth)):
    """Check if the current session is authenticated."""
    return {"authenticated": True}


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    """Liveness + DB connectivity check."""
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}
