"""Debug logging helpers for the TraceLoom client SDK."""

import logging
import sys
import urllib.request

_HANDLER_ATTR = "_traceloom_debug_handler"


def setup_debug_logging() -> None:
    """Attach a stderr handler to the ``"traceloom"`` logger at DEBUG level.

    Idempotent — safe to call multiple times.  Only touches the handler
    it owns (tagged with ``_traceloom_debug_handler``), so it never
    interferes with handlers the user attached manually.
    """
    traceloom_logger = logging.getLogger("traceloom")
    traceloom_logger.setLevel(logging.DEBUG)
    traceloom_logger.propagate = False

    for h in traceloom_logger.handlers:
        if getattr(h, _HANDLER_ATTR, False):
            return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("traceloom: %(message)s"))
    setattr(handler, _HANDLER_ATTR, True)
    traceloom_logger.addHandler(handler)


def teardown_debug_logging() -> None:
    """Remove the handler installed by :func:`setup_debug_logging`.

    Only removes TraceLoom's own handler; user-attached handlers and the
    logger level are left untouched.
    """
    traceloom_logger = logging.getLogger("traceloom")
    traceloom_logger.handlers = [
        h for h in traceloom_logger.handlers if not getattr(h, _HANDLER_ATTR, False)
    ]


def check_connectivity(server_url: str) -> None:
    """Ping the TraceLoom server and log the result. Never raises."""
    logger = logging.getLogger("traceloom")
    try:
        req = urllib.request.Request(f"{server_url}/api/meta", method="GET")
        resp = urllib.request.urlopen(req, timeout=2)  # noqa: S310
        logger.debug("connected to %s (%d)", server_url, resp.status)
    except Exception as err:
        logger.warning("failed to reach %s (%s)", server_url, err)


def log_resolved_config(provenance: dict[str, str], **fields: object) -> None:
    """Log the resolved configuration with provenance info."""
    logger = logging.getLogger("traceloom")
    lines = []
    for name, value in fields.items():
        source = provenance.get(name, "default")
        lines.append(f"  {name} = {value} ({source})")
    logger.debug("resolved config:\n%s", "\n".join(lines))
