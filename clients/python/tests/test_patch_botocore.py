"""Tests for botocore outgoing HTTP correlation and failure capture."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

botocore = pytest.importorskip("botocore")

from botocore.httpsession import URLLib3Session  # noqa: E402
from traceloom.config import TraceLoomConfig  # noqa: E402
from traceloom.hierarchy import (  # noqa: E402
    activate_context,
    current_context,
    start_root,
)
from traceloom.patches.patch_botocore import patch_botocore  # noqa: E402


@pytest.fixture()
def config():
    return TraceLoomConfig(server_url="http://traceloom:5110")


def _request():
    return SimpleNamespace(
        method="GET",
        url="https://s3.example.com/bucket",
        headers={"X-Test": b"value"},
        body=None,
    )


def test_success_is_child_of_active_context(config):
    response = SimpleNamespace(
        _content=b'{"ok": true}',
        content=b'{"ok": true}',
        status_code=200,
        headers={"content-type": "application/json"},
    )
    parent = start_root(trace_id="1" * 32, span_id="2" * 16)
    original_send = URLLib3Session.send
    captured = []

    try:
        with (
            patch.object(URLLib3Session, "send", return_value=response),
            patch(
                "traceloom.patches.patch_botocore.send_http",
                side_effect=lambda payload, *, context: captured.append(
                    (payload, context)
                ),
            ),
        ):
            patch_botocore(config)
            with activate_context(parent):
                result = URLLib3Session().send(_request())
                assert current_context() is parent
    finally:
        URLLib3Session.send = original_send

    assert result is response
    payload, context = captured[0]
    assert payload["response"]["status_code"] == 200
    assert context.operation.trace_id == parent.operation.trace_id
    assert context.operation.parent_span_id == parent.operation.span_id
    assert context.group_memberships[0].hostname.id == "s3.example.com"
    assert current_context() is None


def test_failure_is_typed_and_original_exception_is_raised(config):
    error = TimeoutError("AWS timed out")
    original_send = URLLib3Session.send
    captured = []

    try:
        with (
            patch.object(URLLib3Session, "send", side_effect=error),
            patch(
                "traceloom.patches.patch_botocore.send_http",
                side_effect=lambda payload, *, context: captured.append(
                    (payload, context)
                ),
            ),
        ):
            patch_botocore(config)
            with pytest.raises(TimeoutError) as exc_info:
                URLLib3Session().send(_request())
    finally:
        URLLib3Session.send = original_send

    assert exc_info.value is error
    payload, context = captured[0]
    assert payload["error"]["type"] == "TimeoutError"
    assert "response" not in payload
    assert context.group_memberships[0].hostname.id == "s3.example.com"
    assert current_context() is None
