"""Serialize captured HTTP request/response pairs for sending to the server."""

import time
import uuid

import traceloom
from traceloom.config import TraceLoomConfig
from traceloom.utils import (
    body_to_str,
    python_version,
    redact_headers,
    redact_query_params,
)


def serialize_request_response(
    *,
    config: TraceLoomConfig,
    method: str,
    url: str,
    request_headers: dict,
    request_body: str | bytes | None,
    status_code: int,
    response_headers: dict,
    response_body: str | bytes | None,
    duration_s: float,
    library: str,
) -> dict:
    """Build the capture payload dict."""
    payload = _serialize_request(
        config=config,
        method=method,
        url=url,
        request_headers=request_headers,
        request_body=request_body,
        duration_s=duration_s,
        library=library,
    )
    resp_headers = dict(response_headers)
    resp_body_str = body_to_str(response_body)
    payload["response"] = {
        "status_code": status_code,
        "headers": resp_headers,
        "body": resp_body_str,
        "body_size": len(response_body) if response_body else 0,
    }
    return payload


def serialize_request_error(
    *,
    config: TraceLoomConfig,
    method: str,
    url: str,
    request_headers: dict,
    request_body: str | bytes | None,
    error: Exception,
    duration_s: float,
    library: str,
    response_status_code: int | None = None,
    response_headers: dict | None = None,
    response_body: str | bytes | None = None,
) -> dict:
    """Build a capture payload for an outgoing call that raised."""
    payload = _serialize_request(
        config=config,
        method=method,
        url=url,
        request_headers=request_headers,
        request_body=request_body,
        duration_s=duration_s,
        library=library,
    )
    payload["error"] = {
        "type": type(error).__name__,
        "message": str(error),
        "module": type(error).__module__,
    }
    if response_status_code is not None:
        response_body_str = body_to_str(response_body)
        payload["response"] = {
            "status_code": response_status_code,
            "headers": dict(response_headers or {}),
            "body": response_body_str,
            "body_size": len(response_body) if response_body else 0,
        }
    return payload


def _serialize_request(
    *,
    config: TraceLoomConfig,
    method: str,
    url: str,
    request_headers: dict,
    request_body: str | bytes | None,
    duration_s: float,
    library: str,
) -> dict:
    """Build fields shared by successful and failed HTTP operations."""
    req_headers = redact_headers(dict(request_headers), config.redact_headers)
    url = redact_query_params(url, config.redact_query_params)

    req_body_str = body_to_str(request_body)

    return {
        "id": str(uuid.uuid4()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_ms": int(duration_s * 1000),
        "request": {
            "method": method,
            "url": url,
            "headers": req_headers,
            "body": req_body_str,
            "body_size": len(request_body) if request_body else 0,
        },
        "meta": {
            "library": library,
            "python_version": python_version(),
            # Keep this wire key for compatibility with pre-TraceLoom servers.
            "traceloom_version": traceloom.__version__,
        },
    }
