"""Route-level tests for the API endpoints.

These tests verify HTTP wiring only — Pydantic validation, status codes,
and that each route reaches the right service. Persistence and filter
behavior live in `test_services_*`.
"""

from fastapi.testclient import TestClient
from traceloom_server.types import (
    EventDetail,
    ExceptionEventData,
    HttpEventData,
    HttpIncomingEventData,
    LogEventData,
    TestEventData,
)


def _events(client: TestClient, query: str = "") -> list[dict]:
    """Return just the rows from the `GET /api/events` envelope."""
    return client.get(f"/api/events{query}").json()["events"]


# --- Typed capture endpoints ---


def test_capture_http_returns_201(client, http_payload):
    resp = client.post("/api/capture/http", json=http_payload)
    assert resp.status_code == 201
    assert resp.json() == {"status": "ok"}

    events = _events(client)
    assert len(events) == 1
    assert events[0]["event_type"] == "http"


def test_capture_http_requires_request_and_response(client):
    resp = client.post("/api/capture/http", json={"duration_ms": 0})
    assert resp.status_code == 422


def test_capture_log_returns_201(client, log_payload):
    resp = client.post("/api/capture/log", json=log_payload)
    assert resp.status_code == 201

    events = _events(client)
    assert events[0]["event_type"] == "log"


def test_capture_log_requires_data(client):
    resp = client.post("/api/capture/log", json={})
    assert resp.status_code == 422


def test_capture_exception_returns_201(client, exception_payload):
    resp = client.post("/api/capture/exception", json=exception_payload)
    assert resp.status_code == 201

    events = _events(client)
    assert events[0]["event_type"] == "exception"


def test_capture_exception_requires_data(client):
    resp = client.post("/api/capture/exception", json={})
    assert resp.status_code == 422


def test_capture_test_returns_201(client, test_payload):
    # Act
    response = client.post("/api/capture/test", json=test_payload)

    # Assert
    assert response.status_code == 201
    assert response.json() == {"status": "ok"}
    events = _events(client)
    assert events[0]["event_type"] == "test"
    assert events[0]["summary"] == ("FAILED tests/test_checkout.py::test_total[usd]")


def test_capture_test_requires_data(client):
    # Act
    response = client.post("/api/capture/test", json={})

    # Assert
    assert response.status_code == 422


def test_capture_http_incoming_returns_201(client, http_incoming_payload):
    resp = client.post("/api/capture/http_incoming", json=http_incoming_payload)
    assert resp.status_code == 201
    assert resp.json() == {"status": "ok"}

    events = _events(client)
    assert len(events) == 1
    assert events[0]["event_type"] == "http_incoming"


def test_capture_http_incoming_requires_request_and_response(client):
    resp = client.post("/api/capture/http_incoming", json={"duration_ms": 0})
    assert resp.status_code == 422


def test_event_detail_validates_against_typed_union_http_incoming(
    client, http_incoming_payload
):
    client.post("/api/capture/http_incoming", json=http_incoming_payload)
    event_id = _events(client)[0]["id"]
    raw = client.get(f"/api/events/{event_id}").json()
    parsed = EventDetail.model_validate(raw)
    assert isinstance(parsed.data, HttpIncomingEventData)
    assert parsed.data.method == "POST"
    assert parsed.data.path == "/api/users"
    assert parsed.data.framework == "fastapi"
    assert parsed.data.route == "/api/users"
    assert parsed.data.client_ip == "127.0.0.1"


def test_capture_endpoints_marked_deprecated_in_openapi(client):
    spec = client.get("/openapi.json").json()
    assert spec["paths"]["/api/capture"]["post"].get("deprecated") is True
    # Typed endpoints must NOT be deprecated.
    for path in (
        "/api/capture/http",
        "/api/capture/log",
        "/api/capture/exception",
        "/api/capture/test",
    ):
        assert not spec["paths"][path]["post"].get("deprecated")


# --- Deprecated HTTP-only endpoint ---


def test_deprecated_capture_accepts_http_payload(client, sample_payload):
    resp = client.post("/api/capture", json=sample_payload)
    assert resp.status_code == 201
    events = _events(client)
    assert events[0]["event_type"] == "http"


def test_deprecated_capture_rejects_payload_without_request(client):
    resp = client.post("/api/capture", json={"duration_ms": 0})
    assert resp.status_code == 422


# --- Read endpoints (smoke tests; bulk coverage in test_services_events.py) ---


def test_event_detail_returns_full_data(client, http_payload):
    client.post("/api/capture/http", json=http_payload)
    detail = client.get(f"/api/events/{http_payload['id']}").json()
    assert detail["event_type"] == "http"
    assert detail["data"]["event_type"] == "http"
    assert detail["data"]["method"] == "GET"
    assert detail["data"]["url"] == "https://api.example.com/v1/test"
    assert detail["data"]["host"] == "api.example.com"
    assert detail["data"]["status_code"] == 200


def test_event_detail_validates_against_typed_union_http(client, http_payload):
    client.post("/api/capture/http", json=http_payload)
    raw = client.get(f"/api/events/{http_payload['id']}").json()
    parsed = EventDetail.model_validate(raw)
    assert isinstance(parsed.data, HttpEventData)
    assert parsed.data.method == "GET"
    assert parsed.data.python_version == "3.12.2"
    assert parsed.data.traceloom_version == "0.1.0"


def test_event_detail_validates_against_typed_union_log(client, log_payload):
    client.post("/api/capture/log", json=log_payload)
    event_id = _events(client)[0]["id"]
    raw = client.get(f"/api/events/{event_id}").json()
    parsed = EventDetail.model_validate(raw)
    assert isinstance(parsed.data, LogEventData)
    assert parsed.data.level == "WARNING"
    assert parsed.data.logger_name == "myapp.auth"


def test_event_detail_validates_against_typed_union_exception(
    client, exception_payload
):
    client.post("/api/capture/exception", json=exception_payload)
    event_id = _events(client)[0]["id"]
    raw = client.get(f"/api/events/{event_id}").json()
    parsed = EventDetail.model_validate(raw)
    assert isinstance(parsed.data, ExceptionEventData)
    assert parsed.data.exc_type == "ValueError"
    assert parsed.data.frames[0].filename == "app.py"


def test_event_detail_validates_against_typed_union_test(client, test_payload):
    # Arrange
    client.post("/api/capture/test", json=test_payload)

    # Act
    raw = client.get(f"/api/events/{test_payload['id']}").json()
    parsed = EventDetail.model_validate(raw)

    # Assert
    assert isinstance(parsed.data, TestEventData)
    assert parsed.data.status == "failed"
    assert parsed.data.test_id == "tests/test_checkout.py::test_total[usd]"
    assert parsed.data.parameter_id == "usd"
    assert parsed.data.fixtures == ["currency", "db"]
    assert parsed.data.failures[0].exception_type == "AssertionError"


def test_openapi_schema_exposes_discriminated_union(client):
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    # Each output model is present.
    assert "HttpEventData" in schemas
    assert "LogEventData" in schemas
    assert "ExceptionEventData" in schemas
    assert "TestEventData" in schemas
    # EventDetail.data is a discriminated union by event_type.
    event_detail = schemas["EventDetail"]
    data_prop = event_detail["properties"]["data"]
    assert "discriminator" in data_prop
    assert data_prop["discriminator"]["propertyName"] == "event_type"


def test_event_not_found(client):
    resp = client.get("/api/events/550e8400-e29b-41d4-a716-446655440000")
    assert resp.status_code == 404


def test_event_detail_accepts_displayed_id(client, http_payload):
    # Arrange
    client.post("/api/capture/http", json=http_payload)

    # Act
    response = client.get(f"/api/events/{http_payload['id'][:8]}")

    # Assert
    assert response.status_code == 200
    assert response.json()["id"] == http_payload["id"]


def test_meta_endpoint(client, http_payload):
    client.post("/api/capture/http", json=http_payload)
    data = client.get("/api/meta").json()
    assert data["hosts"] == ["api.example.com"]
    assert data["methods"] == ["GET"]
    assert data["event_types"] == ["http"]


def test_clear_events(client, http_payload):
    client.post("/api/capture/http", json=http_payload)
    assert len(_events(client)) == 1
    resp = client.delete("/api/events")
    assert resp.status_code == 204
    assert _events(client) == []


# --- Cursor, envelope, and aggregate endpoints ---


def test_list_events_returns_an_envelope(client, http_payload):
    client.post("/api/capture/http", json=http_payload)

    body = client.get("/api/events").json()

    assert set(body) == {"epoch", "max_seq", "events"}
    assert body["max_seq"] == 1
    assert body["events"][0]["seq"] == 1


def test_after_seq_returns_only_newer_events(client, http_payload, make_payload):
    client.post("/api/capture/http", json=http_payload)
    baseline = client.get("/api/events").json()["max_seq"]
    client.post("/api/capture/http", json=make_payload(url="https://a.test/second"))

    body = client.get(f"/api/events?after_seq={baseline}").json()

    assert len(body["events"]) == 1
    assert body["events"][0]["summary"].endswith("/second → 200")


def test_after_seq_with_include_ancestors_returns_400(client):
    resp = client.get("/api/events?after_seq=1&include_ancestors=true")

    assert resp.status_code == 400
    assert "include_ancestors" in resp.json()["detail"]


def test_events_limit_accepts_ten_thousand(client):
    assert client.get("/api/events?limit=10000").status_code == 200
    assert client.get("/api/events?limit=10001").status_code == 422


def test_event_ids_endpoint_is_not_matched_as_an_event_id(client, http_payload):
    client.post("/api/capture/http", json=http_payload)

    body = client.get("/api/events/ids").json()

    assert body["ids"] == [http_payload["id"]]
    assert "epoch" in body


def test_event_stats_endpoint_is_not_matched_as_an_event_id(client, http_payload):
    client.post("/api/capture/http", json=http_payload)

    body = client.get("/api/events/stats").json()

    assert body["total"] == 1
    assert body["by_event_type"] == {"http": 1}
    assert body["by_status_class"] == {"2xx": 1}
    assert body["max_seq"] == 1


def test_clearing_events_changes_the_epoch(client, http_payload):
    client.post("/api/capture/http", json=http_payload)
    before = client.get("/api/events").json()["epoch"]

    client.delete("/api/events")

    assert client.get("/api/events").json()["epoch"] != before


# --- App and session filtering ---


def test_capture_http_with_app_and_session(client, http_payload):
    http_payload["app"] = "myapp"
    http_payload["session"] = "sess-1"
    client.post("/api/capture/http", json=http_payload)

    detail = client.get(f"/api/events/{http_payload['id']}").json()
    assert detail["app"] == "myapp"
    assert detail["session"] == "sess-1"
    assert detail["data"]["app"] == "myapp"
    assert detail["data"]["session"] == "sess-1"


def test_capture_log_with_app_and_session(client, log_payload):
    log_payload["app"] = "backend"
    log_payload["session"] = "sess-2"
    client.post("/api/capture/log", json=log_payload)

    events = _events(client)
    event_id = events[0]["id"]
    detail = client.get(f"/api/events/{event_id}").json()
    assert detail["app"] == "backend"
    assert detail["session"] == "sess-2"


def test_filter_events_by_app(client, http_payload):
    http_payload["app"] = "frontend"
    client.post("/api/capture/http", json=http_payload)

    payload2 = {**http_payload, "id": None, "app": "backend"}
    client.post("/api/capture/http", json=payload2)

    events = _events(client, "?app=frontend")
    assert len(events) == 1
    assert events[0]["app"] == "frontend"


def test_filter_events_by_empty_app(client, http_payload):
    client.post("/api/capture/http", json=http_payload)

    payload2 = {**http_payload, "id": None, "app": "myapp"}
    client.post("/api/capture/http", json=payload2)

    events = _events(client, "?app=")
    assert len(events) == 1
    assert events[0]["app"] == ""


def test_filter_events_by_session(client, http_payload):
    http_payload["session"] = "debug-payment"
    client.post("/api/capture/http", json=http_payload)

    payload2 = {**http_payload, "id": None, "session": "debug-auth"}
    client.post("/api/capture/http", json=payload2)

    events = _events(client, "?session=debug-payment")
    assert len(events) == 1
    assert events[0]["session"] == "debug-payment"


def test_no_app_param_returns_all(client, http_payload):
    http_payload["app"] = "myapp"
    client.post("/api/capture/http", json=http_payload)

    payload2 = {**http_payload, "id": None, "app": ""}
    client.post("/api/capture/http", json=payload2)

    events = _events(client)
    assert len(events) == 2


def test_meta_includes_apps_and_sessions(client, http_payload):
    http_payload["app"] = "myapp"
    http_payload["session"] = "sess-1"
    client.post("/api/capture/http", json=http_payload)

    meta = client.get("/api/meta").json()
    assert "myapp" in meta["apps"]
    assert "sess-1" in meta["sessions"]


def test_event_summary_includes_app_and_session(client, http_payload):
    http_payload["app"] = "myapp"
    http_payload["session"] = "sess-1"
    client.post("/api/capture/http", json=http_payload)

    events = _events(client)
    assert events[0]["app"] == "myapp"
    assert events[0]["session"] == "sess-1"
