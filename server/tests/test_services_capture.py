"""Service-level tests for capture (write) functions."""

from datetime import datetime, timezone

import pytest
from traceloom_server.models import CapturedEvent
from traceloom_server.services.capture import (
    create_exception_event,
    create_http_event,
    create_http_incoming_event,
    create_log_event,
    create_test_event,
)
from traceloom_server.types import (
    ExceptionData,
    ExceptionFrame,
    HttpIncomingMeta,
    HttpIncomingRequestData,
    HttpIncomingResponseData,
    HttpMeta,
    HttpRequestData,
    HttpResponseData,
    LogData,
    TestData,
    TestFailure,
)


@pytest.mark.asyncio
async def test_create_http_event_persists_row(services_db):
    event = await create_http_event(
        event_id="550e8400-e29b-41d4-a716-446655440000",
        duration_ms=150,
        request=HttpRequestData(
            method="get",
            url="https://api.example.com/v1/test",
            headers={"Content-Type": "application/json"},
        ),
        response=HttpResponseData(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body='{"result": "success"}',
            body_size=21,
        ),
        meta=HttpMeta(library="requests"),
    )

    stored = await CapturedEvent.get(id=event.id)
    assert stored.event_type == "http"
    assert stored.summary == "GET /v1/test → 200"
    assert stored.data["event_type"] == "http"
    assert stored.data["method"] == "GET"
    assert stored.data["host"] == "api.example.com"
    assert stored.data["status_code"] == 200
    assert stored.data["duration_ms"] == 150
    assert stored.data["library"] == "requests"


@pytest.mark.asyncio
async def test_create_http_event_persists_meta_fields(services_db):
    """python_version and traceloom_version are first-class output fields."""
    event = await create_http_event(
        event_id=None,
        duration_ms=0,
        request=HttpRequestData(method="GET", url="https://x.test/", headers={}),
        response=HttpResponseData(status_code=200, headers={}),
        meta=HttpMeta(library="httpx", python_version="3.12.2", traceloom_version="0.4.0"),
    )
    stored = await CapturedEvent.get(id=event.id)
    assert stored.data["python_version"] == "3.12.2"
    assert stored.data["traceloom_version"] == "0.4.0"


@pytest.mark.asyncio
async def test_create_http_event_auto_generates_id(services_db):
    event = await create_http_event(
        event_id=None,
        duration_ms=0,
        request=HttpRequestData(method="GET", url="https://x.test/", headers={}),
        response=HttpResponseData(status_code=200, headers={}),
        meta=HttpMeta(),
    )
    assert event.id is not None
    assert str(event.id)


@pytest.mark.asyncio
async def test_create_http_event_uppercases_method(services_db):
    event = await create_http_event(
        event_id=None,
        duration_ms=0,
        request=HttpRequestData(method="post", url="https://x.test/", headers={}),
        response=HttpResponseData(status_code=201, headers={}),
        meta=HttpMeta(),
    )
    stored = await CapturedEvent.get(id=event.id)
    assert stored.data["method"] == "POST"
    assert "POST" in stored.summary


@pytest.mark.asyncio
async def test_create_log_event_persists_row(services_db):
    event = await create_log_event(
        event_id=None,
        data=LogData(
            level="WARNING",
            logger_name="myapp.auth",
            message="Token expired for user 42",
            pathname="/app/auth.py",
            lineno=87,
            func_name="validate_token",
        ),
    )

    stored = await CapturedEvent.get(id=event.id)
    assert stored.event_type == "log"
    assert stored.summary == "WARNING myapp.auth: Token expired for user 42"
    assert stored.data["event_type"] == "log"
    assert stored.data["level"] == "WARNING"
    assert stored.data["pathname"] == "/app/auth.py"
    assert stored.data["lineno"] == 87


@pytest.mark.asyncio
async def test_create_log_event_truncates_long_message(services_db):
    long_msg = "x" * 500
    event = await create_log_event(
        event_id=None,
        data=LogData(level="INFO", logger_name="big", message=long_msg),
    )
    stored = await CapturedEvent.get(id=event.id)
    assert "…" in stored.summary
    assert len(stored.summary) < 250


@pytest.mark.asyncio
async def test_create_http_event_honors_client_timestamp(services_db):
    client_ts = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    event = await create_http_event(
        event_id=None,
        timestamp=client_ts,
        duration_ms=0,
        request=HttpRequestData(method="GET", url="https://x.test/", headers={}),
        response=HttpResponseData(status_code=200, headers={}),
        meta=HttpMeta(),
    )
    stored = await CapturedEvent.get(id=event.id)
    assert stored.timestamp == client_ts


@pytest.mark.asyncio
async def test_create_http_event_defaults_timestamp_to_now(services_db):
    before = datetime.now(timezone.utc)
    event = await create_http_event(
        event_id=None,
        duration_ms=0,
        request=HttpRequestData(method="GET", url="https://x.test/", headers={}),
        response=HttpResponseData(status_code=200, headers={}),
        meta=HttpMeta(),
    )
    after = datetime.now(timezone.utc)
    stored = await CapturedEvent.get(id=event.id)
    assert before <= stored.timestamp <= after


@pytest.mark.asyncio
async def test_create_exception_event_persists_row(services_db):
    event = await create_exception_event(
        event_id=None,
        data=ExceptionData(
            exc_type="ValueError",
            exc_value="invalid literal for int() with base 10: 'abc'",
            exc_module="builtins",
            traceback_text="Traceback...\nValueError: invalid\n",
            frames=[
                ExceptionFrame(
                    filename="app.py",
                    lineno=42,
                    function="main",
                    context_line="    x = int(user_input)",
                )
            ],
        ),
    )

    stored = await CapturedEvent.get(id=event.id)
    assert stored.event_type == "exception"
    assert stored.summary.startswith("ValueError: invalid literal")
    assert stored.data["event_type"] == "exception"
    assert stored.data["exc_type"] == "ValueError"
    assert stored.data["frames"][0]["filename"] == "app.py"
    assert stored.data["frames"][0]["pre_context"] == []


@pytest.mark.asyncio
async def test_create_test_event_persists_row(services_db):
    # Act
    event = await create_test_event(
        event_id="770e8400-e29b-41d4-a716-446655440000",
        data=TestData(
            framework_version="9.0.2",
            python_version="3.14.0",
            traceloom_version="0.14.1",
            run_id="run-123",
            worker_id="gw0",
            test_id="tests/test_checkout.py::test_total[usd]",
            parameter_id="usd",
            name="test_total[usd]",
            path="tests/test_checkout.py",
            line=42,
            status="failed",
            duration_ms=18.75,
            setup_duration_ms=5.25,
            call_duration_ms=12.5,
            teardown_duration_ms=1.0,
            fixtures=["currency", "db"],
            failures=[
                TestFailure(
                    phase="call",
                    exception_type="AssertionError",
                    message="assert 9 == 10",
                    traceback_text="tests/test_checkout.py:43: AssertionError",
                )
            ],
        ),
        app="shop",
        session="checkout-run",
    )

    # Assert
    stored = await CapturedEvent.get(id=event.id)
    assert stored.event_type == "test"
    assert stored.summary == "FAILED tests/test_checkout.py::test_total[usd]"
    assert stored.data["event_type"] == "test"
    assert stored.data["status"] == "failed"
    assert stored.data["parameter_id"] == "usd"
    assert stored.data["duration_ms"] == 18.75
    assert stored.data["fixtures"] == ["currency", "db"]
    assert stored.data["failures"][0]["exception_type"] == "AssertionError"
    assert stored.data["worker_id"] == "gw0"
    assert stored.data["app"] == "shop"
    assert stored.data["session"] == "checkout-run"


@pytest.mark.asyncio
async def test_create_http_incoming_event_persists_row(services_db):
    event = await create_http_incoming_event(
        event_id="660e8400-e29b-41d4-a716-446655440000",
        duration_ms=45,
        request=HttpIncomingRequestData(
            method="post",
            path="/api/users",
            url="http://localhost:8000/api/users",
            headers={"host": "localhost:8000", "content-type": "application/json"},
            body='{"name": "Alice"}',
            body_size=17,
        ),
        response=HttpIncomingResponseData(
            status_code=201,
            headers={"content-type": "application/json"},
            body='{"id": 1}',
            body_size=10,
        ),
        meta=HttpIncomingMeta(
            framework="fastapi",
            route="/api/users",
            client_ip="127.0.0.1",
        ),
    )

    stored = await CapturedEvent.get(id=event.id)
    assert stored.event_type == "http_incoming"
    assert stored.summary == "← POST /api/users → 201"
    assert stored.data["event_type"] == "http_incoming"
    assert stored.data["method"] == "POST"
    assert stored.data["host"] == "localhost:8000"
    assert stored.data["path"] == "/api/users"
    assert stored.data["framework"] == "fastapi"
    assert stored.data["route"] == "/api/users"
    assert stored.data["client_ip"] == "127.0.0.1"
    assert stored.data["duration_ms"] == 45


@pytest.mark.asyncio
async def test_create_http_incoming_event_auto_generates_id(services_db):
    event = await create_http_incoming_event(
        event_id=None,
        duration_ms=0,
        request=HttpIncomingRequestData(
            method="GET", path="/", url="http://x.test/", headers={}
        ),
        response=HttpIncomingResponseData(status_code=200, headers={}),
        meta=HttpIncomingMeta(),
    )
    assert event.id is not None


@pytest.mark.asyncio
async def test_create_http_incoming_event_uppercases_method(services_db):
    event = await create_http_incoming_event(
        event_id=None,
        duration_ms=0,
        request=HttpIncomingRequestData(
            method="get", path="/health", url="http://x.test/health", headers={}
        ),
        response=HttpIncomingResponseData(status_code=200, headers={}),
        meta=HttpIncomingMeta(),
    )
    stored = await CapturedEvent.get(id=event.id)
    assert stored.data["method"] == "GET"
    assert "GET" in stored.summary
