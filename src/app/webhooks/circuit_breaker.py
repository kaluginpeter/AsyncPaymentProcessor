import time
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit is open."""


class CircuitBreaker:
    """
    Minimal per-host circuit breaker for outbound webhook calls.

    After enough consecutive failures for a given host the breaker
    opens and fails fast for a cool-down
    window, then allows one trial (half-open) request to test recovery.
    """

    def __init__(self, failure_threshold: int, reset_timeout_seconds: float) -> None:
        self._failure_threshold = failure_threshold
        self._reset_timeout_seconds = reset_timeout_seconds
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def _state(self, host: str) -> CircuitState:
        if host not in self._opened_at:
            return CircuitState.CLOSED
        elapsed = time.monotonic() - self._opened_at[host]
        if elapsed >= self._reset_timeout_seconds:
            return CircuitState.HALF_OPEN
        return CircuitState.OPEN

    def before_call(self, host: str) -> None:
        if self._state(host) == CircuitState.OPEN:
            raise CircuitOpenError(f"circuit open for host={host}")

    def record_success(self, host: str) -> None:
        self._failures.pop(host, None)
        self._opened_at.pop(host, None)

    def record_failure(self, host: str) -> None:
        failures = self._failures.get(host, 0) + 1
        self._failures[host] = failures
        if failures >= self._failure_threshold:
            self._opened_at[host] = time.monotonic()
