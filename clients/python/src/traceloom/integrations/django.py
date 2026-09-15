"""Django middleware for capturing incoming HTTP requests."""

import logging
import time
import uuid
from typing import Any

import traceloom
from traceloom.hierarchy import (
    CaptureContext,
    activate_context,
    current_context,
    start_child,
)
from traceloom.patches.patch_excepthook import capture_exception
from traceloom.transport import send_http_incoming
from traceloom.utils import (
    body_to_str,
    python_version,
    redact_headers,
    redact_query_params,
)

logger = logging.getLogger(__name__)

MAX_BODY_CAPTURE = 1_048_576  # 1 MB


class TraceLoomMiddleware:
    """Django middleware that captures incoming request/response pairs.

    Usage::

        # settings.py
        MIDDLEWARE = [
            "traceloom.integrations.django.TraceLoomMiddleware",
            ...
        ]

        # Optional: skip noisy paths
        TRACELOOM_IGNORE_PATHS = ["/admin/", "/static/"]
    """

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response
        from django.conf import settings  # noqa: PLC0415

        self.ignore_paths: list[str] = getattr(settings, "TRACELOOM_IGNORE_PATHS", [])

    def __call__(self, request: Any) -> Any:
        config = traceloom._config
        if config is None:
            return self.get_response(request)

        if self.ignore_paths:
            if any(request.path.startswith(prefix) for prefix in self.ignore_paths):
                return self.get_response(request)

        start = time.monotonic()
        context = start_child()
        request._traceloom_capture_context = context

        req_body = None
        req_body_size = 0
        try:
            content_length = int(request.META.get("CONTENT_LENGTH") or 0)
        except (ValueError, TypeError):
            content_length = 0

        if content_length <= MAX_BODY_CAPTURE:
            try:
                raw_body = request.body
                req_body_size = len(raw_body)
                if req_body_size <= MAX_BODY_CAPTURE:
                    req_body = raw_body
            except Exception:
                pass
        else:
            req_body_size = content_length

        with activate_context(context):
            response = self.get_response(request)

            duration_ms = int((time.monotonic() - start) * 1000)

            exc_type_name = getattr(request, "_traceloom_exc_type", None)
            exc_value_str = getattr(request, "_traceloom_exc_value", None)

            _capture(
                config=config,
                context=context,
                request=request,
                response=response,
                duration_ms=duration_ms,
                req_body=req_body,
                req_body_size=req_body_size,
                exc_type_name=exc_type_name,
                exc_value_str=exc_value_str,
            )

        return response

    def process_exception(self, request: Any, exception: Exception) -> None:
        if traceloom._config is None:
            return None
        if self.ignore_paths and any(
            request.path.startswith(prefix) for prefix in self.ignore_paths
        ):
            return None
        request._traceloom_exc_type = type(exception).__qualname__
        request._traceloom_exc_value = str(exception)
        config = traceloom._config
        if config is not None and config.capture_exceptions:
            context = getattr(request, "_traceloom_capture_context", None)
            if context is not None and current_context() is not context:
                with activate_context(context):
                    capture_exception(
                        type(exception), exception, exception.__traceback__
                    )
            else:
                capture_exception(type(exception), exception, exception.__traceback__)
        return None


def _capture(
    *,
    config: Any,
    context: CaptureContext,
    request: Any,
    response: Any,
    duration_ms: int,
    req_body: bytes | None,
    req_body_size: int,
    exc_type_name: str | None,
    exc_value_str: str | None,
) -> None:
    try:
        url = request.build_absolute_uri()
        url = redact_query_params(url, config.redact_query_params)

        req_headers = redact_headers(dict(request.headers), config.redact_headers)

        resp_headers = redact_headers(
            {k: v for k, v in response.items()}, config.redact_headers
        )

        if getattr(response, "streaming", False):
            resp_body_str = "[streaming]"
            resp_body_size = 0
        else:
            resp_content = response.content
            resp_body_size = len(resp_content)
            resp_body_str = (
                body_to_str(resp_content)
                if resp_body_size <= MAX_BODY_CAPTURE
                else None
            )

        route = None
        resolver_match = getattr(request, "resolver_match", None)
        if resolver_match is not None:
            route = getattr(resolver_match, "route", None)

        client_ip = request.META.get("REMOTE_ADDR")

        payload = {
            "id": str(uuid.uuid4()),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_ms": duration_ms,
            "request": {
                "method": request.method,
                "path": request.path,
                "url": url,
                "headers": req_headers,
                "body": body_to_str(req_body),
                "body_size": req_body_size,
            },
            "response": {
                "status_code": response.status_code,
                "headers": resp_headers,
                "body": resp_body_str,
                "body_size": resp_body_size,
            },
            "meta": {
                "framework": "django",
                "route": route,
                "client_ip": client_ip,
                "python_version": python_version(),
                # Keep this wire key for compatibility with pre-TraceLoom servers.
                "traceloom_version": traceloom.__version__,
                "exc_type": exc_type_name,
                "exc_value": exc_value_str,
            },
        }
        send_http_incoming(payload, context=context)
    except Exception as err:
        logger.debug("failed to capture incoming request: %s", err)
