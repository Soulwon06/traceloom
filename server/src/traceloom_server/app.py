"""FastAPI application setup with Tortoise ORM."""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.types import Receive, Scope, Send
from tortoise.contrib.fastapi import register_tortoise

from traceloom_server.routes.api import router as api_router
from traceloom_server.tasks import cleanup_events_task, run_cleanup_loop_task

logger = logging.getLogger("traceloom_server")

DEFAULT_RETENTION_DAYS = 7
RETENTION_ENV_VAR = "TRACELOOM_RETENTION_DAYS"


class SPAStaticFiles(StaticFiles):
    """StaticFiles subclass that falls back to index.html for SPA routing."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        except HTTPException as exc:
            if exc.status_code == 404:
                scope["path"] = "/index.html"
                await super().__call__(scope, receive, send)
            else:
                raise


def create_app(db_url: str | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""

    application = FastAPI(title="TraceLoom", lifespan=_cleanup_lifespan)

    application.include_router(api_router)

    frontend_dir = get_frontend_dir()
    if frontend_dir:
        application.mount(
            "/", SPAStaticFiles(directory=str(frontend_dir), html=True), name="spa"
        )

    register_tortoise(
        application,
        db_url=db_url or _get_db_url(),
        modules={"models": ["traceloom_server.models"]},
        generate_schemas=True,
        add_exception_handlers=True,
    )

    return application


def get_retention_days() -> int:
    """Return the configured event retention period."""
    value = os.environ.get(RETENTION_ENV_VAR)
    if value is None:
        return DEFAULT_RETENTION_DAYS

    try:
        retention_days = int(value)
    except ValueError as exc:
        raise ValueError(
            f"{RETENTION_ENV_VAR} must be a non-negative integer, got {value!r}"
        ) from exc

    if retention_days < 0:
        raise ValueError(
            f"{RETENTION_ENV_VAR} must be a non-negative integer, got {value!r}"
        )
    return retention_days


def get_frontend_dir() -> Path | None:
    """Return the configured or bundled frontend directory."""
    frontend_dir = os.environ.get("TRACELOOM_FRONTEND_DIR")
    if frontend_dir:
        path = Path(frontend_dir)
        if path.is_dir() and (path / "index.html").is_file():
            return path

    bundled = Path(__file__).parent / "_frontend"
    if bundled.is_dir() and (bundled / "index.html").is_file():
        return bundled
    return None


@asynccontextmanager
async def _cleanup_lifespan(_application: FastAPI) -> AsyncIterator[None]:
    retention_days = get_retention_days()
    if retention_days == 0:
        logger.info("Event cleanup disabled")
        yield
        return

    logger.info("Event retention configured (days=%d)", retention_days)
    await cleanup_events_task(retention_days=retention_days)
    cleanup_task = asyncio.create_task(
        run_cleanup_loop_task(retention_days=retention_days),
        name="traceloom-event-cleanup",
    )
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


def _get_db_url() -> str:
    """Return the configured or default SQLite database URL."""
    db_path = os.environ.get("TRACELOOM_DB_PATH")
    if db_path:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite://{db_path}"
    default_dir = Path.home() / ".traceloom"
    default_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite://{default_dir / 'traceloom.db'}"
