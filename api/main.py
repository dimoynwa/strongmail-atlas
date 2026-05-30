from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api import state
from api.routers import chat, health, preview, refresh, session, templates, tone, tone_batch, working_copy
from shared.config import DATABASE_URL, REDIS_URL
from shared.db import close_pool, init_pool
from shared.redis_client import init_redis
from template_assistant.ml.goemotions import get_classifier


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    state.db_pool = await init_pool(DATABASE_URL)
    state.redis_client = await init_redis(REDIS_URL)
    state.classifier = get_classifier()
    from api.refresh.job_registry import mark_orphaned_jobs_failed

    mark_orphaned_jobs_failed(REDIS_URL)
    from api.tone_batch.job_registry import mark_orphaned_tone_jobs_failed

    mark_orphaned_tone_jobs_failed(REDIS_URL)
    yield
    await close_pool()
    if state.redis_client is not None:
        await state.redis_client.aclose()
        state.redis_client = None
    state.refresh_executor.shutdown(wait=False)


app = FastAPI(title="StrongMail Agent Studio API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        body = exc.detail
    else:
        body = {"error": "HTTPError", "message": str(exc.detail), "detail": None}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "ValidationError",
            "message": "Request validation failed",
            "detail": exc.errors(),
        },
    )


app.include_router(session.router)
app.include_router(templates.router)
app.include_router(chat.router)
app.include_router(working_copy.router)
app.include_router(preview.router)
app.include_router(tone.router)
app.include_router(tone_batch.router, prefix="/tone")
app.include_router(health.router)
app.include_router(refresh.router)
