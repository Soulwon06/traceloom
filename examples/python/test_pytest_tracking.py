"""Pytest demo for TraceLoom test execution tracking.

Run:
    traceloom run --capture-logs --log-level WARNING -- \
        pytest examples/python/test_pytest_tracking.py -v

The small-order parameter fails intentionally. The provider test catches an
expected connection failure so its test operation still passes while the runtime
tree contains a failed outgoing child operation and a warning annotation.
"""

import logging

import pytest
import requests

logger = logging.getLogger("pytest_hierarchy_demo")


@pytest.fixture
def discount_percent() -> int:
    return 10


def discounted_total(subtotal: int, discount_percent: int) -> int:
    # Intentional bug: this subtracts 10 currency units, not 10 percent.
    return subtotal - discount_percent


@pytest.mark.parametrize(
    ("subtotal", "expected"),
    [(100, 90), (50, 45)],
    ids=["large-order", "small-order"],
)
def test_total_after_discount(
    subtotal: int,
    expected: int,
    discount_percent: int,
) -> None:
    assert discounted_total(subtotal, discount_percent) == expected


def test_empty_cart_total() -> None:
    assert sum([]) == 0


def test_provider_failure_is_handled() -> None:
    logger.warning("payment provider unavailable", extra={"order_id": 42})

    with pytest.raises(requests.ConnectionError):
        requests.post(
            "http://127.0.0.1:1/charge",
            json={"order_id": 42},
            timeout=0.2,
        )


@pytest.mark.xfail(reason="coupon stacking is not implemented")
def test_stacked_coupons() -> None:
    assert discounted_total(100, 20) == 70


@pytest.mark.skip(reason="requires the optional tax service")
def test_total_with_remote_tax() -> None:
    assert False
