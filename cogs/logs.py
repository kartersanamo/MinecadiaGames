from discord.ext import commands
from discord import app_commands
import discord
from core.database.pool import DatabasePool
from core.config.manager import ConfigManager
from core.logging.setup import get_logger
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from utils.paginator import Paginator


class Logs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Commands")
    
    def _check_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user has admin permissions"""
        if not interaction.guild:
            return False
        
        admin_roles = self.config.get('config', 'ADMIN_ROLES', [])
        user_roles = [role.name for role in interaction.user.roles]
        
        if "*" in admin_roles:
            return True
        
        return any(role in admin_roles for role in user_roles)
    
    @app_commands.command(name="logs", description="View detailed logs of all system activity")
    @app_commands.describe(
        filter_type="Type of filter to apply",
        filter_value="Value to filter by (user mention, game ID, etc.)",
        log_type="Type of logs to view",
        time_range="Time range for logs"
    )
    @app_commands.choices(
        filter_type=[
            app_commands.Choice(name="No Filter", value="none"),
            app_commands.Choice(name="By User", value="user"),
            app_commands.Choice(name="By Game ID", value="game_id"),
            app_commands.Choice(name="By Game Type", value="game_type"),
            app_commands.Choice(name="By Source", value="source"),
        ],
        log_type=[
            app_commands.Choice(name="All Logs", value="all"),
            app_commands.Choice(name="XP Logs Only", value="xp"),
            app_commands.Choice(name="Game Logs Only", value="games"),
            app_commands.Choice(name="Suspicious Logs", value="suspicious"),
        ],
        time_range=[
            app_commands.Choice(name="Last Hour", value="1h"),
            app_commands.Choice(name="Last 6 Hours", value="6h"),
            app_commands.Choice(name="Last 24 Hours", value="24h"),
            app_commands.Choice(name="Last 7 Days", value="7d"),
            app_commands.Choice(name="Last 30 Days", value="30d"),
            app_commands.Choice(name="All Time", value="all"),
        ]
    )
    async def logs(
        self,
        interaction: discord.Interaction,
        log_type: app_commands.Choice[str] = None,
        filter_type: app_commands.Choice[str] = None,
        filter_value: str = None,
        time_range: app_commands.Choice[str] = None
    ):
        if not self._check_admin(interaction):
            await interaction.response.send_message("`❌` You don't have permission to use this command.", ephemeral=True)
            return
        
        if interaction.guild is None:
            await interaction.response.send_message("Commands cannot be run in DMs!", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Parse choices
        log_type_val = log_type.value if log_type else "all"
        filter_type_val = filter_type.value if filter_type else "none"
        time_range_val = time_range.value if time_range else "24h"
        
        # Parse filter value
        user_id = None
        game_id = None
        game_type = None
        source = None
        
        if filter_type_val == "user" and filter_value:
            # Extract user ID from mention or try to parse as ID
            try:
                if filter_value.startswith("<@") and filter_value.endswith(">"):
                    user_id = int(filter_value[2:-1])
                else:
                    user_id = int(filter_value)
            except ValueError:
                await interaction.followup.send("`❌` Invalid user format. Use a mention or user ID.", ephemeral=True)
                return
        elif filter_type_val == "game_id" and filter_value:
            try:
                game_id = int(filter_value)
            except ValueError:
                await interaction.followup.send("`❌` Invalid game ID. Must be a number.", ephemeral=True)
                return
        elif filter_type_val == "game_type" and filter_value:
            game_type = filter_value
        elif filter_type_val == "source" and filter_value:
            source = filter_value
        
        # Create view
        view = LogsView(
            self.bot,
            self.config,
            log_type=log_type_val,
            filter_type=filter_type_val,
            user_id=user_id,
            game_id=game_id,
            game_type=game_type,
            source=source,
            time_range=time_range_val
        )
        
        # Get initial logs
        logs_data = await view.get_logs()
        
        if not logs_data:
            await interaction.followup.send("No logs found matching your criteria.", ephemeral=True)
            return
        
        # Create paginator with action buttons
        paginator = LogsPaginator(view, logs_data, log_type_val, game_id, user_id, self)
        
        await paginator.send(interaction)
    
    async def _show_game_details(self, interaction: discord.Interaction, game_id: int):
        """Show detailed information about a specific game"""
        await interaction.response.defer(ephemeral=True)
        
        db = await DatabasePool.get_instance()
        
        # Get game info
        game_info = await db.execute(
            "SELECT game_name, refreshed_at, dm_game FROM games WHERE game_id = %s",
            (game_id,)
        )
        
        if not game_info:
            await interaction.followup.send(f"Game #{game_id} not found.", ephemeral=True)
            return
        
        game = game_info[0]
        game_name = game['game_name']
        is_dm_game = game.get('dm_game', False)
        
        embed = discord.Embed(
            title=f"🎮 Game #{game_id} - {game_name}",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.fromtimestamp(game['refreshed_at'], tz=timezone.utc)
        )
        
        embed.add_field(
            name="Game Info",
            value=(
                f"**Type:** {'DM Game' if is_dm_game else 'Chat Game'}\n"
                f"**Created:** <t:{game['refreshed_at']}:F>\n"
                f"**Created:** <t:{game['refreshed_at']}:R>"
            ),
            inline=False
        )
        
        # Get all XP logs for this game
        xp_logs = await db.execute(
            """
            SELECT user_id, xp, source, COALESCE(xl.timestamp, g.refreshed_at) as timestamp
            FROM xp_logs xl
            LEFT JOIN games g ON xl.game_id = g.game_id
            WHERE xl.game_id = %s
            ORDER BY COALESCE(xl.timestamp, g.refreshed_at) DESC
            LIMIT 50
            """,
            (game_id,)
        )
        
        if xp_logs:
            total_xp = sum(log['xp'] for log in xp_logs)
            unique_users = len(set(log['user_id'] for log in xp_logs))
            
            embed.add_field(
                name="XP Statistics",
                value=(
                    f"**Total XP Awarded:** {total_xp:,}\n"
                    f"**Unique Players:** {unique_users}\n"
                    f"**Total Awards:** {len(xp_logs)}"
                ),
                inline=False
            )
            
            # Top 10 players
            user_xp = {}
            for log in xp_logs:
                user_id = int(log['user_id'])
                user_xp[user_id] = user_xp.get(user_id, 0) + log['xp']
            
            top_players = sorted(user_xp.items(), key=lambda x: x[1], reverse=True)[:10]
            top_players_text = "\n".join([
                f"{i+1}. <@{user_id}> - {xp:,} XP"
                for i, (user_id, xp) in enumerate(top_players)
            ])
            
            embed.add_field(
                name="Top Players",
                value=top_players_text or "No players",
                inline=False
            )
        
        # Get game-specific data for DM games
        if is_dm_game:
            game_name_lower = game_name.lower().replace(" ", "")
            table_name = f"users_{game_name_lower}"
            
            try:
                game_data = await db.execute(
                    f"""
                    SELECT user_id, status, score, started_at, ended_at
                    FROM {table_name}
                    WHERE game_id = %s
                    ORDER BY started_at DESC
                    LIMIT 20
                    """,
                    (game_id,)
                )
                
                if game_data:
                    status_counts = {}
                    for data in game_data:
                        status = data.get('status', 'Unknown')
                        status_counts[status] = status_counts.get(status, 0) + 1
                    
                    status_text = "\n".join([
                        f"**{status}:** {count}"
                        for status, count in status_counts.items()
                    ])
                    
                    embed.add_field(
                        name="Game Statuses",
                        value=status_text or "No data",
                        inline=True
                    )
            except Exception as e:
                self.logger.error(f"Error fetching game data from {table_name}: {e}")
        
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def _show_user_details(self, interaction: discord.Interaction, user_id: int):
        """Show detailed information about a specific user"""
        await interaction.response.defer(ephemeral=True)
        
        user = self.bot.get_user(user_id)
        if not user:
            try:
                user = await self.bot.fetch_user(user_id)
            except:
                await interaction.followup.send(f"User {user_id} not found.", ephemeral=True)
                return
        
        db = await DatabasePool.get_instance()
        
        embed = discord.Embed(
            title=f"👤 User Logs - {user.display_name}",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        
        # Get user's leveling stats
        leveling = await db.execute(
            "SELECT xp, level FROM leveling WHERE user_id = %s",
            (str(user_id),)
        )
        
        if leveling:
            embed.add_field(
                name="Current Stats",
                value=(
                    f"**Level:** {leveling[0]['level']}\n"
                    f"**Total XP:** {int(leveling[0]['xp']):,}"
                ),
                inline=False
            )
        
        # Get XP summary
        xp_summary = await db.execute(
            """
            SELECT 
                source,
                COUNT(*) as count,
                SUM(xp) as total_xp,
                AVG(xp) as avg_xp,
                MAX(xp) as max_xp
            FROM xp_logs
            WHERE user_id = %s
            GROUP BY source
            ORDER BY total_xp DESC
            LIMIT 10
            """,
            (str(user_id),)
        )
        
        if xp_summary:
            summary_text = "\n".join([
                f"**{row['source']}:** {int(row['total_xp']):,} XP ({row['count']} times, avg: {int(row['avg_xp']):.1f})"
                for row in xp_summary
            ])
            embed.add_field(
                name="XP by Source",
                value=summary_text,
                inline=False
            )
        
        # Get recent game activity
        recent_games = await db.execute(
            """
            SELECT game_name, COUNT(*) as games_played
            FROM games g
            INNER JOIN xp_logs xl ON g.game_id = xl.game_id
            WHERE xl.user_id = %s
            GROUP BY game_name
            ORDER BY games_played DESC
            LIMIT 10
            """,
            (str(user_id),)
        )
        
        if recent_games:
            games_text = "\n".join([
                f"**{row['game_name']}:** {row['games_played']} games"
                for row in recent_games
            ])
            embed.add_field(
                name="Game Activity",
                value=games_text,
                inline=False
            )
        
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        
        await interaction.followup.send(embed=embed, ephemeral=True)


class LogsView(discord.ui.View):
    def __init__(
        self,
        bot,
        config,
        log_type: str = "all",
        filter_type: str = "none",
        user_id: Optional[int] = None,
        game_id: Optional[int] = None,
        game_type: Optional[str] = None,
        source: Optional[str] = None,
        time_range: str = "24h"
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.config = config
        self.logger = get_logger("Commands")
        self.log_type = log_type
        self.filter_type = filter_type
        self.user_id = user_id
        self.game_id = game_id
        self.game_type = game_type
        self.source = source
        self.time_range = time_range
        
        # Add filter select menu
        self.add_item(LogsFilterSelect(self))
    
    def _get_time_filter(self) -> Optional[int]:
        """Get timestamp for time range filter"""
        from datetime import datetime, timedelta, timezone
        
        now = datetime.now(timezone.utc)
        
        if self.time_range == "1h":
            return int((now - timedelta(hours=1)).timestamp())
        elif self.time_range == "6h":
            return int((now - timedelta(hours=6)).timestamp())
        elif self.time_range == "24h":
            return int((now - timedelta(hours=24)).timestamp())
        elif self.time_range == "7d":
            return int((now - timedelta(days=7)).timestamp())
        elif self.time_range == "30d":
            return int((now - timedelta(days=30)).timestamp())
        else:
            return None
    
    async def get_logs(self) -> List[Dict[str, Any]]:
        """Get logs based on current filters"""
        try:
            db = await DatabasePool.get_instance()
            logs = []
            time_filter = self._get_time_filter()
            
            if self.log_type == "suspicious":
                return await self._get_suspicious_logs(time_filter)
            
            # Get XP logs
            if self.log_type in ["all", "xp"]:
                try:
                    xp_logs = await self._get_xp_logs(db, time_filter)
                    logs.extend(xp_logs)
                except Exception as e:
                    self.logger.error(f"Error getting XP logs: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
            
            # Get game logs (DM game player entries)
            if self.log_type in ["all", "games"]:
                try:
                    game_logs = await self._get_game_logs(db, time_filter)
                    logs.extend(game_logs)
                except Exception as e:
                    self.logger.error(f"Error getting game logs: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
                
                # Also get chat game creation events (for "Game Logs Only")
                if self.log_type == "games":
                    try:
                        chat_game_events = await self._get_chat_game_events(db, time_filter)
                        logs.extend(chat_game_events)
                    except Exception as e:
                        self.logger.error(f"Error getting chat game events: {e}")
                        import traceback
                        self.logger.error(traceback.format_exc())
            
            # Get game creation/refresh events (for "All Logs" only)
            if self.log_type == "all":
                try:
                    game_events = await self._get_game_events(db, time_filter)
                    logs.extend(game_events)
                except Exception as e:
                    self.logger.error(f"Error getting game events: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
            
            # Sort by timestamp (newest first) and limit to 500 total
            # Handle both string and int timestamps
            def get_timestamp(log):
                ts = log.get('timestamp', 0)
                if isinstance(ts, str):
                    try:
                        return int(ts)
                    except (ValueError, TypeError):
                        return 0
                return int(ts) if ts else 0
            
            logs.sort(key=get_timestamp, reverse=True)
            logs = logs[:500]  # Limit to 500 logs to prevent timeout
            
            return logs
        except Exception as e:
            self.logger.error(f"Error in get_logs: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []
    
    async def _get_xp_logs(self, db: DatabasePool, time_filter: Optional[int]) -> List[Dict[str, Any]]:
        """Get XP logs with filters"""
        query = """
            SELECT 
                xl.game_id,
                xl.user_id,
                xl.xp,
                xl.channel_id,
                xl.source,
                COALESCE(xl.timestamp, g.refreshed_at) as timestamp,
                g.game_name,
                g.dm_game
            FROM xp_logs xl
            LEFT JOIN games g ON xl.game_id = g.game_id
            WHERE 1=1
        """
        params = []
        
        if self.user_id:
            query += " AND xl.user_id = %s"
            params.append(str(self.user_id))
        
        if self.game_id:
            query += " AND xl.game_id = %s"
            params.append(self.game_id)
        
        if self.source:
            query += " AND xl.source = %s"
            params.append(self.source)
        
        if time_filter:
            query += " AND COALESCE(xl.timestamp, g.refreshed_at) >= %s"
            params.append(time_filter)
        
        query += " ORDER BY COALESCE(xl.timestamp, g.refreshed_at) DESC LIMIT 500"
        
        rows = await db.execute(query, tuple(params) if params else None)
        
        logs = []
        for row in rows:
            logs.append({
                'type': 'xp',
                'game_id': row['game_id'],
                'user_id': int(row['user_id']),
                'xp': row['xp'],
                'channel_id': row['channel_id'],
                'source': row['source'],
                'timestamp': row['timestamp'],
                'game_name': row.get('game_name'),
                'dm_game': row.get('dm_game', False)
            })
        
        return logs
    
    async def _get_game_logs(self, db: DatabasePool, time_filter: Optional[int]) -> List[Dict[str, Any]]:
        """Get game logs from DM game tables"""
        dm_game_tables = {
            'tictactoe': 'users_tictactoe',
            'wordle': 'users_wordle',
            'connectfour': 'users_connectfour',
            'memory': 'users_memory',
            '2048': 'users_2048',
            'minesweeper': 'users_minesweeper',
            'hangman': 'users_hangman'
        }
        
        all_logs = []
        
        # Limit to 100 per table to avoid timeout
        limit_per_table = 100
        
        for game_name, table_name in dm_game_tables.items():
            # Skip if filtering by game type and it doesn't match
            if self.game_type and game_name.lower() != self.game_type.lower():
                continue
            
            # Build query with proper field selection based on table structure
            # Each table has different columns, so we need to handle them separately
            if game_name == 'connectfour':
                query = f"""
                    SELECT 
                        u.game_id,
                        u.user_id,
                        u.status,
                        NULL as score,
                        u.started_at,
                        u.ended_at,
                        u.moves,
                        NULL as highest_tile,
                        g.game_name,
                        g.refreshed_at,
                        g.dm_game
                """
            elif game_name == 'memory':
                query = f"""
                    SELECT 
                        u.game_id,
                        u.user_id,
                        u.won as status,
                        NULL as score,
                        u.started_at,
                        u.ended_at,
                        u.attempts as moves,
                        NULL as highest_tile,
                        g.game_name,
                        g.refreshed_at,
                        g.dm_game
                """
            elif game_name == '2048':
                query = f"""
                    SELECT 
                        u.game_id,
                        u.user_id,
                        u.status,
                        u.score,
                        u.started_at,
                        u.ended_at,
                        u.moves,
                        u.highest_tile,
                        g.game_name,
                        g.refreshed_at,
                        g.dm_game
                """
            elif game_name == 'wordle':
                query = f"""
                    SELECT 
                        u.game_id,
                        u.user_id,
                        u.won as status,
                        NULL as score,
                        u.started_at,
                        u.ended_at,
                        u.attempts as moves,
                        NULL as highest_tile,
                        g.game_name,
                        g.refreshed_at,
                        g.dm_game
                """
            elif game_name == 'minesweeper':
                query = f"""
                    SELECT 
                        u.game_id,
                        u.user_id,
                        u.won as status,
                        NULL as score,
                        u.started_at,
                        u.ended_at,
                        u.cells_revealed as moves,
                        NULL as highest_tile,
                        g.game_name,
                        g.refreshed_at,
                        g.dm_game
                """
            else:  # tictactoe
                query = f"""
                    SELECT 
                        u.game_id,
                        u.user_id,
                        u.won as status,
                        NULL as score,
                        u.started_at,
                        u.ended_at,
                        NULL as moves,
                        NULL as highest_tile,
                        g.game_name,
                        g.refreshed_at,
                        g.dm_game
                """
            
            # Complete the query
            query += f"""
                FROM {table_name} u
                INNER JOIN games g ON u.game_id = g.game_id
                WHERE 1=1
            """
            params = []
            
            if self.user_id:
                query += " AND u.user_id = %s"
                params.append(str(self.user_id))
            
            if self.game_id:
                query += " AND u.game_id = %s"
                params.append(self.game_id)
            
            if time_filter:
                query += " AND u.started_at >= %s"
                params.append(time_filter)
            
            query += f" ORDER BY u.started_at DESC LIMIT {limit_per_table}"
            
            try:
                rows = await db.execute(query, tuple(params) if params else None)
                
                for row in rows:
                    # Get additional game-specific fields
                    moves = row.get('moves')
                    highest_tile = row.get('highest_tile')
                    
                    all_logs.append({
                        'type': 'game',
                        'game_id': row['game_id'],
                        'user_id': int(row['user_id']),
                        'game_name': game_name.title(),
                        'status': row['status'],
                        'score': row.get('score'),
                        'moves': moves,
                        'highest_tile': highest_tile,
                        'started_at': row['started_at'],
                        'ended_at': row.get('ended_at', 0),
                        'timestamp': row['started_at'],
                        'dm_game': True
                    })
            except Exception as e:
                self.logger.error(f"Error fetching logs from {table_name}: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
                continue
        
        return all_logs
    
    async def _get_game_events(self, db: DatabasePool, time_filter: Optional[int]) -> List[Dict[str, Any]]:
        """Get game creation/refresh events from games table"""
        query = """
            SELECT 
                game_id,
                game_name,
                refreshed_at,
                dm_game
            FROM games
            WHERE 1=1
        """
        params = []
        
        if time_filter:
            query += " AND refreshed_at >= %s"
            params.append(time_filter)
        
        query += " ORDER BY refreshed_at DESC LIMIT 200"
        
        rows = await db.execute(query, tuple(params) if params else None)
        
        events = []
        for row in rows:
            event_type = "DM Game Refreshed" if row['dm_game'] else "Chat Game Started"
            events.append({
                'type': 'game_event',
                'game_id': row['game_id'],
                'game_name': row['game_name'],
                'event_type': event_type,
                'timestamp': row['refreshed_at'],
                'dm_game': row['dm_game']
            })
        
        return events
    
    async def _get_chat_game_events(self, db: DatabasePool, time_filter: Optional[int]) -> List[Dict[str, Any]]:
        """Get chat game creation events for Game Logs Only"""
        query = """
            SELECT 
                game_id,
                game_name,
                refreshed_at,
                dm_game
            FROM games
            WHERE dm_game = FALSE
        """
        params = []
        
        if time_filter:
            query += " AND refreshed_at >= %s"
            params.append(time_filter)
        
        query += " ORDER BY refreshed_at DESC LIMIT 200"
        
        rows = await db.execute(query, tuple(params) if params else None)
        
        events = []
        for row in rows:
            events.append({
                'type': 'game',
                'game_id': row['game_id'],
                'game_name': row['game_name'],
                'status': 'Started',
                'score': None,
                'moves': None,
                'highest_tile': None,
                'started_at': row['refreshed_at'],
                'ended_at': 0,
                'timestamp': row['refreshed_at'],
                'dm_game': False,
                'user_id': None  # Chat games don't have a single user
            })
        
        return events
    
    async def _get_suspicious_logs(self, time_filter: Optional[int]) -> List[Dict[str, Any]]:
        """Detect suspicious activity patterns"""
        db = await DatabasePool.get_instance()
        suspicious = []
        
        # 1. Large XP gains in short time
        query = """
            SELECT 
                user_id,
                SUM(xp) as total_xp,
                COUNT(*) as count,
                MIN(COALESCE(xl.timestamp, g.refreshed_at)) as first_time,
                MAX(COALESCE(xl.timestamp, g.refreshed_at)) as last_time,
                MAX(COALESCE(xl.timestamp, g.refreshed_at)) - MIN(COALESCE(xl.timestamp, g.refreshed_at)) as time_span
            FROM xp_logs xl
            LEFT JOIN games g ON xl.game_id = g.game_id
            WHERE 1=1
        """
        params = []
        
        if time_filter:
            query += " AND COALESCE(xl.timestamp, g.refreshed_at) >= %s"
            params.append(time_filter)
        
        query += """
            GROUP BY user_id
            HAVING total_xp > 500 AND time_span < 3600 AND count > 10
            ORDER BY total_xp DESC
            LIMIT 50
        """
        
        rows = await db.execute(query, tuple(params) if params else None)
        
        for row in rows:
            suspicious.append({
                'type': 'suspicious',
                'reason': 'large_xp_short_time',
                'user_id': int(row['user_id']),
                'total_xp': row['total_xp'],
                'count': row['count'],
                'time_span': row['time_span'],
                'timestamp': row['last_time']
            })
        
        # 2. Large single XP gains
        query2 = """
            SELECT 
                xl.game_id,
                xl.user_id,
                xl.xp,
                xl.source,
                COALESCE(xl.timestamp, g.refreshed_at) as timestamp,
                g.game_name
            FROM xp_logs xl
            LEFT JOIN games g ON xl.game_id = g.game_id
            WHERE xl.xp > 100
        """
        params2 = []
        
        if time_filter:
            query2 += " AND COALESCE(xl.timestamp, g.refreshed_at) >= %s"
            params2.append(time_filter)
        
        query2 += " ORDER BY xl.xp DESC LIMIT 50"
        
        rows2 = await db.execute(query2, tuple(params2) if params2 else None)
        
        for row in rows2:
            suspicious.append({
                'type': 'suspicious',
                'reason': 'large_single_xp',
                'game_id': row['game_id'],
                'user_id': int(row['user_id']),
                'xp': row['xp'],
                'source': row['source'],
                'game_name': row.get('game_name'),
                'timestamp': row['timestamp']
            })
        
        # 3. Unusual patterns (same user, same game, many wins quickly)
        query3 = """
            SELECT 
                xl.user_id,
                xl.source,
                COUNT(*) as count,
                SUM(xl.xp) as total_xp,
                MAX(COALESCE(xl.timestamp, g.refreshed_at)) as last_time
            FROM xp_logs xl
            LEFT JOIN games g ON xl.game_id = g.game_id
            WHERE 1=1
        """
        params3 = []
        
        if time_filter:
            query3 += " AND COALESCE(xl.timestamp, g.refreshed_at) >= %s"
            params3.append(time_filter)
        
        query3 += """
            GROUP BY xl.user_id, xl.source
            HAVING count > 20 AND total_xp > 300
            ORDER BY count DESC
            LIMIT 30
        """
        
        rows3 = await db.execute(query3, tuple(params3) if params3 else None)
        
        for row in rows3:
            suspicious.append({
                'type': 'suspicious',
                'reason': 'unusual_pattern',
                'user_id': int(row['user_id']),
                'source': row['source'],
                'count': row['count'],
                'total_xp': row['total_xp'],
                'timestamp': row['last_time']
            })
        
        # Sort by timestamp
        suspicious.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        
        return suspicious


class LogsFilterSelect(discord.ui.Select):
    def __init__(self, parent_view: LogsView):
        self.parent_view = parent_view
        
        options = [
            discord.SelectOption(
                label="Change Filter Type",
                value="filter_type",
                description="Change what to filter by",
                emoji="🔍"
            ),
            discord.SelectOption(
                label="Change Log Type",
                value="log_type",
                description="Change type of logs to view",
                emoji="📋"
            ),
            discord.SelectOption(
                label="Change Time Range",
                value="time_range",
                description="Change time range for logs",
                emoji="⏰"
            ),
            discord.SelectOption(
                label="View Suspicious Logs",
                value="suspicious",
                description="View detected suspicious activity",
                emoji="⚠️"
            )
        ]
        
        super().__init__(
            placeholder="Filter Options...",
            options=options,
            custom_id="logs_filter_select",
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        
        if value == "suspicious":
            self.parent_view.log_type = "suspicious"
            await interaction.response.defer(ephemeral=True)
            logs = await self.parent_view.get_logs()
            if logs:
                paginator = LogsPaginator(self.parent_view, logs, "suspicious")
                await paginator.send(interaction)
            else:
                await interaction.followup.send("No suspicious logs found.", ephemeral=True)
        else:
            # For now, just show a message that these will be implemented
            await interaction.response.send_message(
                f"Filter options will be available in the next update. Current filter: {value}",
                ephemeral=True
            )


class LogsPaginator(Paginator):
    def __init__(self, parent_view: LogsView, logs_data: List[Dict], log_type: str, game_id: Optional[int] = None, user_id: Optional[int] = None, logs_cog = None):
        super().__init__(timeout=900)
        self.parent_view = parent_view
        self.logs_data = logs_data
        self.log_type = log_type
        self.game_id = game_id
        self.user_id = user_id
        self.logs_cog = logs_cog
        self.title = self._get_title()
        self.data = self._format_logs()
        self.sep = 10
        self.ephemeral = True
        
        # Add quick action buttons
        if game_id:
            view_button = discord.ui.Button(
                label=f"View Game #{game_id}",
                style=discord.ButtonStyle.blurple,
                emoji="🎮",
                custom_id=f"view_game_{game_id}",
                row=1
            )
            view_button.callback = self._create_game_callback(game_id)
            self.add_item(view_button)
        
        if user_id:
            view_user_button = discord.ui.Button(
                label="View User Details",
                style=discord.ButtonStyle.blurple,
                emoji="👤",
                custom_id=f"view_user_{user_id}",
                row=1
            )
            view_user_button.callback = self._create_user_callback(user_id)
            self.add_item(view_user_button)
    
    def _create_game_callback(self, game_id: int):
        async def callback(interaction: discord.Interaction):
            if self.logs_cog:
                await self.logs_cog._show_game_details(interaction, game_id)
        return callback
    
    def _create_user_callback(self, user_id: int):
        async def callback(interaction: discord.Interaction):
            if self.logs_cog:
                await self.logs_cog._show_user_details(interaction, user_id)
        return callback
    
    def _get_title(self) -> str:
        title = "📊 System Logs"
        if self.log_type == "suspicious":
            title = "⚠️ Suspicious Activity Logs"
        elif self.log_type == "xp":
            title = "💰 XP Logs"
        elif self.log_type == "games":
            title = "🎮 Game Logs"
        
        return title
    
    def _format_logs(self) -> List[str]:
        """Format logs for display"""
        formatted = []
        
        for log in self.logs_data:
            if log['type'] == 'xp':
                formatted.append(self._format_xp_log(log))
            elif log['type'] == 'game':
                formatted.append(self._format_game_log(log))
            elif log['type'] == 'game_event':
                formatted.append(self._format_game_event_log(log))
            elif log['type'] == 'suspicious':
                formatted.append(self._format_suspicious_log(log))
            
            # Add spacing between logs (empty line)
            formatted.append("")
        
        # Remove last empty line if exists
        if formatted and formatted[-1] == "":
            formatted.pop()
        
        return formatted
    
    def _format_xp_log(self, log: Dict) -> str:
        """Format an XP log entry"""
        user = self.parent_view.bot.get_user(log['user_id'])
        user_name = user.mention if user else f"<@{log['user_id']}>"
        
        timestamp = log.get('timestamp', 0)
        time_str = f"<t:{timestamp}:R>" if timestamp else "Unknown"
        
        game_info = ""
        if log.get('game_id'):
            game_info = f" | Game #{log['game_id']}"
            if log.get('game_name'):
                game_info += f" ({log['game_name']})"
        
        source = log.get('source', 'Unknown')
        
        return (
            f"**💰 XP Award**\n"
            f"User: {user_name}\n"
            f"XP: `{log['xp']}`\n"
            f"Source: `{source}`{game_info}\n"
            f"Time: {time_str}"
        )
    
    def _format_game_log(self, log: Dict) -> str:
        """Format a game log entry"""
        timestamp = log.get('timestamp', 0)
        time_str = f"<t:{timestamp}:R>" if timestamp else "Unknown"
        
        # Handle chat games (no user_id)
        if log.get('user_id') is None:
            status = log.get('status', 'Started')
            status_emoji = {
                'Finished': '✅',
                'Started': '🟡'
            }.get(status, '❓')
            game_info = f"**🎮 {log.get('game_name', 'Game')} #{log['game_id']}**\n"
            game_info += f"Type: `Chat Game`\n"
            game_info += f"Status: {status_emoji} `{status}`\n"
            game_info += f"Started: {time_str}"
            return game_info
        
        # Handle DM games (with user_id)
        user = self.parent_view.bot.get_user(log['user_id'])
        user_name = user.mention if user else f"<@{log['user_id']}>"
        
        status_emoji = {
            'Won': '✅',
            'Lost': '❌',
            'Started': '🟡',
            'Cashed Out': '💰'
        }.get(log.get('status', ''), '❓')
        
        game_info = f"**🎮 {log.get('game_name', 'Game')} #{log['game_id']}**\n"
        game_info += f"User: {user_name}\n"
        game_info += f"Status: {status_emoji} `{log.get('status', 'Unknown')}`\n"
        
        if log.get('score') is not None:
            game_info += f"Score: `{log['score']}`\n"
        if log.get('moves') is not None:
            game_info += f"Moves: `{log['moves']}`\n"
        if log.get('highest_tile') is not None:
            game_info += f"Highest Tile: `{log['highest_tile']}`\n"
        
        if log.get('ended_at', 0) > 0:
            duration = log['ended_at'] - log.get('started_at', 0)
            game_info += f"Duration: `{duration}s`\n"
        
        game_info += f"Started: {time_str}"
        
        return game_info
    
    def _format_game_event_log(self, log: Dict) -> str:
        """Format a game creation/refresh event log"""
        timestamp = log.get('timestamp', 0)
        time_str = f"<t:{timestamp}:R>" if timestamp else "Unknown"
        
        event_type = log.get('event_type', 'Game Event')
        game_name = log.get('game_name', 'Game')
        game_id = log.get('game_id', 0)
        is_dm = log.get('dm_game', False)
        
        emoji = "🔄" if is_dm else "▶️"
        
        event_info = f"**{emoji} {event_type}**\n"
        event_info += f"Game: `{game_name} #{game_id}`\n"
        event_info += f"Type: `{'DM Game' if is_dm else 'Chat Game'}`\n"
        event_info += f"Time: {time_str}"
        
        return event_info
    
    def _format_suspicious_log(self, log: Dict) -> str:
        """Format a suspicious log entry"""
        user = self.parent_view.bot.get_user(log['user_id'])
        user_name = user.mention if user else f"<@{log['user_id']}>"
        
        timestamp = log.get('timestamp', 0)
        time_str = f"<t:{timestamp}:R>" if timestamp else "Unknown"
        
        reason = log.get('reason', 'unknown')
        reason_text = {
            'large_xp_short_time': 'Large XP gain in short time',
            'large_single_xp': 'Large single XP gain',
            'unusual_pattern': 'Unusual activity pattern'
        }.get(reason, reason)
        
        suspicious_info = f"**⚠️ Suspicious Activity**\n"
        suspicious_info += f"User: {user_name}\n"
        suspicious_info += f"Reason: `{reason_text}`\n"
        
        if 'total_xp' in log:
            suspicious_info += f"Total XP: `{log['total_xp']}`\n"
        if 'count' in log:
            suspicious_info += f"Count: `{log['count']}`\n"
        if 'time_span' in log:
            suspicious_info += f"Time Span: `{log['time_span']}s`\n"
        if 'xp' in log:
            suspicious_info += f"XP: `{log['xp']}`\n"
        if 'source' in log:
            suspicious_info += f"Source: `{log['source']}`\n"
        if 'game_id' in log:
            suspicious_info += f"Game ID: `{log['game_id']}`\n"
        
        suspicious_info += f"Time: {time_str}"
        
        return suspicious_info


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))

