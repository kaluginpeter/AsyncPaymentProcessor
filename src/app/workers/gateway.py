import asyncio
import random
from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True)
class GatewayResult:
    succeeded: bool
    failure_reason: str | None = None


class PaymentGatewayEmulator:
    """
    Takes 2-5 seconds and resolves to a business outcome (succeeded/failed)
    with a 90/10 split, per the spec.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def process(self) -> GatewayResult:
        delay = random.uniform(
            self._settings.gateway_min_delay_seconds,
            self._settings.gateway_max_delay_seconds,
        )
        await asyncio.sleep(delay)

        if random.random() < self._settings.gateway_success_rate:
            return GatewayResult(succeeded=True)
        return GatewayResult(succeeded=False, failure_reason="declined_by_gateway")
