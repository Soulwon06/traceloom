"""CLI entry point: `traceloom-server` (or `python -m traceloom_server`).

By default, `traceloom-server [OPTIONS]` starts the server. The `run` and
`openapi-export` subcommands exist but are hidden from `--help` since they
are dev/CI tooling — `run` stays callable as an explicit alias for
backwards compatibility (e.g. `just server`, the Dockerfile).
"""

import json
import logging
import os
import threading
import webbrowser
from copy import deepcopy
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from uvicorn.config import LOGGING_CONFIG

import traceloom_server

logger = logging.getLogger("traceloom_server")

DEFAULT_DB_DIR = Path.home() / ".traceloom"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "traceloom.db"

UVICORN_LOGGING_CONFIG = deepcopy(LOGGING_CONFIG)
UVICORN_LOGGING_CONFIG["loggers"]["traceloom_server"] = {
    "handlers": ["default"],
    "level": "INFO",
    "propagate": False,
}


def _version_callback(value: bool):
    if value:
        typer.echo(f"traceloom-server {traceloom_server.__version__}")
        raise typer.Exit()


app = typer.Typer(add_completion=False)


def _get_url(host: str, port: int) -> str:
    if host in ("0.0.0.0", "127.0.0.1", "localhost"):
        return f"http://localhost:{port}"
    return f"http://{host}:{port}"


def _print_banner(host: str, port: int):
    console = Console()
    url = _get_url(host, port)

    body = Text()
    body.append("TraceLoom is running at ", style="bold")
    body.append(url, style="bold #FFA600")
    body.append("\n\n", style="dim")
    body.append("Local dashboard ready.", style="dim")

    console.print()
    console.print(Panel(body, border_style="#FFA600", expand=False, padding=(1, 2)))
    console.print()


def _start_server(
    *,
    host: str,
    port: int,
    db_path: str | None,
    reload: bool,
    open_browser: bool,
) -> None:
    if db_path:
        os.environ["TRACELOOM_DB_PATH"] = db_path

    resolved_db = db_path or os.environ.get("TRACELOOM_DB_PATH") or str(DEFAULT_DB_PATH)
    logging.basicConfig(level=logging.INFO)
    logger.info("Database: %s", resolved_db)

    _print_banner(host, port)

    if open_browser:
        url = _get_url(host, port)
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()

    uvicorn.run(
        "traceloom_server.app:create_app",
        factory=True,
        host=host,
        port=port,
        log_level="info",
        log_config=UVICORN_LOGGING_CONFIG,
        reload=reload,
    )


HOST_OPT = Annotated[str, typer.Option(help="Host to bind to.")]
PORT_OPT = Annotated[int, typer.Option(help="Port to bind to.")]
DB_PATH_OPT = Annotated[
    str | None,
    typer.Option(help=f"Path to SQLite database file (default: {DEFAULT_DB_PATH})."),
]
RELOAD_OPT = Annotated[bool, typer.Option(help="Enable auto-reload on code changes.")]
OPEN_BROWSER_OPT = Annotated[
    bool,
    typer.Option("--open/--no-open", help="Open the dashboard in a browser."),
]


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    host: HOST_OPT = "127.0.0.1",
    port: PORT_OPT = 5110,
    db_path: DB_PATH_OPT = None,
    reload: RELOAD_OPT = False,
    open_browser: OPEN_BROWSER_OPT = True,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
):
    """Start the TraceLoom server."""
    if ctx.invoked_subcommand is not None:
        return
    _start_server(
        host=host,
        port=port,
        db_path=db_path,
        reload=reload,
        open_browser=open_browser,
    )


@app.command(hidden=True)
def run(
    host: HOST_OPT = "127.0.0.1",
    port: PORT_OPT = 5110,
    db_path: DB_PATH_OPT = None,
    reload: RELOAD_OPT = False,
    open_browser: OPEN_BROWSER_OPT = True,
):
    """Start the TraceLoom server (alias for the bare invocation)."""
    _start_server(
        host=host,
        port=port,
        db_path=db_path,
        reload=reload,
        open_browser=open_browser,
    )


@app.command("openapi-export", hidden=True)
def openapi_export(
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Where to write the OpenAPI schema."),
    ] = Path("frontend/openapi.json"),
):
    """Export the FastAPI OpenAPI schema to a JSON file.

    Used by the frontend's `openapi-typescript` step to generate TS types.
    """
    # Imported lazily so unrelated CLI invocations (e.g. `--help`) don't pay
    # the cost of loading FastAPI + Tortoise.
    from traceloom_server.app import create_app  # noqa: PLC0415

    schema = create_app().openapi()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, indent=2) + "\n")
    typer.echo(f"Wrote OpenAPI schema → {output}")


def main():
    app()


if __name__ == "__main__":
    main()
