from datetime import datetime, timezone
import discord
from games.base.dm_game import DMGame
from core.logging.setup import get_logger
import pymysql
class TwentyFortyEight(DMGame):
    def __init__(self, bot):
        super().__init__(bot)
        # Support both old and new config structure
        games = self.dm_config.get('GAMES', {})
        if not games:
            games = self.dm_config.get('games', {})
        self.game_config = games.get('2048', {}) or games.get('Twenty Forty Eight', {})
        self.logger = get_logger("DMGames")
    
    async def _run_game(self, user: discord.User, game_name: str, test_mode: bool = False) -> bool:
        try:
            if test_mode:
                last_game_id = -999999  # Fake game_id for test mode
            else:
                # Game name in database is "2048"
                last_game_id = await self.bot.app.games.get_last_game_id('2048')
                if not last_game_id:
                    return False
            
            test_label = " 🧪 TEST GAME 🧪" if test_mode else ""
            
            embed = discord.Embed(
                title=f"2048 #{last_game_id}{test_label}",
                description="Welcome to 2048! Use the direction buttons to move tiles. Combine tiles with the same number to reach 2048!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.add_field(name="Score", value="0", inline=True)
            embed.add_field(name="Moves", value="0", inline=True)
            embed.add_field(name="Highest Tile", value="2", inline=True)
            logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            from games.dm.twenty_forty_eight.twenty_forty_eight_buttons import TwentyFortyEightButtons
            view = TwentyFortyEightButtons(last_game_id, self.bot, self.config, self.game_config, self.dm_config, user.id, test_mode=test_mode)
            # Register view for persistence across bot restarts
            self.bot.add_view(view)
            await user.send(embed=embed, view=view)
            
            # Save initial state
            if not test_mode:
                await view._save_state()
            
            if not test_mode:
                db = await self._get_db()
                current_unix = int(datetime.now(timezone.utc).timestamp())
                # Table name is users_2048 (numbers are allowed in MySQL table names)
                # Check if user already has a record for this game_id to avoid duplicate key errors
                existing = await db.execute(
                    "SELECT game_id FROM users_2048 WHERE game_id = %s AND user_id = %s",
                    (last_game_id, user.id)
                )
                if not existing:
                    try:
                        # Use INSERT IGNORE to handle duplicate key errors gracefully
                        # This allows multiple users to play the same game_id
                        await db.execute(
                            "INSERT IGNORE INTO users_2048 (game_id, user_id, status, score, moves, highest_tile, started_at, ended_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                            (last_game_id, user.id, 'Started', 0, 0, 2, current_unix, 0)
                        )
                    except pymysql.err.IntegrityError as e:
                        # Handle duplicate key error gracefully (race condition when multiple users start at same time)
                        error_code = e.args[0] if e.args else 0
                        if error_code == 1062:  # Duplicate entry
                            # Try to update existing record if it exists (in case game_id is primary key)
                            try:
                                await db.execute(
                                    "UPDATE users_2048 SET status = 'Started', score = 0, moves = 0, highest_tile = 2, started_at = %s, ended_at = 0 WHERE game_id = %s AND user_id = %s",
                                    (current_unix, last_game_id, user.id)
                                )
                            except Exception as update_error:
                                self.logger.warning(f"Could not update users_2048 for game_id {last_game_id}, user {user.id}: {update_error}")
                        else:
                            raise
                    except Exception as e:
                        # Re-raise other exceptions
                        self.logger.error(f"Error inserting into users_2048: {e}")
                        raise
            
            self.logger.info(f"2048 ({user.name}#{user.discriminator}){' [TEST MODE]' if test_mode else ''}")
            return True
        except Exception as e:
            self.logger.error(f"2048 error: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return False
