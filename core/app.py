from discord.ext import commands

from core.config.manager import ConfigManager
from repositories.game_repository import GameRepository
from repositories.statistics_repository import StatisticsRepository
from services.achievement_service import AchievementService
from services.asset_path_service import AssetPathService
from services.embed_service import EmbedService
from services.game_query_service import GameQueryService
from services.game_state_service import GameStateService
from services.leveling_service import LevelingService


class BotApp:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.statistics_repo = StatisticsRepository()
        self.leveling = LevelingService(self.statistics_repo)
        self.games_repo = GameRepository()
        self.games = GameQueryService(self.games_repo)
        self.game_state = GameStateService()
        self.achievements = AchievementService()
        self.paths = AssetPathService()
        self.embeds = EmbedService()

    @classmethod
    def from_bot(cls, bot: commands.Bot) -> "BotApp":
        return cls(bot)
