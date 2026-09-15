"""API routes: typed capture endpoints + JSON read API.

Routes are thin wrappers over `traceloom_server.services.{capture,events}`.
Per the project convention, route handlers carry the `_api` suffix so they
don't collide with service function names.
"""

from datetime import datetime
from typing import Self

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from traceloom_server.services.capture import (
    create_exception_event,
    create_http_event,
    create_http_incoming_event,
    create_log_event,
    create_test_event,
)
from traceloom_server.services.events import (
    clear_events,
    get_event,
    get_meta,
    get_stats,
    list_event_ids,
    list_events,
)
from traceloom_server.types import (
    EventDetail,
    EventHierarchy,
    EventIdsResponse,
    EventListResponse,
    EventStatsResponse,
    ExceptionData,
    HttpIncomingMeta,
    HttpIncomingRequestData,
    HttpIncomingResponseData,
    HttpMeta,
    HttpOperationError,
    HttpRequestData,
    HttpResponseData,
    LogData,
    MetaResponse,
    TestData,
)

router = APIRouter(prefix="/api")


# --- Capture payloads (per event type) ---


class CapturePayloadBase(BaseModel):
    id: str | None = None
    timestamp: datetime | None = None
    app: str = ""
    session: str = ""
    hierarchy: EventHierarchy | None = None


class HttpCapturePayload(CapturePayloadBase):
    duration_ms: int = 0
    request: HttpRequestData
    response: HttpResponseData | None = None
    error: HttpOperationError | None = None
    meta: HttpMeta = Field(default_factory=HttpMeta)

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        if self.response is None and self.error is None:
            raise ValueError("provide a response or error")
        return self


class LogCapturePayload(CapturePayloadBase):
    data: LogData


class ExceptionCapturePayload(CapturePayloadBase):
    data: ExceptionData


class TestCapturePayload(CapturePayloadBase):
    data: TestData


class HttpIncomingCapturePayload(CapturePayloadBase):
    duration_ms: int = 0
    request: HttpIncomingRequestData
    response: HttpIncomingResponseData
    meta: HttpIncomingMeta = Field(default_factory=HttpIncomingMeta)


class CaptureResponse(BaseModel):
    status: str


OK = CaptureResponse(status="ok")


# --- Capture routes ---


@router.post("/capture/http", status_code=201, response_model=CaptureResponse)
async def capture_http_api(payload: HttpCapturePayload) -> CaptureResponse:
    await create_http_event(
        event_id=payload.id,
        timestamp=payload.timestamp,
        duration_ms=payload.duration_ms,
        request=payload.request,
        response=payload.response,
        error=payload.error,
        meta=payload.meta,
        app=payload.app,
        session=payload.session,
        hierarchy=payload.hierarchy,
    )
    return OK


@router.post("/capture/http_incoming", status_code=201, response_model=CaptureResponse)
async def capture_http_incoming_api(
    payload: HttpIncomingCapturePayload,
) -> CaptureResponse:
    await create_http_incoming_event(
        event_id=payload.id,
        timestamp=payload.timestamp,
        duration_ms=payload.duration_ms,
        request=payload.request,
        response=payload.response,
        meta=payload.meta,
        app=payload.app,
        session=payload.session,
        hierarchy=payload.hierarchy,
    )
    return OK


@router.post("/capture/log", status_code=201, response_model=CaptureResponse)
async def capture_log_api(payload: LogCapturePayload) -> CaptureResponse:
    await create_log_event(
        event_id=payload.id,
        timestamp=payload.timestamp,
        data=payload.data,
        app=payload.app,
        session=payload.session,
        hierarchy=payload.hierarchy,
    )
    return OK


@router.post("/capture/exception", status_code=201, response_model=CaptureResponse)
async def capture_exception_api(payload: ExceptionCapturePayload) -> CaptureResponse:
    await create_exception_event(
        event_id=payload.id,
        timestamp=payload.timestamp,
        data=payload.data,
        app=payload.app,
        session=payload.session,
        hierarchy=payload.hierarchy,
    )
    return OK


@router.post("/capture/test", status_code=201, response_model=CaptureResponse)
async def capture_test_api(payload: TestCapturePayload) -> CaptureResponse:
    await create_test_event(
        event_id=payload.id,
        timestamp=payload.timestamp,
        data=payload.data,
        app=payload.app,
        session=payload.session,
        hierarchy=payload.hierarchy,
    )
    return OK


@router.post(
    "/capture",
    status_code=201,
    response_model=CaptureResponse,
    deprecated=True,
    summary="Deprecated: use /api/capture/http",
)
async def capture_legacy_api(payload: HttpCapturePayload) -> CaptureResponse:
    """Deprecated HTTP capture endpoint.

    Kept for backwards compatibility with legacy pre-TraceLoom client wheels,
    which only ever posted HTTP captures here. New clients should use the
    typed endpoints `/api/capture/http`, `/api/capture/log`,
    `/api/capture/exception`.
    """
    return await capture_http_api(payload)


# --- Read routes ---


@router.get("/events", response_model=EventListResponse)
async def list_events_api(
    event_type: str | None = Query(None),
    host: str | None = Query(None),
    method: str | None = Query(None),
    status: int | None = Query(None),
    search: str | None = Query(None),
    app: str | None = Query(None),
    session: str | None = Query(None),
    include_ancestors: bool = Query(False),
    after_seq: int | None = Query(
        None, description="Return only events inserted after this seq, oldest first."
    ),
    before_seq: int | None = Query(
        None, description="Return only events inserted before this seq (backfill)."
    ),
    limit: int = Query(200, le=10000),
) -> EventListResponse:
    try:
        return await list_events(
            event_type=event_type,
            host=host,
            method=method,
            status=status,
            search=search,
            app=app,
            session=session,
            include_ancestors=include_ancestors,
            after_seq=after_seq,
            before_seq=before_seq,
            limit=limit,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


# Declared before `/events/{event_id}` so FastAPI does not match these as IDs.
@router.get("/events/ids", response_model=EventIdsResponse)
async def list_event_ids_api(
    event_type: str | None = Query(None),
    host: str | None = Query(None),
    method: str | None = Query(None),
    status: int | None = Query(None),
    search: str | None = Query(None),
    app: str | None = Query(None),
    session: str | None = Query(None),
    limit: int = Query(10000, le=10000),
) -> EventIdsResponse:
    return await list_event_ids(
        event_type=event_type,
        host=host,
        method=method,
        status=status,
        search=search,
        app=app,
        session=session,
        limit=limit,
    )


@router.get("/events/stats", response_model=EventStatsResponse)
async def get_stats_api(
    event_type: str | None = Query(None),
    host: str | None = Query(None),
    method: str | None = Query(None),
    status: int | None = Query(None),
    search: str | None = Query(None),
    app: str | None = Query(None),
    session: str | None = Query(None),
) -> EventStatsResponse:
    return await get_stats(
        event_type=event_type,
        host=host,
        method=method,
        status=status,
        search=search,
        app=app,
        session=session,
    )


@router.get("/events/{event_id}", response_model=EventDetail)
async def get_event_api(event_id: str) -> EventDetail:
    event = await get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.get("/meta", response_model=MetaResponse)
async def get_meta_api() -> MetaResponse:
    return await get_meta()


@router.delete("/events", status_code=204)
async def clear_events_api() -> None:
    await clear_events()
