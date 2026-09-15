"""Service-level tests for reading and deleting events."""

from datetime import datetime, timedelta, timezone

import pytest
from traceloom_server.models import CapturedEvent
from traceloom_server.services.capture import (
    create_http_event,
    create_log_event,
    create_test_event,
)
from traceloom_server.services.events import (
    clear_events,
    delete_expired_events,
    get_event,
    get_meta,
    get_stats,
    hydrate_event_data,
    list_event_ids,
    list_events,
)
from traceloom_server.types import (
    EventHierarchy,
    HttpEventData,
    HttpMeta,
    HttpOperationError,
    HttpRequestData,
    HttpResponseData,
    LogData,
    RuntimeCorrelation,
    TestData,
)

TRACE_ID = "1" * 32


def _http(
    *,
    method: str = "GET",
    url: str = "https://api.example.com/test",
    status_code: int = 200,
    body: str | None = None,
    timestamp: datetime | None = None,
    hierarchy: EventHierarchy | None = None,
):
    return create_http_event(
        event_id=None,
        timestamp=timestamp,
        duration_ms=10,
        request=HttpRequestData(method=method, url=url, headers={}),
        response=HttpResponseData(
            status_code=status_code, headers={}, body=body, body_size=len(body or "")
        ),
        meta=HttpMeta(library="requests"),
        hierarchy=hierarchy,
    )


def _log(
    *,
    level: str = "INFO",
    message: str = "hello",
    timestamp: datetime | None = None,
    hierarchy: EventHierarchy | None = None,
):
    return create_log_event(
        event_id=None,
        timestamp=timestamp,
        data=LogData(level=level, logger_name="app", message=message),
        hierarchy=hierarchy,
    )


def _test(
    *,
    status: str = "passed",
    test_id: str = "tests/test_a.py::test_one",
):
    return create_test_event(
        event_id=None,
        data=TestData(
            run_id="run-1",
            test_id=test_id,
            name=test_id.rsplit("::", 1)[-1],
            path=test_id.split("::", 1)[0],
            status=status,  # type: ignore[arg-type]
            duration_ms=1.0,
        ),
    )


@pytest.mark.asyncio
async def test_list_events_empty(services_db):
    assert (await list_events()).events == []


@pytest.mark.asyncio
async def test_list_events_returns_summaries_newest_first(services_db):
    await _http(url="https://a.test/one")
    await _http(url="https://a.test/two")
    rows = (await list_events()).events
    assert len(rows) == 2
    assert {r.event_type for r in rows} == {"http"}


@pytest.mark.asyncio
async def test_list_events_filter_by_event_type(services_db):
    await _http()
    await _log(level="WARNING", message="boom")
    rows = (await list_events(event_type="log")).events
    assert len(rows) == 1
    assert rows[0].event_type == "log"


@pytest.mark.asyncio
async def test_list_events_includes_runtime_ancestors_of_filtered_operations(
    services_db,
):
    # Arrange
    root = await _http(
        url="https://internal.test/root",
        hierarchy=EventHierarchy(
            runtime=RuntimeCorrelation(
                trace_id=TRACE_ID,
                span_id="a" * 16,
                role="operation",
            )
        ),
    )
    middle = await _http(
        url="https://internal.test/middle",
        hierarchy=EventHierarchy(
            runtime=RuntimeCorrelation(
                trace_id=TRACE_ID,
                span_id="b" * 16,
                parent_span_id="a" * 16,
                role="operation",
            )
        ),
    )
    leaf = await _http(
        url="https://api.stripe.com/v1/charges",
        hierarchy=EventHierarchy(
            runtime=RuntimeCorrelation(
                trace_id=TRACE_ID,
                span_id="c" * 16,
                parent_span_id="b" * 16,
                role="operation",
            )
        ),
    )
    await _http(url="https://unrelated.test/request")

    # Act
    rows = (await list_events(host="api.stripe.com", include_ancestors=True)).events

    # Assert
    assert {row.id for row in rows} == {str(root.id), str(middle.id), str(leaf.id)}


@pytest.mark.asyncio
async def test_list_events_applies_limit_before_adding_runtime_ancestors(services_db):
    # Arrange
    older_root = await _http(
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        hierarchy=EventHierarchy(
            runtime=RuntimeCorrelation(
                trace_id="1" * 32,
                span_id="a" * 16,
                role="operation",
            )
        ),
    )
    await _http(
        url="https://api.stripe.com/older",
        timestamp=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        hierarchy=EventHierarchy(
            runtime=RuntimeCorrelation(
                trace_id="1" * 32,
                span_id="b" * 16,
                parent_span_id="a" * 16,
                role="operation",
            )
        ),
    )
    newer_root = await _http(
        timestamp=datetime(2026, 1, 1, 0, 0, 2, tzinfo=timezone.utc),
        hierarchy=EventHierarchy(
            runtime=RuntimeCorrelation(
                trace_id="2" * 32,
                span_id="c" * 16,
                role="operation",
            )
        ),
    )
    newer_leaf = await _http(
        url="https://api.stripe.com/newer",
        timestamp=datetime(2026, 1, 1, 0, 0, 3, tzinfo=timezone.utc),
        hierarchy=EventHierarchy(
            runtime=RuntimeCorrelation(
                trace_id="2" * 32,
                span_id="d" * 16,
                parent_span_id="c" * 16,
                role="operation",
            )
        ),
    )

    # Act
    rows = (
        await list_events(
            host="api.stripe.com",
            include_ancestors=True,
            limit=1,
        )
    ).events

    # Assert
    assert {row.id for row in rows} == {str(newer_root.id), str(newer_leaf.id)}
    assert str(older_root.id) not in {row.id for row in rows}


@pytest.mark.asyncio
async def test_list_events_includes_owning_operation_and_ancestors_for_annotation(
    services_db,
):
    # Arrange
    root = await _http(
        hierarchy=EventHierarchy(
            runtime=RuntimeCorrelation(
                trace_id=TRACE_ID,
                span_id="a" * 16,
                role="operation",
            )
        )
    )
    owner = await _http(
        hierarchy=EventHierarchy(
            runtime=RuntimeCorrelation(
                trace_id=TRACE_ID,
                span_id="b" * 16,
                parent_span_id="a" * 16,
                role="operation",
            )
        )
    )
    annotation = await _log(
        hierarchy=EventHierarchy(
            runtime=RuntimeCorrelation(
                trace_id=TRACE_ID,
                span_id="b" * 16,
                role="annotation",
            )
        )
    )

    # Act
    rows = (await list_events(event_type="log", include_ancestors=True)).events

    # Assert
    assert {row.id for row in rows} == {
        str(root.id),
        str(owner.id),
        str(annotation.id),
    }


@pytest.mark.asyncio
async def test_list_events_filter_by_method(services_db):
    await _http(method="GET")
    await _http(method="POST")
    rows = (await list_events(method="POST")).events
    assert len(rows) == 1
    assert "POST" in rows[0].summary


@pytest.mark.asyncio
async def test_list_events_filter_by_host(services_db):
    await _http(url="https://api.stripe.com/v1/charges")
    await _http(url="https://api.openai.com/v1/models")
    rows = (await list_events(host="api.stripe.com")).events
    assert len(rows) == 1
    assert "/v1/charges" in rows[0].summary


@pytest.mark.asyncio
async def test_list_events_filter_by_status(services_db):
    await _http(status_code=200)
    await _http(status_code=404)
    rows = (await list_events(status=404)).events
    assert len(rows) == 1
    assert "404" in rows[0].summary


@pytest.mark.asyncio
async def test_list_events_search_summary(services_db):
    await _http()
    await _log(level="WARNING", message="Token expired")
    rows = (await list_events(search="Token expired")).events
    assert len(rows) == 1
    assert rows[0].event_type == "log"


@pytest.mark.asyncio
async def test_list_events_search_data(services_db):
    await _http(body='{"error": "unique-sentinel-value"}')
    await _http()
    rows = (await list_events(search="unique-sentinel-value")).events
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_list_events_limit(services_db):
    for _ in range(5):
        await _http()
    rows = (await list_events(limit=2)).events
    assert len(rows) == 2


# --- seq cursor ---


@pytest.mark.asyncio
async def test_list_events_assigns_increasing_seq_in_insertion_order(services_db):
    # Arrange
    first = await _http(url="https://a.test/one")
    second = await _http(url="https://a.test/two")

    # Act
    page = await list_events()

    # Assert
    by_id = {row.id: row.seq for row in page.events}
    assert by_id[str(first.id)] < by_id[str(second.id)]
    assert page.max_seq == by_id[str(second.id)]


@pytest.mark.asyncio
async def test_after_seq_returns_every_event_sharing_one_timestamp(services_db):
    """The client stamps timestamps at second resolution, so a fast run puts
    dozens of events on the identical timestamp. A `(timestamp, id)` cursor
    would drop all but one; `seq` must return them all."""
    # Arrange
    same_second = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)
    for index in range(50):
        await _http(url=f"https://a.test/{index}", timestamp=same_second)

    # Act
    delta = await list_events(after_seq=0, limit=10_000)

    # Assert
    assert len(delta.events) == 50
    assert len({row.id for row in delta.events}) == 50


@pytest.mark.asyncio
async def test_after_seq_truncated_delta_returns_the_oldest_page(services_db):
    # Arrange
    for index in range(10):
        await _http(url=f"https://a.test/{index}")

    # Act
    first_page = await list_events(after_seq=0, limit=4)

    # Assert
    assert [row.seq for row in first_page.events] == [4, 3, 2, 1]
    assert first_page.max_seq == 10


@pytest.mark.asyncio
async def test_successive_after_seq_pages_lose_nothing(services_db):
    # Arrange
    for index in range(10):
        await _http(url=f"https://a.test/{index}")

    # Act
    collected: list[int] = []
    cursor = 0
    while True:
        page = await list_events(after_seq=cursor, limit=3)
        if not page.events:
            break
        collected.extend(row.seq for row in page.events)
        cursor = max(row.seq for row in page.events)

    # Assert
    assert sorted(collected) == list(range(1, 11))


@pytest.mark.asyncio
async def test_after_seq_respects_other_filters(services_db):
    # Arrange
    await _http()
    await _log(message="first")
    baseline = await list_events()
    await _http()
    await _log(message="second")

    # Act
    delta = await list_events(event_type="log", after_seq=baseline.max_seq)

    # Assert
    assert [row.summary for row in delta.events] == ["INFO app: second"]
    assert delta.max_seq == 4


@pytest.mark.asyncio
async def test_before_seq_backfills_older_events(services_db):
    # Arrange
    for index in range(10):
        await _http(url=f"https://a.test/{index}")

    # Act
    page = await list_events(before_seq=5, limit=3)

    # Assert
    assert [row.seq for row in page.events] == [4, 3, 2]


@pytest.mark.asyncio
async def test_list_events_rejects_ancestors_with_a_cursor(services_db):
    with pytest.raises(ValueError, match="include_ancestors cannot be combined"):
        await list_events(after_seq=1, include_ancestors=True)


@pytest.mark.asyncio
async def test_list_events_rejects_both_cursors(services_db):
    with pytest.raises(ValueError, match="not both"):
        await list_events(after_seq=1, before_seq=5)


@pytest.mark.asyncio
async def test_max_seq_reflects_the_table_not_the_page(services_db):
    # Arrange
    for index in range(5):
        await _http(url=f"https://a.test/{index}")

    # Act
    page = await list_events(limit=2)

    # Assert
    assert len(page.events) == 2
    assert page.max_seq == 5


@pytest.mark.asyncio
async def test_list_events_orders_same_timestamp_events_deterministically(services_db):
    # Arrange
    same_second = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)
    for index in range(20):
        await _http(url=f"https://a.test/{index}", timestamp=same_second)

    # Act
    first = await list_events(limit=10_000)
    second = await list_events(limit=10_000)

    # Assert
    assert [row.seq for row in first.events] == list(range(20, 0, -1))
    assert [row.id for row in first.events] == [row.id for row in second.events]


@pytest.mark.asyncio
async def test_summary_carries_host_method_and_status_code(services_db):
    # Arrange
    await _http(method="POST", url="https://api.stripe.com/v1/charges", status_code=402)

    # Act
    row = (await list_events()).events[0]

    # Assert
    assert row.host == "api.stripe.com"
    assert row.method == "POST"
    assert row.status_code == 402


# --- epoch ---


@pytest.mark.asyncio
async def test_clear_events_bumps_the_epoch(services_db):
    # Arrange
    await _http()
    before = (await list_events()).epoch

    # Act
    await clear_events()

    # Assert
    assert (await list_events()).epoch != before


@pytest.mark.asyncio
async def test_delete_expired_events_bumps_the_epoch_only_when_it_deletes(services_db):
    # Arrange
    now = datetime(2026, 7, 27, tzinfo=timezone.utc)
    await _http(timestamp=now - timedelta(days=30))
    await _http(timestamp=now)
    before = (await list_events()).epoch

    # Act
    await delete_expired_events(retention_days=7, now=now)
    after_prune = (await list_events()).epoch
    await delete_expired_events(retention_days=7, now=now)

    # Assert
    assert after_prune != before
    assert (await list_events()).epoch == after_prune


@pytest.mark.asyncio
async def test_epoch_is_stable_across_appends(services_db):
    # Arrange
    await _http()
    before = (await list_events()).epoch

    # Act
    await _http()

    # Assert
    assert (await list_events()).epoch == before


# --- ids and stats ---


@pytest.mark.asyncio
async def test_list_event_ids_matches_bodies(services_db):
    # Arrange
    matching = await _http(body='{"error": "unique-sentinel-value"}')
    await _http()

    # Act
    result = await list_event_ids(search="unique-sentinel-value")

    # Assert
    assert result.ids == [str(matching.id)]


@pytest.mark.asyncio
async def test_get_stats_counts_types_test_statuses_and_status_classes(services_db):
    # Arrange
    await _http(status_code=200)
    await _http(status_code=404)
    await _http(status_code=503)
    await _log()
    await _test(status="failed", test_id="tests/test_a.py::test_one")
    await _test(status="passed", test_id="tests/test_a.py::test_two")
    await _test(status="passed", test_id="tests/test_a.py::test_three")

    # Act
    stats = await get_stats()

    # Assert
    assert stats.total == 7
    assert stats.by_event_type == {"http": 3, "log": 1, "test": 3}
    assert stats.by_test_status == {"failed": 1, "passed": 2}
    assert stats.by_status_class == {"2xx": 1, "4xx": 1, "5xx": 1}
    assert stats.max_seq == 7


@pytest.mark.asyncio
async def test_get_stats_buckets_failed_http_operations_as_error(services_db):
    # Arrange
    await create_http_event(
        event_id=None,
        timestamp=None,
        duration_ms=1,
        request=HttpRequestData(method="GET", url="https://a.test/x", headers={}),
        response=None,
        error=HttpOperationError(type="ConnectTimeout", message="timed out"),
        meta=HttpMeta(library="requests"),
    )

    # Act
    stats = await get_stats()

    # Assert
    assert stats.by_status_class == {"error": 1}


@pytest.mark.asyncio
async def test_get_stats_applies_filters(services_db):
    # Arrange
    await _http(status_code=200)
    await _log()

    # Act
    stats = await get_stats(event_type="log")

    # Assert
    assert stats.total == 1
    assert stats.by_event_type == {"log": 1}


@pytest.mark.asyncio
async def test_get_event_returns_none_for_unknown(services_db):
    assert await get_event("550e8400-e29b-41d4-a716-446655440000") is None


@pytest.mark.asyncio
async def test_get_event_returns_none_for_invalid_uuid(services_db):
    assert await get_event("not-a-uuid") is None


@pytest.mark.asyncio
async def test_get_event_returns_typed_detail(services_db):
    created = await _http()
    found = await get_event(str(created.id))
    assert found is not None
    assert found.event_type == "http"
    assert isinstance(found.data, HttpEventData)


@pytest.mark.asyncio
async def test_get_event_accepts_eight_character_id_prefix(services_db):
    # Arrange
    created = await _http()

    # Act
    found = await get_event(str(created.id)[:8])

    # Assert
    assert found is not None
    assert found.id == str(created.id)


@pytest.mark.asyncio
async def test_get_meta_empty(services_db):
    meta = await get_meta()
    assert meta.hosts == []
    assert meta.methods == []
    assert meta.event_types == []


@pytest.mark.asyncio
async def test_get_meta_returns_hosts_methods_event_types(services_db):
    await _http(url="https://api.stripe.com/v1/charges")
    await _http(method="POST", url="https://api.openai.com/v1/models")
    await _log(level="WARNING")

    meta = await get_meta()
    assert meta.hosts == ["api.openai.com", "api.stripe.com"]
    assert meta.methods == ["GET", "POST"]
    assert sorted(meta.event_types) == ["http", "log"]


@pytest.mark.asyncio
async def test_clear_events(services_db):
    await _http()
    await _log()
    assert len((await list_events()).events) == 2
    await clear_events()
    assert (await list_events()).events == []


@pytest.mark.asyncio
async def test_delete_expired_events_removes_only_expired_events(services_db):
    # Arrange
    now = datetime(2026, 7, 27, tzinfo=timezone.utc)
    cutoff = now - timedelta(days=7)
    expired_http = await _http(timestamp=cutoff - timedelta(microseconds=1))
    expired_log = await _log(timestamp=cutoff - timedelta(days=3))
    boundary_event = await _http(timestamp=cutoff)
    current_event = await _log(timestamp=cutoff + timedelta(days=1))

    # Act
    deleted_count = await delete_expired_events(retention_days=7, now=now)

    # Assert
    remaining_ids = {
        str(event_id)
        for event_id in await CapturedEvent.all().values_list("id", flat=True)
    }
    assert deleted_count == 2
    assert remaining_ids == {str(boundary_event.id), str(current_event.id)}
    assert str(expired_http.id) not in remaining_ids
    assert str(expired_log.id) not in remaining_ids


@pytest.mark.asyncio
async def test_delete_expired_events_does_nothing_when_retention_is_disabled(
    services_db,
):
    # Arrange
    event = await _http(
        timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )

    # Act
    deleted_count = await delete_expired_events(retention_days=0)

    # Assert
    assert deleted_count == 0
    assert await CapturedEvent.filter(id=event.id).exists()


@pytest.mark.asyncio
async def test_delete_expired_events_rejects_negative_retention(services_db):
    # Act / Assert
    with pytest.raises(ValueError, match="retention_days must be non-negative"):
        await delete_expired_events(retention_days=-1)


@pytest.mark.asyncio
async def test_hydrate_event_data_validates_typed_payload(services_db):
    """New writes round-trip through the typed union without modification."""
    created = await _http(method="POST", url="https://x.test/y", status_code=201)
    stored = await CapturedEvent.get(id=created.id)
    typed = hydrate_event_data(stored.event_type, stored.data)
    assert isinstance(typed, HttpEventData)
    assert typed.method == "POST"
    assert typed.status_code == 201


@pytest.mark.asyncio
async def test_hydrate_event_data_backfills_legacy_rows(services_db):
    """Rows written before the typed-output refactor lacked `event_type`
    inside `data`. Hydration should inject it from the column."""
    legacy_data = {
        "duration_ms": 5,
        "method": "GET",
        "url": "https://legacy.test/",
        "host": "legacy.test",
        "request_headers": {},
        "request_body": None,
        "request_body_size": 0,
        "status_code": 200,
        "response_headers": {},
        "response_body": None,
        "response_body_size": 0,
        "library": "requests",
    }
    typed = hydrate_event_data("http", legacy_data)
    assert isinstance(typed, HttpEventData)
    assert typed.event_type == "http"
    assert typed.url == "https://legacy.test/"
