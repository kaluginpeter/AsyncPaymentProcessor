from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxEvent, OutboxStatus


class OutboxRepository:
    """Data-access layer for the transactional outbox table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, event: OutboxEvent) -> None:
        self._session.add(event)

    async def lock_pending_batch(self, limit: int) -> list[OutboxEvent]:
        """
        Select a batch of pending events for exclusive processing by this worker.

        Uses FOR UPDATE SKIP LOCKED so multiple relay instances can run
        concurrently without contending for the same rows (horizontal scaling
        of the relay without duplicate publishes).
        """
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.PENDING)
            .order_by(OutboxEvent.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
