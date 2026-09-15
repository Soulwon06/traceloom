"""Tests for dependency-free capture context handling."""

import asyncio

import pytest
from traceloom.hierarchy import (
    GroupReference,
    HttpRequestGroupMembership,
    PytestGroupMembership,
    activate_context,
    current_context,
    merge_group_memberships,
    serialize_hierarchy,
    start_child,
    start_http_request,
    start_root,
)


def _pytest_membership(label: str = "test_example") -> PytestGroupMembership:
    return PytestGroupMembership(
        test_directory=GroupReference(id="tests", label="tests"),
        test_file=GroupReference(id="tests/test_example.py", label="test_example.py"),
        test_class=None,
        test_case=GroupReference(
            id=f"tests/test_example.py::{label}",
            label=label,
        ),
    )


def test_start_child_inherits_and_replaces_memberships_by_kind():
    # Arrange
    root = start_root(
        trace_id="1" * 32,
        span_id="a" * 16,
        memberships=(_pytest_membership("parent"),),
    )

    # Act
    child = root.start_child(
        span_id="b" * 16,
        memberships=(
            _pytest_membership("child"),
            HttpRequestGroupMembership(
                hostname=GroupReference(id="api.stripe.com", label="api.stripe.com")
            ),
        ),
    )

    # Assert
    assert child.operation.trace_id == root.operation.trace_id
    assert child.operation.parent_span_id == root.operation.span_id
    assert [membership.kind for membership in child.group_memberships] == [
        "pytest",
        "http_request",
    ]
    assert child.group_memberships[0] == _pytest_membership("child")


def test_activate_context_restores_parent_after_exception():
    # Arrange
    root = start_root(trace_id="1" * 32, span_id="a" * 16)
    child = root.start_child(span_id="b" * 16)

    # Act / Assert
    with activate_context(root):
        with pytest.raises(RuntimeError, match="boom"):
            with activate_context(child):
                assert current_context() == child
                raise RuntimeError("boom")
        assert current_context() == root
    assert current_context() is None


def test_start_child_uses_active_context():
    # Arrange
    root = start_root(trace_id="1" * 32, span_id="a" * 16)

    # Act
    with activate_context(root):
        child = start_child(span_id="b" * 16)

    # Assert
    assert child.operation.parent_span_id == root.operation.span_id


def test_http_request_without_hostname_has_no_invalid_group_membership():
    # Act
    context = start_http_request("")

    # Assert
    assert context.group_memberships == ()


def test_serialize_hierarchy_distinguishes_operations_and_annotations():
    # Arrange
    context = start_root(
        trace_id="1" * 32,
        span_id="a" * 16,
        memberships=(_pytest_membership(),),
    ).start_child(span_id="b" * 16)

    # Act
    operation = serialize_hierarchy(context, role="operation")
    annotation = serialize_hierarchy(context, role="annotation")

    # Assert
    assert operation is not None
    assert annotation is not None
    assert operation["runtime"]["parent_span_id"] == "a" * 16
    assert operation["runtime"]["role"] == "operation"
    assert annotation["runtime"]["parent_span_id"] is None
    assert annotation["runtime"]["role"] == "annotation"
    assert annotation["group_memberships"][0]["kind"] == "pytest"


def test_contextvars_isolate_concurrent_async_work():
    # Arrange
    first = start_root(trace_id="1" * 32, span_id="a" * 16)
    second = start_root(trace_id="2" * 32, span_id="b" * 16)

    async def observe(context):
        with activate_context(context):
            await asyncio.sleep(0)
            return current_context()

    async def run():
        return await asyncio.gather(observe(first), observe(second))

    # Act
    observed = asyncio.run(run())

    # Assert
    assert observed == [first, second]
    assert current_context() is None


def test_merge_group_memberships_keeps_distinct_kinds():
    # Arrange
    pytest_membership = _pytest_membership()
    http_membership = HttpRequestGroupMembership(
        hostname=GroupReference(id="example.com", label="example.com")
    )

    # Act
    memberships = merge_group_memberships(
        inherited=(pytest_membership,),
        own=(http_membership,),
    )

    # Assert
    assert memberships == (pytest_membership, http_membership)
