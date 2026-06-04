from abc import ABC, abstractmethod
from typing import Optional
from discord.ext import commands
from core.config.manager import ConfigManager
from core.database.pool import DatabasePool
from core.cache.manager import CacheManager
from core.logging.setup import get_logger


class BaseGame(ABC):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.db = None
        self.cache = CacheManager.get_instance()
        self.logger = get_logger(self.__class__.__name__)
        self._game_id: Optional[int] = None
        self._test_mode: bool = False
    
    async def _get_db(self):
        if self.db is None:
            self.db = await DatabasePool.get_instance()
        return self.db
    
    @abstractmethod
    async def run(self, *args, **kwargs):
        pass
    
    async def _create_game_entry(self, game_name: str, dm_game: bool, test_mode: bool = False, end_time: Optional[int] = None) -> int:
        if test_mode:
            # Return a fake game_id for test mode (negative to avoid conflicts)
            self._game_id = -999999
            self._test_mode = True
            return self._game_id
        
        from datetime import datetime, timezone
        db = await self._get_db()
        refreshed_at = int(datetime.now(timezone.utc).timestamp())
        
        # Try to insert with status and end_time columns, fallback if columns don't exist
        try:
            if end_time:
                query = "INSERT INTO games (game_name, refreshed_at, dm_game, status, end_time) VALUES (%s, %s, %s, %s, %s)"
                game_id = await db.execute_insert(query, (game_name, refreshed_at, dm_game, 'Started', end_time))
            else:
                query = "INSERT INTO games (game_name, refreshed_at, dm_game, status) VALUES (%s, %s, %s, %s)"
                game_id = await db.execute_insert(query, (game_name, refreshed_at, dm_game, 'Started'))
        except Exception:
            # If status/end_time columns don't exist, insert without them
            try:
                query = "INSERT INTO games (game_name, refreshed_at, dm_game, status) VALUES (%s, %s, %s, %s)"
                game_id = await db.execute_insert(query, (game_name, refreshed_at, dm_game, 'Started'))
            except Exception:
                query = "INSERT INTO games (game_name, refreshed_at, dm_game) VALUES (%s, %s, %s)"
                game_id = await db.execute_insert(query, (game_name, refreshed_at, dm_game))
        
        self._game_id = game_id
        return game_id
    
    async def _update_game_status(self, status: str = 'Finished'):
        """Update the game status in the database"""
        if self._test_mode or not self._game_id or self._game_id == -999999:
            return
        
        try:
            db = await self._get_db()
            duration_seconds = None
            game_name = self.__class__.__name__
            try:
                row = await db.fetch_one(
                    "SELECT game_name, refreshed_at FROM games WHERE game_id = %s",
                    (self._game_id,),
                )
                if row:
                    game_name = row.get("game_name") or game_name
                    refreshed = int(row.get("refreshed_at") or 0)
                    if refreshed:
                        from datetime import datetime, timezone
                        duration_seconds = int(
                            datetime.now(timezone.utc).timestamp() - refreshed
                        )
            except Exception:
                pass
            # Try to update status column, ignore if it doesn't exist
            try:
                await db.execute(
                    "UPDATE games SET status = %s WHERE game_id = %s",
                    (status, self._game_id)
                )
            except Exception:
                # Status column doesn't exist, that's okay
                pass
            if status == "Finished":
                try:
                    import sys
                    from pathlib import Path
                    _root = Path(__file__).resolve().parents[3]
                    if str(_root) not in sys.path:
                        sys.path.insert(0, str(_root))
                    from _analytics import logger as analytics
                    analytics.record_game_outcome(
                        game_name,
                        "finished",
                        game_id=self._game_id,
                        duration_seconds=duration_seconds,
                    )
                except Exception:
                    pass
        except Exception as e:
            self.logger.error(f"Error updating game status: {e}")
    
    @property
    def game_id(self) -> Optional[int]:
        return self._game_id
    
    @property
    def test_mode(self) -> bool:
        return self._test_mode

