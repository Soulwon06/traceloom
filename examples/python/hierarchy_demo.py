"""Demonstrate TraceLoom runtime trees and virtual grouping.

Start TraceLoom, then run this app:

    uv run traceloom run --capture-logs --log-level INFO -- \
        uvicorn examples.python.hierarchy_demo:app --port 8001

Visit http://localhost:8001/docs and call the checkout endpoints. In TraceLoom,
use the Group selector to switch between None and Remote host. Runtime parenthood
remains visible in both views.
"""

import logging
import os

import httpx
from fastapi import FastAPI
from traceloom.integrations.fastapi import TraceLoomMiddleware

app = FastAPI(title="TraceLoom hierarchy demo")
app.add_middleware(
    TraceLoomMiddleware,
    ignore_paths=["/docs", "/openapi.json", "/favicon.ico"],
)

logger = logging.getLogger("hierarchy_demo")
PROVIDER_URL = os.getenv(
    "HIERARCHY_DEMO_PROVIDER_URL",
    "http://127.0.0.1:8001/provider/charge",
)


@app.post("/checkout")
def checkout() -> dict[str, object]:
    """Emit a log and a successful outgoing child operation."""
    logger.info("starting checkout", extra={"order_id": 42})
    response = httpx.post(PROVIDER_URL, json={"order_id": 42}, timeout=5)
    response.raise_for_status()
    logger.info("checkout completed", extra={"order_id": 42})
    return {"ok": True, "provider": response.json()}


@app.post("/checkout/provider-down")
def checkout_provider_down() -> dict[str, bool]:
    """Raise after TraceLoom records a failed outgoing child operation."""
    logger.warning("calling unavailable provider", extra={"order_id": 43})
    httpx.post("http://127.0.0.1:1/charge", json={"order_id": 43}, timeout=0.2)
    return {"ok": True}


@app.post("/provider/charge")
def provider_charge(payload: dict[str, object]) -> dict[str, object]:
    """Act as the local provider called by the checkout endpoint."""
    return {"accepted": True, "order_id": payload.get("order_id")}
