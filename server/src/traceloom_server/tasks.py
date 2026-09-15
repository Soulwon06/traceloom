"""Background tasks for TraceLoom server maintenance."""

import asyncio
import logging

from traceloom_server.services.events import delete_expired_events

logger = logging.getLogger("traceloom_server")

CLEANUP_INTERVAL_SECONDS = 60 * 60


async def cleanup_events_task(*, retention_days: int) -> int | None:
    """Delete expired events, logging failures without stopping the server."""
    try:
        deleted_count = await delete_expired_events(retention_days=retention_days)
    except Exception:
        logger.exception("Failed to delete expired events")
        return None

    if deleted_count:
        logger.info(
            "Deleted expired events (count=%d, retention_days=%d)",
            deleted_count,
            retention_days,
        )
    return deleted_count


async def run_cleanup_loop_task(*, retention_days: int) -> None:
    """Delete expired events every hour until the task is cancelled."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        await cleanup_events_task(retention_days=retention_days)
