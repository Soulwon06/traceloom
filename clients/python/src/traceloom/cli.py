"""``traceloom`` console script.

``traceloom run <command>`` activates TraceLoom in a wrapped process without code
changes. It prepends a bootstrap directory containing ``sitecustomize.py`` to
``PYTHONPATH``, then executes the user's command. Subprocess
instrumentation propagates automatically because PYTHONPATH is inherited.

``traceloom clear`` deletes all captured events from a TraceLoom server.

Modeled on ``ddtrace-run`` and ``opentelemetry-instrument``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence

import traceloom
from traceloom._env import parse_log_level
from traceloom.query import (
    DEFAULT_SERVER_URL,
    QueryError,
    print_events,
    print_meta,
    print_stats,
    query_events,
    query_meta,
    query_stats,
)

CLEAR_TIMEOUT_SECONDS = 5
MAX_QUERY_LIMIT = 10000


def _parse_query_limit(value: str) -> int:
    """Argparse type for a query limit between 1 and MAX_QUERY_LIMIT."""
    try:
        limit = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("limit must be an integer") from error
    if not 1 <= limit <= MAX_QUERY_LIMIT:
        raise argparse.ArgumentTypeError(
            f"limit must be between 1 and {MAX_QUERY_LIMIT}"
        )
    return limit


def _parse_log_level_arg(value: str) -> int:
    """Argparse type for --log-level: accepts an int or a level name."""
    result = parse_log_level(value)
    if result is None:
        raise argparse.ArgumentTypeError(
            f"invalid log level: {value!r} "
            "(use DEBUG, INFO, WARNING, ERROR, CRITICAL, or an integer)"
        )
    return result


def _bootstrap_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(traceloom.__file__)), "bootstrap")


PYTHON_SCRIPT_SUFFIXES = (".py", ".pyw")


def _resolve_executable(command: list[str]) -> tuple[str, list[str]]:
    """Find the executable to invoke and return ``(executable, argv)``.

    If ``command[0]`` looks like a Python script (ends in ``.py``/``.pyw``),
    prepend ``sys.executable`` so the script runs even when it lacks an
    executable bit or shebang. This matches ``coverage run script.py`` UX.
    Otherwise, resolve via ``PATH``.
    """
    first = command[0]
    if first.endswith(PYTHON_SCRIPT_SUFFIXES):
        return sys.executable, [sys.executable, *command]
    return shutil.which(first) or first, command


def _traceloom_env_overrides(args: argparse.Namespace) -> dict[str, str]:
    """Translate parsed CLI flags into ``TRACELOOM_*`` env vars to set on the child.

    Pure function: depends only on ``args``. Returns the env vars the user
    asked for via flags. The caller merges these into the child's environment
    (see :func:`_build_child_env`).
    """
    overrides: dict[str, str] = {}

    if args.server:
        overrides["TRACELOOM_URL"] = args.server
    if args.capture_host:
        overrides["TRACELOOM_CAPTURE_HOSTS"] = ",".join(args.capture_host)
    if args.ignore_host:
        overrides["TRACELOOM_IGNORE_HOSTS"] = ",".join(args.ignore_host)
    if args.capture_all is not None:
        overrides["TRACELOOM_CAPTURE_ALL"] = "true" if args.capture_all else "false"
    elif args.capture_host:
        # `--capture-host` without an explicit `--capture-all` means "only these".
        # Match the help text ("Capture only this host") and the user's intuition.
        overrides["TRACELOOM_CAPTURE_ALL"] = "false"
    if args.redact_header:
        overrides["TRACELOOM_REDACT_HEADERS"] = ",".join(args.redact_header)
    if args.redact_query_param:
        overrides["TRACELOOM_REDACT_QUERY_PARAMS"] = ",".join(args.redact_query_param)
    if args.capture_exceptions is not None:
        overrides["TRACELOOM_CAPTURE_EXCEPTIONS"] = (
            "true" if args.capture_exceptions else "false"
        )
    if args.capture_tests is not None:
        overrides["TRACELOOM_CAPTURE_TESTS"] = "true" if args.capture_tests else "false"
    if args.capture_logs is not None:
        overrides["TRACELOOM_CAPTURE_LOGS"] = "true" if args.capture_logs else "false"
    if args.log_level is not None:
        overrides["TRACELOOM_LOG_LEVEL"] = str(args.log_level)
    if args.ignore_logger:
        overrides["TRACELOOM_IGNORE_LOGGERS"] = ",".join(args.ignore_logger)
    if args.app is not None:
        overrides["TRACELOOM_APP"] = args.app
    if args.session is not None:
        overrides["TRACELOOM_SESSION"] = args.session
    if args.debug is not None:
        overrides["TRACELOOM_DEBUG"] = "true" if args.debug else "false"

    return overrides


_ENV_TO_FLAG: dict[str, str] = {
    "TRACELOOM_URL": "--server",
    "TRACELOOM_CAPTURE_HOSTS": "--capture-host",
    "TRACELOOM_IGNORE_HOSTS": "--ignore-host",
    "TRACELOOM_REDACT_HEADERS": "--redact-header",
    "TRACELOOM_REDACT_QUERY_PARAMS": "--redact-query-param",
    "TRACELOOM_LOG_LEVEL": "--log-level",
    "TRACELOOM_IGNORE_LOGGERS": "--ignore-logger",
    "TRACELOOM_APP": "--app",
    "TRACELOOM_SESSION": "--session",
}


def _cli_provenance(
    args: argparse.Namespace, overrides: dict[str, str]
) -> dict[str, str | None]:
    """Map TRACELOOM_* env vars set by the CLI to the flag that produced them.

    Returns a dict of ``{env_var_name: flag_name_or_None}``.  A string
    value means the user explicitly passed that flag; ``None`` means the
    CLI injected a default (e.g. ``TRACELOOM_URL`` when ``--server`` was
    not given).
    """
    provenance: dict[str, str | None] = {}
    for env_var in overrides:
        if env_var in _ENV_TO_FLAG:
            provenance[env_var] = _ENV_TO_FLAG[env_var]
        elif env_var == "TRACELOOM_CAPTURE_ALL":
            if args.capture_all is not None:
                provenance[env_var] = (
                    "--capture-all" if args.capture_all is True else "--no-capture-all"
                )
            else:
                provenance[env_var] = "--capture-host"
        elif env_var == "TRACELOOM_CAPTURE_EXCEPTIONS":
            provenance[env_var] = (
                "--capture-exceptions"
                if args.capture_exceptions is True
                else "--no-capture-exceptions"
            )
        elif env_var == "TRACELOOM_CAPTURE_TESTS":
            provenance[env_var] = (
                "--capture-tests"
                if args.capture_tests is True
                else "--no-capture-tests"
            )
        elif env_var == "TRACELOOM_CAPTURE_LOGS":
            provenance[env_var] = (
                "--capture-logs" if args.capture_logs is True else "--no-capture-logs"
            )
        elif env_var == "TRACELOOM_DEBUG":
            provenance[env_var] = "--debug" if args.debug is True else "--no-debug"
    return provenance


def _build_child_env(args: argparse.Namespace) -> dict[str, str]:
    """Build the full environment for the wrapped child process.

    Starts from ``os.environ``, applies CLI-flag overrides, prepends the
    bootstrap directory to ``PYTHONPATH``, and defaults ``TRACELOOM_URL`` if
    neither flag nor env var supplied one.
    """
    env = os.environ.copy()
    overrides = _traceloom_env_overrides(args)
    env.update(overrides)

    bootstrap = _bootstrap_dir()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{bootstrap}{os.pathsep}{existing}" if existing else bootstrap

    provenance = _cli_provenance(args, overrides)

    # Default server URL when neither --server nor TRACELOOM_URL is set.
    if "TRACELOOM_URL" not in env:
        env["TRACELOOM_URL"] = DEFAULT_SERVER_URL
        provenance["TRACELOOM_URL"] = None

    env["_TRACELOOM_CLI_PROVENANCE"] = json.dumps(provenance)
    return env


def _run_child(executable: str, command: list[str], env: dict[str, str]) -> int:
    """Run the wrapped command and return its exit code.

    ``os.execvpe`` is reliable on POSIX, but on Windows with the supported
    Python runtime it can terminate with an access violation before the target
    process starts. ``subprocess.run`` preserves inherited stdout/stderr and
    avoids shell command-line reconstruction on Windows.
    """
    if sys.platform == "win32":
        completed = subprocess.run(command, env=env, check=False)
        return completed.returncode

    os.execvpe(executable, command, env)
    return 0  # unreachable on successful POSIX exec


def _server_url(server: str | None) -> str:
    """Resolve a CLI server flag, environment variable, or the default URL."""
    return (server or os.environ.get("TRACELOOM_URL") or DEFAULT_SERVER_URL).strip()


def _clear_events(server_url: str) -> int:
    """Delete all events from a TraceLoom server and return a process exit code."""
    endpoint = f"{server_url.rstrip('/')}/api/events"
    try:
        request = urllib.request.Request(endpoint, method="DELETE")
        with urllib.request.urlopen(request, timeout=CLEAR_TIMEOUT_SECONDS) as response:  # noqa: S310
            if response.status != 204:
                print(
                    f"traceloom: failed to clear events: server returned {response.status}",
                    file=sys.stderr,
                )
                return 1
    except urllib.error.HTTPError as error:
        print(
            f"traceloom: failed to clear events: server returned {error.code}",
            file=sys.stderr,
        )
        return 1
    except urllib.error.URLError as error:
        print(f"traceloom: failed to reach {server_url}: {error.reason}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"traceloom: invalid server URL {server_url!r}: {error}", file=sys.stderr)
        return 1

    print(f"traceloom: cleared all events from {server_url}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser."""
    parser = argparse.ArgumentParser(
        prog="traceloom",
        description=(
            "Capture Python HTTP traffic, pytest executions, logs, and exceptions "
            "in a local dashboard."
        ),
    )
    parser.add_argument("--version", action="version", version=traceloom.__version__)
    sub = parser.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")

    run = sub.add_parser(
        "run",
        help="Run a command with TraceLoom capturing its HTTP traffic.",
        description=(
            "Wrap a command so TraceLoom captures its outgoing HTTP traffic without "
            "modifying source. Use `--` to separate TraceLoom flags from the wrapped "
            "command when needed."
        ),
    )
    run.add_argument(
        "--server",
        metavar="URL",
        help=f"TraceLoom server URL (default: {DEFAULT_SERVER_URL}).",
    )
    run.add_argument(
        "--clear",
        action="store_true",
        help="Clear all existing events before running the command.",
    )
    run.add_argument(
        "--capture-host",
        action="append",
        metavar="HOST",
        help="Capture only this host (repeatable). Sets TRACELOOM_CAPTURE_HOSTS.",
    )
    run.add_argument(
        "--ignore-host",
        action="append",
        metavar="HOST",
        help="Ignore this host (repeatable). Sets TRACELOOM_IGNORE_HOSTS.",
    )
    run.add_argument(
        "--capture-all",
        dest="capture_all",
        action="store_true",
        default=None,
        help="Capture all hosts (default).",
    )
    run.add_argument(
        "--no-capture-all",
        dest="capture_all",
        action="store_false",
        help="Capture only hosts listed via --capture-host.",
    )
    run.add_argument(
        "--redact-header",
        action="append",
        metavar="HEADER",
        help="Redact this header value (repeatable).",
    )
    run.add_argument(
        "--redact-query-param",
        action="append",
        metavar="PARAM",
        help="Redact this query parameter value (repeatable).",
    )
    run.add_argument(
        "--capture-exceptions",
        dest="capture_exceptions",
        action="store_true",
        default=None,
        help="Capture unhandled exceptions (default).",
    )
    run.add_argument(
        "--no-capture-exceptions",
        dest="capture_exceptions",
        action="store_false",
        help="Disable unhandled-exception capture.",
    )
    run.add_argument(
        "--capture-tests",
        dest="capture_tests",
        action="store_true",
        default=None,
        help="Capture pytest test executions (default).",
    )
    run.add_argument(
        "--no-capture-tests",
        dest="capture_tests",
        action="store_false",
        help="Disable pytest test capture.",
    )
    run.add_argument(
        "--capture-logs",
        dest="capture_logs",
        action="store_true",
        default=None,
        help="Capture Python log records (off by default).",
    )
    run.add_argument(
        "--no-capture-logs",
        dest="capture_logs",
        action="store_false",
        help="Disable log capture.",
    )
    run.add_argument(
        "--log-level",
        type=_parse_log_level_arg,
        metavar="LEVEL",
        default=None,
        help=(
            "Minimum log level to capture (e.g. DEBUG, INFO, WARNING, or 10, 20, 30). "
            "Acts as a filter on records that already pass the app's logger level — "
            "it cannot override the app's logging configuration."
        ),
    )
    run.add_argument(
        "--ignore-logger",
        action="append",
        metavar="LOGGER",
        help="Ignore this logger name for log capture (repeatable). Sets TRACELOOM_IGNORE_LOGGERS.",
    )
    run.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        default=None,
        help="Enable debug logging to stderr.",
    )
    run.add_argument(
        "--no-debug",
        dest="debug",
        action="store_false",
        help="Disable debug logging.",
    )
    run.add_argument(
        "--app",
        metavar="NAME",
        help="Application name tag. Sets TRACELOOM_APP.",
    )
    run.add_argument(
        "--session",
        metavar="ID",
        help="Session ID tag. Sets TRACELOOM_SESSION.",
    )
    run.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        metavar="COMMAND [ARGS...]",
        help="The command to wrap. Use `--` to disambiguate from TraceLoom flags.",
    )

    clear = sub.add_parser(
        "clear",
        help="Clear all captured events from a TraceLoom server.",
    )
    clear.add_argument(
        "--server",
        metavar="URL",
        help=f"TraceLoom server URL (default: {DEFAULT_SERVER_URL}).",
    )

    query = sub.add_parser(
        "query",
        help="Query captured events from a TraceLoom server.",
        description=(
            "List captured events or inspect one event by displayed ID, UUID, or "
            "dashboard URL. "
            "List queries default to compact text; event lookups default to JSON."
        ),
    )
    query.add_argument(
        "target",
        nargs="?",
        metavar="EVENT_ID_OR_URL",
        help="Displayed ID, full UUID, or dashboard URL. Omit to list events.",
    )
    query.add_argument(
        "--server",
        metavar="URL",
        help=(
            "TraceLoom server URL. Defaults to TRACELOOM_URL, the dashboard URL origin, "
            f"or {DEFAULT_SERVER_URL}."
        ),
    )
    query.add_argument("--type", dest="event_type", metavar="TYPE", help="Event type.")
    query.add_argument("--host", help="Exact remote hostname.")
    query.add_argument("--method", help="Exact HTTP method.")
    query.add_argument("--status", type=int, help="Exact HTTP response status.")
    query.add_argument("--search", help="Text in the event summary or data.")
    query.add_argument("--app", help="Exact application tag.")
    query.add_argument("--session", help="Exact session tag.")
    query.add_argument(
        "--ancestors",
        action="store_true",
        help="Include runtime parents of matching events.",
    )
    query.add_argument(
        "--after-seq",
        type=int,
        metavar="SEQ",
        help=(
            "Return only events captured after this seq, so repeated calls tail "
            "a run instead of re-listing it. Cannot be combined with --ancestors."
        ),
    )
    query.add_argument(
        "--stats",
        action="store_true",
        help="Print counts by event type, test status, and HTTP status class "
        "instead of the events themselves.",
    )
    query.add_argument(
        "--limit",
        type=_parse_query_limit,
        default=50,
        metavar="N",
        help=f"Maximum matching events, from 1 to {MAX_QUERY_LIMIT} (default: 50).",
    )
    query.add_argument(
        "--format",
        choices=("text", "json", "jsonl"),
        dest="output_format",
        help="Output format. Defaults to text for lists and JSON for one event.",
    )

    meta = sub.add_parser(
        "meta",
        help="Show which apps, sessions, hosts, and event types were captured.",
        description=(
            "Show the filter metadata a TraceLoom server knows about: its version, "
            "and every application, session, event type, host, and HTTP method "
            "present in the captured events."
        ),
    )
    meta.add_argument(
        "--server",
        metavar="URL",
        help=f"TraceLoom server URL. Defaults to TRACELOOM_URL, or {DEFAULT_SERVER_URL}.",
    )
    meta.add_argument(
        "--format",
        choices=("text", "json"),
        dest="output_format",
        default="text",
        help="Output format (default: text).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Console-script entry point. Returns a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.subcommand == "clear":
        return _clear_events(_server_url(args.server))

    if args.subcommand == "meta":
        try:
            meta = query_meta(server=args.server)
        except QueryError as error:
            print(f"traceloom meta: {error}", file=sys.stderr)
            return 1
        print_meta(meta, output_format=args.output_format)
        return 0

    if args.subcommand == "query":
        if args.stats and args.target is not None:
            print("traceloom query: --stats does not take an event ID", file=sys.stderr)
            return 2
        try:
            if args.stats:
                stats = query_stats(
                    server=args.server,
                    event_type=args.event_type,
                    host=args.host,
                    method=args.method,
                    status=args.status,
                    search=args.search,
                    app=args.app,
                    session=args.session,
                )
                print_stats(stats, output_format=args.output_format or "text")
                return 0
            payload = query_events(
                target=args.target,
                server=args.server,
                event_type=args.event_type,
                host=args.host,
                method=args.method,
                status=args.status,
                search=args.search,
                app=args.app,
                session=args.session,
                ancestors=args.ancestors,
                after_seq=args.after_seq,
                limit=args.limit,
            )
        except QueryError as error:
            print(f"traceloom query: {error}", file=sys.stderr)
            return 1
        print_events(
            payload,
            output_format=args.output_format
            or ("json" if args.target is not None else "text"),
        )
        return 0

    if args.subcommand != "run":
        parser.print_help(sys.stderr)
        return 2

    command = list(args.command)
    # argparse.REMAINDER preserves a leading `--` (it doesn't consume it the
    # way a normal positional would). Strip it so users can write
    # `traceloom run -- pytest tests/` for disambiguation.
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("traceloom run: no command specified", file=sys.stderr)
        print("usage: traceloom run [OPTIONS] [--] COMMAND [ARGS...]", file=sys.stderr)
        return 2

    if args.clear:
        clear_exit_code = _clear_events(_server_url(args.server))
        if clear_exit_code:
            return clear_exit_code

    env = _build_child_env(args)
    executable, command = _resolve_executable(command)

    try:
        return _run_child(executable, command, env)
    except FileNotFoundError:
        print(f"traceloom run: command not found: {command[0]}", file=sys.stderr)
        return 127
    except PermissionError:
        print(
            f"traceloom run: permission denied: {command[0]}\n"
            "If this is a Python script, prefix the command with `python`:\n"
            f"  traceloom run -- python {command[0]}",
            file=sys.stderr,
        )
        return 126
    return 0  # unreachable on successful POSIX exec


if __name__ == "__main__":
    sys.exit(main())
