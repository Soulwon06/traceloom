"""Shared fixtures for client SDK tests."""

import sys

import pytest
import traceloom

pytest_plugins = ["pytester"]


@pytest.fixture(autouse=True)
def restore_traceloom_config():
    """Keep tests that call traceloom.init() from activating later tests."""
    original_config = traceloom._config
    try:
        yield
    finally:
        traceloom._config = original_config


class MockTransport:
    """In-memory recorder that mirrors the traceloom.transport API surface.

    Tests that patch a specific module's bound `transport` reference assert
    on the matching `*_calls` list.
    """

    def __init__(self):
        self.send_http_calls: list[dict] = []
        self.send_log_calls: list[dict] = []
        self.send_test_calls: list[dict] = []
        self.send_exception_calls: list[dict] = []
        self.flush_calls = 0

    def send_http(self, payload: dict, **kwargs) -> None:
        self.send_http_calls.append(payload)

    def send_log(self, payload: dict, **kwargs) -> None:
        self.send_log_calls.append(payload)

    def send_test(self, payload: dict, **kwargs) -> None:
        self.send_test_calls.append(payload)

    def send_exception(self, payload: dict, **kwargs) -> None:
        self.send_exception_calls.append(payload)

    def flush(self, timeout: float | None = None) -> bool:
        self.flush_calls += 1
        return True


@pytest.fixture
def mock_transport(monkeypatch):
    """Replace the `transport` attribute on every patch module with a recorder.

    Patches are bound by `from traceloom import transport` at module load, so
    the substitution must happen on each importing module. Doing it for all
    patch modules in one fixture keeps the test files simple.
    """
    recorder = MockTransport()
    for mod_name in (
        "traceloom.patches.patch_excepthook",
        "traceloom.patches.patch_logging",
        "traceloom.pytest_plugin",
    ):
        if mod_name in sys.modules:
            monkeypatch.setattr(sys.modules[mod_name], "transport", recorder)
    yield recorder
