"""Store epoch — the token clients use to detect that their cursor is void.

The event cursor is SQLite's ``rowid``, which only ever grows while rows are
appended. Anything that removes rows wholesale (clear-all, retention prune) or
renumbers them (``VACUUM``, a fresh process against a new database) invalidates
a client's accumulated store. Rather than track tombstones, the server publishes
an opaque epoch string; when it changes, clients drop everything and resync.

The instance id is generated at import, so a server restart is itself an epoch
change — which is what we want, because a restart may have followed a
``VACUUM``.
"""

from uuid import uuid4

_INSTANCE_ID = uuid4().hex[:8]
_counter = 0


def current_epoch() -> str:
    """Return the epoch token to hand to clients."""
    return f"{_INSTANCE_ID}:{_counter}"


def bump_epoch() -> None:
    """Invalidate every client store. Call after deleting rows."""
    global _counter
    _counter += 1
