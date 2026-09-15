"""In-process runtime correlation and navigation grouping context."""

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class OperationHandle:
    trace_id: str
    span_id: str
    parent_span_id: str | None = None


@dataclass(frozen=True, slots=True)
class GroupReference:
    id: str
    label: str


@dataclass(frozen=True, slots=True)
class PytestGroupMembership:
    test_directory: GroupReference | None
    test_file: GroupReference
    test_class: GroupReference | None
    test_case: GroupReference
    kind: Literal["pytest"] = field(init=False, default="pytest")


@dataclass(frozen=True, slots=True)
class HttpRequestGroupMembership:
    hostname: GroupReference
    kind: Literal["http_request"] = field(init=False, default="http_request")


GroupMembership = PytestGroupMembership | HttpRequestGroupMembership


@dataclass(frozen=True, slots=True)
class CaptureContext:
    operation: OperationHandle
    group_memberships: tuple[GroupMembership, ...] = ()

    def start_child(
        self,
        *,
        span_id: str | None = None,
        memberships: tuple[GroupMembership, ...] = (),
    ) -> "CaptureContext":
        return CaptureContext(
            operation=OperationHandle(
                trace_id=self.operation.trace_id,
                span_id=span_id or _new_span_id(),
                parent_span_id=self.operation.span_id,
            ),
            group_memberships=merge_group_memberships(
                inherited=self.group_memberships,
                own=memberships,
            ),
        )


CURRENT_CONTEXT: ContextVar[CaptureContext | None] = ContextVar(
    "traceloom_capture_context",
    default=None,
)


def start_root(
    *,
    trace_id: str | None = None,
    span_id: str | None = None,
    memberships: tuple[GroupMembership, ...] = (),
) -> CaptureContext:
    """Create a root operation context without activating it."""
    return CaptureContext(
        operation=OperationHandle(
            trace_id=trace_id or _new_trace_id(),
            span_id=span_id or _new_span_id(),
        ),
        group_memberships=memberships,
    )


def start_child(
    *,
    span_id: str | None = None,
    memberships: tuple[GroupMembership, ...] = (),
) -> CaptureContext:
    """Create a child of the active operation, or a root when none is active."""
    current = CURRENT_CONTEXT.get()
    if current is None:
        return start_root(span_id=span_id, memberships=memberships)
    return current.start_child(span_id=span_id, memberships=memberships)


def start_http_request(hostname: str) -> CaptureContext:
    """Create an outgoing HTTP child with normalized host membership."""
    normalized_hostname = hostname.lower()
    if not normalized_hostname:
        return start_child()
    return start_child(
        memberships=(
            HttpRequestGroupMembership(
                hostname=GroupReference(
                    id=normalized_hostname,
                    label=normalized_hostname,
                )
            ),
        )
    )


def set_context(context: CaptureContext) -> Token[CaptureContext | None]:
    """Activate a context and return the token needed to restore its parent."""
    return CURRENT_CONTEXT.set(context)


def reset_context(token: Token[CaptureContext | None]) -> None:
    """Restore the context that was active before the matching set."""
    CURRENT_CONTEXT.reset(token)


@contextmanager
def activate_context(context: CaptureContext) -> Iterator[CaptureContext]:
    """Activate a context for the duration of a caller-thread operation."""
    token = set_context(context)
    try:
        yield context
    finally:
        reset_context(token)


def current_context() -> CaptureContext | None:
    """Return the active immutable context snapshot."""
    return CURRENT_CONTEXT.get()


def serialize_hierarchy(
    context: CaptureContext | None,
    *,
    role: Literal["operation", "annotation"],
) -> dict[str, object] | None:
    """Serialize a detached or active context for a capture payload."""
    if context is None:
        return None

    operation = context.operation
    runtime: dict[str, object] = {
        "trace_id": operation.trace_id,
        "span_id": operation.span_id,
        "parent_span_id": operation.parent_span_id if role == "operation" else None,
        "role": role,
        "origin": "traceloom",
    }
    return {
        "runtime": runtime,
        "group_memberships": [
            asdict(membership) for membership in context.group_memberships
        ],
    }


def merge_group_memberships(
    *,
    inherited: tuple[GroupMembership, ...],
    own: tuple[GroupMembership, ...],
) -> tuple[GroupMembership, ...]:
    """Inherit memberships and replace matching kinds with child values."""
    merged = {membership.kind: membership for membership in inherited}
    merged.update({membership.kind: membership for membership in own})
    return tuple(merged.values())


def _new_span_id() -> str:
    """Create one non-zero lowercase hexadecimal span ID."""
    return _new_hex_id(8)


def _new_trace_id() -> str:
    """Create one non-zero lowercase hexadecimal trace ID."""
    return _new_hex_id(16)


def _new_hex_id(byte_count: int) -> str:
    """Generate a random hexadecimal ID, retrying the forbidden all-zero value."""
    while True:
        value = secrets.token_hex(byte_count)
        if int(value, 16) != 0:
            return value
