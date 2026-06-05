from datetime import datetime, timezone
from discord.ext import commands
from core.logging.setup import get_logger
from repositories.game_session_repository import GameSessionRepository
class HangmanListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.hangman_game = None
        self.logger = get_logger("DMGames")
        self._cleanup_done = False
    
    def set_hangman_game(self, hangman_game):
        self.hangman_game = hangman_game
    
    @commands.Cog.listener("on_ready")
    async def on_ready(self):
        """Clean up stale Hangman games on bot startup"""
        if self._cleanup_done:
            return
        
        self._cleanup_done = True
        
        try:
            await self._cleanup_stale_games()
        except Exception as e:
            self.logger.error(f"Error cleaning up stale Hangman games: {e}")
    
    async def _cleanup_stale_games(self):
        """Clean up Hangman games that have been 'Started' for too long (likely stale)"""
        try:
            repo = GameSessionRepository()
            current_unix = int(datetime.now(timezone.utc).timestamp())
            stale_time = current_unix - 86400  # 24 hours ago

            active = await repo.get_active_dm_games()
            rows = [
                g for g in active
                if g.get("game_type") == "hangman" and g.get("started_at", 0) < stale_time
            ]
            
            if rows:
                self.logger.info(f"HangmanListener: Found {len(rows)} stale Hangman games to clean up")
                
                for row in rows:
                    game_id = row["game_id"]
                    user_id = row["user_id"]
                    
                    try:
                        await repo.finish_session(
                            game_id, user_id, "hangman", "lost", ended_at=current_unix
                        )
                        self.logger.info(
                            f"HangmanListener: Cleaned up stale game {game_id} for user {user_id}"
                        )
                    except Exception as e:
                        self.logger.error(f"HangmanListener: Error cleaning up game {game_id}: {e}")
                
                self.logger.info(f"HangmanListener: Cleaned up {len(rows)} stale Hangman games")
            else:
                self.logger.debug("HangmanListener: No stale Hangman games found to clean up")
        except Exception as e:
            self.logger.error(f"HangmanListener: Error in _cleanup_stale_games: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
