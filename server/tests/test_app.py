"""Tests for server configuration, application lifespan, and SPA serving."""

from unittest.mock import AsyncMock

import pytest
import traceloom_server.app as app_module
import tortoise.context
from fastapi.testclient import TestClient
from traceloom_server.app import create_app, get_frontend_dir, get_retention_days


def test_retention_days_defaults_to_seven(monkeypatch):
    # Arrange
    monkeypatch.delenv("TRACELOOM_RETENTION_DAYS", raising=False)

    # Act
    retention_days = get_retention_days()

    # Assert
    assert retention_days == 7


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", 0),
        ("1", 1),
        (" 14 ", 14),
    ],
)
def test_retention_days_accepts_non_negative_integers(value, expected, monkeypatch):
    # Arrange
    monkeypatch.setenv("TRACELOOM_RETENTION_DAYS", value)

    # Act
    retention_days = get_retention_days()

    # Assert
    assert retention_days == expected


@pytest.mark.parametrize("value", ["", "abc", "1.5", "-1"])
def test_retention_days_rejects_invalid_values(value, monkeypatch):
    # Arrange
    monkeypatch.setenv("TRACELOOM_RETENTION_DAYS", value)

    # Act / Assert
    with pytest.raises(
        ValueError,
        match=r"TRACELOOM_RETENTION_DAYS must be a non-negative integer",
    ):
        get_retention_days()


def test_lifespan_runs_startup_cleanup_and_starts_loop(tmp_path, monkeypatch):
    # Arrange
    tortoise.context._global_context = None
    monkeypatch.setenv("TRACELOOM_RETENTION_DAYS", "3")
    startup_cleanup = AsyncMock(return_value=0)
    cleanup_loop = AsyncMock()
    monkeypatch.setattr(app_module, "cleanup_events_task", startup_cleanup)
    monkeypatch.setattr(app_module, "run_cleanup_loop_task", cleanup_loop)
    app = create_app(db_url=f"sqlite://{tmp_path / 'retention.db'}")

    # Act
    with TestClient(app):
        pass

    # Assert
    startup_cleanup.assert_awaited_once_with(retention_days=3)
    cleanup_loop.assert_awaited_once_with(retention_days=3)
    tortoise.context._global_context = None


def test_lifespan_skips_cleanup_when_disabled(tmp_path, monkeypatch):
    # Arrange
    tortoise.context._global_context = None
    monkeypatch.setenv("TRACELOOM_RETENTION_DAYS", "0")
    startup_cleanup = AsyncMock()
    cleanup_loop = AsyncMock()
    monkeypatch.setattr(app_module, "cleanup_events_task", startup_cleanup)
    monkeypatch.setattr(app_module, "run_cleanup_loop_task", cleanup_loop)
    app = create_app(db_url=f"sqlite://{tmp_path / 'retention.db'}")

    # Act
    with TestClient(app):
        pass

    # Assert
    startup_cleanup.assert_not_awaited()
    cleanup_loop.assert_not_awaited()
    tortoise.context._global_context = None


def test_lifespan_rejects_invalid_retention_value(tmp_path, monkeypatch):
    # Arrange
    tortoise.context._global_context = None
    monkeypatch.setenv("TRACELOOM_RETENTION_DAYS", "invalid")
    app = create_app(db_url=f"sqlite://{tmp_path / 'retention.db'}")

    # Act / Assert
    with pytest.raises(
        ValueError,
        match=r"TRACELOOM_RETENTION_DAYS must be a non-negative integer",
    ):
        with TestClient(app):
            pass

    tortoise.context._global_context = None


def test_env_var_with_valid_dir(tmp_path, monkeypatch):
    """TRACELOOM_FRONTEND_DIR pointing to a dir with index.html is returned."""
    (tmp_path / "index.html").write_text("<html></html>")
    monkeypatch.setenv("TRACELOOM_FRONTEND_DIR", str(tmp_path))
    assert get_frontend_dir() == tmp_path


def test_env_var_missing_index_html(tmp_path, monkeypatch):
    """Env var dir without index.html falls through."""
    fake_package = tmp_path / "traceloom_server"
    fake_package.mkdir()
    monkeypatch.setenv("TRACELOOM_FRONTEND_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "__file__", str(fake_package / "app.py"))
    # No index.html in tmp_path, should fall through to bundled check
    assert get_frontend_dir() is None


def test_bundled_frontend_detected(tmp_path, monkeypatch):
    """Bundled _frontend/ next to app.py is detected when no env var."""
    monkeypatch.delenv("TRACELOOM_FRONTEND_DIR", raising=False)

    # Create a fake _frontend dir next to a fake __file__
    fake_package = tmp_path / "traceloom_server"
    fake_package.mkdir()
    bundled = fake_package / "_frontend"
    bundled.mkdir()
    (bundled / "index.html").write_text("<html></html>")

    monkeypatch.setattr(app_module, "__file__", str(fake_package / "app.py"))
    assert get_frontend_dir() == bundled


def test_env_var_takes_precedence_over_bundled(tmp_path, monkeypatch):
    """TRACELOOM_FRONTEND_DIR takes precedence over bundled _frontend/."""
    env_dir = tmp_path / "env_frontend"
    env_dir.mkdir()
    (env_dir / "index.html").write_text("<html></html>")
    monkeypatch.setenv("TRACELOOM_FRONTEND_DIR", str(env_dir))

    # Also set up bundled dir
    fake_package = tmp_path / "traceloom_server"
    fake_package.mkdir()
    bundled = fake_package / "_frontend"
    bundled.mkdir()
    (bundled / "index.html").write_text("<html></html>")

    monkeypatch.setattr(app_module, "__file__", str(fake_package / "app.py"))
    assert get_frontend_dir() == env_dir


def test_no_frontend_returns_none(tmp_path, monkeypatch):
    """Neither env var nor bundled → returns None."""
    fake_package = tmp_path / "traceloom_server"
    fake_package.mkdir()
    monkeypatch.delenv("TRACELOOM_FRONTEND_DIR", raising=False)
    monkeypatch.setattr(app_module, "__file__", str(fake_package / "app.py"))
    result = get_frontend_dir()
    assert result is None


# --- SPA path traversal protection ---


@pytest.fixture()
def spa_client(tmp_path, monkeypatch):
    """TestClient with a frontend directory and a secret file outside it."""
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<html>index</html>")
    (frontend / "legit.txt").write_text("legit file")
    monkeypatch.setenv("TRACELOOM_FRONTEND_DIR", str(frontend))

    (tmp_path / "secret.txt").write_text("SECRET")

    tortoise.context._global_context = None
    app = create_app(db_url=f"sqlite://{tmp_path / 'test.db'}")
    with TestClient(app) as tc:
        yield tc
    tortoise.context._global_context = None


def test_spa_serves_legit_file(spa_client):
    """Files inside the frontend directory are served normally."""
    resp = spa_client.get("/legit.txt")
    assert resp.status_code == 200
    assert resp.text == "legit file"


def test_spa_path_traversal_percent_encoded(spa_client):
    """%2e%2e path traversal is blocked."""
    resp = spa_client.get("/%2e%2e/secret.txt")
    assert resp.status_code == 200
    assert "SECRET" not in resp.text
    assert "index" in resp.text


def test_spa_path_traversal_dot_dot(spa_client):
    """Literal ../ path traversal is blocked."""
    resp = spa_client.get("/../secret.txt")
    assert resp.status_code == 200
    assert "SECRET" not in resp.text


def test_spa_unknown_path_returns_index(spa_client):
    """Unknown paths return index.html (SPA fallback)."""
    resp = spa_client.get("/nonexistent/page")
    assert resp.status_code == 200
    assert "index" in resp.text
