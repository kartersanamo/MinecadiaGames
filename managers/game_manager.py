import asyncio
import random
import time
from datetime import datetime, timezone
from typing import Optional, Dict
import discord
from discord.ext import commands
from core.config.manager import ConfigManager
from core.database.pool import DatabasePool
from core.logging.setup import get_logger
from games.chat.unscramble import Unscramble
from games.chat.flag_guesser import FlagGuesser
from games.chat.math_quiz import MathQuiz
from games.chat.trivia import Trivia
from games.chat.emoji_quiz import EmojiQuiz
from games.chat.guess_the_number import GuessTheNumber
from games.dm.wordle import Wordle
from games.dm.tictactoe import TicTacToe
from games.dm.connect_four import ConnectFour
from games.dm.memory import Memory
from games.dm.twenty_forty_eight import TwentyFortyEight
from games.dm.minesweeper import Minesweeper
from games.dm.hangman import Hangman


def format_wait_time(seconds: int) -> str:
    """Format wait time in seconds to human-readable format (e.g., '15m 32s')"""
    if seconds <= 0:
        return "0s"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")
    
    return " ".join(parts)


class GameManager:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.db = None
        self.logger = get_logger("Tasks")
        self.chat_config = self.config.get('chat_games')
        self.dm_config = self.config.get('dm_games')
        
        self.chat_game_task: Optional[asyncio.Task] = None
        self.dm_game_task: Optional[asyncio.Task] = None
        
        self.chat_game_running = True
        self.dm_game_running = True

        self._initialized = False
        self.last_dm_refresh_msg: Optional[discord.Message] = None
        self.last_chat_game_msg: Optional[discord.Message] = None
        self.last_chat_game_heartbeat: float = 0.0  # Timestamp of last activity in chat game loop
        
        # Store DM game instances for listeners
        self.dm_games: Dict[str, any] = {
            'Wordle': Wordle(self.bot),
            'TicTacToe': TicTacToe(self.bot),
            'Connect Four': ConnectFour(self.bot),
            'Memory': Memory(self.bot),
            '2048': TwentyFortyEight(self.bot),
            'Minesweeper': Minesweeper(self.bot),
            'Hangman': Hangman(self.bot)
        }
    
    async def _get_db(self):
        if self.db is None:
            self.db = await asyncio.wait_for(DatabasePool.get_instance(), timeout=3.0)
        return self.db
    
    async def initialize(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.chat_game_task = asyncio.create_task(self._chat_game_loop())
        self.dm_game_task = asyncio.create_task(self._dm_game_loop())
        # Start monitoring task to restart chat game loop if it stops
        asyncio.create_task(self._monitor_chat_game_task())
        self.logger.info("Game Manager initialized")
    
    async def _monitor_chat_game_task(self):
        """Monitor chat game task and restart if it stops unexpectedly or gets stuck"""
        await self.bot.wait_until_ready()
        while True:
            await asyncio.sleep(120)  # Check every 2 minutes (more frequent)
            if not self.chat_game_running:
                continue
            
            # Check if task is done
            if self.chat_game_task is None or self.chat_game_task.done():
                self.logger.warning("Chat game task stopped unexpectedly, restarting...")
                try:
                    if self.chat_game_task and self.chat_game_task.done():
                        # Get exception if task failed
                        try:
                            await self.chat_game_task
                        except Exception as e:
                            self.logger.error(f"Chat game task exception: {e}")
                except Exception:
                    pass
                self.chat_game_task = asyncio.create_task(self._chat_game_loop())
                self.last_chat_game_heartbeat = time.time()
                self.logger.info("Chat game task restarted")
            # Check if task is stuck (no heartbeat in 10 minutes - reduced from 30)
            elif self.last_chat_game_heartbeat > 0 and (time.time() - self.last_chat_game_heartbeat) > 600:
                self.logger.warning(f"Chat game task appears stuck (no heartbeat in {int(time.time() - self.last_chat_game_heartbeat)}s), restarting...")
                try:
                    if self.chat_game_task:
                        self.chat_game_task.cancel()
                        try:
                            await asyncio.wait_for(self.chat_game_task, timeout=5.0)
                        except asyncio.CancelledError:
                            pass
                        except asyncio.TimeoutError:
                            self.logger.warning("Chat game task didn't cancel within timeout")
                        except Exception as e:
                            self.logger.error(f"Error cancelling stuck chat game task: {e}")
                except Exception:
                    pass
                self.chat_game_task = asyncio.create_task(self._chat_game_loop())
                self.last_chat_game_heartbeat = time.time()
                self.logger.info("Chat game task restarted after detecting stuck state")
    
    async def _chat_game_loop(self):
        await self.bot.wait_until_ready()
        self.logger.info("Chat game loop started")
        self.last_chat_game_heartbeat = time.time()
        
        while self.chat_game_running:
            try:
                # Ensure bot is still ready before proceeding
                if not self.bot.is_ready():
                    self.logger.warning("Bot not ready, waiting...")
                    await self.bot.wait_until_ready()
                
                self.last_chat_game_heartbeat = time.time()
                wait_time = await self._calc_chat_wait()
                formatted_time = format_wait_time(wait_time)
                self.logger.info(f"Waiting {formatted_time} before next chat game")
                
                # Break long sleeps into 1-minute chunks with periodic health checks
                # This ensures the loop stays responsive and can detect issues quickly
                if wait_time > 0:
                    remaining_time = wait_time
                    while remaining_time > 0 and self.chat_game_running:
                        # Sleep in 60-second chunks, but don't sleep longer than remaining time
                        sleep_chunk = min(60, remaining_time)
                        await asyncio.sleep(sleep_chunk)
                        remaining_time -= sleep_chunk
                        
                        # Update heartbeat every minute during long waits
                        self.last_chat_game_heartbeat = time.time()
                        
                        # Ensure bot is still ready after each chunk
                        if not self.bot.is_ready():
                            self.logger.warning("Bot disconnected during wait, waiting for reconnection...")
                            await self.bot.wait_until_ready()
                            self.last_chat_game_heartbeat = time.time()
                
                if not self.chat_game_running:
                    break
                
                # Final readiness check before sending game
                if not self.bot.is_ready():
                    self.logger.warning("Bot not ready before sending game, waiting...")
                    await self.bot.wait_until_ready()
                
                self.last_chat_game_heartbeat = time.time()
                choices = [Unscramble, FlagGuesser, MathQuiz, Trivia, EmojiQuiz, GuessTheNumber]
                game_class = random.choice(choices)
                
                try:
                    game = game_class(self.bot)
                except Exception as e:
                    import traceback
                    self.logger.error(f"Error instantiating {game_class.__name__}: {e}")
                    self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
                    self.last_chat_game_heartbeat = time.time()
                    await asyncio.sleep(60)
                    continue
                
                try:
                    self.last_chat_game_heartbeat = time.time()
                    result = await game.run()
                    self.last_chat_game_heartbeat = time.time()
                    if result is None:
                        self.logger.warning(f"{game_class.__name__}.run() returned None - game may not have been sent")
                    else:
                        self.logger.info(f"Successfully sent chat game: {game_class.__name__}")
                except Exception as e:
                    import traceback
                    self.logger.error(f"Error running {game_class.__name__}: {e}")
                    self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
                    # Continue loop even if game.run() fails
                    self.last_chat_game_heartbeat = time.time()
                    await asyncio.sleep(60)
                    continue
                
            except asyncio.CancelledError:
                self.logger.info("Chat game loop cancelled")
                break
            except Exception as e:
                import traceback
                self.logger.error(f"Chat game loop error: {e}")
                self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
                self.last_chat_game_heartbeat = time.time()
                # Sleep for a short time before retrying, but don't give up
                try:
                    await asyncio.sleep(60)
                except Exception:
                    pass
        
        self.logger.info("Chat game loop exited")
    
    async def _dm_game_loop(self):
        await self.bot.wait_until_ready()
        
        while self.dm_game_running:
            try:
                wait_time = await self._calc_dm_wait()
                last_game = await self._get_last_dm_game()
                last_game_name = last_game.get('game_name', 'Unknown') if last_game else 'Unknown'
                next_game = self._get_next_dm_game(last_game_name if last_game else None)
                formatted_time = format_wait_time(wait_time)
                
                self.logger.info(
                    f"Waiting {formatted_time} before refreshing DM game: {last_game_name} → {next_game}"
                )
                await asyncio.sleep(wait_time)
                
                if not self.dm_game_running:
                    break
                
                await self._refresh_dm_game(next_game)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"DM game loop error: {e}")
                await asyncio.sleep(60)
    
    async def _calc_chat_wait(self) -> int:
        try:
            db = await asyncio.wait_for(self._get_db(), timeout=5.0)
            rows = await asyncio.wait_for(
                db.execute("SELECT game_name, refreshed_at FROM games WHERE dm_game = FALSE ORDER BY refreshed_at DESC LIMIT 1"),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            self.logger.warning("[GameManager] Database timeout in _calc_chat_wait, using default delay")
            # Return a default wait time if database is slow (use min delay to avoid long waits)
            delay_config = self.chat_config.get('DELAY', {}) or self.chat_config.get('delay', {})
            min_delay = delay_config.get('LOWER') or delay_config.get('min_seconds', 1500)
            # Use min_delay instead of max_delay to avoid waiting too long when DB is slow
            return min_delay
        except Exception as e:
            self.logger.error(f"[GameManager] Database error in _calc_chat_wait: {e}")
            # Return a default wait time if database fails (use min delay)
            delay_config = self.chat_config.get('DELAY', {}) or self.chat_config.get('delay', {})
            min_delay = delay_config.get('LOWER') or delay_config.get('min_seconds', 1500)
            return min_delay
        
        if not rows:
            return 0
        
        last = int(rows[0]['refreshed_at'])
        now = int(datetime.now(timezone.utc).timestamp())
        time_since_last = now - last
        
        # Support both old and new delay structure
        delay_config = self.chat_config.get('DELAY', {})
        if not delay_config:
            delay_config = self.chat_config.get('delay', {})
        min_delay = delay_config.get('LOWER') or delay_config.get('min_seconds', 1500)
        max_delay = delay_config.get('UPPER') or delay_config.get('max_seconds', 2100)
        
        # Ensure delays are reasonable (25-35 minutes = 1500-2100 seconds)
        min_delay = max(1500, min(min_delay, 2100))
        max_delay = max(min_delay, min(max_delay, 2100))
        
        delay = random.randint(min_delay, max_delay)
        
        wait_time = delay - time_since_last
        
        # If it's been more than max_delay since last game, send immediately (wait_time = 0)
        if time_since_last >= max_delay:
            formatted_time_since = format_wait_time(time_since_last)
            formatted_max_delay = format_wait_time(max_delay)
            self.logger.info(f"Last game was {formatted_time_since} ago (>{formatted_max_delay}), sending immediately")
            return 0
        
        # Cap wait_time to max_delay to prevent extremely long waits
        wait_time = max(0, min(wait_time, max_delay))
        
        # If wait_time is still too long, clamp it
        if wait_time > max_delay:
            self.logger.warning(f"Calculated wait time ({wait_time}s) exceeded max delay ({max_delay}s), clamping")
            wait_time = max_delay
        
        return wait_time
    
    async def _calc_dm_wait(self) -> int:
        try:
            db = await asyncio.wait_for(self._get_db(), timeout=3.0)
            rows = await asyncio.wait_for(
                db.execute("SELECT game_name, refreshed_at FROM games WHERE dm_game = TRUE ORDER BY refreshed_at DESC LIMIT 1"),
                timeout=3.0
            )
        except asyncio.TimeoutError:
            self.logger.warning("[GameManager] Database timeout in _calc_dm_wait, using default delay")
            delay = self.dm_config.get('DELAY') or self.dm_config.get('rotation_delay', 7200)
            return delay
        except Exception as e:
            self.logger.error(f"[GameManager] Database error in _calc_dm_wait: {e}")
            delay = self.dm_config.get('DELAY') or self.dm_config.get('rotation_delay', 7200)
            return delay
        
        if not rows:
            return 0
        
        last = int(rows[0]['refreshed_at'])
        now = int(datetime.now(timezone.utc).timestamp())
        # Support both old (DELAY) and new (rotation_delay) structure
        delay = self.dm_config.get('DELAY') or self.dm_config.get('rotation_delay', 7200)
        
        wait_time = delay - (now - last)
        return max(wait_time, 0)
    
    async def _get_last_dm_game(self) -> Optional[Dict]:
        try:
            db = await asyncio.wait_for(self._get_db(), timeout=3.0)
            rows = await asyncio.wait_for(
                db.execute("SELECT game_name, refreshed_at FROM games WHERE dm_game = TRUE ORDER BY refreshed_at DESC LIMIT 1"),
                timeout=3.0
            )
            return rows[0] if rows else None
        except asyncio.TimeoutError:
            self.logger.warning("[GameManager] Database timeout in _get_last_dm_game")
            return None
        except Exception as e:
            self.logger.error(f"[GameManager] Database error in _get_last_dm_game: {e}")
            return None
    
    def _get_next_dm_game(self, last_game_name: Optional[str]) -> str:
        # Support both old (GAMES) and new (games) structure
        games_dict = self.dm_config.get('GAMES', {}) or self.dm_config.get('games', {})
        games = list(games_dict.keys())
        if not games:
            return "TicTacToe"
        
        if not last_game_name:
            return games[0]
        
        try:
            index = [name.lower() for name in games].index(last_game_name.lower())
            next_index = (index + 1) % len(games)
        except ValueError:
            next_index = 0
        
        return games[next_index]
    
    async def _refresh_dm_game(self, game_name: str):
        try:
            db = await asyncio.wait_for(self._get_db(), timeout=3.0)
            refreshed_at = int(datetime.now(timezone.utc).timestamp())
            
            # For 2048, keep it as "2048" instead of title case
            db_game_name = "2048" if game_name.lower() == "2048" else game_name.title()
            await asyncio.wait_for(
                db.execute_insert(
                    "INSERT INTO games (game_name, refreshed_at, dm_game) VALUES (%s, %s, %s)",
                    (db_game_name, refreshed_at, True)
                ),
                timeout=3.0
            )
        except asyncio.TimeoutError:
            self.logger.error(f"[GameManager] Database timeout in _refresh_dm_game for {game_name}")
            return
        except Exception as e:
            self.logger.error(f"[GameManager] Database error in _refresh_dm_game for {game_name}: {e}")
            return
        
        guild = self.bot.get_guild(self.config.get('config', 'GUILD_ID'))
        if not guild:
            return
        
        leveling_channel = guild.get_channel(self.config.get('config', 'LEVELING_CHANNEL'))
        games_role = guild.get_role(self.config.get('config', 'GAMES_ROLE'))
        
        if leveling_channel and games_role:
            # Delete the previous refresh message if it exists
            if self.last_dm_refresh_msg:
                try:
                    await self.last_dm_refresh_msg.delete()
                except Exception:
                    pass  # Message might have been deleted already
            
            # Send the new refresh message and store it
            msg = await leveling_channel.send(
                content=f"🚨 {games_role.mention} {game_name.title()} has been refreshed!"
            )
            self.last_dm_refresh_msg = msg
            
            # Update the top message with the new active game
            await self._update_leveling_channel_message(leveling_channel, game_name, refreshed_at)
        
        self.logger.info(f"Refreshed DM game: {game_name}")
    
    async def _update_leveling_channel_message(self, channel: discord.TextChannel, active_game: str, refreshed_at: int):
        """Update the leaderboard message in leveling channel with new active game info."""
        try:
            from ui.dm_games_view import DMGamesView
            from ui.sendgames_view import SendGamesView
            
            game_sequence = ["TicTacToe", "Wordle", "Connect Four", "Memory", "2048", "Minesweeper", "Hangman"]
            new_dm_game = refreshed_at + 7200  # 2 hours from now
            
            rotation_display = " → ".join(
                f"**{g}**" if g.lower().replace(" ", "") == active_game.lower().replace(" ", "") else g
                for g in game_sequence
            )
            
            # Find the leaderboard message (second message, has "Leaderboard" in title)
            target_message = None
            
            async for message in channel.history(limit=10):
                if message.embeds and len(message.embeds) > 0:
                    if "Leaderboard" in (message.embeds[0].title or ""):
                        target_message = message
                        break
            
            if target_message:
                # Get current leaderboard
                guild = channel.guild
                leaderboard_text = await SendGamesView.get_leaderboard(guild, self.bot)
                
                current_time = int(datetime.now(timezone.utc).timestamp())
                
                embed = discord.Embed(
                    color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
                    title="Leaderboard <:minecadia_2:1444800686372950117>",
                    description=(
                        leaderboard_text +
                        f'\n\n**Last Updated** <t:{current_time}:R>\n\n'
                        f'✅ **Active DM Game**: {active_game}\n'
                        f'🚨 **Next DM Game**: <t:{new_dm_game}:R>\n'
                        f"-# {rotation_display}"
                    )
                )
                # Only set thumbnail if logo is a valid URL (not a local file path)
                from utils.helpers import get_embed_logo_url
                logo_url = get_embed_logo_url("Assets/Logo.png")
                if logo_url:
                    embed.set_thumbnail(url=logo_url)
                embed.set_image(url="https://i.imgur.com/z3bbBSA.png")
                
                # Update the message with new embed and view (DMGamesView only)
                view = DMGamesView(self.bot, active_game.lower())
                await target_message.edit(embed=embed, view=view)
                self.logger.info(f"Updated leveling channel leaderboard message with active game: {active_game}")
            else:
                self.logger.warning("Could not find leveling channel leaderboard message to update")
        except Exception as e:
            self.logger.error(f"Error updating leveling channel message: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
    
    def stop_chat_games(self):
        self.chat_game_running = False
        if self.chat_game_task:
            self.chat_game_task.cancel()
    
    def start_chat_games(self):
        self.chat_game_running = True
        if not self.chat_game_task or self.chat_game_task.done():
            self.chat_game_task = asyncio.create_task(self._chat_game_loop())
    
    def stop_dm_games(self):
        self.dm_game_running = False
        if self.dm_game_task:
            self.dm_game_task.cancel()
    
    def start_dm_games(self):
        self.dm_game_running = True
        if not self.dm_game_task or self.dm_game_task.done():
            self.dm_game_task = asyncio.create_task(self._dm_game_loop())
    
    async def force_send_chat_game(self):
        """Force send a new chat game immediately and refresh the timer."""
        try:
            choices = [Unscramble, FlagGuesser, MathQuiz, Trivia, EmojiQuiz]
            game_class = random.choice(choices)
            
            # Instantiate the game - this is where the error might occur
            try:
                game = game_class(self.bot)
            except Exception as e:
                import traceback
                self.logger.error(f"Error instantiating {game_class.__name__} in force_send_chat_game: {e}")
                self.logger.error(f"Traceback: {traceback.format_exc()}")
                return False
            
            if self.last_chat_game_msg:
                try:
                    await self.last_chat_game_msg.delete()
                except:
                    pass
            
            msg = await game.run()
            if msg:
                self.last_chat_game_msg = msg
                self.logger.info(f"Force sent chat game: {game_class.__name__}")
                return True
            return False
        except Exception as e:
            import traceback
            self.logger.error(f"Error force sending chat game: {e}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    async def force_cycle_dm_game(self):
        """Force cycle to the next DM game immediately."""
        try:
            last_game = await self._get_last_dm_game()
            next_game = self._get_next_dm_game(last_game['game_name'] if last_game else None)
            await self._refresh_dm_game(next_game)
            return next_game
        except Exception as e:
            self.logger.error(f"Error force cycling DM game: {e}")
            return None

