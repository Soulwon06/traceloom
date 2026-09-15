"""Tests for traceloom.integrations.fastapi — TraceLoomMiddleware."""

from unittest.mock import patch

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi import FastAPI  # noqa: E402
from traceloom.config import TraceLoomConfig  # noqa: E402
from traceloom.hierarchy import (  # noqa: E402
    activate_context,
    current_context,
    start_root,
)
from traceloom.integrations.fastapi import TraceLoomMiddleware  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.routing import WebSocketRoute  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocket  # noqa: E402


@pytest.fixture()
def config():
    return TraceLoomConfig(
        server_url="http://traceloom:5110",
        redact_headers=["authorization"],
    )


@pytest.fixture()
def captured(config):
    """Patch traceloom._config and collect send_http_incoming payloads."""

    class Captures(list):
        contexts: list = []

    payloads = Captures()

    def record(payload, *, context=None):
        payloads.append(payload)
        payloads.contexts.append(context)

    with (
        patch("traceloom._config", config),
        patch(
            "traceloom.integrations.fastapi.send_http_incoming",
            side_effect=record,
        ),
    ):
        yield payloads


def _make_app():
    app = FastAPI()
    app.add_middleware(TraceLoomMiddleware)

    @app.get("/hello")
    def hello():
        return {"message": "world"}

    @app.post("/echo")
    async def echo(body: dict):
        return body

    @app.get("/error")
    def error():
        raise ValueError("boom")

    return app


@pytest.fixture()
def app():
    return _make_app()


@pytest.fixture()
def client(app):
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc


def test_captures_basic_get(captured, client):
    resp = client.get("/hello")
    assert resp.status_code == 200

    assert len(captured) == 1
    payload = captured[0]
    assert payload["request"]["method"] == "GET"
    assert payload["request"]["path"] == "/hello"
    assert payload["response"]["status_code"] == 200
    assert payload["duration_ms"] >= 0
    assert payload["meta"]["framework"] == "fastapi"
    assert captured.contexts[0].operation.parent_span_id is None


def test_incoming_request_is_child_of_active_context(captured, client):
    parent = start_root(trace_id="1" * 32, span_id="2" * 16)

    with activate_context(parent):
        client.get("/hello")
        assert current_context() is parent

    context = captured.contexts[0]
    assert context.operation.trace_id == parent.operation.trace_id
    assert context.operation.parent_span_id == parent.operation.span_id
    assert current_context() is None


def test_url_uses_host_header_over_server(captured, client):
    client.get("/hello")
    payload = captured[0]
    assert "testserver" in payload["request"]["url"]


def test_payload_includes_timestamp(captured, client):
    client.get("/hello")
    payload = captured[0]
    assert "timestamp" in payload
    assert "T" in payload["timestamp"]


def test_captures_request_body(captured, client):
    resp = client.post("/echo", json={"key": "value"})
    assert resp.status_code == 200

    payload = captured[0]
    assert '"key"' in payload["request"]["body"]
    assert payload["request"]["body_size"] > 0


def test_captures_response_body(captured, client):
    client.get("/hello")
    payload = captured[0]
    assert '"message"' in payload["response"]["body"]
    assert payload["response"]["body_size"] > 0


def test_redacts_query_params(captured, config, client):
    config.redact_query_params = ["token"]
    client.get("/hello?token=secret&page=1")
    payload = captured[0]
    assert "secret" not in payload["request"]["url"]
    assert "REDACTED" in payload["request"]["url"]
    assert "page=1" in payload["request"]["url"]


def test_redacts_headers(captured, client):
    client.get("/hello", headers={"Authorization": "Bearer secret123"})
    payload = captured[0]
    auth_values = [
        v
        for k, v in payload["request"]["headers"].items()
        if k.lower() == "authorization"
    ]
    assert all(v == "[REDACTED]" for v in auth_values)


def test_captures_exception_info(captured, client):
    exception_calls: list[tuple] = []
    with patch(
        "traceloom.integrations.fastapi.capture_exception",
        side_effect=lambda *args: exception_calls.append(args),
    ):
        resp = client.get("/error")
    assert resp.status_code == 500

    exc_payloads = [p for p in captured if p["meta"]["exc_type"] is not None]
    assert len(exc_payloads) == 1
    payload = exc_payloads[0]
    assert payload["meta"]["exc_type"] == "ValueError"
    assert payload["meta"]["exc_value"] == "boom"
    assert payload["response"]["status_code"] == 500

    assert len(exception_calls) == 1
    exc_type, exc_value, exc_tb = exception_calls[0]
    assert exc_type is ValueError
    assert str(exc_value) == "boom"
    assert exc_tb is not None


def test_no_capture_when_config_is_none(client):
    """When traceloom is not initialized, middleware is a no-op."""
    payloads: list[dict] = []
    with (
        patch("traceloom._config", None),
        patch(
            "traceloom.integrations.fastapi.send_http_incoming",
            side_effect=payloads.append,
        ),
    ):
        resp = client.get("/hello")
        assert resp.status_code == 200
        assert len(payloads) == 0


def test_websocket_passthrough(captured):
    """Non-HTTP scopes pass through without capture."""

    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        await ws.send_text("hi")
        await ws.close()

    app = Starlette(routes=[WebSocketRoute("/ws", ws_endpoint)])
    app.add_middleware(TraceLoomMiddleware)

    with TestClient(app) as tc:
        with tc.websocket_connect("/ws") as ws:
            data = ws.receive_text()
            assert data == "hi"

    assert len(captured) == 0


# --- ignore_paths ---


def _make_app_with_ignore_paths(ignore_paths):
    app = FastAPI()
    app.add_middleware(TraceLoomMiddleware, ignore_paths=ignore_paths)

    @app.get("/hello")
    def hello():
        return {"message": "world"}

    @app.get("/docs/extra")
    def docs_extra():
        return {"docs": True}

    return app


def test_ignore_paths_skips_capture(captured):
    app = _make_app_with_ignore_paths(["/docs"])
    with TestClient(app) as tc:
        resp = tc.get("/docs/extra")
        assert resp.status_code == 200
    assert len(captured) == 0


def test_ignore_paths_prefix_match(captured):
    app = _make_app_with_ignore_paths(["/docs"])
    with TestClient(app) as tc:
        tc.get("/docs/extra")
    assert len(captured) == 0


def test_ignore_paths_does_not_affect_other_routes(captured):
    app = _make_app_with_ignore_paths(["/docs"])
    with TestClient(app) as tc:
        tc.get("/hello")
    assert len(captured) == 1
    assert captured[0]["request"]["path"] == "/hello"


def test_ignore_paths_empty_list(captured):
    app = _make_app_with_ignore_paths([])
    with TestClient(app) as tc:
        tc.get("/hello")
    assert len(captured) == 1
