from discord.ext import commands

from core.config.manager import ConfigManager
from repositories.statistics_repository import StatisticsRepository
from services.leveling_service import LevelingService


class BotApp:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.statistics_repo = StatisticsRepository()
        self.leveling = LevelingService(self.statistics_repo)

    @classmethod
    def from_bot(cls, bot: commands.Bot) -> "BotApp":
        return cls(bot)
