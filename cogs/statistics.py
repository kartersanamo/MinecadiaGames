
from discord.ext import commands
from discord import app_commands
import discord
from core.database.pool import DatabasePool
from core.logging.setup import get_logger
from core.config.manager import ConfigManager
from datetime import datetime, timezone
from typing import Optional
from ui.views.statistics_view import StatisticsView

class Statistics(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Commands")
        self.GAMES_CHANNEL_ID = 1456658225964388504  # #games channel
    
    @app_commands.command(name="statistics", description="View your game statistics")
    @app_commands.describe(user="View another user's statistics (optional)")
    async def statistics(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        if interaction.guild is None:
            await interaction.response.send_message("`❌` This command can only be used in a server.", ephemeral=False)
            return
        
        # Check if in #games channel
        if interaction.channel.id != self.GAMES_CHANNEL_ID:
            await interaction.response.send_message(
                f"`❌` This command can only be used in <#{self.GAMES_CHANNEL_ID}>.",
                ephemeral=False
            )
            return
        
        try:
            target_user = user if user else interaction.user
            await interaction.response.defer(ephemeral=False)
            
            # Create main statistics view
            view = StatisticsView(self.bot, self.config, target_user.id)
            embed = await self._create_overview_embed(target_user)
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=False)
        except Exception as e:
            self.logger.error(f"Error in statistics command: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(f"`❌` An error occurred while fetching statistics. This might be because you have no game data yet. Error: {str(e)}", ephemeral=False)
                else:
                    await interaction.response.send_message(f"`❌` An error occurred while fetching statistics. This might be because you have no game data yet. Error: {str(e)}", ephemeral=False)
            except:
                pass
    
    async def _create_overview_embed(self, user: discord.Member) -> discord.Embed:
        """Create the overview statistics embed"""
        try:
            db = await DatabasePool.get_instance()
            
            # Get overall stats
            leveling_data = await db.execute(
                "SELECT level, xp FROM leveling WHERE user_id = %s",
                (str(user.id),)
            )
            
            level = int(leveling_data[0]['level']) if leveling_data and len(leveling_data) > 0 and leveling_data[0]['level'] else 0
            xp = int(leveling_data[0]['xp']) if leveling_data and len(leveling_data) > 0 and leveling_data[0]['xp'] else 0
            
            # Get total XP from logs
            xp_logs = await db.execute(
                "SELECT SUM(xp) as total_xp, COUNT(*) as total_games FROM xp_logs WHERE user_id = %s",
                (str(user.id),)
            )
            total_xp_from_games = int(xp_logs[0]['total_xp']) if xp_logs and len(xp_logs) > 0 and xp_logs[0]['total_xp'] else 0
            total_games_played = int(xp_logs[0]['total_games']) if xp_logs and len(xp_logs) > 0 and xp_logs[0]['total_games'] else 0
            
            # Count games by type
            games_by_type = await db.execute(
                "SELECT source, COUNT(*) as count, SUM(xp) as total_xp FROM xp_logs WHERE user_id = %s GROUP BY source",
                (str(user.id),)
            )
        except Exception as e:
            self.logger.error(f"Error fetching statistics data: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            # Return default values
            level = 0
            xp = 0
            total_xp_from_games = 0
            total_games_played = 0
            games_by_type = []
        
        embed = discord.Embed(
            title=f"📊 Statistics for {user.display_name}",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Get daily streak
        try:
            from cogs.daily import Daily
            daily_streak = await Daily.get_daily_streak(user.id)
            streak_text = f"🔥 {daily_streak['streak']} day streak" if daily_streak and daily_streak.get('streak', 0) > 0 else "No active streak"
        except Exception as e:
            self.logger.error(f"Error getting daily streak: {e}")
            streak_text = "No active streak"
        
        embed.add_field(
            name="🎮 Overall Stats",
            value=(
                f"**Level:** {level}\n"
                f"**Total XP:** {xp:,}\n"
                f"**XP from Games:** {total_xp_from_games:,}\n"
                f"**Total Games Played:** {total_games_played:,}\n"
                f"**Daily Streak:** {streak_text}"
            ),
            inline=False
        )
        
        # Games by type summary
        if games_by_type:
            games_summary = "\n".join([
                f"**{row['source']}:** {row['count']} games ({row['total_xp']:,} XP)"
                for row in games_by_type[:10]  # Top 10
            ])
            embed.add_field(
                name="🎯 Games by Type",
                value=games_summary or "No games played yet",
                inline=False
            )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        
        return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(Statistics(bot))
