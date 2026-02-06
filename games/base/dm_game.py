from typing import Optional
import discord
from discord.ext import commands
from .game import BaseGame
from core.logging.setup import get_logger


class DMGame(BaseGame):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.logger = get_logger("DMGames")
        self.dm_config = self.config.get('dm_games')
        self._last_error: Optional[str] = None
    
    async def can_play(self, user: discord.User, game_name: str) -> tuple[bool, Optional[str]]:
        db = await self._get_db()
        
        last_game_info = await db.execute(
            "SELECT game_name, game_id FROM games WHERE dm_game = TRUE ORDER BY game_id DESC LIMIT 1"
        )
        
        if not last_game_info:
            return False, "No active game found"
        
        last_game = last_game_info[0]
        if last_game['game_name'].lower() != game_name.lower():
            return False, f"This is not the most recent game. Only {last_game['game_name']} is available."
        
        safe_game_name = game_name.lower().replace(" ", "")
        has_played = await db.execute(
            f"SELECT user_id FROM users_{safe_game_name} WHERE game_id = %s AND user_id = %s",
            (last_game['game_id'], user.id)
        )
        
        if has_played:
            return False, f"You have already started {game_name} game #{last_game['game_id']}"
        
        try:
            await user.send()
        except discord.Forbidden:
            return False, "I cannot send you a DM! Please enable DMs to play."
        except discord.HTTPException:
            pass
        
        return True, None
    
    async def run(self, user: discord.User, game_name: str, test_mode: bool = False) -> bool:
        self._last_error = None
        if not test_mode:
            can_play, error = await self.can_play(user, game_name)
            if not can_play:
                self._last_error = error
                return False
        
        self._test_mode = test_mode
        return await self._run_game(user, game_name, test_mode=test_mode)
    
    @property
    def last_error(self) -> Optional[str]:
        """Get the last error message from can_play() if run() returned False"""
        return self._last_error
    
    async def _run_game(self, user: discord.User, game_name: str, test_mode: bool = False) -> bool:
        raise NotImplementedError("Subclasses must implement _run_game")

