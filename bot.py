import discord
from discord.ext import commands
from pathlib import Path
from datetime import datetime, timezone
from core.config.manager import ConfigManager
from core.database.pool import DatabasePool
from core.cache.manager import CacheManager
from core.logging.setup import setup_logging, get_logger
from managers.game_manager import GameManager
from typing import Optional, Tuple
import asyncio
import json
import re


class MinecadiaBot(commands.Bot):
    def __init__(self):
        setup_logging()
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Tasks")
        
        intents = discord.Intents.all()
        super().__init__(command_prefix='.', intents=intents)
        
        self.game_manager: Optional[GameManager] = None
    
    async def setup_hook(self):
        try:
            self.logger.info("Starting bot setup...")
            
            # Initialize database pool in background (non-blocking)
            self.logger.info("Initializing database pool in background...")
            asyncio.create_task(self._initialize_database_pool_background())
            
            self.logger.info("Starting cache cleanup task...")
            cache = CacheManager.get_instance()
            await cache.start_cleanup_task()
            self.logger.info("Cache cleanup task started")
            
            self.logger.info("Loading extensions...")
            await self.load_extensions()
            self.logger.info("Bot setup complete")
        except Exception as e:
            self.logger.error(f"Error in setup_hook: {e}", exc_info=True)
    
    async def _initialize_database_pool_background(self):
        """Initialize database pool in background without blocking startup"""
        try:
            # Get instance (doesn't initialize yet)
            db_pool = await DatabasePool.get_instance()
            # Try to initialize with timeout - this warms up the connection
            try:
                await asyncio.wait_for(db_pool.initialize(), timeout=15.0)
                self.logger.info("Database pool initialized in background")
            except asyncio.TimeoutError:
                self.logger.warning("Database pool initialization timed out after 15 seconds - will retry on first use")
            except Exception as init_e:
                self.logger.warning(f"Database pool initialization failed: {init_e} - will retry on first use")
        except Exception as e:
            self.logger.error(f"Failed to get database pool instance: {e} - database features may not work", exc_info=True)
    
    async def load_extensions(self):
        import os
        from pathlib import Path
        cog_dir = Path(__file__).parent / "cogs"
        if cog_dir.exists():
            for filename in cog_dir.iterdir():
                if filename.suffix == '.py' and not filename.name.startswith('_'):
                    ext_name = f"cogs.{filename.stem}"
                    try:
                        await self.load_extension(ext_name)
                        self.logger.info(f"Loaded extension: {ext_name}")
                    except Exception as e:
                        self.logger.error(f"Failed to load {ext_name}: {e}")
    
    async def on_ready(self):
        self.logger.info(f"Logged in as {self.user} ({self.user.id})")
        
        if not self.game_manager:
            self.game_manager = GameManager(self)
            await self.game_manager.initialize()
        else:
            # Check if tasks are still running after reconnection
            await self._ensure_game_tasks_running()
        
        # Load Wordle listener for DM message handling
        try:
            from games.dm.wordle import WordleListener
            wordle_listener = WordleListener(self)
            if self.game_manager and hasattr(self.game_manager, 'dm_games'):
                wordle_game = self.game_manager.dm_games.get('Wordle')
                if wordle_game:
                    wordle_listener.set_wordle_game(wordle_game)
                    self.logger.info("Wordle listener: Set wordle_game instance")
                else:
                    self.logger.warning("Wordle listener: wordle_game not found in dm_games")
            else:
                self.logger.warning("Wordle listener: game_manager or dm_games not available")
            await self.add_cog(wordle_listener)
            self.logger.info("Loaded Wordle listener")
        except Exception as e:
            self.logger.error(f"Failed to load Wordle listener: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        
        # Load Minesweeper listener for DM message handling (flagging)
        try:
            from games.dm.minesweeper import MinesweeperListener
            minesweeper_listener = MinesweeperListener(self)
            if self.game_manager and hasattr(self.game_manager, 'dm_games'):
                minesweeper_listener.set_minesweeper_game(self.game_manager.dm_games.get('Minesweeper'))
            await self.add_cog(minesweeper_listener)
            self.logger.info("Loaded Minesweeper listener")
        except Exception as e:
            self.logger.error(f"Failed to load Minesweeper listener: {e}")
        
        # Load Hangman listener for DM message handling
        try:
            from games.dm.hangman import HangmanListener
            hangman_listener = HangmanListener(self)
            if self.game_manager and hasattr(self.game_manager, 'dm_games'):
                hangman_game = self.game_manager.dm_games.get('Hangman')
                if hangman_game:
                    hangman_listener.set_hangman_game(hangman_game)
                    self.logger.info("Hangman listener: Set hangman_game instance")
                else:
                    self.logger.warning("Hangman listener: hangman_game not found in dm_games")
            else:
                self.logger.warning("Hangman listener: game_manager or dm_games not available")
            await self.add_cog(hangman_listener)
            self.logger.info("Loaded Hangman listener")
        except Exception as e:
            self.logger.error(f"Failed to load Hangman listener: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        
        # Register persistent views
        try:
            await self._register_persistent_views()
            self.logger.info("Registered persistent views")
        except Exception as e:
            self.logger.error(f"Failed to register persistent views: {e}")
        
        # Restore active chat games
        try:
            await self._restore_active_chat_games()
            self.logger.info("Restored active chat games")
        except Exception as e:
            self.logger.error(f"Failed to restore active chat games: {e}")
        
        # Restore active DM games
        try:
            await self._restore_active_dm_games()
            self.logger.info("Restored active DM games")
        except Exception as e:
            self.logger.error(f"Failed to restore active DM games: {e}")
        
        await self.change_presence(activity=discord.Game(name=self.config.get('config', 'PRESENCE', 'play.minecadia.com')))
        
        try:
            self.remove_command('help')
        except:
            pass
        
        # Sync application commands
        await self._sync_commands()
    
    async def on_resume(self):
        """Called when the bot resumes a connection after disconnection"""
        self.logger.info("Bot connection resumed - checking game tasks")
        if self.game_manager:
            await self._ensure_game_tasks_running()
    
    async def _ensure_game_tasks_running(self):
        """Ensure chat and DM game tasks are running, restart if needed"""
        if not self.game_manager:
            return
        
        # Check chat game task
        if self.game_manager.chat_game_running:
            if self.game_manager.chat_game_task is None or self.game_manager.chat_game_task.done():
                self.logger.warning("Chat game task is not running, restarting...")
                try:
                    if self.game_manager.chat_game_task and self.game_manager.chat_game_task.done():
                        # Get exception if task failed
                        try:
                            await self.game_manager.chat_game_task
                        except Exception as e:
                            self.logger.error(f"Chat game task exception: {e}")
                except Exception:
                    pass
                self.game_manager.chat_game_task = asyncio.create_task(self.game_manager._chat_game_loop())
                self.logger.info("Chat game task restarted")
        
        # Check DM game task
        if self.game_manager.dm_game_running:
            if self.game_manager.dm_game_task is None or self.game_manager.dm_game_task.done():
                self.logger.warning("DM game task is not running, restarting...")
                try:
                    if self.game_manager.dm_game_task and self.game_manager.dm_game_task.done():
                        # Get exception if task failed
                        try:
                            await self.game_manager.dm_game_task
                        except Exception as e:
                            self.logger.error(f"DM game task exception: {e}")
                except Exception:
                    pass
                self.game_manager.dm_game_task = asyncio.create_task(self.game_manager._dm_game_loop())
                self.logger.info("DM game task restarted")
    
    async def _sync_commands(self):
        """Sync application commands with Discord"""
        try:
            synced = await self.tree.sync()
            self.logger.info(f"Synced {len(synced)} commands")
        except Exception as e:
            self.logger.error(f"Failed to sync commands: {e}")

    async def _register_persistent_views(self):
        """Register all persistent views that need to work after bot restarts."""
        from ui.dm_games_view import (
            DMGamesView, StartWordleView, StartTicTacToeView, 
            StartMemoryView, StartConnectFourView, Start2048View, StartMinesweeperView
        )
        from ui.sendgames_view import ViewMore
        from ui.all_time_leaderboard import AllTimeLeaderboardView
        from cogs.game_manager_cog import (
            MainGameManagerView, ChatGamesView, ChatGamesManageView,
            DMGamesManagerView, DMGamesManageView, TestDMGameSelectorView
        )
        
        # Create dummy interaction for views that require it
        class DummyInteraction:
            def __init__(self):
                self.user = None
        
        dummy_interaction = DummyInteraction()
        
        # ==========================================
        # DM Games Views
        # ==========================================
        
        # Register DMGamesView for each possible active game
        game_options = ["wordle", "tictactoe", "memory", "connect four", "2048", "minesweeper"]
        for game in game_options:
            view = DMGamesView(self, game)
            self.add_view(view)
        
        # Register Start*View classes
        start_wordle_view = StartWordleView(dummy_interaction, self)
        self.add_view(start_wordle_view)
        
        start_tic_view = StartTicTacToeView(dummy_interaction, self)
        self.add_view(start_tic_view)
        
        start_memory_view = StartMemoryView(dummy_interaction, self)
        self.add_view(start_memory_view)
        
        start_connect_four_view = StartConnectFourView(dummy_interaction, self)
        self.add_view(start_connect_four_view)
        
        start_2048_view = Start2048View(dummy_interaction, self)
        self.add_view(start_2048_view)
        
        start_minesweeper_view = StartMinesweeperView(dummy_interaction, self)
        self.add_view(start_minesweeper_view)
        
        # ==========================================
        # UI Views
        # ==========================================
        
        # Register ViewMore (sendgames view)
        view_more = ViewMore()
        self.add_view(view_more)
        
        # Register AllTimeLeaderboardView
        guild = self.guilds[0] if self.guilds else None
        if guild:
            all_time_lb_view = AllTimeLeaderboardView(self, guild)
            self.add_view(all_time_lb_view)
        
        # ==========================================
        # Game Manager Views
        # ==========================================
        
        # These views need GameManager instance - register if available
        # Note: TestDMGameSelectorView is NOT registered here as it has a timeout and is temporary
        if self.game_manager:
            try:
                main_gm_view = MainGameManagerView(self.game_manager, self.config)
                self.add_view(main_gm_view)
                
                chat_games_view = ChatGamesView(self.game_manager, self.config, self)
                self.add_view(chat_games_view)
                
                chat_games_manage_view = ChatGamesManageView(self.game_manager, self.config, self)
                self.add_view(chat_games_manage_view)
                
                dm_games_manager_view = DMGamesManagerView(self.game_manager, self.config, self)
                self.add_view(dm_games_manager_view)
                
                dm_games_manage_view = DMGamesManageView(self.game_manager, self.config, self)
                self.add_view(dm_games_manage_view)
            except Exception as e:
                self.logger.error(f"Failed to register game manager views: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
        
        # ==========================================
        # Chat Game Views (registered dynamically by game_id)
        # These are restored in _restore_active_chat_games
        # ==========================================
        
        # Note: Chat game views (TriviaButtons, MathQuizButtons, CountryButtons, 
        # GuessTheNumberButtons, UnscrambleButtons, EmojiQuizButtons) have dynamic
        # custom_ids based on game_id, so they are registered when games are created
        # and restored via _restore_active_chat_games
        
        # ==========================================
        # DM Game Button Views (registered dynamically)
        # These are restored in _restore_active_dm_games
        # ==========================================
        
        # Note: DM game button views (TicTacToeButtons, ConnectFourButtons, 
        # MemoryButtons, TwentyFortyEightButtons, MinesweeperButtons) are registered
        # when games are created and restored via _restore_active_dm_games
        
        # ==========================================
        # Practice Views (registered dynamically)
        # ==========================================
        
        # Note: Practice views (PracticeTriviaView, PracticeMathQuizView, 
        # PracticeFlagGuesserView, PracticeUnscrambleView, PracticeEmojiQuizView)
        # are created dynamically per-session and registered when practice starts
        
        # ==========================================
        # Admin/Utility Views (now persistent)
        # ==========================================
        
        from cogs.config_management import ConfigManagerView, ConfigViewer
        from cogs.logs import LogsView
        from cogs.milestones import MilestonesView
        from cogs.statistics import StatisticsView
        from cogs.chat_game_admin import ChatGameAdminView
        from utils.paginator import Paginator
        from managers.milestones import MilestonesManager
        
        # Register ConfigManagerView with available configs
        try:
            from cogs.config_management import ConfigManagement
            # Create a temporary instance to get available configs
            temp_cog = ConfigManagement(self)
            available_configs = temp_cog._get_available_configs()
            config_manager_view = ConfigManagerView(self.config, available_configs)
            self.add_view(config_manager_view)
        except Exception as e:
            self.logger.error(f"Failed to register ConfigManagerView: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        
        # Register ConfigViewer (empty data, will be populated when used)
        try:
            config_viewer = ConfigViewer(self.config, "", {}, [])
            self.add_view(config_viewer)
        except Exception as e:
            self.logger.error(f"Failed to register ConfigViewer: {e}")
        
        # Register LogsView
        try:
            logs_view = LogsView(self, self.config)
            self.add_view(logs_view)
        except Exception as e:
            self.logger.error(f"Failed to register LogsView: {e}")
        
        # Register MilestonesView (with dummy user_id, actual views created per-user)
        try:
            milestones_manager = MilestonesManager()
            milestones_view = MilestonesView(self, self.config, 0, milestones_manager)
            self.add_view(milestones_view)
        except Exception as e:
            self.logger.error(f"Failed to register MilestonesView: {e}")
        
        # Register StatisticsView (with dummy user_id, actual views created per-user)
        try:
            statistics_view = StatisticsView(self, self.config, 0)
            self.add_view(statistics_view)
        except Exception as e:
            self.logger.error(f"Failed to register StatisticsView: {e}")
        
        # Register Paginator
        try:
            paginator = Paginator()
            self.add_view(paginator)
        except Exception as e:
            self.logger.error(f"Failed to register Paginator: {e}")
        
        # Register ChatGameAdminView (with dummy message for custom_id registration)
        try:
            class DummyMessage:
                id = 0
            chat_admin_view = ChatGameAdminView(DummyMessage(), "", None, self, self.config)
            self.add_view(chat_admin_view)
        except Exception as e:
            self.logger.error(f"Failed to register ChatGameAdminView: {e}")
        
        self.logger.info("Registered all persistent views")
    
    async def _restore_active_chat_games(self):
        """Restore active chat games that were running when bot restarted"""
        try:
            db = await DatabasePool.get_instance()
            current_time = int(datetime.now(timezone.utc).timestamp())
            chat_config = self.config.get('chat_games')
            game_length = chat_config.get('GAME_LENGTH') or chat_config.get('game_duration', 600)
            
            # Get all active chat games (status='Started' or NULL, and end_time > current_time, or refreshed_at + game_length > current_time)
            # Try with end_time column first
            try:
                active_games = await db.execute(
                    """
                    SELECT game_id, game_name, refreshed_at, end_time 
                    FROM games 
                    WHERE dm_game = FALSE 
                    AND (status = 'Started' OR status IS NULL)
                    AND (end_time > %s OR (end_time IS NULL AND refreshed_at + %s > %s))
                    ORDER BY refreshed_at DESC
                    """,
                    (current_time, game_length, current_time)
                )
            except Exception:
                # If end_time or status columns don't exist, use refreshed_at + default game_length
                # Don't check status since the column might not exist
                try:
                    active_games = await db.execute(
                        """
                        SELECT game_id, game_name, refreshed_at 
                        FROM games 
                        WHERE dm_game = FALSE 
                        AND refreshed_at + %s > %s
                        ORDER BY refreshed_at DESC
                        """,
                        (game_length, current_time)
                    )
                except Exception:
                    # If even this fails, just get all recent non-DM games
                    active_games = await db.execute(
                        """
                        SELECT game_id, game_name, refreshed_at 
                        FROM games 
                        WHERE dm_game = FALSE 
                        AND refreshed_at > %s
                        ORDER BY refreshed_at DESC
                        LIMIT 10
                        """,
                        (current_time - 3600,)  # Only games from last hour
                    )
            
            if not active_games:
                self.logger.info("No active chat games to restore")
                return
            
            self.logger.info(f"Found {len(active_games)} active chat games to restore")
            
            for game in active_games:
                try:
                    game_id = game['game_id']
                    game_name = game['game_name']
                    refreshed_at = int(game.get('refreshed_at', 0))
                    end_time = game.get('end_time')
                    
                    # Calculate end_time if not stored
                    if not end_time:
                        end_time = refreshed_at + game_length
                    
                    # Check if game should have already ended
                    if end_time <= current_time:
                        # Game should have ended, mark it as finished
                        try:
                            await db.execute(
                                "UPDATE games SET status = 'Finished' WHERE game_id = %s",
                                (game_id,)
                            )
                        except:
                            pass
                        continue
                    
                    # Calculate remaining time
                    remaining_time = end_time - current_time
                    
                    # Restore timer for this game
                    asyncio.create_task(self._restore_chat_game_timer(game_id, game_name, end_time, remaining_time))
                    
                except Exception as e:
                    self.logger.error(f"Error restoring game {game.get('game_id')}: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
        
        except Exception as e:
            self.logger.error(f"Error restoring active chat games: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def _parse_dm_game_from_embed_title(self, title: str) -> Optional[Tuple[str, int]]:
        """Parse (game_type, game_id) from a game embed title, e.g. 'Minesweeper #14815' or '2048 #123 🧪 TEST GAME 🧪'."""
        if not title or '#' not in title:
            return None
        match = re.search(r'#(\d+)', title)
        if not match:
            return None
        game_id = int(match.group(1))
        prefix = title.split('#')[0].strip()
        # Strip test label if present
        prefix = re.sub(r'\s*🧪\s*TEST\s*GAME\s*🧪\s*$', '', prefix, flags=re.IGNORECASE).strip()
        # Map embed title prefix to game_type (must match game_tables values)
        title_to_type = {
            '2048': '2048',
            'TicTacToe': 'tictactoe',
            'Connect Four': 'connectfour',
            'Memory': 'memory',
            'Minesweeper': 'minesweeper',
            'Hangman': 'hangman',
        }
        game_type = title_to_type.get(prefix)
        if game_type is None:
            return None
        return (game_type, game_id)
    
    async def _get_most_recent_dm_game_for_user(self, user_id: int) -> Optional[Tuple[str, int]]:
        """Return (game_type, game_id) for the most recent DM game message in this user's DM, or None."""
        try:
            user = await self.fetch_user(user_id)
            if not user:
                return None
            channel = user.dm_channel or await user.create_dm()
            # Most recent messages first
            async for message in channel.history(limit=50):
                if message.author.id != self.user.id:
                    continue
                if not message.embeds:
                    continue
                title = message.embeds[0].title
                parsed = self._parse_dm_game_from_embed_title(title)
                if parsed:
                    return parsed
            return None
        except Exception as e:
            self.logger.debug(f"Could not get most recent DM game for user {user_id}: {e}")
            return None
    
    async def _end_dm_game_in_db(self, game_type: str, game_id: int, user_id: int):
        """Mark a DM game as ended (closed) in the database so it is no longer considered active."""
        try:
            db = await DatabasePool.get_instance()
            now = int(datetime.now(timezone.utc).timestamp())
            table_map = {
                '2048': ('users_2048', "status = 'Lost'"),
                'tictactoe': ('users_tictactoe', "won = 'Lost'"),
                'connectfour': ('users_connectfour', "status = 'Lost'"),
                'memory': ('users_memory', "won = 'Lost'"),
                'minesweeper': ('users_minesweeper', "won = 'Lost'"),
                'hangman': ('users_hangman', "won = 'Lost'"),
            }
            table, set_clause = table_map.get(game_type, (None, None))
            if not table:
                return
            await db.execute(
                f"UPDATE {table} SET {set_clause}, ended_at = %s WHERE user_id = %s AND game_id = %s",
                (now, user_id, game_id)
            )
            self.logger.debug(f"Ended non-most-recent DM game {game_type} #{game_id} for user {user_id}")
        except Exception as e:
            self.logger.warning(f"Error ending DM game {game_type} #{game_id} for user {user_id}: {e}")
    
    async def _restore_active_dm_games(self):
        """Restore active DM games that were running when bot restarted.
        Only restores a game if it is the most recent DM game in that user's DM;
        otherwise the game is closed in the DB and not restored.
        """
        try:
            db = await DatabasePool.get_instance()
            
            # Game type mapping: database table name -> game type identifier
            # Note: Wordle is not included here because it doesn't use game_state
            # Wordle games are restored on-demand by WordleListener when users send messages
            game_tables = {
                'users_2048': '2048',
                'users_tictactoe': 'tictactoe',
                'users_connectfour': 'connectfour',
                'users_memory': 'memory',
                'users_minesweeper': 'minesweeper',
                'users_hangman': 'hangman'
            }
            
            restored_count = 0
            
            for table_name, game_type in game_tables.items():
                try:
                    # Different tables use different column names for status
                    # users_2048 and users_connectfour use 'status', all others use 'won'
                    if table_name in ['users_2048', 'users_connectfour']:
                        status_condition = "status = 'Started'"
                    else:
                        status_condition = "won = 'Started'"
                    
                    # Get active games (status/won='Started', ended_at=0, game_state IS NOT NULL)
                    active_games = await db.execute(
                        f"""
                        SELECT game_id, user_id, game_state
                        FROM {table_name}
                        WHERE {status_condition}
                        AND (ended_at = 0 OR ended_at IS NULL)
                        AND game_state IS NOT NULL
                        ORDER BY started_at DESC
                        LIMIT 100
                        """
                    )
                    
                    if not active_games:
                        continue
                    
                    self.logger.info(f"Found {len(active_games)} active {game_type} games to restore")
                    
                    for game in active_games:
                        try:
                            game_id = game['game_id']
                            user_id = game['user_id']
                            game_state_json = game.get('game_state')
                            
                            if not game_state_json:
                                continue
                            
                            # Only restore if this game is the most recent DM game for this user
                            most_recent = await self._get_most_recent_dm_game_for_user(user_id)
                            if most_recent is None or most_recent != (game_type, game_id):
                                await self._end_dm_game_in_db(game_type, game_id, user_id)
                                continue
                            
                            # Parse game state
                            try:
                                if isinstance(game_state_json, str):
                                    game_state = json.loads(game_state_json)
                                else:
                                    game_state = game_state_json
                            except Exception as e:
                                self.logger.error(f"Error parsing game_state for {game_type} game {game_id}: {e}")
                                continue
                            
                            # Wordle doesn't use views - it uses WordleListener which restores on-demand
                            if game_type == 'wordle':
                                continue
                            
                            # Restore the view based on game type
                            view = await self._restore_dm_game_view(game_type, game_id, user_id, game_state)
                            
                            if view:
                                # Register view for persistence
                                self.add_view(view)
                                restored_count += 1
                                
                        except Exception as e:
                            self.logger.error(f"Error restoring {game_type} game {game.get('game_id')}: {e}")
                            import traceback
                            self.logger.error(traceback.format_exc())
                            
                except Exception as e:
                    self.logger.error(f"Error querying {table_name} for active games: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
            
            if restored_count > 0:
                self.logger.info(f"Restored {restored_count} active DM games")
            else:
                self.logger.info("No active DM games to restore")
                
        except Exception as e:
            self.logger.error(f"Error restoring active DM games: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    async def _restore_dm_game_view(self, game_type: str, game_id: int, user_id: int, game_state: dict):
        """Restore a DM game view from saved state"""
        try:
            config = self.config
            
            if game_type == '2048':
                from games.dm.twenty_forty_eight import TwentyFortyEightButtons
                dm_config = config.get('dm_games')
                games = dm_config.get('GAMES', {}) or dm_config.get('games', {})
                game_config = games.get('2048', {}) or games.get('Twenty Forty Eight', {})
                view = TwentyFortyEightButtons(
                    game_id, self, config, game_config, dm_config, user_id,
                    test_mode=False, saved_state=game_state
                )
                view.player_id = user_id
                return view
                
            elif game_type == 'tictactoe':
                from games.dm.tictactoe import TicTacToeButtons
                dm_config = config.get('dm_games')
                games = dm_config.get('GAMES', {}) or dm_config.get('games', {})
                game_config = games.get('TicTacToe', {})
                view = TicTacToeButtons(
                    game_id, self, config, game_config,
                    test_mode=False, saved_state=game_state
                )
                view.player_id = user_id
                return view
                
            elif game_type == 'connectfour':
                from games.dm.connect_four import ConnectFourButtons
                dm_config = config.get('dm_games')
                games = dm_config.get('GAMES', {}) or dm_config.get('games', {})
                game_config = games.get('Connect Four', {})
                view = ConnectFourButtons(
                    game_id, self, config, game_config,
                    test_mode=False, saved_state=game_state
                )
                view.player_id = user_id
                return view
                
            elif game_type == 'memory':
                from games.dm.memory import MemoryButtons
                dm_config = config.get('dm_games')
                games = dm_config.get('GAMES', {}) or dm_config.get('games', {})
                game_config = games.get('Memory', {})
                view = MemoryButtons(
                    game_id, self, config, game_config, dm_config,
                    test_mode=False, saved_state=game_state
                )
                view.player_id = user_id
                return view
                
            elif game_type == 'minesweeper':
                from games.dm.minesweeper import MinesweeperButtons
                # Minesweeper needs board and mine_positions - these should be in game_state
                board = game_state.get('board', [[0 for _ in range(5)] for _ in range(5)])
                mine_positions = game_state.get('mine_positions', [])
                num_mines = len(mine_positions) if mine_positions else 4
                dm_config = config.get('dm_games')
                games = dm_config.get('GAMES', {}) or dm_config.get('games', {})
                game_config = games.get('Minesweeper', {})
                view = MinesweeperButtons(
                    game_id, board, mine_positions, num_mines, self, config, game_config,
                    test_mode=False, saved_state=game_state
                )
                view.player_id = user_id
                return view
            
            elif game_type == 'hangman':
                from games.dm.hangman import HangmanButtons
                # Hangman needs word - should be in game_state
                word = game_state.get('word', '')
                if not word:
                    # If word not in game_state, try to get from database
                    db = await DatabasePool.get_instance()
                    rows = await db.execute(
                        "SELECT word FROM users_hangman WHERE game_id = %s AND user_id = %s",
                        (game_id, user_id)
                    )
                    if rows and len(rows) > 0:
                        word = rows[0].get('word', '')
                
                if not word:
                    self.logger.error(f"Could not restore Hangman game {game_id} - word not found")
                    return None
                
                dm_config = config.get('dm_games')
                games = dm_config.get('GAMES', {}) or dm_config.get('games', {})
                game_config = games.get('Hangman', {})
                view = HangmanButtons(
                    game_id, self, config, game_config, dm_config, word, user_id,
                    test_mode=False, saved_state=game_state
                )
                view.player_id = user_id
                return view
                
        except Exception as e:
            self.logger.error(f"Error creating view for {game_type} game {game_id}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
    
    async def _restore_chat_game_timer(self, game_id: int, game_name: str, end_time: int, remaining_time: float):
        """Restore timer for a chat game"""
        try:
            # Wait for remaining time
            if remaining_time > 0:
                await asyncio.sleep(remaining_time)
            
            # End the game
            db = await DatabasePool.get_instance()
            
            # Try to find the message - we'll need to search channels
            try:
                await db.execute(
                    "UPDATE games SET status = 'Finished' WHERE game_id = %s",
                    (game_id,)
                )
            except:
                pass
            
            # Try to end the game properly through GameManager
            if self.game_manager:
                try:
                    await self.game_manager.end_chat_game(game_id)
                except:
                    pass
        
        except Exception as e:
            self.logger.error(f"Error in chat game timer for game {game_id}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())


def main():
    bot = MinecadiaBot()
    token = bot.config.get('config', 'TOKEN')
    bot.run(token)


if __name__ == '__main__':
    main()