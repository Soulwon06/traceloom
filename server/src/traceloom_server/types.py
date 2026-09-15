"""Shared Pydantic types for captured events.

Two layers:

- **Input** models — what clients POST to
  `/api/capture/{http,http_incoming,test,log,exception}`.
  Open (``extra="allow"``) where it matters so older/forward clients can send
  unrecognized fields without rejection.
- **Output** models — what the server stores in ``CapturedEvent.data`` and
  returns from ``/api/events/{id}``. Closed (no extras) so the generated
  TypeScript types are tight. Each carries a ``Literal[...] event_type``
  discriminator and the union ``EventData`` is what the read API exposes.
"""

from datetime import datetime
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

TraceId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
SpanId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{16}$")]
RuntimeRole = Literal["operation", "annotation"]
RuntimeOrigin = Literal["traceloom", "otel"]


class RuntimeCorrelation(BaseModel):
    """Runtime identity owned or referenced by one captured event."""

    model_config = ConfigDict(frozen=True)

    trace_id: TraceId
    span_id: SpanId
    parent_span_id: SpanId | None = None
    role: RuntimeRole
    origin: RuntimeOrigin = "traceloom"

    @field_validator("trace_id", "span_id", "parent_span_id")
    @classmethod
    def _reject_zero_id(cls, value: str | None) -> str | None:
        if value is not None and int(value, 16) == 0:
            raise ValueError("trace and span IDs must not be all zero")
        return value

    @model_validator(mode="after")
    def _validate_parent(self) -> Self:
        if self.role == "annotation" and self.parent_span_id is not None:
            raise ValueError("annotations cannot have parent_span_id")
        if self.parent_span_id == self.span_id:
            raise ValueError("an operation cannot be its own parent")
        return self


class GroupReference(BaseModel):
    """Stable group identity and its display label."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)


class PytestGroupMembership(BaseModel):
    """Position in pytest's collection hierarchy."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["pytest"] = "pytest"
    test_directory: GroupReference | None = None
    test_file: GroupReference
    test_class: GroupReference | None = None
    test_case: GroupReference


class HttpRequestGroupMembership(BaseModel):
    """Position in the outgoing HTTP target hierarchy."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["http_request"] = "http_request"
    hostname: GroupReference


GroupMembership = Annotated[
    PytestGroupMembership | HttpRequestGroupMembership,
    Field(discriminator="kind"),
]


class EventHierarchy(BaseModel):
    """Runtime correlation and grouping context captured with one event."""

    model_config = ConfigDict(frozen=True)

    runtime: RuntimeCorrelation | None = None
    group_memberships: tuple[GroupMembership, ...] = ()

    @model_validator(mode="after")
    def _validate_hierarchy(self) -> Self:
        if self.runtime is None and not self.group_memberships:
            raise ValueError("hierarchy must contain runtime or group memberships")

        kinds = [membership.kind for membership in self.group_memberships]
        if len(kinds) != len(set(kinds)):
            raise ValueError("group membership kinds must be unique")

        return self


class HttpOperationError(BaseModel):
    """Exception raised by an outgoing HTTP operation."""

    type: str = Field(min_length=1)
    message: str = ""
    module: str | None = None


# --- Input models (capture endpoints) ---


class HttpRequestData(BaseModel):
    method: str
    url: str
    headers: dict[str, str]
    body: str | None = None
    body_size: int = 0


class HttpResponseData(BaseModel):
    status_code: int
    headers: dict[str, str]
    body: str | None = None
    body_size: int = 0


class HttpMeta(BaseModel):
    library: str = "unknown"
    python_version: str = ""
    traceloom_version: str = ""


class LogData(BaseModel):
    level: str
    logger_name: str
    message: str
    pathname: str | None = None
    lineno: int | None = None
    func_name: str | None = None
    exc_text: str | None = None
    extra: dict[str, Any] | None = None
    # Allow arbitrary additional fields the client may send.
    model_config = {"extra": "allow"}


class ExceptionFrame(BaseModel):
    filename: str
    lineno: int | None = None
    function: str | None = None
    context_line: str | None = None
    pre_context: list[str] = []
    post_context: list[str] = []


class ExceptionData(BaseModel):
    exc_type: str
    exc_value: str = ""
    exc_module: str | None = None
    traceback_text: str = ""
    frames: list[ExceptionFrame] = []
    model_config = {"extra": "allow"}


TestStatus = Literal["passed", "failed", "error", "skipped", "xfailed", "xpassed"]
TestPhase = Literal["setup", "call", "teardown"]


class TestFailure(BaseModel):
    __test__: ClassVar[bool] = False

    phase: TestPhase
    exception_type: str | None = None
    message: str = ""
    traceback_text: str = ""


class TestData(BaseModel):
    __test__: ClassVar[bool] = False

    framework: str = "pytest"
    framework_version: str = ""
    python_version: str = ""
    traceloom_version: str = ""
    run_id: str
    worker_id: str = "master"
    test_id: str
    parameter_id: str | None = None
    name: str
    path: str
    line: int | None = None
    status: TestStatus
    duration_ms: float
    setup_duration_ms: float = 0
    call_duration_ms: float = 0
    teardown_duration_ms: float = 0
    fixtures: list[str] = []
    failures: list[TestFailure] = []
    model_config = {"extra": "allow"}


# --- Output models (read API + storage) ---


class HttpEventData(BaseModel):
    """HTTP capture as stored and served. Flat by convention."""

    event_type: Literal["http"] = "http"
    app: str = ""
    session: str = ""
    duration_ms: int
    method: str
    url: str
    host: str
    request_headers: dict[str, str]
    request_body: str | None = None
    request_body_size: int = 0
    status_code: int | None = None
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_body: str | None = None
    response_body_size: int = 0
    error: HttpOperationError | None = None
    library: str = "unknown"
    python_version: str = ""
    traceloom_version: str = ""


class LogEventData(BaseModel):
    event_type: Literal["log"] = "log"
    app: str = ""
    session: str = ""
    level: str
    logger_name: str
    message: str
    pathname: str | None = None
    lineno: int | None = None
    func_name: str | None = None
    exc_text: str | None = None
    extra: dict[str, Any] | None = None


class ExceptionEventData(BaseModel):
    event_type: Literal["exception"] = "exception"
    app: str = ""
    session: str = ""
    exc_type: str
    exc_value: str = ""
    exc_module: str | None = None
    traceback_text: str = ""
    frames: list[ExceptionFrame] = []


class TestEventData(BaseModel):
    __test__: ClassVar[bool] = False

    event_type: Literal["test"] = "test"
    app: str = ""
    session: str = ""
    framework: str = "pytest"
    framework_version: str = ""
    python_version: str = ""
    traceloom_version: str = ""
    run_id: str
    worker_id: str = "master"
    test_id: str
    parameter_id: str | None = None
    name: str
    path: str
    line: int | None = None
    status: TestStatus
    duration_ms: float
    setup_duration_ms: float = 0
    call_duration_ms: float = 0
    teardown_duration_ms: float = 0
    fixtures: list[str] = []
    failures: list[TestFailure] = []


class HttpIncomingRequestData(BaseModel):
    method: str
    path: str
    url: str
    headers: dict[str, str]
    body: str | None = None
    body_size: int = 0


class HttpIncomingResponseData(BaseModel):
    status_code: int
    headers: dict[str, str]
    body: str | None = None
    body_size: int = 0


class HttpIncomingMeta(BaseModel):
    framework: str = "unknown"
    route: str | None = None
    client_ip: str | None = None
    exc_type: str | None = None
    exc_value: str | None = None
    python_version: str = ""
    traceloom_version: str = ""


class HttpIncomingEventData(BaseModel):
    """Incoming HTTP request as stored and served."""

    event_type: Literal["http_incoming"] = "http_incoming"
    app: str = ""
    session: str = ""
    duration_ms: int
    method: str
    path: str
    url: str
    host: str
    route: str | None = None
    client_ip: str | None = None
    request_headers: dict[str, str]
    request_body: str | None = None
    request_body_size: int = 0
    status_code: int
    response_headers: dict[str, str]
    response_body: str | None = None
    response_body_size: int = 0
    exc_type: str | None = None
    exc_value: str | None = None
    framework: str = "unknown"
    python_version: str = ""
    traceloom_version: str = ""


EventType = Literal["http", "http_incoming", "log", "exception", "test"]

EventData = Annotated[
    HttpEventData
    | HttpIncomingEventData
    | LogEventData
    | ExceptionEventData
    | TestEventData,
    Field(discriminator="event_type"),
]


# --- API response models ---


class EventSummary(BaseModel):
    """One row of the event list.

    ``seq`` is the server's insertion-order cursor (SQLite's ``rowid``). It is
    the only ordering that survives a fast run: ``timestamp`` has one-second
    resolution on the client and the client's background worker does not
    preserve order anyway.

    ``host``, ``method`` and ``status_code`` are carried so consumers can filter
    a loaded store without going back to the server.
    """

    id: str
    seq: int
    timestamp: datetime
    event_type: EventType
    summary: str
    app: str = ""
    session: str = ""
    host: str | None = None
    method: str | None = None
    status_code: int | None = None
    hierarchy: EventHierarchy | None = None


class EventDetail(EventSummary):
    data: EventData

    @model_validator(mode="after")
    def _check_event_type_consistency(self) -> Self:
        if self.event_type != self.data.event_type:
            raise ValueError(
                f"event_type mismatch: outer={self.event_type!r},"
                f" data={self.data.event_type!r}"
            )
        return self


class EventListResponse(BaseModel):
    """A page of events plus the cursor state needed to follow the tail.

    ``epoch`` changes whenever stored rows are removed wholesale (clear-all,
    retention prune, server restart). A client whose cached ``epoch`` no longer
    matches must drop its store and resync.

    ``max_seq`` is the largest ``seq`` in the table matching the non-cursor
    filters — not merely the largest on this page. A delta whose page tops out
    below ``max_seq`` was truncated by ``limit``; poll again immediately.
    """

    epoch: str
    max_seq: int
    events: list[EventSummary]


class EventIdsResponse(BaseModel):
    """Matching event IDs only — the payload for server-side body search."""

    epoch: str
    ids: list[str]


class EventStatsResponse(BaseModel):
    """Aggregate counts for a filter, so consumers need not download the rows."""

    epoch: str
    max_seq: int
    total: int
    by_event_type: dict[str, int]
    by_test_status: dict[str, int]
    by_status_class: dict[str, int]


class MetaResponse(BaseModel):
    server_version: str
    hosts: list[str]
    methods: list[str]
    event_types: list[EventType]
    apps: list[str]
    sessions: list[str]
