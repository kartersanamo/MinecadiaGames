import time
from datetime import datetime, timezone
from typing import Optional, Dict, Union
import discord
from core.config.manager import ConfigManager
from core.database.pool import DatabasePool
from core.logging.setup import get_logger
from utils.helpers import get_embed_logo_url


class _LevelingManagerCore:
    """
    Core singleton manager for handling user leveling and XP operations.
    Follows proper OOP principles with separation of concerns.
    """
    _instance: Optional['_LevelingManagerCore'] = None
    _debounce_ms = 2500
    _last_xp_times: Dict[int, float] = {}
    
    def __new__(cls):
        """Singleton pattern - ensure only one instance exists"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize the manager (only called once due to singleton)"""
        if hasattr(self, '_initialized'):
            return
        
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Leveling")
        self._db: Optional[DatabasePool] = None
        self._level_data: Optional[Dict] = None
        self._initialized = True
    
    @property
    async def db(self) -> DatabasePool:
        """Lazy-load database connection"""
        if self._db is None:
            self._db = await DatabasePool.get_instance()
        return self._db
    
    @property
    def level_data(self) -> Dict:
        """Lazy-load level data"""
        if self._level_data is None:
            self._level_data = self.config.get('levels', {})
        return self._level_data
    
    async def award_xp(
        self,
        user: discord.User,
        xp: int,
        source: str,
        game_id: int,
        channel: Optional[Union[discord.TextChannel, discord.DMChannel]] = None,
        bot: Optional[discord.Client] = None,
        test_mode: bool = False
    ) -> bool:
        """
        Award XP to a user. Main entry point for XP operations.
        
        Args:
            user: The user to award XP to
            xp: Amount of XP to award
            source: Source of the XP (game name, "Daily Reward", etc.)
            game_id: ID of the game (if applicable)
            channel: Channel where XP was earned (optional, for logging/announcements)
            bot: Bot client (optional, for announcements)
            test_mode: If True, only log, don't update database
            
        Returns:
            True if XP was awarded, False if debounced or test mode
        """
        # Check for test mode - either explicitly set or if game_id is the test game ID (-999999)
        if test_mode or game_id == -999999:
            self._log_test_mode(user, xp, source, channel)
            return False
        
        # Debounce check
        if not self._should_award_xp(user.id):
            return False
        
        try:
            # Get current stats
            stats = await self._get_user_stats(user.id)
            if stats is None:
                stats = await self._create_user_entry(user.id)
            
            current_xp = int(stats.get('xp', 0))
            current_level = int(stats.get('level', 0))
            new_xp = current_xp + xp
            
            # Update XP in database
            await self._update_user_xp(user.id, new_xp)
            
            # Log XP to xp_logs
            await self._log_xp_to_database(user.id, xp, source, game_id, channel)
            
            # Check for level up
            new_level = await self._check_and_update_level(user.id, current_level, new_xp)
            
            # Handle level up announcements
            if new_level > current_level:
                await self._handle_level_up(user, new_level, channel, bot)
            
            # Check achievements (only if not test mode)
            await self._check_achievements(user, source, new_xp, channel, bot)
            
            # Log to admin logs
            await self._log_to_admin_channel(user, xp, source, bot)
            
            # Log to console
            self._log_xp_award(user, xp, source, channel)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error awarding XP to user {user.id}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def _should_award_xp(self, user_id: int) -> bool:
        """Check if XP should be awarded (debounce check)"""
        current_ms = int(time.time() * 1000)
        last_time = self._last_xp_times.get(user_id, 0)
        
        if current_ms - last_time < self._debounce_ms:
            return False
        
        self._last_xp_times[user_id] = current_ms
        return True
    
    async def _get_user_stats(self, user_id: int) -> Optional[Dict[str, str]]:
        """Get user's current leveling stats from database"""
        db = await self.db
        rows = await db.execute(
            "SELECT user_id, xp, level FROM leveling WHERE user_id = %s",
            (str(user_id),)
        )
        return rows[0] if rows else None
    
    async def _create_user_entry(self, user_id: int) -> Dict[str, str]:
        """Create a new user entry in the leveling table"""
        db = await self.db
        await db.execute_insert(
            "INSERT INTO leveling (user_id, xp, level) VALUES (%s, %s, %s)",
            (str(user_id), '0', '0')
        )
        return {'user_id': str(user_id), 'xp': '0', 'level': '0'}
    
    async def _update_user_xp(self, user_id: int, new_xp: int):
        """Update user's XP in the database"""
        db = await self.db
        await db.execute(
            "UPDATE leveling SET xp = %s WHERE user_id = %s",
            (new_xp, str(user_id))
        )
    
    async def _log_xp_to_database(
        self,
        user_id: int,
        xp: int,
        source: str,
        game_id: int,
        channel: Optional[Union[discord.TextChannel, discord.DMChannel]]
    ):
        """Log XP award to xp_logs table"""
        db = await self.db
        timestamp = int(datetime.now(timezone.utc).timestamp())
        channel_id = channel.id if channel else 0
        
        try:
            await db.execute_insert(
                "INSERT INTO xp_logs (game_id, user_id, xp, channel_id, source, timestamp) VALUES (%s, %s, %s, %s, %s, %s)",
                (game_id, user_id, xp, channel_id, source, timestamp)
            )
        except Exception as e:
            # Fallback if timestamp column doesn't exist
            if "timestamp" in str(e).lower() or "unknown column" in str(e).lower():
                await db.execute_insert(
                    "INSERT INTO xp_logs (game_id, user_id, xp, channel_id, source) VALUES (%s, %s, %s, %s, %s)",
                    (game_id, user_id, xp, channel_id, source)
                )
            else:
                raise
    
    async def _check_and_update_level(self, user_id: int, current_level: int, new_xp: int) -> int:
        """
        Check if user should level up and update if necessary.
        
        Returns:
            New level (may be same as current_level if no level up)
        """
        levels_dict = self.level_data.get('LEVELS', {}) or self.level_data.get('levels', {})
        
        # Find the highest level the user qualifies for
        new_level = current_level
        for level_num in sorted([int(k) for k in levels_dict.keys()], reverse=True):
            required_xp = levels_dict.get(str(level_num), 0)
            if new_xp >= required_xp:
                new_level = level_num
                break
        
        # Update level if it changed
        if new_level > current_level:
            db = await self.db
            await db.execute(
                "UPDATE leveling SET level = %s WHERE user_id = %s",
                (new_level, str(user_id))
            )
        
        return new_level
    
    async def _handle_level_up(
        self,
        user: discord.User,
        new_level: int,
        channel: Optional[Union[discord.TextChannel, discord.DMChannel]],
        bot: Optional[discord.Client]
    ):
        """Handle level up announcements and achievements"""
        # Check for level achievements
        if channel:
            from utils.achievements import check_level_achievement
            await check_level_achievement(user, new_level, channel, bot)
        
        # Send level up announcement
        if bot:
            # Always try to send to the designated announce channel first
            LEVEL_UP_CHANNEL_ID = 1456658225964388504
            guild = bot.get_guild(self.config.get('config', 'GUILD_ID'))
            
            if guild:
                announce_channel = guild.get_channel(LEVEL_UP_CHANNEL_ID)
                if announce_channel:
                    try:
                        await announce_channel.send(f'{user.mention} has leveled up to level **{new_level}**!')
                        return  # Successfully sent to announce channel
                    except Exception as e:
                        self.logger.error(f"Error sending level up message to announce channel: {e}")
                        # Fall through to DM fallback
            
            # Fallback to DMs if announce channel failed or doesn't exist
            try:
                dm_channel = await user.create_dm()
                await dm_channel.send(f'{user.mention} has leveled up to level **{new_level}**!')
            except Exception as e:
                self.logger.error(f"Error sending level up DM: {e}")
    
    async def _check_achievements(
        self,
        user: discord.User,
        source: str,
        new_xp: int,
        channel: Optional[Union[discord.TextChannel, discord.DMChannel]],
        bot: Optional[discord.Client] = None
    ):
        """Check for various achievements"""
        if not channel:
            return
        
        from utils.achievements import check_chat_game_play, check_xp_achievement
        
        # Check chat game achievements
        await check_chat_game_play(user, source, channel, bot)
        
        # Check total XP achievements
        await check_xp_achievement(user, new_xp, channel, bot)
    
    async def _log_to_admin_channel(
        self,
        user: discord.User,
        xp: int,
        source: str,
        bot: Optional[discord.Client]
    ):
        """Log XP award to admin logs channel"""
        if not bot:
            return
        
        guild = bot.get_guild(self.config.get('config', 'GUILD_ID'))
        if not guild:
            return
        
        channel = guild.get_channel(self.config.get('config', 'ADMIN_LOGS'))
        if not channel:
            return
        
        embed = discord.Embed(
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            title="Experience Added",
            description=(
                f"`Source` {source}\n"
                f"`User` {user.mention} ({user.name})\n"
                f"`XP` {xp}"
            ),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(
            text=self.config.get('config', 'FOOTER'),
            icon_url=get_embed_logo_url(self.config.get('config', 'LOGO'))
        )
        
        try:
            await channel.send(embed=embed)
        except Exception as e:
            self.logger.error(f"Failed to log XP to admin channel: {e}")
    
    def _log_xp_award(
        self,
        user: discord.User,
        xp: int,
        source: str,
        channel: Optional[Union[discord.TextChannel, discord.DMChannel]]
    ):
        """Log XP award to console"""
        if channel:
            if hasattr(channel, 'name'):
                channel_info = f"{channel.name} / {channel.id}"
            elif hasattr(channel, 'recipient'):
                channel_info = f"{channel.recipient} / {channel.id}"
            else:
                channel_info = str(channel.id)
        else:
            channel_info = "Unknown"
        
        self.logger.info(f"+{xp}xp | {user.name} / {user.id} | {source} | {channel_info}")
    
    def _log_test_mode(
        self,
        user: discord.User,
        xp: int,
        source: str,
        channel: Optional[Union[discord.TextChannel, discord.DMChannel]]
    ):
        """Log test mode XP award"""
        if channel:
            if hasattr(channel, 'name'):
                channel_info = f"{channel.name} / {channel.id}"
            elif hasattr(channel, 'recipient'):
                channel_info = f"{channel.recipient} / {channel.id}"
            else:
                channel_info = str(channel.id)
        else:
            channel_info = "Unknown"
        
        self.logger.info(f"[TEST MODE] Would have earned +{xp}xp | {user.name} / {user.id} | {source} | {channel_info}")
    
    # Public API methods for utility
    
    async def get_user_level(self, user_id: int) -> int:
        """Get a user's current level"""
        stats = await self._get_user_stats(user_id)
        if stats:
            return int(stats.get('level', 0))
        return 0
    
    async def get_user_xp(self, user_id: int) -> int:
        """Get a user's current XP"""
        stats = await self._get_user_stats(user_id)
        if stats:
            return int(stats.get('xp', 0))
        return 0
    
    async def calculate_level_from_xp(self, xp: int) -> int:
        """Calculate what level a user should be based on their XP"""
        levels_dict = self.level_data.get('LEVELS', {}) or self.level_data.get('levels', {})
        
        if not levels_dict:
            return 0
        
        # Find the highest level the user has enough XP for
        level = 0
        for level_num in sorted([int(k) for k in levels_dict.keys()], reverse=True):
            required_xp = levels_dict.get(str(level_num), 0)
            if xp >= required_xp:
                level = level_num
                break
        
        return level
    
    async def update_user_level(self, user_id: int, xp: int) -> int:
        """
        Update user's level based on their XP.
        Useful for commands like /add-xp that need to recalculate level.
        
        Returns:
            The new level
        """
        new_level = await self.calculate_level_from_xp(xp)
        db = await self.db
        await db.execute(
            "UPDATE leveling SET level = %s WHERE user_id = %s",
            (new_level, str(user_id))
        )
        return new_level


# Wrapper class for backward compatibility with old API
class _LevelingManagerInstance:
    """
    Instance wrapper for backward compatibility with old API.
    This allows the old pattern to work:
        manager = LevelingManager(user, channel, client, xp, source, game_id)
        await manager.update()
    """
    def __init__(
        self,
        user: discord.Member,
        channel: Union[discord.TextChannel, discord.DMChannel],
        client: discord.Client,
        xp: int,
        source: str,
        game_id: int,
        test_mode: bool = False
    ):
        self.user = user
        self.channel = channel
        self.client = client
        self.xp = xp
        self.source = source
        self.game_id = game_id
        self.test_mode = test_mode
        self._manager = _LevelingManagerCore()
        self.stats: Optional[Dict[str, str]] = None
    
    async def update(self):
        """Legacy update method - calls the new award_xp method"""
        await self._manager.award_xp(
            user=self.user,
            xp=self.xp,
            source=self.source,
            game_id=self.game_id,
            channel=self.channel,
            bot=self.client,
            test_mode=self.test_mode
        )
    
    async def get_stats(self) -> Optional[Dict[str, str]]:
        """Legacy get_stats method"""
        self.stats = await self._manager._get_user_stats(self.user.id)
        if not self.stats:
            self.stats = await self._manager._create_user_entry(self.user.id)
        return self.stats
    
    async def add_experience(self):
        """Legacy method - now handled in award_xp"""
        # This is now part of award_xp, but kept for compatibility
        pass
    
    async def check_level_up(self):
        """Legacy method - now handled in award_xp"""
        # This is now part of award_xp, but kept for compatibility
        pass


# Main LevelingManager class that supports both old and new API
class LevelingManager:
    """
    LevelingManager - supports both old and new API.
    
    Old API (backward compatible):
        manager = LevelingManager(user, channel, client, xp, source, game_id, test_mode)
        await manager.update()
    
    New API (recommended):
        manager = LevelingManager()
        await manager.award_xp(user, xp, source, game_id, channel=channel, bot=client, test_mode=test_mode)
    """
    _singleton_instance = None
    
    def __new__(cls, user=None, channel=None, client=None, xp=None, source=None, game_id=None, test_mode=False):
        if user is not None:
            # Old API - return instance wrapper
            return _LevelingManagerInstance(user, channel, client, xp, source, game_id, test_mode)
        else:
            # New API - return singleton
            if cls._singleton_instance is None:
                cls._singleton_instance = _LevelingManagerCore()
            return cls._singleton_instance
    
    def __init__(self, user=None, channel=None, client=None, xp=None, source=None, game_id=None, test_mode=False):
        """Initialize - only called for singleton (new API)"""
        if user is not None:
            # Old API - don't initialize here, handled by _LevelingManagerInstance
            return
        
        # New API - initialization handled by _LevelingManagerCore
        pass
