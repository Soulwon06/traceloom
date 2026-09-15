"""Contract tests for event hierarchy capture and read models."""

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from traceloom_server.models import CapturedEvent
from traceloom_server.routes.api import HttpCapturePayload
from traceloom_server.services.capture import create_http_event
from traceloom_server.services.events import get_event, list_events
from traceloom_server.types import (
    EventHierarchy,
    GroupReference,
    HttpMeta,
    HttpRequestData,
    HttpRequestGroupMembership,
    HttpResponseData,
    PytestGroupMembership,
    RuntimeCorrelation,
)

TRACE_ID = "11111111111111111111111111111111"
SPAN_ID = "aaaaaaaaaaaaaaaa"
PARENT_SPAN_ID = "bbbbbbbbbbbbbbbb"


def _events(client: TestClient, query: str = "") -> list[dict]:
    """Return just the rows from the `GET /api/events` envelope."""
    return client.get(f"/api/events{query}").json()["events"]


@pytest.fixture()
def hierarchy_payload() -> dict[str, object]:
    return {
        "runtime": {
            "trace_id": TRACE_ID,
            "span_id": SPAN_ID,
            "parent_span_id": None,
            "role": "operation",
            "origin": "traceloom",
        },
        "group_memberships": [
            {
                "kind": "pytest",
                "test_directory": {"id": "tests", "label": "tests"},
                "test_file": {
                    "id": "tests/test_checkout.py",
                    "label": "test_checkout.py",
                },
                "test_class": None,
                "test_case": {
                    "id": "tests/test_checkout.py::test_total",
                    "label": "test_total",
                },
            }
        ],
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trace_id", "1" * 31),
        ("trace_id", "A" * 32),
        ("trace_id", "0" * 32),
        ("span_id", "a" * 15),
        ("span_id", "A" * 16),
        ("span_id", "0" * 16),
        ("parent_span_id", "0" * 16),
    ],
)
def test_runtime_correlation_rejects_invalid_ids(field, value):
    # Arrange
    payload = {
        "trace_id": TRACE_ID,
        "span_id": SPAN_ID,
        "parent_span_id": PARENT_SPAN_ID,
        "role": "operation",
    }
    payload[field] = value

    # Act / Assert
    with pytest.raises(ValidationError):
        RuntimeCorrelation.model_validate(payload)


def test_runtime_correlation_rejects_parent_for_annotation():
    # Act / Assert
    with pytest.raises(ValidationError, match="annotations cannot have parent_span_id"):
        RuntimeCorrelation(
            trace_id=TRACE_ID,
            span_id=SPAN_ID,
            parent_span_id=PARENT_SPAN_ID,
            role="annotation",
        )


def test_runtime_correlation_rejects_own_span_as_parent():
    # Act / Assert
    with pytest.raises(ValidationError, match="operation cannot be its own parent"):
        RuntimeCorrelation(
            trace_id=TRACE_ID,
            span_id=SPAN_ID,
            parent_span_id=SPAN_ID,
            role="operation",
        )


def test_event_hierarchy_rejects_empty_object():
    # Act / Assert
    with pytest.raises(
        ValidationError,
        match="hierarchy must contain runtime or group memberships",
    ):
        EventHierarchy()


def test_event_hierarchy_rejects_duplicate_membership_kinds():
    # Arrange
    hostname = GroupReference(id="api.stripe.com", label="api.stripe.com")

    # Act / Assert
    with pytest.raises(ValidationError, match="membership kinds must be unique"):
        EventHierarchy(
            group_memberships=(
                HttpRequestGroupMembership(hostname=hostname),
                HttpRequestGroupMembership(hostname=hostname),
            )
        )


def test_event_hierarchy_accepts_runtime_and_multiple_membership_kinds():
    # Act
    hierarchy = EventHierarchy(
        runtime=RuntimeCorrelation(
            trace_id=TRACE_ID,
            span_id=SPAN_ID,
            role="operation",
        ),
        group_memberships=(
            PytestGroupMembership(
                test_directory=GroupReference(id="tests", label="tests"),
                test_file=GroupReference(
                    id="tests/test_checkout.py", label="test_checkout.py"
                ),
                test_class=None,
                test_case=GroupReference(
                    id="tests/test_checkout.py::test_total", label="test_total"
                ),
            ),
            HttpRequestGroupMembership(
                hostname=GroupReference(id="api.stripe.com", label="api.stripe.com")
            ),
        ),
    )

    # Assert
    assert [membership.kind for membership in hierarchy.group_memberships] == [
        "pytest",
        "http_request",
    ]


@pytest.mark.parametrize(
    "endpoint,payload_fixture",
    [
        ("/api/capture/http", "http_payload"),
        ("/api/capture/http_incoming", "http_incoming_payload"),
        ("/api/capture/log", "log_payload"),
        ("/api/capture/exception", "exception_payload"),
        ("/api/capture/test", "test_payload"),
    ],
)
def test_typed_capture_endpoints_accept_hierarchy(
    client,
    request,
    hierarchy_payload,
    endpoint,
    payload_fixture,
):
    # Arrange
    payload = deepcopy(request.getfixturevalue(payload_fixture))
    payload["id"] = None
    payload["hierarchy"] = hierarchy_payload

    # Act
    response = client.post(endpoint, json=payload)

    # Assert
    assert response.status_code == 201
    summary = _events(client)[0]
    assert summary["hierarchy"] == hierarchy_payload


def test_event_detail_returns_hierarchy_only_on_envelope(
    client,
    http_payload,
    hierarchy_payload,
):
    # Arrange
    http_payload["hierarchy"] = hierarchy_payload
    client.post("/api/capture/http", json=http_payload)

    # Act
    detail = client.get(f"/api/events/{http_payload['id']}").json()

    # Assert
    assert detail["hierarchy"] == hierarchy_payload
    assert "hierarchy" not in detail["data"]


def test_old_http_payload_returns_null_hierarchy(client, http_payload):
    # Arrange
    client.post("/api/capture/http", json=http_payload)

    # Act
    summary = _events(client)[0]

    # Assert
    assert summary["hierarchy"] is None


def test_http_capture_requires_an_outcome_and_allows_response_with_error(http_payload):
    # Arrange
    neither = {key: value for key, value in http_payload.items() if key != "response"}
    both = {
        **http_payload,
        "error": {"type": "ConnectTimeout", "message": "timed out"},
    }

    # Act
    combined = HttpCapturePayload.model_validate(both)

    # Assert
    with pytest.raises(ValidationError, match="provide a response or error"):
        HttpCapturePayload.model_validate(neither)
    assert combined.response is not None
    assert combined.error is not None


def test_http_capture_persists_response_and_raised_error(client, http_payload):
    # Arrange
    http_payload["response"]["status_code"] = 404
    http_payload["error"] = {
        "type": "ClientResponseError",
        "message": "404, message='Not Found'",
        "module": "aiohttp.client_exceptions",
    }

    # Act
    response = client.post("/api/capture/http", json=http_payload)
    detail = client.get(f"/api/events/{http_payload['id']}").json()

    # Assert
    assert response.status_code == 201
    assert detail["summary"] == "GET /v1/test → 404"
    assert detail["data"]["status_code"] == 404
    assert detail["data"]["error"] == http_payload["error"]


def test_failed_http_capture_persists_typed_error(client, http_payload):
    # Arrange
    http_payload.pop("response")
    http_payload["error"] = {
        "type": "ConnectTimeout",
        "message": "connection timed out",
        "module": "httpx",
    }

    # Act
    response = client.post("/api/capture/http", json=http_payload)
    detail = client.get(f"/api/events/{http_payload['id']}").json()

    # Assert
    assert response.status_code == 201
    assert detail["summary"] == "GET /v1/test → ConnectTimeout"
    assert detail["data"]["status_code"] is None
    assert detail["data"]["response_headers"] == {}
    assert detail["data"]["response_body"] is None
    assert detail["data"]["response_body_size"] == 0
    assert detail["data"]["error"] == http_payload["error"]


def test_openapi_exposes_hierarchy_membership_union(client):
    # Act
    schemas = client.get("/openapi.json").json()["components"]["schemas"]

    # Assert
    memberships = schemas["EventHierarchy-Input"]["properties"]["group_memberships"]
    membership_items = memberships["items"]
    assert membership_items["discriminator"]["propertyName"] == "kind"
    assert set(membership_items["discriminator"]["mapping"]) == {
        "http_request",
        "pytest",
    }
    for capture_model in (
        "HttpCapturePayload",
        "HttpIncomingCapturePayload",
        "LogCapturePayload",
        "ExceptionCapturePayload",
        "TestCapturePayload",
    ):
        assert "hierarchy" in schemas[capture_model]["properties"]


@pytest.mark.asyncio
async def test_list_events_returns_hierarchy_filtered_and_unfiltered(services_db):
    # Arrange
    hierarchy = EventHierarchy(
        runtime=RuntimeCorrelation(
            trace_id=TRACE_ID,
            span_id=SPAN_ID,
            role="operation",
        )
    )
    created = await create_http_event(
        event_id=None,
        duration_ms=10,
        request=HttpRequestData(
            method="GET",
            url="https://api.stripe.com/v1/charges",
            headers={},
        ),
        response=HttpResponseData(status_code=200, headers={}),
        meta=HttpMeta(),
        hierarchy=hierarchy,
    )

    # Act
    unfiltered = await list_events()
    filtered = await list_events(host="api.stripe.com")
    detail = await get_event(str(created.id))

    # Assert
    assert unfiltered.events[0].hierarchy == hierarchy
    assert filtered.events[0].hierarchy == hierarchy
    assert detail is not None
    assert detail.hierarchy == hierarchy
    assert "hierarchy" not in detail.data.model_dump()


@pytest.mark.asyncio
async def test_existing_stored_row_hydrates_with_null_hierarchy(services_db):
    # Arrange
    event = await CapturedEvent.create(
        event_type="http",
        summary="GET / → 200",
        data={
            "duration_ms": 1,
            "method": "GET",
            "url": "https://legacy.test/",
            "host": "legacy.test",
            "request_headers": {},
            "status_code": 200,
            "response_headers": {},
        },
    )

    # Act
    detail = await get_event(str(event.id))

    # Assert
    assert detail is not None
    assert detail.hierarchy is None
