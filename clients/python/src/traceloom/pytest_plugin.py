"""Pytest plugin for capturing one event per test function or method invocation."""

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pytest import CallInfo, Class, Function, TestReport

import traceloom
from traceloom import transport
from traceloom.hierarchy import (
    CaptureContext,
    GroupReference,
    PytestGroupMembership,
    activate_context,
    start_root,
)
from traceloom.utils import python_version

logger = logging.getLogger(__name__)


@dataclass
class TestState:
    timestamp: datetime
    test_id: str
    parameter_id: str | None
    name: str
    path: str
    line: int | None
    fixtures: list[str]
    context: CaptureContext
    reports: dict[str, TestReport] = field(default_factory=dict)
    failures: list[dict[str, str | None]] = field(default_factory=list)


_states: dict[str, TestState] = {}
_run_id = str(uuid.uuid4())
_worker_id = "master"


def pytest_configure(config: pytest.Config) -> None:
    """Resolve identifiers shared by all test events in this pytest process."""
    global _run_id, _worker_id

    worker_input = getattr(config, "workerinput", {})
    _run_id = (
        os.environ.get("PYTEST_XDIST_TESTRUNUID")
        or worker_input.get("testrunuid")
        or str(uuid.uuid4())
    )
    _worker_id = (
        os.environ.get("PYTEST_XDIST_WORKER")
        or worker_input.get("workerid")
        or "master"
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: pytest.Item):
    """Keep one root operation active across setup, call, and teardown."""
    if not traceloom.is_test_capture_enabled() or not isinstance(item, Function):
        yield
        return

    try:
        state = _create_test_state(item)
    except Exception:
        logger.debug("failed to start pytest capture", exc_info=True)
        yield
        return
    _states[item.nodeid] = state
    try:
        with activate_context(state.context):
            yield
    finally:
        _states.pop(item.nodeid, None)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Collect each runtest phase and emit one event after teardown."""
    outcome = yield
    if not traceloom.is_test_capture_enabled():
        _states.pop(getattr(item, "nodeid", ""), None)
        return

    report = outcome.get_result()

    try:
        if not isinstance(item, Function):
            return
        _record_report(item, call, report)
        if report.when == "teardown":
            _emit_test(item.nodeid)
    except Exception:
        logger.debug("failed to capture pytest test", exc_info=True)


def pytest_sessionfinish() -> None:
    """Flush completed test events before pytest exits."""
    if traceloom.is_test_capture_enabled():
        transport.flush(timeout=2.0)


def _record_report(item: Function, call: CallInfo[None], report: TestReport) -> None:
    """Add one setup, call, or teardown report to an invocation state."""
    phase = report.when
    if phase not in {"setup", "call", "teardown"}:
        return

    state = _states.get(item.nodeid)
    report_timestamp = datetime.fromtimestamp(report.start, tz=timezone.utc)
    if state is None:
        state = _create_test_state(item, timestamp=report_timestamp)
        _states[item.nodeid] = state
    elif report_timestamp < state.timestamp:
        state.timestamp = report_timestamp

    state.reports[phase] = report
    if report.failed and call.excinfo is not None:
        state.failures.append(
            {
                "phase": phase,
                "exception_type": call.excinfo.typename,
                "message": str(call.excinfo.value),
                "traceback_text": report.longreprtext,
            }
        )


def _emit_test(test_id: str) -> None:
    """Serialize a completed invocation and queue it for transport."""
    state = _states.pop(test_id, None)
    if state is None or not traceloom.is_test_capture_enabled():
        return

    setup_ms = _phase_duration_ms(state, "setup")
    call_ms = _phase_duration_ms(state, "call")
    teardown_ms = _phase_duration_ms(state, "teardown")
    status = _resolve_status(state.reports)

    transport.send_test(
        {
            "id": str(uuid.uuid4()),
            "timestamp": state.timestamp.isoformat(),
            "data": {
                "framework": "pytest",
                "framework_version": pytest.__version__,
                "python_version": python_version(),
                # Keep this wire key for compatibility with pre-TraceLoom servers.
                "traceloom_version": traceloom.__version__,
                "run_id": _run_id,
                "worker_id": _worker_id,
                "test_id": state.test_id,
                "parameter_id": state.parameter_id,
                "name": state.name,
                "path": state.path,
                "line": state.line,
                "status": status,
                "duration_ms": round(setup_ms + call_ms + teardown_ms, 3),
                "setup_duration_ms": setup_ms,
                "call_duration_ms": call_ms,
                "teardown_duration_ms": teardown_ms,
                "fixtures": state.fixtures,
                "failures": state.failures,
            },
        },
        context=state.context,
    )
    logger.debug("captured pytest test %s (%s)", state.test_id, status)


def _create_test_state(
    item: Function,
    *,
    timestamp: datetime | None = None,
) -> TestState:
    """Build invocation state and its immutable pytest hierarchy snapshot."""
    _path, zero_based_line, _domain = item.location
    membership = _pytest_membership(item)
    callspec = getattr(item, "callspec", None)
    return TestState(
        timestamp=timestamp or datetime.now(timezone.utc),
        test_id=item.nodeid,
        parameter_id=callspec.id if callspec is not None else None,
        name=item.name,
        path=str(item.path),
        line=zero_based_line + 1 if zero_based_line is not None else None,
        fixtures=list(item.fixturenames),
        context=start_root(memberships=(membership,)),
    )


def _pytest_membership(item: Function) -> PytestGroupMembership:
    """Describe a pytest invocation's collection path without parsing its node ID."""
    root_path = Path(item.config.rootpath)
    file_path = Path(item.path)
    try:
        relative_file = file_path.relative_to(root_path)
    except ValueError:
        relative_file = Path(os.path.relpath(file_path, root_path))

    file_id = relative_file.as_posix()
    directory = relative_file.parent.as_posix()
    class_node = item.getparent(Class)
    original_name = item.originalname or item.name
    parent_node_id = item.parent.nodeid if item.parent is not None else file_id
    return PytestGroupMembership(
        test_directory=(
            GroupReference(id=directory, label=directory) if directory != "." else None
        ),
        test_file=GroupReference(id=file_id, label=relative_file.name),
        test_class=(
            GroupReference(id=class_node.nodeid, label=class_node.name)
            if class_node is not None
            else None
        ),
        test_case=GroupReference(
            id=f"{parent_node_id}::{original_name}",
            label=original_name,
        ),
    )


def _phase_duration_ms(state: TestState, phase: str) -> float:
    """Return one phase duration in milliseconds."""
    report = state.reports.get(phase)
    return round(report.duration * 1000, 3) if report is not None else 0


def _resolve_status(reports: dict[str, TestReport]) -> str:
    """Map pytest's phase reports to one stable test status."""
    setup = reports.get("setup")
    call = reports.get("call")
    teardown = reports.get("teardown")

    if teardown is not None and teardown.failed:
        return "error"
    if setup is not None and setup.failed:
        return "error"
    if setup is not None and setup.skipped:
        return "xfailed" if _was_xfail(setup) else "skipped"
    if call is None:
        return "passed"
    if _was_xfail(call):
        return "xfailed" if call.skipped else "xpassed"
    if call.failed:
        return "failed"
    if call.skipped:
        return "skipped"
    if teardown is not None and teardown.skipped:
        return "skipped"
    return "passed"


def _was_xfail(report: TestReport) -> bool:
    """Return whether pytest marked the report as an expected failure."""
    return bool(getattr(report, "wasxfail", False))
