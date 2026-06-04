from datetime import datetime, timezone
from discord.ext import commands
from core.database.pool import DatabasePool
from core.logging.setup import get_logger
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
            db = await DatabasePool.get_instance()
            current_unix = int(datetime.now(timezone.utc).timestamp())
            
            # Mark games as 'Lost' if they've been 'Started' for more than 24 hours (86400 seconds)
            stale_time = current_unix - 86400  # 24 hours ago
            
            rows = await db.execute(
                "SELECT game_id, user_id, started_at FROM users_hangman WHERE won = 'Started' AND started_at < %s AND game_id != -999999",
                (stale_time,)
            )
            
            if rows:
                self.logger.info(f"HangmanListener: Found {len(rows)} stale Hangman games to clean up")
                
                for row in rows:
                    game_id = row['game_id']
                    user_id = row['user_id']
                    
                    try:
                        await db.execute(
                            "UPDATE users_hangman SET won = 'Lost', ended_at = %s WHERE game_id = %s AND user_id = %s AND won = 'Started'",
                            (current_unix, game_id, user_id)
                        )
                        self.logger.info(f"HangmanListener: Cleaned up stale game {game_id} for user {user_id}")
                    except Exception as e:
                        self.logger.error(f"HangmanListener: Error cleaning up game {game_id}: {e}")
                
                self.logger.info(f"HangmanListener: Cleaned up {len(rows)} stale Hangman games")
            else:
                self.logger.debug("HangmanListener: No stale Hangman games found to clean up")
        except Exception as e:
            self.logger.error(f"HangmanListener: Error in _cleanup_stale_games: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
