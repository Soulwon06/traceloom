"""Tests for querying captured events from the command line."""

import io
import json
import os
import urllib.error
from unittest.mock import patch

import pytest
from traceloom import cli
from traceloom.query import print_events


def _response(payload: object) -> io.BytesIO:
    return io.BytesIO(json.dumps(payload).encode())


def _envelope(events: list[dict], *, epoch: str = "abc12345:0") -> dict:
    """Wrap events the way `GET /api/events` returns them."""
    max_seq = max((event["seq"] for event in events), default=0)
    return {"epoch": epoch, "max_seq": max_seq, "events": events}


def _event(
    event_id: str,
    *,
    seq: int = 1,
    event_type: str = "http",
    summary: str = "GET /health -> 200",
    trace_id: str | None = None,
    span_id: str | None = None,
    parent_span_id: str | None = None,
    role: str = "operation",
    app: str = "",
    session: str = "",
) -> dict:
    hierarchy = None
    if trace_id is not None and span_id is not None:
        hierarchy = {
            "runtime": {
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "role": role,
            }
        }
    return {
        "id": event_id,
        "seq": seq,
        "timestamp": "2026-08-04T12:42:31+00:00",
        "event_type": event_type,
        "summary": summary,
        "app": app,
        "session": session,
        "hierarchy": hierarchy,
    }


def test_query_list_sends_existing_api_filters(capsys):
    # Arrange
    payload = _envelope([_event("5ae54ca2-45a7-45a6-a6cd-533569fc8db7", seq=12)])

    # Act
    with patch(
        "traceloom.query.urllib.request.urlopen", return_value=_response(payload)
    ) as urlopen:
        exit_code = cli.main(
            [
                "query",
                "--server",
                "http://traceloom:5110/",
                "--type",
                "http",
                "--host",
                "api.example.com",
                "--method",
                "post",
                "--status",
                "500",
                "--search",
                "ConnectError",
                "--app",
                "checkout",
                "--session",
                "debug-payment",
                "--ancestors",
                "--limit",
                "100",
            ]
        )

    # Assert
    assert exit_code == 0
    assert urlopen.call_args.args[0] == (
        "http://traceloom:5110/api/events?limit=100&event_type=http"
        "&host=api.example.com&method=post&status=500&search=ConnectError"
        "&app=checkout&session=debug-payment&include_ancestors=true"
    )
    assert urlopen.call_args.kwargs["timeout"] == 5
    assert capsys.readouterr().out == (
        "12:42:31     12  http          GET /health -> 200  5ae54ca2\n"
    )


def test_query_after_seq_tails_a_run(capsys):
    # Arrange
    payload = _envelope([_event("5ae54ca2-45a7-45a6-a6cd-533569fc8db7", seq=41)])

    # Act
    with patch(
        "traceloom.query.urllib.request.urlopen", return_value=_response(payload)
    ) as urlopen:
        exit_code = cli.main(["query", "--after-seq", "40"])

    # Assert
    assert exit_code == 0
    assert urlopen.call_args.args[0] == (
        "http://localhost:5110/api/events?limit=50&after_seq=40"
    )


def test_query_json_keeps_the_envelope_so_callers_get_the_cursor(capsys):
    # Arrange
    payload = _envelope([_event("5ae54ca2-45a7-45a6-a6cd-533569fc8db7", seq=7)])

    # Act
    with patch("traceloom.query.urllib.request.urlopen", return_value=_response(payload)):
        exit_code = cli.main(["query", "--format", "json"])

    # Assert
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == payload


def test_query_stats_prints_counts(capsys):
    # Arrange
    payload = {
        "epoch": "abc12345:0",
        "max_seq": 1400,
        "total": 1400,
        "by_event_type": {"test": 1400},
        "by_test_status": {"failed": 3, "passed": 1397},
        "by_status_class": {},
    }

    # Act
    with patch(
        "traceloom.query.urllib.request.urlopen", return_value=_response(payload)
    ) as urlopen:
        exit_code = cli.main(["query", "--stats", "--session", "run-1"])

    # Assert
    assert exit_code == 0
    assert urlopen.call_args.args[0] == (
        "http://localhost:5110/api/events/stats?session=run-1"
    )
    assert capsys.readouterr().out == (
        "total  1400\n"
        "\nby type\n"
        "  test  1400\n"
        "\nby test status\n"
        "  failed  3\n"
        "  passed  1397\n"
    )


def test_query_stats_rejects_an_event_id(capsys):
    # Act
    exit_code = cli.main(["query", "5ae54ca2", "--stats"])

    # Assert
    assert exit_code == 2
    assert "--stats does not take an event ID" in capsys.readouterr().err


def test_query_event_id_defaults_to_formatted_json(capsys):
    # Arrange
    event_id = "5ae54ca2-45a7-45a6-a6cd-533569fc8db7"
    payload = {**_event(event_id), "data": {"event_type": "http", "body": "hello"}}

    # Act
    with patch(
        "traceloom.query.urllib.request.urlopen", return_value=_response(payload)
    ) as urlopen:
        exit_code = cli.main(["query", event_id])

    # Assert
    assert exit_code == 0
    assert urlopen.call_args.args[0] == f"http://localhost:5110/api/events/{event_id}"
    assert json.loads(capsys.readouterr().out) == payload


def test_query_accepts_displayed_event_id(capsys):
    # Arrange
    short_id = "5ae54ca2"
    full_id = "5ae54ca2-45a7-45a6-a6cd-533569fc8db7"
    payload = {**_event(full_id), "data": {"event_type": "http"}}

    # Act
    with patch(
        "traceloom.query.urllib.request.urlopen", return_value=_response(payload)
    ) as urlopen:
        exit_code = cli.main(["query", short_id])

    # Assert
    assert exit_code == 0
    assert urlopen.call_args.args[0] == (f"http://localhost:5110/api/events/{short_id}")
    assert json.loads(capsys.readouterr().out) == payload


@pytest.mark.parametrize(
    ("dashboard_url", "expected_server"),
    [
        (
            "http://localhost:5111/#5ae54ca2-45a7-45a6-a6cd-533569fc8db7",
            "http://localhost:5110",
        ),
        (
            "https://traceloom.example/#5ae54ca2-45a7-45a6-a6cd-533569fc8db7",
            "https://traceloom.example",
        ),
        (
            "https://traceloom.example/tools/#5ae54ca2-45a7-45a6-a6cd-533569fc8db7",
            "https://traceloom.example/tools",
        ),
    ],
)
def test_query_dashboard_url_infers_server(dashboard_url, expected_server):
    # Arrange
    event_id = "5ae54ca2-45a7-45a6-a6cd-533569fc8db7"

    # Act
    with (
        patch.dict(os.environ, {}, clear=True),
        patch(
            "traceloom.query.urllib.request.urlopen",
            return_value=_response(
                {**_event(event_id), "data": {"event_type": "http"}}
            ),
        ) as urlopen,
    ):
        exit_code = cli.main(["query", dashboard_url])

    # Assert
    assert exit_code == 0
    assert urlopen.call_args.args[0] == f"{expected_server}/api/events/{event_id}"


def test_query_explicit_server_overrides_dashboard_url():
    # Arrange
    event_id = "5ae54ca2-45a7-45a6-a6cd-533569fc8db7"
    dashboard_url = f"https://dashboard.example/#{event_id}"

    # Act
    with patch(
        "traceloom.query.urllib.request.urlopen",
        return_value=_response({**_event(event_id), "data": {"event_type": "http"}}),
    ) as urlopen:
        exit_code = cli.main(
            ["query", dashboard_url, "--server", "http://api.example:5110"]
        )

    # Assert
    assert exit_code == 0
    assert urlopen.call_args.args[0] == (
        f"http://api.example:5110/api/events/{event_id}"
    )


def test_query_jsonl_writes_one_complete_event_per_line(capsys):
    # Arrange
    events = [_event("first"), _event("second", event_type="log")]

    # Act
    print_events(events, output_format="jsonl")

    # Assert
    lines = capsys.readouterr().out.splitlines()
    assert [json.loads(line) for line in lines] == events


def test_query_text_prints_runtime_children_oldest_first(capsys):
    # Arrange
    parent = _event(
        "parent-id",
        seq=1,
        event_type="test",
        summary="test_checkout",
        trace_id="trace",
        span_id="parent",
    )
    annotation = _event(
        "log-id",
        seq=2,
        event_type="log",
        summary="provider unavailable",
        trace_id="trace",
        span_id="parent",
        role="annotation",
    )
    child = _event(
        "child-id",
        seq=3,
        summary="POST /charge -> ConnectError",
        trace_id="trace",
        span_id="child",
        parent_span_id="parent",
    )

    # Act
    print_events([child, annotation, parent], output_format="text")

    # Assert
    assert capsys.readouterr().out == (
        "12:42:31      1  test          test_checkout  parent-i\n"
        "12:42:31      2  ├─ log        provider unavailable  log-id\n"
        "12:42:31      3  └─ http       POST /charge -> ConnectError  child-id\n"
    )


def test_query_text_labels_every_row_when_runs_are_mixed(capsys):
    # Arrange
    checkout = _event(
        "aaaaaaaa-1",
        seq=10,
        event_type="test",
        summary="test_checkout",
        app="shop",
        session="checkout",
    )
    nightly = _event(
        "bbbbbbbb-2",
        seq=11,
        event_type="test",
        summary="test_cart",
        app="shop",
        session="nightly",
    )
    untagged = _event("cccccccc-3", seq=12, event_type="log", summary="startup")

    # Act
    print_events([untagged, nightly, checkout], output_format="text")

    # Assert
    assert capsys.readouterr().out == (
        "12:42:31     10  shop/checkout  test          test_checkout  aaaaaaaa\n"
        "12:42:31     11  shop/nightly   test          test_cart  bbbbbbbb\n"
        "12:42:31     12  -/-            log           startup  cccccccc\n"
    )


def test_query_text_omits_run_columns_for_a_single_run(capsys):
    # Arrange
    events = [
        _event(
            "aaaaaaaa-1",
            seq=10,
            event_type="test",
            summary="test_checkout",
            app="shop",
            session="checkout",
        ),
        _event(
            "bbbbbbbb-2",
            seq=11,
            event_type="log",
            summary="charging",
            app="shop",
            session="checkout",
        ),
    ]

    # Act
    print_events(events, output_format="text")

    # Assert
    assert capsys.readouterr().out == (
        "12:42:31     11  log           charging  bbbbbbbb\n"
        "12:42:31     10  test          test_checkout  aaaaaaaa\n"
    )


def test_meta_prints_every_captured_filter_value(capsys):
    # Arrange
    meta = {
        "server_version": "0.12.0",
        "hosts": ["api.stripe.com"],
        "methods": ["POST"],
        "event_types": ["http", "test"],
        "apps": ["shop"],
        "sessions": [],
    }

    # Act
    with patch("traceloom.query.urllib.request.urlopen", return_value=_response(meta)):
        exit_code = cli.main(["meta", "--server", "http://localhost:5110"])

    # Assert
    assert exit_code == 0
    assert capsys.readouterr().out == (
        "server:       0.12.0\n"
        "apps:         shop\n"
        "sessions:     -\n"
        "event types:  http, test\n"
        "hosts:        api.stripe.com\n"
        "methods:      POST\n"
    )


def test_meta_requests_the_meta_endpoint(capsys):
    # Arrange
    meta = {"server_version": "0.12.0", "apps": []}

    # Act
    with patch(
        "traceloom.query.urllib.request.urlopen", return_value=_response(meta)
    ) as urlopen:
        exit_code = cli.main(
            ["meta", "--server", "http://traceloom.internal:5110", "--format", "json"]
        )

    # Assert
    assert exit_code == 0
    assert urlopen.call_args.args[0] == "http://traceloom.internal:5110/api/meta"
    assert json.loads(capsys.readouterr().out) == meta


def test_meta_reports_an_unreachable_server(capsys):
    # Act
    with patch(
        "traceloom.query.urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        exit_code = cli.main(["meta", "--server", "http://localhost:5110"])

    # Assert
    assert exit_code == 1
    assert "traceloom meta: failed to reach http://localhost:5110" in (
        capsys.readouterr().err
    )


def test_query_reports_invalid_dashboard_url(capsys):
    # Act
    exit_code = cli.main(["query", "http://localhost:5111/"])

    # Assert
    assert exit_code == 1
    assert "dashboard URL does not contain an event ID" in capsys.readouterr().err


def test_query_reports_missing_event(capsys):
    # Arrange
    event_id = "5ae54ca2-45a7-45a6-a6cd-533569fc8db7"

    # Act
    with patch(
        "traceloom.query.urllib.request.urlopen",
        side_effect=urllib.error.HTTPError("url", 404, "Not Found", {}, None),
    ):
        exit_code = cli.main(["query", event_id])

    # Assert
    assert exit_code == 1
    assert capsys.readouterr().err == "traceloom query: event not found\n"


@pytest.mark.parametrize("limit", ["0", "10001", "many"])
def test_query_rejects_invalid_limit(limit):
    # Act / Assert
    with pytest.raises(SystemExit, match="2"):
        cli.main(["query", "--limit", limit])
