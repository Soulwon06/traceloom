"""Tests for traceloom.config.TraceLoomConfig."""

import pytest
from traceloom.config import TraceLoomConfig


@pytest.fixture()
def default_config():
    return TraceLoomConfig(server_url="http://test:5110")


@pytest.fixture()
def selective_config():
    return TraceLoomConfig(
        server_url="http://test:5110",
        capture_all=False,
        capture_hosts=["api.stripe.com"],
    )


def test_capture_all_by_default(default_config):
    assert default_config.should_capture("api.stripe.com") is True
    assert default_config.should_capture("example.com") is True


def test_ignore_hosts():
    config = TraceLoomConfig(
        server_url="http://test:5110", ignore_hosts=["localhost", "127.0.0.1"]
    )
    assert config.should_capture("localhost") is False
    assert config.should_capture("127.0.0.1") is False
    assert config.should_capture("api.stripe.com") is True


def test_capture_specific_hosts_only(selective_config):
    assert selective_config.should_capture("api.stripe.com") is True
    assert selective_config.should_capture("api.openai.com") is False


def test_ignore_takes_precedence_over_capture_hosts():
    config = TraceLoomConfig(
        server_url="http://test:5110",
        capture_all=False,
        capture_hosts=["api.stripe.com"],
        ignore_hosts=["api.stripe.com"],
    )
    assert config.should_capture("api.stripe.com") is False


def test_ignore_loggers_defaults_to_empty():
    config = TraceLoomConfig(server_url="http://test:5110")
    assert config.ignore_loggers == []


def test_ignore_loggers_accepts_list():
    config = TraceLoomConfig(
        server_url="http://test:5110",
        ignore_loggers=["uvicorn.access", "uvicorn.error"],
    )
    assert config.ignore_loggers == ["uvicorn.access", "uvicorn.error"]


def test_capture_tests_defaults_to_true(default_config):
    assert default_config.capture_tests is True


def test_capture_tests_can_be_disabled():
    config = TraceLoomConfig(server_url="http://test:5110", capture_tests=False)
    assert config.capture_tests is False


def test_ignore_takes_precedence_over_capture_all():
    config = TraceLoomConfig(
        server_url="http://test:5110",
        capture_all=True,
        ignore_hosts=["secret.internal"],
    )
    assert config.should_capture("secret.internal") is False
    assert config.should_capture("anything.else") is True


def test_app_and_session_default_to_empty():
    config = TraceLoomConfig(server_url="http://test:5110")
    assert config.app == ""
    assert config.session == ""


def test_app_and_session_accept_values():
    config = TraceLoomConfig(server_url="http://test:5110", app="myapp", session="sess-1")
    assert config.app == "myapp"
    assert config.session == "sess-1"
