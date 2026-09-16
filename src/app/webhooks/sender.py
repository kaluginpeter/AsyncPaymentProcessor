import logging
from urllib.parse import urlparse

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import Settings
from app.webhooks.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = logging.getLogger(__name__)


class WebhookDeliveryError(Exception):
    """Raised when a webhook could not be delivered after all retries."""


class WebhookSender:
    """Delivers payment-result notifications with retry + a per-host circuit breaker."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=settings.webhook_timeout_seconds)
        self._owns_client = client is None
        self._breaker = CircuitBreaker(
            failure_threshold=settings.webhook_circuit_breaker_failure_threshold,
            reset_timeout_seconds=settings.webhook_circuit_breaker_reset_seconds,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def send(self, url: str, payload: dict) -> None:
        host = urlparse(url).netloc

        try:
            self._breaker.before_call(host)
        except CircuitOpenError:
            logger.warning("webhook circuit open, skipping delivery host=%s", host)
            raise WebhookDeliveryError(f"circuit open for host={host}") from None

        try:
            await self._send_with_retry(url, payload)
        except Exception as exc:
            self._breaker.record_failure(host)
            raise WebhookDeliveryError(str(exc)) from exc
        else:
            self._breaker.record_success(host)

    async def _send_with_retry(self, url: str, payload: dict) -> None:
        @retry(
            stop=stop_after_attempt(self._settings.webhook_max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((httpx.HTTPError,)),
            reraise=True,
        )
        async def _attempt() -> None:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()

        await _attempt()
