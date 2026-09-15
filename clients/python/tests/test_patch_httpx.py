"""Tests for traceloom.patches.patch_httpx — sync and async, streaming and non-streaming."""

import asyncio
import gzip
from unittest.mock import patch

import pytest

httpx = pytest.importorskip("httpx")

from traceloom.config import TraceLoomConfig  # noqa: E402
from traceloom.hierarchy import (  # noqa: E402
    activate_context,
    current_context,
    start_root,
)
from traceloom.patches.patch_httpx import patch_httpx  # noqa: E402


@pytest.fixture()
def config():
    return TraceLoomConfig(
        server_url="http://test:5110",
        redact_headers=["authorization"],
    )


@pytest.fixture()
def captured(config):
    """Apply patches and return a list that collects send_http payloads."""
    orig_sync_init = httpx.Client.__init__
    orig_async_init = httpx.AsyncClient.__init__
    orig_sync_send = httpx.Client.send
    orig_async_send = httpx.AsyncClient.send

    class Captures(list):
        contexts: list = []

    payloads = Captures()

    def record(payload, *, context=None):
        payloads.append(payload)
        payloads.contexts.append(context)

    with patch("traceloom.patches.patch_httpx.send_http", side_effect=record):
        patch_httpx(config)
        yield payloads
    httpx.Client.__init__ = orig_sync_init
    httpx.AsyncClient.__init__ = orig_async_init
    httpx.Client.send = orig_sync_send
    httpx.AsyncClient.send = orig_async_send


def _stream_handler(request: httpx.Request) -> httpx.Response:
    """Mock handler that returns a stream-based response (no pre-set _content)."""
    return httpx.Response(
        200,
        headers={"content-type": "application/json"},
        stream=httpx.ByteStream(b'{"ok":true}'),
    )


# ---- sync non-streaming ----------------------------------------------------


def test_sync_non_streaming_captured(captured):
    transport = httpx.MockTransport(_stream_handler)
    with httpx.Client(transport=transport) as client:
        resp = client.get("https://example.com/api")

    assert resp.status_code == 200
    assert len(captured) == 1
    p = captured[0]
    assert p["request"]["method"] == "GET"
    assert "example.com" in p["request"]["url"]
    assert p["response"]["status_code"] == 200
    assert p["response"]["body"] is not None
    assert captured.contexts[0].operation.parent_span_id is None
    assert captured.contexts[0].group_memberships[0].hostname.id == "example.com"


def test_sync_capture_is_child_of_active_context(captured):
    parent = start_root(trace_id="1" * 32, span_id="2" * 16)
    transport = httpx.MockTransport(_stream_handler)

    with activate_context(parent):
        with httpx.Client(transport=transport) as client:
            client.get("https://example.com/api")
        assert current_context() is parent

    context = captured.contexts[0]
    assert context.operation.trace_id == parent.operation.trace_id
    assert context.operation.parent_span_id == parent.operation.span_id
    assert current_context() is None


def test_sync_error_captured_and_original_exception_raised(captured):
    error = httpx.ConnectTimeout("timed out")

    def fail(_request):
        raise error

    transport = httpx.MockTransport(fail)
    with httpx.Client(transport=transport) as client:
        with pytest.raises(httpx.ConnectTimeout) as exc_info:
            client.get("https://example.com/api")

    assert exc_info.value is error
    assert len(captured) == 1
    assert "response" not in captured[0]
    assert captured[0]["error"]["type"] == "ConnectTimeout"
    assert current_context() is None


def test_sync_body_read_error_emits_only_error_capture(captured):
    class FailingStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"partial"
            raise httpx.ReadTimeout("timed out while reading")

    def respond(_request):
        return httpx.Response(200, stream=FailingStream())

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(httpx.ReadTimeout):
            client.get("https://example.com/api")

    assert len(captured) == 1
    assert "response" not in captured[0]
    assert captured[0]["error"]["type"] == "ReadTimeout"


def test_sync_non_streaming_body_content(captured):
    transport = httpx.MockTransport(_stream_handler)
    with httpx.Client(transport=transport) as client:
        client.get("https://example.com/data")

    assert "ok" in captured[0]["response"]["body"]


# ---- sync streaming ---------------------------------------------------------


def test_sync_streaming_captured_via_read(captured):
    transport = httpx.MockTransport(_stream_handler)
    with httpx.Client(transport=transport) as client:
        with client.stream("GET", "https://example.com/stream") as resp:
            resp.read()

    assert resp.status_code == 200
    assert len(captured) == 1
    assert "ok" in captured[0]["response"]["body"]


def test_sync_streaming_captured_via_iter_bytes(captured):
    transport = httpx.MockTransport(_stream_handler)
    with httpx.Client(transport=transport) as client:
        with client.stream("GET", "https://example.com/stream") as resp:
            list(resp.iter_bytes())

    assert len(captured) == 1
    assert captured[0]["response"]["body"] is not None


def test_sync_streaming_close_without_read(captured):
    """Closing a streaming response without reading should still capture."""
    transport = httpx.MockTransport(_stream_handler)
    with httpx.Client(transport=transport) as client:
        with client.stream("GET", "https://example.com/stream"):
            pass

    assert len(captured) == 1
    assert captured[0]["response"]["status_code"] == 200


# ---- async non-streaming ---------------------------------------------------


def test_async_non_streaming_captured(captured):
    transport = httpx.MockTransport(_stream_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await client.get("https://example.com/api")

    resp = asyncio.run(run())
    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0]["response"]["body"] is not None


def test_async_body_read_error_emits_only_error_capture(captured):
    class FailingStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"partial"
            raise httpx.ReadTimeout("timed out while reading")

    def respond(_request):
        return httpx.Response(200, stream=FailingStream())

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            await client.get("https://example.com/api")

    with pytest.raises(httpx.ReadTimeout):
        asyncio.run(run())

    assert len(captured) == 1
    assert "response" not in captured[0]
    assert captured[0]["error"]["type"] == "ReadTimeout"


# ---- async streaming --------------------------------------------------------


def test_async_streaming_captured_via_aread(captured):
    transport = httpx.MockTransport(_stream_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            async with client.stream("GET", "https://example.com/stream") as resp:
                await resp.aread()
        return resp

    resp = asyncio.run(run())
    assert resp.status_code == 200
    assert len(captured) == 1
    assert "ok" in captured[0]["response"]["body"]


def test_async_streaming_captured_via_aiter_bytes(captured):
    transport = httpx.MockTransport(_stream_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            async with client.stream("GET", "https://example.com/stream") as resp:
                _ = [c async for c in resp.aiter_bytes()]

    asyncio.run(run())
    assert len(captured) == 1
    assert captured[0]["response"]["body"] is not None


def test_async_streaming_captured_via_aiter_lines(captured):
    """SSE-style line iteration should still capture the full body."""
    transport = httpx.MockTransport(_stream_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            async with client.stream("GET", "https://example.com/stream") as resp:
                _ = [line async for line in resp.aiter_lines()]

    asyncio.run(run())
    assert len(captured) == 1
    assert captured[0]["response"]["body"] is not None


def test_async_streaming_close_without_read(captured):
    transport = httpx.MockTransport(_stream_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            async with client.stream("GET", "https://example.com/stream"):
                pass

    asyncio.run(run())
    assert len(captured) == 1
    assert captured[0]["response"]["status_code"] == 200


# ---- host filtering --------------------------------------------------------


def test_ignored_host_not_captured(captured, config):
    config.ignore_hosts = ["ignored.example.com"]
    transport = httpx.MockTransport(_stream_handler)
    with httpx.Client(transport=transport) as client:
        client.get("https://ignored.example.com/api")

    assert len(captured) == 0


def test_ignored_host_streaming_not_captured(captured, config):
    config.ignore_hosts = ["ignored.example.com"]
    transport = httpx.MockTransport(_stream_handler)
    with httpx.Client(transport=transport) as client:
        with client.stream("GET", "https://ignored.example.com/s") as resp:
            resp.read()

    assert len(captured) == 0


# ---- header redaction -------------------------------------------------------


def test_authorization_header_redacted(captured):
    transport = httpx.MockTransport(_stream_handler)
    with httpx.Client(transport=transport) as client:
        client.get(
            "https://example.com/api", headers={"Authorization": "Bearer secret"}
        )

    assert captured[0]["request"]["headers"]["authorization"] == "[REDACTED]"


# ---- metadata ---------------------------------------------------------------


def test_library_field_is_httpx(captured):
    transport = httpx.MockTransport(_stream_handler)
    with httpx.Client(transport=transport) as client:
        client.get("https://example.com/api")

    assert captured[0]["meta"]["library"] == "httpx"


def test_duration_is_positive(captured):
    transport = httpx.MockTransport(_stream_handler)
    with httpx.Client(transport=transport) as client:
        client.get("https://example.com/api")

    assert captured[0]["duration_ms"] >= 0


# ---- request body -----------------------------------------------------------


def test_request_body_captured(captured):
    transport = httpx.MockTransport(_stream_handler)
    with httpx.Client(transport=transport) as client:
        client.post("https://example.com/api", json={"key": "value"})

    assert "key" in captured[0]["request"]["body"]


def test_streaming_post_body_captured(captured):
    transport = httpx.MockTransport(_stream_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            async with client.stream(
                "POST", "https://example.com/api", json={"key": "value"}
            ) as resp:
                await resp.aread()

    asyncio.run(run())
    assert len(captured) == 1
    assert "key" in captured[0]["request"]["body"]


# ---- user event hooks preserved ---------------------------------------------


def test_user_event_hooks_preserved(captured):
    """User-provided event hooks should still fire alongside ours."""
    seen = []

    def user_hook(response):
        seen.append(response.status_code)

    transport = httpx.MockTransport(_stream_handler)
    with httpx.Client(
        transport=transport, event_hooks={"response": [user_hook]}
    ) as client:
        client.get("https://example.com/api")

    assert seen == [200]
    assert len(captured) == 1


# ---- gzip decompression -----------------------------------------------------


def _gzip_handler(request: httpx.Request) -> httpx.Response:
    body = gzip.compress(b'{"message":"hello"}')
    return httpx.Response(
        200,
        headers={"content-type": "application/json", "content-encoding": "gzip"},
        stream=httpx.ByteStream(body),
    )


def test_gzip_response_decompressed(captured):
    transport = httpx.MockTransport(_gzip_handler)
    with httpx.Client(transport=transport) as client:
        client.get("https://example.com/api")

    assert len(captured) == 1
    assert captured[0]["response"]["body"] == '{"message":"hello"}'


def test_gzip_async_response_decompressed(captured):
    transport = httpx.MockTransport(_gzip_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await client.get("https://example.com/api")

    asyncio.run(run())
    assert len(captured) == 1
    assert captured[0]["response"]["body"] == '{"message":"hello"}'


def test_gzip_streaming_response_decompressed(captured):
    transport = httpx.MockTransport(_gzip_handler)
    with httpx.Client(transport=transport) as client:
        with client.stream("GET", "https://example.com/api") as resp:
            resp.read()

    assert len(captured) == 1
    assert captured[0]["response"]["body"] == '{"message":"hello"}'
