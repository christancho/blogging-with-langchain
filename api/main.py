import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from api.db import get_db, engine, Base, AsyncSessionLocal
from api.models import Settings
from api.auth import hash_password, verify_password, create_token, require_auth
from api.routes import settings as settings_router
from api.routes import jobs as jobs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables, seed settings, and start background worker."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Settings))
        if not result.scalar_one_or_none():
            initial_password = os.environ.get("UI_PASSWORD", "changeme")
            db.add(Settings(password_hash=hash_password(initial_password)))
            await db.commit()
    if os.environ.get("ENV") != "test":
        from api.worker import start_worker
        start_worker()
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
