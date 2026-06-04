from discord.ext import commands
from discord import app_commands
import discord
from core.database.pool import DatabasePool
from core.config.manager import ConfigManager
from core.logging.setup import get_logger
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from ui.paginator import Paginator
from ui.views.logs_view import LogsView
from ui.views.logs_filter_select_view import LogsFilterSelect
from ui.views.logs_paginator_view import LogsPaginator

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
        
        logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
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
        
        logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
