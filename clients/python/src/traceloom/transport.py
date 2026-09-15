"""Background transport: sends captured events to the TraceLoom server without blocking."""

import json
import logging
import queue
import threading
import time
import urllib.request
from typing import Literal
from urllib.parse import urlsplit

from traceloom.hierarchy import CaptureContext, current_context, serialize_hierarchy

logger = logging.getLogger(__name__)

# Each queue item is (path, payload). The worker uses the path to choose
# the typed capture endpoint.
_queue: queue.Queue[tuple[str, dict]] = queue.Queue(maxsize=1000)
_server_url: str = ""
_app: str = ""
_session: str = ""
_started: bool = False
_worker_ready = threading.Event()
_send_lock = threading.Lock()
_in_flight_lock = threading.Lock()
_in_flight: tuple[str, dict] | None = None


def start_worker(server_url: str, *, app: str = "", session: str = "") -> None:
    """Start the background worker thread."""
    global _server_url, _app, _session, _started
    parsed_url = urlsplit(server_url)
    if parsed_url.hostname == "localhost":
        # The default Windows localhost resolution tries ::1 before 127.0.0.1.
        # TraceLoom's local server binds IPv4 by default, and that fallback can
        # consume the entire short-process shutdown window.
        netloc = "127.0.0.1"
        if parsed_url.port is not None:
            netloc += f":{parsed_url.port}"
        _server_url = parsed_url._replace(netloc=netloc).geturl()
    else:
        _server_url = server_url
    _app = app
    _session = session

    if _started:
        return
    _started = True

    _worker_ready.clear()
    thread = threading.Thread(target=_worker, daemon=True, name="traceloom-transport")
    thread.start()
    # A short-lived process can enqueue its first event and reach atexit before
    # a newly-created daemon thread has had a chance to enter its loop. Wait for
    # the worker to signal that it is ready, without waiting on the server.
    _worker_ready.wait(timeout=1.0)


def send_http(payload: dict, *, context: CaptureContext | None = None) -> None:
    """Queue an HTTP capture payload for `/api/capture/http`."""
    _enqueue("/api/capture/http", payload, context=context, role="operation")


def send_log(payload: dict, *, context: CaptureContext | None = None) -> None:
    """Queue a log capture payload for `/api/capture/log`."""
    _enqueue("/api/capture/log", payload, context=context, role="annotation")


def send_test(payload: dict, *, context: CaptureContext | None = None) -> None:
    """Queue a test capture payload for `/api/capture/test`."""
    _enqueue("/api/capture/test", payload, context=context, role="operation")


def send_http_incoming(payload: dict, *, context: CaptureContext | None = None) -> None:
    """Queue an incoming HTTP capture payload for `/api/capture/http_incoming`."""
    _enqueue("/api/capture/http_incoming", payload, context=context, role="operation")


def send_exception(payload: dict, *, context: CaptureContext | None = None) -> None:
    """Queue an exception capture payload for `/api/capture/exception`."""
    _enqueue("/api/capture/exception", payload, context=context, role="annotation")


def flush(timeout: float = 2.0) -> bool:
    """Block until all queued payloads are sent, or *timeout* seconds elapse.

    Returns ``True`` if the queue drained in time, ``False`` otherwise.
    """
    # Queue.join() has no timeout parameter. Access the underlying
    # condition variable directly — same technique Sentry's SDK uses.
    with _queue.all_tasks_done:
        pending = _queue.unfinished_tasks
        if not pending:
            return True
        logger.debug("flushing %d pending capture(s)", pending)
        _queue.all_tasks_done.wait(timeout=timeout)

    drained = _queue.unfinished_tasks == 0
    if not drained:
        # During interpreter shutdown a daemon worker may not get another
        # scheduling turn. Take any items it has not dequeued yet and send them
        # from the caller, preserving Queue task accounting.
        drained = _drain_pending(timeout)

    if drained:
        logger.debug("flushed %d capture(s)", pending)
    else:
        logger.warning(
            "flush timed out with %d capture(s) still pending",
            _queue.unfinished_tasks,
        )
    return drained


def shutdown(timeout: float = 2.0) -> bool:
    """Flush pending payloads then stop accepting new ones.

    Returns ``True`` if the queue drained in time, ``False`` otherwise.
    """
    logger.debug("shutting down transport")
    return flush(timeout=timeout)


def _enqueue(
    path: str,
    payload: dict,
    *,
    context: CaptureContext | None,
    role: Literal["operation", "annotation"],
) -> None:
    resolved_context = (
        context
        if context is not None
        else current_context()
        if role == "annotation"
        else None
    )
    hierarchy = serialize_hierarchy(resolved_context, role=role)
    queued_payload = {**payload, "app": _app, "session": _session}
    if hierarchy is not None:
        queued_payload["hierarchy"] = hierarchy
    try:
        _queue.put_nowait((path, queued_payload))
    except queue.Full:
        logger.warning("Payload dropped: capture queue is full")


def _worker() -> None:
    """Background worker that sends queued payloads to the server."""
    global _in_flight
    _worker_ready.set()
    while True:
        path, payload = _queue.get()
        item = (path, payload)
        with _in_flight_lock:
            _in_flight = item

        with _send_lock:
            # shutdown() may have taken ownership of an item that the worker
            # dequeued but had not started sending yet.
            with _in_flight_lock:
                owns_item = _in_flight is item
            if not owns_item:
                continue

            try:
                _send_to_server(path, payload)
            except Exception as err:
                logger.warning("Failed to send capture to %s: %s", _server_url, err)
            finally:
                with _in_flight_lock:
                    _in_flight = None
                _queue.task_done()


def _drain_pending(timeout: float) -> bool:
    """Synchronously send queued items that the worker has not dequeued yet."""
    global _in_flight
    deadline = time.monotonic() + timeout
    if not _send_lock.acquire(blocking=False):
        return _queue.unfinished_tasks == 0

    try:
        # If the worker dequeued an item but has not acquired _send_lock yet,
        # take ownership so interpreter shutdown cannot strand it in-flight.
        with _in_flight_lock:
            item = _in_flight
            _in_flight = None
        if item is not None:
            path, payload = item
            remaining = max(0.01, deadline - time.monotonic())
            try:
                _send_to_server(path, payload, timeout=min(5.0, remaining))
            except Exception as err:
                logger.warning("Failed to send capture to %s: %s", _server_url, err)
            finally:
                _queue.task_done()

        while time.monotonic() < deadline:
            try:
                path, payload = _queue.get_nowait()
            except queue.Empty:
                break

            remaining = max(0.01, deadline - time.monotonic())
            try:
                _send_to_server(path, payload, timeout=min(5.0, remaining))
            except Exception as err:
                logger.warning("Failed to send capture to %s: %s", _server_url, err)
            finally:
                _queue.task_done()
    finally:
        _send_lock.release()

    return _queue.unfinished_tasks == 0


def _send_to_server(path: str, payload: dict, *, timeout: float = 5.0) -> None:
    """Send a payload to the TraceLoom server using urllib (to avoid recursion)."""
    data = json.dumps(payload, default=_json_default).encode("utf-8")
    req = urllib.request.Request(
        f"{_server_url}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    logger.debug("sent %s (%d)", path, resp.status)


def _json_default(obj: object) -> str:
    """Fallback serializer for types that json.dumps cannot handle (e.g. bytes)."""
    try:
        return repr(obj)
    except Exception:
        return "<unserializable>"
