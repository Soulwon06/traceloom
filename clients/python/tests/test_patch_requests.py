"""Tests for Requests runtime hierarchy capture."""

import pytest
from traceloom.config import TraceLoomConfig
from traceloom.hierarchy import (
    GroupReference,
    PytestGroupMembership,
    activate_context,
    current_context,
    start_root,
)
from traceloom.patches.patch_requests import patch_requests

requests = pytest.importorskip("requests")


@pytest.fixture()
def config() -> TraceLoomConfig:
    return TraceLoomConfig(server_url="http://localhost:5110")


@pytest.fixture()
def parent_context():
    membership = PytestGroupMembership(
        test_directory=GroupReference(id="tests", label="tests"),
        test_file=GroupReference(id="tests/test_checkout.py", label="test_checkout.py"),
        test_class=None,
        test_case=GroupReference(
            id="tests/test_checkout.py::test_total",
            label="test_total",
        ),
    )
    return start_root(
        trace_id="1" * 32,
        span_id="a" * 16,
        memberships=(membership,),
    )


def _prepared_request() -> requests.PreparedRequest:
    return requests.Request("GET", "https://API.Example.COM:8443/v1/items").prepare()


def test_request_creates_child_and_inherits_parent_membership(
    monkeypatch,
    config,
    parent_context,
):
    # Arrange
    captured = []
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"ok": true}'
    monkeypatch.setattr(
        requests.Session, "send", lambda self, request, **kwargs: response
    )
    monkeypatch.setattr(
        "traceloom.patches.patch_requests.send_http",
        lambda payload, *, context=None: captured.append((payload, context)),
    )
    patch_requests(config)

    # Act
    with activate_context(parent_context):
        result = requests.Session().send(_prepared_request())
        restored_context = current_context()

    # Assert
    assert result is response
    assert restored_context == parent_context
    assert current_context() is None
    payload, context = captured[0]
    assert payload["response"]["status_code"] == 200
    assert context.operation.trace_id == parent_context.operation.trace_id
    assert context.operation.parent_span_id == parent_context.operation.span_id
    assert [membership.kind for membership in context.group_memberships] == [
        "pytest",
        "http_request",
    ]
    assert context.group_memberships[1].hostname.id == "api.example.com"


def test_request_failure_is_captured_and_original_error_is_raised(
    monkeypatch,
    config,
    parent_context,
):
    # Arrange
    captured = []
    original_error = requests.ConnectTimeout("connection timed out")

    def raise_timeout(self, request, **kwargs):
        raise original_error

    monkeypatch.setattr(requests.Session, "send", raise_timeout)
    monkeypatch.setattr(
        "traceloom.patches.patch_requests.send_http",
        lambda payload, *, context=None: captured.append((payload, context)),
    )
    patch_requests(config)

    # Act / Assert
    with activate_context(parent_context):
        with pytest.raises(requests.ConnectTimeout) as exc_info:
            requests.Session().send(_prepared_request())
        assert current_context() == parent_context

    assert exc_info.value is original_error
    payload, context = captured[0]
    assert "response" not in payload
    assert payload["error"] == {
        "type": "ConnectTimeout",
        "message": "connection timed out",
        "module": "requests.exceptions",
    }
    assert context.operation.parent_span_id == parent_context.operation.span_id
    assert current_context() is None
