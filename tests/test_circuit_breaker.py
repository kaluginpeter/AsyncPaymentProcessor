import time

import pytest

from app.webhooks.circuit_breaker import CircuitBreaker, CircuitOpenError


def test_circuit_stays_closed_below_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout_seconds=60)

    breaker.record_failure("host")
    breaker.record_failure("host")
    breaker.before_call("host")  # should not raise - only 2 failures so far


def test_circuit_opens_at_threshold_and_rejects_calls() -> None:
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout_seconds=60)

    for _ in range(3):
        breaker.record_failure("host")

    with pytest.raises(CircuitOpenError):
        breaker.before_call("host")


def test_circuit_is_per_host() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=60)

    breaker.record_failure("host-a")

    with pytest.raises(CircuitOpenError):
        breaker.before_call("host-a")
    breaker.before_call("host-b")  # unaffected


def test_success_resets_failure_count() -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=60)

    breaker.record_failure("host")
    breaker.record_success("host")
    breaker.record_failure("host")
    breaker.before_call("host")  # only 1 failure since the reset - still closed


def test_circuit_half_opens_after_reset_timeout() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=0.05)

    breaker.record_failure("host")
    with pytest.raises(CircuitOpenError):
        breaker.before_call("host")

    time.sleep(0.06)
    breaker.before_call("host")  # half-open: trial call is allowed through
