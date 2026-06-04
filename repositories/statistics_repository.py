from core.database.pool import DatabasePool


class StatisticsRepository:
    def __init__(self, db: DatabasePool | None = None):
        self._db = db or DatabasePool.get_instance()

    async def execute(self, query: str) -> list:
        return await self._db.execute(query)
