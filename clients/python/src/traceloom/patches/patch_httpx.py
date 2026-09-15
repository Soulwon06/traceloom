"""Instrument ``httpx`` with send boundaries and response event hooks.

The send wrappers establish runtime context before network I/O and capture
raised failures. Init wrappers inject response hooks that retain that detached
context until streaming response bodies close.

The ``response`` hook wraps the response byte-stream with a tee that
accumulates chunks and sends the capture when the stream is closed.  This
works uniformly for both streaming and non-streaming requests: httpx always
reads the body through ``response.stream`` and calls ``close()`` afterwards.
"""

import logging
import time
from urllib.parse import urlparse

from traceloom.capture import serialize_request_error, serialize_request_response
from traceloom.config import TraceLoomConfig
from traceloom.hierarchy import CaptureContext, activate_context, start_http_request
from traceloom.transport import send_http
from traceloom.utils import redact_query_params

logger = logging.getLogger(__name__)

MAX_BODY_CAPTURE = 1_048_576  # 1 MB


def patch_httpx(config: TraceLoomConfig) -> None:
    """Inject event hooks into every httpx Client and AsyncClient."""
    try:
        import httpx  # noqa: PLC0415 -- optional dependency
    except ImportError:
        logger.debug("skipped httpx patch (not installed)")
        return

    _patch_init(httpx.Client, _make_sync_hooks(config))
    _patch_init(httpx.AsyncClient, _make_async_hooks(config))
    _patch_sync_send(httpx.Client, config)
    _patch_async_send(httpx.AsyncClient, config)
    logger.debug("patched httpx.Client and httpx.AsyncClient")


# ---------------------------------------------------------------------------
# __init__ patching — inject event hooks into every client
# ---------------------------------------------------------------------------


def _patch_init(client_cls, hooks: dict) -> None:
    original_init = client_cls.__init__

    def patched_init(self, *args, **kwargs):
        event_hooks = dict(kwargs.get("event_hooks") or {})
        for key, new_hooks in hooks.items():
            existing = list(event_hooks.get(key, []))
            existing.extend(new_hooks)
            event_hooks[key] = existing
        kwargs["event_hooks"] = event_hooks
        return original_init(self, *args, **kwargs)

    client_cls.__init__ = patched_init


def _patch_sync_send(client_cls, config: TraceLoomConfig) -> None:
    original_send = client_cls.send

    def patched_send(self, request, *args, **kwargs):
        return _send_sync(
            config=config,
            original_send=original_send,
            client=self,
            request=request,
            args=args,
            kwargs=kwargs,
        )

    client_cls.send = patched_send


def _patch_async_send(client_cls, config: TraceLoomConfig) -> None:
    original_send = client_cls.send

    async def patched_send(self, request, *args, **kwargs):
        return await _send_async(
            config=config,
            original_send=original_send,
            client=self,
            request=request,
            args=args,
            kwargs=kwargs,
        )

    client_cls.send = patched_send


# ---------------------------------------------------------------------------
# Hook factories
# ---------------------------------------------------------------------------

_START_KEY = "_traceloom_start"
_CONTEXT_KEY = "_traceloom_context"


def _make_sync_hooks(config: TraceLoomConfig) -> dict:
    def on_request(request):
        request.extensions.setdefault(_START_KEY, time.monotonic())

    def on_response(response):
        host = urlparse(str(response.request.url)).hostname or ""
        if not config.should_capture(host):
            logger.debug("skipped %s %s (ignored host)", response.request.method, host)
            return
        start = response.request.extensions.pop(_START_KEY, time.monotonic())
        context = response.request.extensions.get(_CONTEXT_KEY)
        _wrap_sync_stream(response, start, config, context)

    return {"request": [on_request], "response": [on_response]}


def _make_async_hooks(config: TraceLoomConfig) -> dict:
    async def on_request(request):
        request.extensions.setdefault(_START_KEY, time.monotonic())

    async def on_response(response):
        host = urlparse(str(response.request.url)).hostname or ""
        if not config.should_capture(host):
            logger.debug("skipped %s %s (ignored host)", response.request.method, host)
            return
        start = response.request.extensions.pop(_START_KEY, time.monotonic())
        context = response.request.extensions.get(_CONTEXT_KEY)
        _wrap_async_stream(response, start, config, context)

    return {"request": [on_request], "response": [on_response]}


# ---------------------------------------------------------------------------
# Capture helper
# ---------------------------------------------------------------------------


def _send_capture(*, config, request, response, response_body, start, context):
    duration = time.monotonic() - start
    try:
        payload = serialize_request_response(
            config=config,
            method=request.method,
            url=str(request.url),
            request_headers=dict(request.headers),
            request_body=request.content,
            status_code=response.status_code,
            response_headers=dict(response.headers),
            response_body=response_body,
            duration_s=duration,
            library="httpx",
        )
        send_http(payload, context=context)
        logger.debug(
            "captured %s %s via httpx (%d)",
            request.method,
            redact_query_params(str(request.url), config.redact_query_params),
            response.status_code,
        )
    except Exception as err:
        logger.debug("failed to capture request: %s", err)


# ---------------------------------------------------------------------------
# Stream wrappers — tee bytes and capture on close
# ---------------------------------------------------------------------------


def _wrap_sync_stream(response, start, config, context):
    import httpx  # noqa: PLC0415

    original_stream = response.stream
    chunks: list[bytes] = []
    exceeded = False
    failed = False
    sent = False

    class _TeeStream(httpx.SyncByteStream):
        def __iter__(self):
            nonlocal exceeded, failed
            try:
                for chunk in original_stream:
                    if not exceeded:
                        chunks.append(chunk)
                        if sum(len(c) for c in chunks) > MAX_BODY_CAPTURE:
                            chunks.clear()
                            exceeded = True
                    yield chunk
            except Exception:
                failed = True
                raise

        def close(self):
            nonlocal sent
            if not sent and not failed:
                sent = True
                body = b"".join(chunks) if not exceeded else None
                _send_capture(
                    config=config,
                    request=response.request,
                    response=response,
                    response_body=body,
                    start=start,
                    context=context,
                )
            original_stream.close()

    response.stream = _TeeStream()


def _wrap_async_stream(response, start, config, context):
    import httpx  # noqa: PLC0415

    original_stream = response.stream
    chunks: list[bytes] = []
    exceeded = False
    failed = False
    sent = False

    class _TeeStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal exceeded, failed
            try:
                async for chunk in original_stream:
                    if not exceeded:
                        chunks.append(chunk)
                        if sum(len(c) for c in chunks) > MAX_BODY_CAPTURE:
                            chunks.clear()
                            exceeded = True
                    yield chunk
            except Exception:
                failed = True
                raise

        async def aclose(self):
            nonlocal sent
            if not sent and not failed:
                sent = True
                body = b"".join(chunks) if not exceeded else None
                _send_capture(
                    config=config,
                    request=response.request,
                    response=response,
                    response_body=body,
                    start=start,
                    context=context,
                )
            await original_stream.aclose()

    response.stream = _TeeStream()


def _prepare_context(config: TraceLoomConfig, request) -> CaptureContext | None:
    """Attach a child context to a captured request before network I/O."""
    host = urlparse(str(request.url)).hostname or ""
    if not config.should_capture(host):
        return None
    context = start_http_request(host)
    request.extensions[_CONTEXT_KEY] = context
    request.extensions[_START_KEY] = time.monotonic()
    return context


def _capture_error(
    *,
    config: TraceLoomConfig,
    request,
    error: Exception,
    context: CaptureContext,
) -> None:
    try:
        start = request.extensions.pop(_START_KEY, time.monotonic())
        payload = serialize_request_error(
            config=config,
            method=request.method,
            url=str(request.url),
            request_headers=dict(request.headers),
            request_body=request.content,
            error=error,
            duration_s=time.monotonic() - start,
            library="httpx",
        )
        send_http(payload, context=context)
        logger.debug(
            "captured %s %s via httpx (%s)",
            request.method,
            redact_query_params(str(request.url), config.redact_query_params),
            type(error).__name__,
        )
    except Exception as capture_error:
        logger.debug("failed to capture request: %s", capture_error)


def _send_sync(*, config, original_send, client, request, args, kwargs):
    context = _prepare_context(config, request)
    if context is None:
        return original_send(client, request, *args, **kwargs)
    with activate_context(context):
        try:
            return original_send(client, request, *args, **kwargs)
        except Exception as error:
            _capture_error(
                config=config,
                request=request,
                error=error,
                context=context,
            )
            raise


async def _send_async(*, config, original_send, client, request, args, kwargs):
    context = _prepare_context(config, request)
    if context is None:
        return await original_send(client, request, *args, **kwargs)
    with activate_context(context):
        try:
            return await original_send(client, request, *args, **kwargs)
        except Exception as error:
            _capture_error(
                config=config,
                request=request,
                error=error,
                context=context,
            )
            raise
