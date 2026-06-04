from repositories.statistics_repository import StatisticsRepository


class LevelingService:
    def __init__(self, repository: StatisticsRepository | None = None):
        self._repo = repository or StatisticsRepository()

    async def execute(self, query: str) -> list:
        return await self._repo.execute(query)
