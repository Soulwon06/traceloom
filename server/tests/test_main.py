"""Tests for the TraceLoom server CLI configuration."""

from traceloom_server.__main__ import UVICORN_LOGGING_CONFIG


def test_uvicorn_logging_config_enables_server_info_logs():
    # Act
    server_logger = UVICORN_LOGGING_CONFIG["loggers"]["traceloom_server"]

    # Assert
    assert server_logger == {
        "handlers": ["default"],
        "level": "INFO",
        "propagate": False,
    }
