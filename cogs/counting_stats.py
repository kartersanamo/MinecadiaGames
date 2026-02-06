

from discord.ext import commands
from discord import app_commands
import discord
from core.database.pool import DatabasePool
from core.logging.setup import get_logger
from core.config.manager import ConfigManager


class CountingStats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Commands")
    
    async def get_user_stats(self, guild_id: int, user_id: int) -> dict:
        db = await DatabasePool.get_instance()
        rows = await db.execute(
            "SELECT total_counts, highest_count, mistakes FROM counting_users WHERE guild_id = %s AND user_id = %s",
            (str(guild_id), str(user_id))
        )
        
        if rows:
            return rows[0]
        
        return {
            "total_counts": 0,
            "highest_count": 0,
            "mistakes": 0
        }
    
    async def get_server_stats(self, guild_id: int) -> dict:
        db = await DatabasePool.get_instance()
        rows = await db.execute(
            "SELECT last_number, total_counts, highest_count FROM counting_server WHERE guild_id = %s",
            (str(guild_id),)
        )
        
        if rows:
            return rows[0]
        
        return {
            "last_number": 0,
            "total_counts": 0,
            "highest_count": 0
        }
    
    async def get_top_counters(self, guild_id: int, limit: int = 5):
        db = await DatabasePool.get_instance()
        return await db.execute(
            "SELECT user_id, total_counts FROM counting_users WHERE guild_id = %s ORDER BY total_counts DESC LIMIT %s",
            (str(guild_id), limit)
        )
    
    @app_commands.command(name="countingstats", description="View counting statistics")
    async def countingstats(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None
    ):
        if interaction.guild is None:
            await interaction.response.send_message("`❌` This command can only be used in a server.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        
        if user is not None:
            stats = await self.get_user_stats(guild_id, user.id)
            
            embed = discord.Embed(
                title=f"{user.display_name}'s counting statistics",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            
            embed.add_field(name="Total Counts", value=str(stats["total_counts"]), inline=False)
            embed.add_field(name="Highest Count", value=str(stats["highest_count"]), inline=False)
            embed.add_field(name="Mistakes", value=str(stats["mistakes"]), inline=False)
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        server_stats = await self.get_server_stats(guild_id)
        top_users = await self.get_top_counters(guild_id)
        
        embed = discord.Embed(
            title="Server counting statistics",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
        )
        
        embed.add_field(name="Last Count", value=str(server_stats["last_number"]), inline=False)
        embed.add_field(name="Total Counts", value=str(server_stats["total_counts"]), inline=False)
        embed.add_field(name="Highest Count", value=str(server_stats["highest_count"]), inline=False)
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        
        if top_users:
            # Emoji mapping for leaderboard positions (same as leveling leaderboard)
            POSITION_EMOJIS = {
                1: "<:minecadia_one:1111028062981718026>",
                2: "<:minecadia_two:1111028088546021466>",
                3: "<:minecadia_three:1111028142430228520>",
                4: "<:minecadia_four:1186027785735643216>",
                5: "<:minecadia_five:1186027816156930058>"
            }
            
            from managers.milestones import MilestonesManager
            milestones_manager = MilestonesManager()
            
            top_text = ""
            for index, row in enumerate(top_users, 1):
                user_id = int(row['user_id'])
                user_obj = self.bot.get_user(user_id)
                
                # Fallback to fetching from guild if not in cache
                if not user_obj and interaction.guild:
                    user_obj = interaction.guild.get_member(user_id)
                
                # Get badge emoji
                badge_emoji = await milestones_manager.get_display_badge(user_id, interaction.guild)
                badge_text = f"{badge_emoji} " if badge_emoji else ""
                
                # Get emoji for position (1-5)
                emoji = POSITION_EMOJIS.get(index, f"**{index}.**")
                
                if user_obj:
                    top_text += f"{emoji} {badge_text}{user_obj.mention}: {row['total_counts']}\n"
                else:
                    top_text += f"{emoji} {badge_text}<@{user_id}>: {row['total_counts']}\n"
            
            if top_text:
                embed.add_field(name="Top 5 counters", value=top_text, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CountingStats(bot))

