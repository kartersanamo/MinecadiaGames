from typing import List, Optional, Tuple

import discord

from core.config.manager import ConfigManager
from repositories.game_repository import GameRepository


class GameQueryService:
    def __init__(self, repository: GameRepository | None = None):
        self._repo = repository or GameRepository()

    async def get_last_game_id(self, game_name: str) -> Optional[int]:
        return await self._repo.get_last_game_id(game_name)

    async def has_played_game(self, game_name: str, user_id: int, game_id: int) -> bool:
        return await self._repo.has_played_game(game_name, user_id, game_id)

    async def get_last_dm_game_info(self):
        return await self._repo.get_last_dm_game_info()

    async def get_recent_games(self) -> tuple[List[str], List[str]]:
        return await self._repo.get_recent_games()

    @staticmethod
    async def can_dm_user(user: discord.User) -> bool:
        try:
            await user.send()
            return True
        except discord.Forbidden:
            return False
        except discord.HTTPException:
            return True

    async def check_dm_game_requirements(
        self,
        interaction: discord.Interaction,
        game_name: str,
        config: ConfigManager,
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        verified_role_id = config.get("config", "VERIFIED_ROLE")
        if verified_role_id and interaction.guild:
            verified_role = interaction.guild.get_role(verified_role_id)
            if verified_role and verified_role not in interaction.user.roles:
                return (
                    False,
                    None,
                    f"You need the {verified_role.mention} role to play games!",
                )

        last_game_info = await self.get_last_dm_game_info()
        if not last_game_info:
            return False, None, "No active game found"

        last_game_id = last_game_info["game_id"]
        last_game_name = last_game_info["game_name"]

        if last_game_name.lower() != game_name.lower():
            return (
                False,
                None,
                f"This is not the most recent game. Only {last_game_name} is available.",
            )

        if await self.has_played_game(game_name, interaction.user.id, last_game_id):
            return (
                False,
                None,
                f"You have already started {game_name} game #{last_game_id}",
            )

        if not await self.can_dm_user(interaction.user):
            return (
                False,
                None,
                f"I cannot send you a DM! Please enable DMs to play {game_name}.",
            )

        return True, last_game_id, None


_default = GameQueryService()
get_last_game_id = _default.get_last_game_id
has_played_game = _default.has_played_game
get_last_dm_game_info = _default.get_last_dm_game_info
get_recent_games = _default.get_recent_games
can_dm_user = GameQueryService.can_dm_user
check_dm_game_requirements = _default.check_dm_game_requirements
