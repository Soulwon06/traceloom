"""Persistence for captured events.

Each ``create_*`` function takes typed input, builds the corresponding typed
output model and a one-line ``summary``, then writes a `CapturedEvent` row with
the output model dumped to JSON in the ``data`` column.
"""

import uuid
from datetime import datetime
from urllib.parse import urlparse

from traceloom_server.models import CapturedEvent, utcnow
from traceloom_server.types import (
    EventData,
    EventHierarchy,
    ExceptionData,
    ExceptionEventData,
    HttpEventData,
    HttpIncomingEventData,
    HttpIncomingMeta,
    HttpIncomingRequestData,
    HttpIncomingResponseData,
    HttpMeta,
    HttpOperationError,
    HttpRequestData,
    HttpResponseData,
    LogData,
    LogEventData,
    TestData,
    TestEventData,
)


async def create_http_event(
    *,
    event_id: str | None,
    timestamp: datetime | None = None,
    duration_ms: int,
    request: HttpRequestData,
    response: HttpResponseData | None,
    meta: HttpMeta,
    error: HttpOperationError | None = None,
    app: str = "",
    session: str = "",
    hierarchy: EventHierarchy | None = None,
) -> CapturedEvent:
    host = urlparse(request.url).hostname or "unknown"
    status_code = response.status_code if response is not None else None
    response_headers = response.headers if response is not None else {}
    response_body = response.body if response is not None else None
    response_body_size = response.body_size if response is not None else 0
    summary = _build_http_summary(
        request.method,
        request.url,
        status_code=status_code,
        error=error,
    )
    event_data = HttpEventData(
        app=app,
        session=session,
        duration_ms=duration_ms,
        method=request.method.upper(),
        url=request.url,
        host=host,
        request_headers=request.headers,
        request_body=request.body,
        request_body_size=request.body_size,
        status_code=status_code,
        response_headers=response_headers,
        response_body=response_body,
        response_body_size=response_body_size,
        error=error,
        library=meta.library,
        python_version=meta.python_version,
        traceloom_version=meta.traceloom_version,
    )
    return await CapturedEvent.create(
        id=_resolve_id(event_id),
        timestamp=timestamp or utcnow(),
        event_type="http",
        summary=summary,
        data=_serialize_event_data(event_data, hierarchy),
    )


def _build_http_summary(
    method: str,
    url: str,
    *,
    status_code: int | None,
    error: HttpOperationError | None,
) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    outcome = (
        status_code if status_code is not None else error.type if error else "failed"
    )
    return f"{method.upper()} {path} → {outcome}"


async def create_http_incoming_event(
    *,
    event_id: str | None,
    timestamp: datetime | None = None,
    duration_ms: int,
    request: HttpIncomingRequestData,
    response: HttpIncomingResponseData,
    meta: HttpIncomingMeta,
    app: str = "",
    session: str = "",
    hierarchy: EventHierarchy | None = None,
) -> CapturedEvent:
    host = next(
        (v for k, v in request.headers.items() if k.lower() == "host"),
        "unknown",
    )
    summary = _build_http_incoming_summary(
        request.method, request.path, response.status_code
    )
    event_data = HttpIncomingEventData(
        app=app,
        session=session,
        duration_ms=duration_ms,
        method=request.method.upper(),
        path=request.path,
        url=request.url,
        host=host,
        route=meta.route,
        client_ip=meta.client_ip,
        request_headers=request.headers,
        request_body=request.body,
        request_body_size=request.body_size,
        status_code=response.status_code,
        response_headers=response.headers,
        response_body=response.body,
        response_body_size=response.body_size,
        exc_type=meta.exc_type,
        exc_value=meta.exc_value,
        framework=meta.framework,
        python_version=meta.python_version,
        traceloom_version=meta.traceloom_version,
    )
    return await CapturedEvent.create(
        id=_resolve_id(event_id),
        timestamp=timestamp or utcnow(),
        event_type="http_incoming",
        summary=summary,
        data=_serialize_event_data(event_data, hierarchy),
    )


def _build_http_incoming_summary(method: str, path: str, status_code: int) -> str:
    return f"← {method.upper()} {path} → {status_code}"


async def create_log_event(
    *,
    event_id: str | None,
    timestamp: datetime | None = None,
    data: LogData,
    app: str = "",
    session: str = "",
    hierarchy: EventHierarchy | None = None,
) -> CapturedEvent:
    summary = _build_log_summary(data.level, data.logger_name, data.message)
    event_data = LogEventData(
        app=app,
        session=session,
        level=data.level,
        logger_name=data.logger_name,
        message=data.message,
        pathname=data.pathname,
        lineno=data.lineno,
        func_name=data.func_name,
        exc_text=data.exc_text,
        extra=data.extra,
    )
    return await CapturedEvent.create(
        id=_resolve_id(event_id),
        timestamp=timestamp or utcnow(),
        event_type="log",
        summary=summary,
        data=_serialize_event_data(event_data, hierarchy),
    )


def _build_log_summary(level: str, logger_name: str, message: str) -> str:
    if len(message) > 200:
        message = message[:200] + "…"
    return f"{level} {logger_name}: {message}"


async def create_exception_event(
    *,
    event_id: str | None,
    timestamp: datetime | None = None,
    data: ExceptionData,
    app: str = "",
    session: str = "",
    hierarchy: EventHierarchy | None = None,
) -> CapturedEvent:
    summary = _build_exception_summary(data.exc_type, data.exc_value)
    event_data = ExceptionEventData(
        app=app,
        session=session,
        exc_type=data.exc_type,
        exc_value=data.exc_value,
        exc_module=data.exc_module,
        traceback_text=data.traceback_text,
        frames=data.frames,
    )
    return await CapturedEvent.create(
        id=_resolve_id(event_id),
        timestamp=timestamp or utcnow(),
        event_type="exception",
        summary=summary,
        data=_serialize_event_data(event_data, hierarchy),
    )


def _build_exception_summary(exc_type: str, exc_value: str) -> str:
    if len(exc_value) > 200:
        exc_value = exc_value[:200] + "…"
    return f"{exc_type}: {exc_value}"


async def create_test_event(
    *,
    event_id: str | None,
    timestamp: datetime | None = None,
    data: TestData,
    app: str = "",
    session: str = "",
    hierarchy: EventHierarchy | None = None,
) -> CapturedEvent:
    summary = _build_test_summary(data.status, data.test_id)
    event_data = TestEventData(
        app=app,
        session=session,
        framework=data.framework,
        framework_version=data.framework_version,
        python_version=data.python_version,
        traceloom_version=data.traceloom_version,
        run_id=data.run_id,
        worker_id=data.worker_id,
        test_id=data.test_id,
        parameter_id=data.parameter_id,
        name=data.name,
        path=data.path,
        line=data.line,
        status=data.status,
        duration_ms=data.duration_ms,
        setup_duration_ms=data.setup_duration_ms,
        call_duration_ms=data.call_duration_ms,
        teardown_duration_ms=data.teardown_duration_ms,
        fixtures=data.fixtures,
        failures=data.failures,
    )
    return await CapturedEvent.create(
        id=_resolve_id(event_id),
        timestamp=timestamp or utcnow(),
        event_type="test",
        summary=summary,
        data=_serialize_event_data(event_data, hierarchy),
    )


def _build_test_summary(status: str, test_id: str) -> str:
    return f"{status.upper()} {test_id}"


def _resolve_id(event_id: str | None) -> str:
    """Shared helper: use the caller-supplied id, or generate a new UUID."""
    return event_id or str(uuid.uuid4())


def _serialize_event_data(
    event_data: EventData,
    hierarchy: EventHierarchy | None,
) -> dict[str, object]:
    """Serialize event data with hierarchy in its reserved storage key."""
    stored_data = event_data.model_dump(mode="json")
    if hierarchy is not None:
        stored_data["hierarchy"] = hierarchy.model_dump(mode="json")
    return stored_data
