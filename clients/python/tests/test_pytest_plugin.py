"""Integration tests for the bundled pytest plugin."""

import json
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
import traceloom
from traceloom import pytest_plugin


class CaptureHandler(BaseHTTPRequestHandler):
    captured: list[dict] = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        self.captured.append({"path": self.path, "body": body})
        self.send_response(201)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format, *args):
        pass


@pytest.fixture()
def capture_server():
    """Start a local HTTP server that records plugin payloads."""
    CaptureHandler.captured = []
    server = HTTPServer(("127.0.0.1", 0), CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", CaptureHandler.captured
    finally:
        server.shutdown()


def _wait_for_events(captured: list[dict], count: int, timeout: float = 5.0) -> None:
    """Wait until the capture server receives the expected event count."""
    deadline = time.monotonic() + timeout
    while len(captured) < count and time.monotonic() < deadline:
        time.sleep(0.05)


def test_protocol_continues_when_capture_state_cannot_be_created(monkeypatch):
    # Arrange
    class FakeFunction:
        nodeid = "tests/test_example.py::test_example"

    item = FakeFunction()
    monkeypatch.setattr(pytest_plugin, "Function", FakeFunction)
    monkeypatch.setattr(traceloom, "is_test_capture_enabled", lambda: True)

    def fail_to_create_state(_item):
        raise ValueError("different drive")

    monkeypatch.setattr(pytest_plugin, "_create_test_state", fail_to_create_state)
    protocol = pytest_plugin.pytest_runtest_protocol(item)

    # Act
    next(protocol)

    # Assert
    with pytest.raises(StopIteration):
        next(protocol)


def test_plugin_uses_xdist_run_and_worker_ids(monkeypatch):
    # Arrange
    monkeypatch.setenv("PYTEST_XDIST_TESTRUNUID", "xdist-run-123")
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw2")
    config = SimpleNamespace(workerinput={})

    # Act
    pytest_plugin.pytest_configure(config)

    # Assert
    assert pytest_plugin._run_id == "xdist-run-123"
    assert pytest_plugin._worker_id == "gw2"


def test_plugin_skips_report_processing_when_test_capture_is_disabled(monkeypatch):
    # Arrange
    monkeypatch.setattr(traceloom, "_config", None)

    def unexpected_get_result():
        raise AssertionError("disabled capture should not inspect the report")

    states_before = dict(pytest_plugin._states)
    outcome = SimpleNamespace(get_result=unexpected_get_result)
    hook = pytest_plugin.pytest_runtest_makereport(object(), object())
    next(hook)

    # Act
    with pytest.raises(StopIteration):
        hook.send(outcome)

    # Assert
    assert pytest_plugin._states == states_before


def test_plugin_captures_pytest_function_invocations(
    pytester,
    capture_server,
    monkeypatch,
):
    # Arrange
    server_url, captured = capture_server
    monkeypatch.setenv("TRACELOOM_URL", server_url)
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    pytester.makeconftest(
        """
        import pytest
        import traceloom

        traceloom.init()

        @pytest.fixture
        def setup_error():
            raise RuntimeError("setup exploded")

        @pytest.fixture
        def teardown_error():
            yield
            raise RuntimeError("teardown exploded")

        @pytest.fixture
        def lifecycle_context():
            from traceloom.hierarchy import current_context
            assert current_context() is not None
            yield
            assert current_context() is not None
        """
    )
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.parametrize("value", [1, 2], ids=["one", "two"])
        def test_parameterized(value):
            assert value > 0

        def test_assertion_failure():
            assert 9 == 10

        def test_skipped():
            pytest.skip("not on this platform")

        @pytest.mark.xfail(reason="known bug")
        def test_expected_failure():
            assert False

        @pytest.mark.xfail(reason="fixed")
        def test_unexpected_pass():
            assert True

        def test_setup_error(setup_error):
            pass

        def test_teardown_error(teardown_error):
            pass

        class TestCheckout:
            def test_method(self, lifecycle_context):
                from traceloom.hierarchy import current_context
                assert current_context() is not None
                assert True
        """
    )
    nested_directory = pytester.path / "page_analytics" / "event_tracker" / "tests"
    nested_directory.mkdir(parents=True)
    (nested_directory / "test_nested.py").write_text(
        "def test_nested():\n    assert True\n",
        encoding="utf-8",
    )

    # Act
    pytester.runpytest_subprocess("-p", "traceloom.pytest_plugin", "-q")

    # Assert
    _wait_for_events(captured, 10)
    test_events = [
        event["body"] for event in captured if event["path"] == "/api/capture/test"
    ]
    assert len(test_events) == 10

    data = [event["data"] for event in test_events]
    assert Counter(event["status"] for event in data) == {
        "passed": 4,
        "failed": 1,
        "error": 2,
        "skipped": 1,
        "xfailed": 1,
        "xpassed": 1,
    }
    assert len({event["run_id"] for event in data}) == 1
    assert {event["worker_id"] for event in data} == {"master"}
    assert all(Path(event["path"]).is_absolute() for event in data)

    parameterized = [
        event for event in data if "test_parameterized" in event["test_id"]
    ]
    assert {event["name"] for event in parameterized} == {
        "test_parameterized[one]",
        "test_parameterized[two]",
    }
    assert {event["parameter_id"] for event in parameterized} == {"one", "two"}
    assert all("value" in event["fixtures"] for event in parameterized)

    for event in test_events:
        runtime = event["hierarchy"]["runtime"]
        assert runtime["role"] == "operation"
        assert runtime["parent_span_id"] is None
        assert len(runtime["trace_id"]) == 32
        assert len(runtime["span_id"]) == 16
        membership = event["hierarchy"]["group_memberships"][0]
        assert membership["kind"] == "pytest"
        assert membership["test_file"]["label"].startswith("test_")

    nested_event = next(
        event for event in test_events if event["data"]["name"] == "test_nested"
    )
    nested_membership = nested_event["hierarchy"]["group_memberships"][0]
    assert nested_membership["test_directory"] == {
        "id": "page_analytics/event_tracker/tests",
        "label": "page_analytics/event_tracker/tests",
    }
    assert all(
        event["hierarchy"]["group_memberships"][0]["test_directory"] is None
        for event in test_events
        if event is not nested_event
    )

    failed = next(
        event for event in data if event["test_id"].endswith("test_assertion_failure")
    )
    assert failed["failures"][0]["phase"] == "call"
    assert failed["failures"][0]["exception_type"] == "AssertionError"
    assert "assert 9 == 10" in failed["failures"][0]["traceback_text"]
    assert failed["duration_ms"] == pytest.approx(
        failed["setup_duration_ms"]
        + failed["call_duration_ms"]
        + failed["teardown_duration_ms"],
        abs=0.002,
    )

    method = next(
        event for event in data if "TestCheckout::test_method" in event["test_id"]
    )
    assert method["name"] == "test_method"
    assert method["line"] > 0
    method_event = next(
        event
        for event in test_events
        if "TestCheckout::test_method" in event["data"]["test_id"]
    )
    method_membership = method_event["hierarchy"]["group_memberships"][0]
    assert method_membership["test_class"]["label"] == "TestCheckout"
    assert method_membership["test_case"]["label"] == "test_method"


def test_plugin_respects_disabled_test_capture(
    pytester,
    capture_server,
    monkeypatch,
):
    # Arrange
    server_url, captured = capture_server
    monkeypatch.setenv("TRACELOOM_URL", server_url)
    monkeypatch.setenv("TRACELOOM_CAPTURE_TESTS", "false")
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    pytester.makeconftest(
        """
        import traceloom
        traceloom.init()
        """
    )
    pytester.makepyfile(
        """
        def test_passes():
            assert True
        """
    )

    # Act
    result = pytester.runpytest_subprocess("-p", "traceloom.pytest_plugin", "-q")

    # Assert
    result.assert_outcomes(passed=1)
    assert captured == []
