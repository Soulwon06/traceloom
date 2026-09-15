"""Instrument ``aiohttp`` via its native TraceConfig signal system.

Instead of monkey-patching ``ClientSession._request`` (which requires
manual handling of merged headers, base_url resolution, redirects,
raise_for_status, streaming, and close-vs-release), we patch
``ClientSession.__init__`` to inject a ``TraceConfig`` that hooks into
aiohttp's lifecycle signals.  This follows the same approach as the
Sentry Python SDK.

Signals used:
  on_request_start          — record start time, merged headers
  on_request_chunk_sent     — accumulate request body bytes
  on_request_redirect       — capture each 3xx hop
  on_request_end            — set up lazy response-body capture
  on_response_chunk_received — capture response body (fires inside read())
  on_request_exception      — capture raise_for_status / connection errors
"""

import logging
import time
from types import SimpleNamespace
from urllib.parse import urljoin, urlparse

from traceloom.capture import serialize_request_error, serialize_request_response
from traceloom.config import TraceLoomConfig
from traceloom.hierarchy import (
    CaptureContext,
    reset_context,
    set_context,
    start_http_request,
)
from traceloom.transport import send_http
from traceloom.utils import redact_query_params

logger = logging.getLogger(__name__)

MAX_BODY_CAPTURE = 1_048_576  # 1 MB


class TraceContext(SimpleNamespace):
    """Per-request state carried across TraceConfig signals."""

    def __init__(self, trace_request_ctx=None):
        super().__init__(trace_request_ctx=trace_request_ctx)
        self.skip = True
        self.start = 0.0
        self.request_headers: dict = {}
        self.body_chunks: list[bytes] | None = []  # None = exceeded cap
        self.send_capture = None  # set by on_request_end
        self.capture_context: CaptureContext | None = None
        self.context_token = None


class AiohttpTracer:
    """Signal handlers for a single TraceLoomConfig, registered on a TraceConfig."""

    def __init__(self, config: TraceLoomConfig) -> None:
        self.config = config

    async def on_request_start(self, session, ctx, params):
        host = params.url.host or ""
        if not self.config.should_capture(host):
            logger.debug("skipped %s %s (ignored host)", params.method, host)
            return
        ctx.skip = False
        ctx.start = time.monotonic()
        ctx.request_headers = dict(params.headers)
        ctx.capture_context = start_http_request(host)
        ctx.context_token = set_context(ctx.capture_context)

    async def on_request_chunk_sent(self, session, ctx, params):
        if ctx.skip or ctx.body_chunks is None:
            return
        ctx.body_chunks.append(params.chunk)
        if sum(len(c) for c in ctx.body_chunks) > MAX_BODY_CAPTURE:
            ctx.body_chunks = None  # stop accumulating

    @staticmethod
    def _extract_body(ctx):
        if ctx.body_chunks is None:
            return "[large upload]"
        return b"".join(ctx.body_chunks) or None

    async def on_request_redirect(self, session, ctx, params):
        if ctx.skip:
            return
        request_body = self._extract_body(ctx)
        try:
            payload = serialize_request_response(
                config=self.config,
                method=params.method,
                url=str(params.response.url),
                request_headers=ctx.request_headers,
                request_body=request_body,
                status_code=params.response.status,
                response_headers=dict(params.response.headers),
                response_body=None,
                duration_s=0,
                library="aiohttp",
            )
            send_http(payload, context=ctx.capture_context)
        except Exception as err:
            logger.debug("failed to capture redirect hop: %s", err)
        finally:
            self._reset_active_context(ctx)

        location = params.response.headers.get("Location", "")
        next_url = urljoin(str(params.response.url), location)
        next_host = urlparse(next_url).hostname or params.response.url.host or ""
        ctx.capture_context = start_http_request(next_host)
        ctx.context_token = set_context(ctx.capture_context)
        ctx.start = time.monotonic()
        # Reset for the next hop — body is not resent after redirect.
        ctx.request_headers = dict(params.headers)
        ctx.body_chunks = []

    async def on_response_chunk_received(self, session, ctx, params):
        """Fires inside response.read() with the full body."""
        if ctx.skip:
            return
        if ctx.send_capture is not None:
            ctx.send_capture(response_body=params.chunk)

    async def on_request_end(self, session, ctx, params):
        if ctx.skip:
            return
        try:
            self._install_response_capture(ctx, params)
        finally:
            self._reset_active_context(ctx)

    def _install_response_capture(self, ctx, params) -> None:
        """Retain detached context until the response stream is consumed."""
        request_body = self._extract_body(ctx)
        config = self.config
        start = ctx.start
        capture_context = ctx.capture_context

        # Build a one-shot sender.  on_response_chunk_received calls it
        # with the body when the caller reads; release/close call it
        # without body as a fallback for streaming consumers.
        sent = {"done": False}

        def _send_if_not_sent(response_body=None):
            if sent["done"]:
                return
            sent["done"] = True
            # Measure duration at send time so it includes response
            # body download, not just headers.
            duration = time.monotonic() - start
            try:
                payload = serialize_request_response(
                    config=config,
                    method=params.method,
                    url=str(params.response.url),
                    request_headers=ctx.request_headers,
                    request_body=request_body,
                    status_code=params.response.status,
                    response_headers=dict(params.response.headers),
                    response_body=response_body,
                    duration_s=duration,
                    library="aiohttp",
                )
                send_http(payload, context=capture_context)
                logger.debug(
                    "captured %s %s via aiohttp (%d)",
                    params.method,
                    redact_query_params(
                        str(params.response.url), config.redact_query_params
                    ),
                    params.response.status,
                )
            except Exception as err:
                logger.debug("failed to capture request: %s", err)

        # Expose to on_response_chunk_received via the trace context.
        ctx.send_capture = _send_if_not_sent

        # Fallback hooks for streaming consumers that never call read().
        resp = params.response
        original_release = resp.release
        original_close = resp.close

        def _releasing():
            _send_if_not_sent()
            return original_release()

        def _closing():
            _send_if_not_sent()
            return original_close()

        resp.release = _releasing
        resp.close = _closing

    async def on_request_exception(self, session, ctx, params):
        if ctx.skip:
            return
        duration = time.monotonic() - ctx.start
        request_body = self._extract_body(ctx)
        response_status_code = None
        response_headers = None

        import aiohttp  # noqa: PLC0415

        if isinstance(params.exception, aiohttp.ClientResponseError):
            response_status_code = params.exception.status
            response_headers = params.exception.headers
        try:
            payload = serialize_request_error(
                config=self.config,
                method=params.method,
                url=str(params.url),
                request_headers=dict(params.headers),
                request_body=request_body,
                error=params.exception,
                duration_s=duration,
                library="aiohttp",
                response_status_code=response_status_code,
                response_headers=response_headers,
            )
            send_http(payload, context=ctx.capture_context)
        except Exception as err:
            logger.debug("failed to capture error response: %s", err)
        finally:
            self._reset_active_context(ctx)

    @staticmethod
    def _reset_active_context(ctx) -> None:
        if ctx.context_token is not None:
            reset_context(ctx.context_token)
            ctx.context_token = None

    def create_trace_config(self):
        """Return a frozen-ready TraceConfig wired to this tracer."""
        from aiohttp import TraceConfig  # noqa: PLC0415

        tc = TraceConfig(trace_config_ctx_factory=TraceContext)
        tc.on_request_start.append(self.on_request_start)
        tc.on_request_chunk_sent.append(self.on_request_chunk_sent)
        tc.on_request_redirect.append(self.on_request_redirect)
        tc.on_response_chunk_received.append(self.on_response_chunk_received)
        tc.on_request_end.append(self.on_request_end)
        tc.on_request_exception.append(self.on_request_exception)
        return tc


def patch_aiohttp(config: TraceLoomConfig) -> None:
    """Inject a TraceConfig into every aiohttp.ClientSession."""
    try:
        import aiohttp  # noqa: PLC0415 -- optional dependency
    except ImportError:
        logger.debug("skipped aiohttp patch (not installed)")
        return

    tracer = AiohttpTracer(config)
    original_init = aiohttp.ClientSession.__init__

    def patched_init(self, *args, **kwargs):
        trace_configs = list(kwargs.get("trace_configs") or [])
        trace_configs.append(tracer.create_trace_config())
        kwargs["trace_configs"] = trace_configs
        return original_init(self, *args, **kwargs)

    aiohttp.ClientSession.__init__ = patched_init  # type: ignore[assignment]
    logger.debug("patched aiohttp.ClientSession")
