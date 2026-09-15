"""Tests for traceloom.transport."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import traceloom.transport as transport
from traceloom.hierarchy import (
    GroupReference,
    HttpRequestGroupMembership,
    activate_context,
    start_root,
)
from traceloom.transport import (
    _json_default,
    flush,
    send_exception,
    send_http,
    send_log,
    send_test,
    shutdown,
    start_worker,
)


class CaptureHandler(BaseHTTPRequestHandler):
    captured: list = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        CaptureHandler.captured.append({"path": self.path, "body": body})
        self.send_response(201)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format, *args):
        pass


@pytest.fixture()
def capture_server():
    """Start a minimal HTTP server that records POSTed payloads."""
    CaptureHandler.captured = []
    server = HTTPServer(("127.0.0.1", 0), CaptureHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}", CaptureHandler.captured
    server.shutdown()


def _wait(captured, n, timeout=5.0):
    deadline = time.monotonic() + timeout
    while len(captured) < n and time.monotonic() < deadline:
        time.sleep(0.05)


def test_send_http_posts_to_capture_http(capture_server):
    url, captured = capture_server
    start_worker(url)

    send_http(
        {
            "id": "test-transport-1",
            "request": {"method": "GET", "url": "https://example.com"},
            "response": {"status_code": 200},
        }
    )

    _wait(captured, 1)
    assert len(captured) == 1
    assert captured[0]["path"] == "/api/capture/http"
    assert captured[0]["body"]["id"] == "test-transport-1"


def test_send_log_posts_to_capture_log(capture_server):
    url, captured = capture_server
    start_worker(url)

    send_log(
        {
            "id": "log-1",
            "data": {"level": "WARNING", "logger_name": "x", "message": "hi"},
        }
    )

    _wait(captured, 1)
    assert captured[0]["path"] == "/api/capture/log"
    assert captured[0]["body"]["id"] == "log-1"
    assert captured[0]["body"]["data"]["message"] == "hi"


def test_send_test_posts_to_capture_test(capture_server):
    # Arrange
    url, captured = capture_server
    start_worker(url)

    # Act
    send_test(
        {
            "id": "test-1",
            "data": {
                "run_id": "run-1",
                "test_id": "tests/test_app.py::test_ok",
                "name": "test_ok",
                "path": "tests/test_app.py",
                "status": "passed",
                "duration_ms": 1.25,
            },
        }
    )

    # Assert
    _wait(captured, 1)
    assert captured[0]["path"] == "/api/capture/test"
    assert captured[0]["body"]["id"] == "test-1"
    assert captured[0]["body"]["data"]["status"] == "passed"


def test_send_exception_posts_to_capture_exception(capture_server):
    url, captured = capture_server
    start_worker(url)

    send_exception(
        {
            "id": "exc-1",
            "data": {"exc_type": "ValueError", "exc_value": "bad"},
        }
    )

    _wait(captured, 1)
    assert captured[0]["path"] == "/api/capture/exception"
    assert captured[0]["body"]["id"] == "exc-1"
    assert captured[0]["body"]["data"]["exc_type"] == "ValueError"


def test_flush_waits_for_pending_payloads(capture_server):
    url, captured = capture_server
    start_worker(url)

    for i in range(5):
        send_http({"id": f"flush-{i}", "request": {}, "response": {}})

    result = flush(timeout=5.0)

    assert result is True
    assert len(captured) == 5


def test_flush_returns_true_when_queue_already_empty(capture_server):
    url, _captured = capture_server
    start_worker(url)

    result = flush(timeout=1.0)
    assert result is True


def test_shutdown_flushes(capture_server):
    url, captured = capture_server
    start_worker(url)

    send_http({"id": "shutdown-1", "request": {}, "response": {}})

    result = shutdown(timeout=5.0)

    assert result is True
    assert len(captured) == 1


def test_flush_forces_in_flight_drain_fallback(monkeypatch):
    """Flush can take over a dequeued item without double task accounting."""
    item = ("/api/capture/http", {"id": "in-flight-drain"})
    sent = []
    fallback_calls = []
    original_drain = transport._drain_pending

    def record_send(path, payload, *, timeout=5.0):
        sent.append((path, payload))

    def record_fallback(timeout):
        fallback_calls.append(timeout)
        return original_drain(timeout)

    monkeypatch.setattr(transport, "_send_to_server", record_send)
    monkeypatch.setattr(transport, "_drain_pending", record_fallback)
    transport._queue.put_nowait(item)
    transport._queue.get_nowait()
    with transport._in_flight_lock:
        transport._in_flight = item

    try:
        assert transport.flush(timeout=0.01) is True
        assert fallback_calls == [0.01]
        assert sent == [item]
        assert transport._queue.unfinished_tasks == 0
    finally:
        with transport._in_flight_lock:
            transport._in_flight = None
        if transport._queue.unfinished_tasks:
            transport._queue.task_done()


# ---------------------------------------------------------------------------
# _json_default() — fallback serializer
# ---------------------------------------------------------------------------


def test_json_default_handles_bytes():
    assert _json_default(b"\x00\x01\x02") == "b'\\x00\\x01\\x02'"


def test_json_default_handles_arbitrary_objects():
    class Custom:
        def __repr__(self):
            return "Custom()"

    assert _json_default(Custom()) == "Custom()"


def test_json_default_survives_broken_repr():
    class Broken:
        def __repr__(self):
            raise RuntimeError("boom")

    assert _json_default(Broken()) == "<unserializable>"


def test_json_dumps_with_default_serializes_bytes():
    """bytes in a payload dict should serialize via the fallback."""
    payload = {"headers": {"x-bin": b"\n\x02"}, "body": "ok"}
    result = json.loads(json.dumps(payload, default=_json_default))
    assert isinstance(result["headers"]["x-bin"], str)


def test_send_http_payload_with_bytes(capture_server):
    """Payloads containing bytes should not crash the transport."""
    url, captured = capture_server
    start_worker(url)

    send_http({"id": "bytes-test", "headers": {"bin": b"\xff"}, "response": {}})

    _wait(captured, 1)
    assert len(captured) == 1
    assert captured[0]["body"]["id"] == "bytes-test"


def test_app_and_session_injected_into_payload(capture_server):
    url, captured = capture_server
    start_worker(url, app="myapp", session="sess-1")

    send_http({"id": "app-test", "request": {}, "response": {}})
    _wait(captured, 1)

    body = captured[0]["body"]
    assert body["app"] == "myapp"
    assert body["session"] == "sess-1"


def test_app_and_session_injected_into_all_event_types(capture_server):
    url, captured = capture_server
    start_worker(url, app="multi", session="s2")

    send_http({"id": "h1"})
    send_log(
        {"id": "l1", "data": {"level": "INFO", "logger_name": "x", "message": "m"}}
    )
    send_test(
        {
            "id": "t1",
            "data": {
                "run_id": "r1",
                "test_id": "test_x",
                "name": "test_x",
                "path": "test_x.py",
                "status": "passed",
                "duration_ms": 1,
            },
        }
    )
    send_exception({"id": "e1", "data": {"exc_type": "E", "exc_value": "v"}})

    _wait(captured, 4)

    for item in captured:
        assert item["body"]["app"] == "multi"
        assert item["body"]["session"] == "s2"


def test_app_and_session_default_to_empty(capture_server):
    url, captured = capture_server
    start_worker(url)

    send_http({"id": "default-test"})
    _wait(captured, 1)

    assert captured[0]["body"]["app"] == ""
    assert captured[0]["body"]["session"] == ""


def test_transport_snapshots_active_context_on_caller_thread(capture_server):
    # Arrange
    url, captured = capture_server
    start_worker(url)
    context = start_root(
        trace_id="1" * 32,
        span_id="a" * 16,
        memberships=(
            HttpRequestGroupMembership(
                hostname=GroupReference(id="api.example.com", label="api.example.com")
            ),
        ),
    )

    # Act
    with activate_context(context):
        send_log(
            {
                "id": "context-log",
                "data": {"level": "INFO", "logger_name": "app", "message": "hi"},
            }
        )

    # Assert
    _wait(captured, 1)
    runtime = captured[0]["body"]["hierarchy"]["runtime"]
    assert runtime == {
        "trace_id": "1" * 32,
        "span_id": "a" * 16,
        "parent_span_id": None,
        "role": "annotation",
        "origin": "traceloom",
    }
    assert captured[0]["body"]["hierarchy"]["group_memberships"] == [
        {
            "hostname": {"id": "api.example.com", "label": "api.example.com"},
            "kind": "http_request",
        }
    ]


def test_uninstrumented_operation_does_not_reuse_active_span(capture_server):
    # Arrange
    url, captured = capture_server
    start_worker(url)
    context = start_root(trace_id="1" * 32, span_id="a" * 16)

    # Act
    with activate_context(context):
        send_http({"id": "uncorrelated-http"})

    # Assert
    _wait(captured, 1)
    assert "hierarchy" not in captured[0]["body"]


def test_explicit_detached_context_replaces_active_context(capture_server):
    # Arrange
    url, captured = capture_server
    start_worker(url)
    active = start_root(trace_id="1" * 32, span_id="a" * 16)
    detached = start_root(trace_id="2" * 32, span_id="b" * 16)

    # Act
    with activate_context(active):
        send_test(
            {"id": "detached", "data": {"test_id": "test_detached"}},
            context=detached,
        )

    # Assert
    _wait(captured, 1)
    runtime = captured[0]["body"]["hierarchy"]["runtime"]
    assert runtime["trace_id"] == "2" * 32
    assert runtime["span_id"] == "b" * 16
    assert runtime["role"] == "operation"
