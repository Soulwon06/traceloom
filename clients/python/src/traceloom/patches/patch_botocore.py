"""Monkey-patch for ``botocore`` (used by boto3 / AWS CLI).

botocore uses ``urllib3`` directly (not ``requests``), so the requests patch
does not cover AWS SDK traffic.  We patch
``botocore.httpsession.URLLib3Session.send`` to capture every HTTP call that
boto3 makes to AWS services.
"""

import logging
import time
from urllib.parse import urlparse

from traceloom.capture import serialize_request_error, serialize_request_response
from traceloom.config import TraceLoomConfig
from traceloom.hierarchy import activate_context, start_http_request
from traceloom.transport import send_http
from traceloom.utils import redact_query_params

logger = logging.getLogger(__name__)


def _decode_headers(headers: dict) -> dict[str, str]:
    """Decode botocore header values from bytes to str."""
    return {
        k: v.decode("utf-8", errors="replace") if isinstance(v, bytes) else str(v)
        for k, v in headers.items()
    }


def patch_botocore(config: TraceLoomConfig) -> None:
    """Patch botocore's HTTP session to capture outgoing AWS traffic."""
    try:
        from botocore.httpsession import URLLib3Session  # noqa: PLC0415
    except ImportError:
        logger.debug("skipped botocore patch (not installed)")
        return

    original_send = URLLib3Session.send

    def patched_send(self, request):
        host = urlparse(request.url).hostname or ""

        if not config.should_capture(host):
            logger.debug("skipped %s %s (ignored host)", request.method, host)
            return original_send(self, request)

        context = start_http_request(host)
        start = time.monotonic()
        with activate_context(context):
            try:
                response = original_send(self, request)
            except Exception as error:
                duration = time.monotonic() - start
                try:
                    payload = serialize_request_error(
                        config=config,
                        method=request.method,
                        url=request.url,
                        request_headers=_decode_headers(request.headers),
                        request_body=_request_body(request.body),
                        error=error,
                        duration_s=duration,
                        library="botocore",
                    )
                    send_http(payload, context=context)
                except Exception as capture_error:
                    logger.debug(
                        "failed to capture botocore request: %s", capture_error
                    )
                raise
        duration = time.monotonic() - start

        try:
            # Read the body — for non-streaming responses this is already
            # buffered; for streaming ones (e.g. S3 GetObject) we read what
            # is available without consuming the stream the caller needs.
            response_body: str | bytes | None = None
            if response._content is not None:
                response_body = response.content
            else:
                # Streaming response — don't consume the stream.  Record
                # a placeholder so the request still shows up in the UI.
                response_body = "[streaming response]"

            payload = serialize_request_response(
                config=config,
                method=request.method,
                url=request.url,
                request_headers=_decode_headers(request.headers),
                request_body=_request_body(request.body),
                status_code=response.status_code,
                response_headers=dict(response.headers),
                response_body=response_body,
                duration_s=duration,
                library="botocore",
            )
            send_http(payload, context=context)
            logger.debug(
                "captured %s %s via botocore (%d)",
                request.method,
                redact_query_params(request.url, config.redact_query_params),
                response.status_code,
            )
        except Exception as err:
            logger.debug("failed to capture botocore request: %s", err)

        return response

    URLLib3Session.send = patched_send  # type: ignore[assignment]
    logger.debug("patched botocore.httpsession.URLLib3Session.send")


def _request_body(body) -> str | bytes | None:
    """Return a safe representation without consuming file-like uploads."""
    if body is None or isinstance(body, (str, bytes)):
        return body
    return "[file upload]"
