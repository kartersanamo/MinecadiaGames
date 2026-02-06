from discord.ext import commands
from discord import app_commands
import discord
from core.config.manager import ConfigManager
from core.database.pool import DatabasePool
from core.logging.setup import get_logger
from managers.leveling import LevelingManager
from datetime import datetime, timezone, timedelta
from typing import Optional


class Daily(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Commands")
    
    @app_commands.command(name="daily", description="Claim your daily XP reward")
    async def daily(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                content="Commands cannot be ran in DMs!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        db = await DatabasePool.get_instance()
        user_id = str(interaction.user.id)
        current_time = int(datetime.now(timezone.utc).timestamp())
        
        # Get or create daily claim record
        daily_data = await db.execute(
            "SELECT * FROM daily_claims WHERE user_id = %s",
            (user_id,)
        )
        
        if not daily_data:
            # First time claiming
            streak = 1
            xp = 10  # Starting XP
            await db.execute_insert(
                "INSERT INTO daily_claims (user_id, last_claimed, streak) VALUES (%s, %s, %s)",
                (user_id, current_time, streak)
            )
        else:
            last_claimed = int(daily_data[0]['last_claimed'])
            current_streak = int(daily_data[0]['streak'])
            
            # Check if already claimed today
            last_claimed_date = datetime.fromtimestamp(last_claimed, tz=timezone.utc).date()
            current_date = datetime.fromtimestamp(current_time, tz=timezone.utc).date()
            
            if last_claimed_date == current_date:
                # Already claimed today
                next_claim_time = datetime.fromtimestamp(last_claimed, tz=timezone.utc) + timedelta(days=1)
                next_claim_timestamp = int(next_claim_time.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
                
                embed = discord.Embed(
                    title="⏰ Daily Reward Already Claimed",
                    description=(
                        f"You've already claimed your daily reward today!\n\n"
                        f"**Current Streak:** {current_streak} days 🔥\n"
                        f"**Next Claim:** <t:{next_claim_timestamp}:R>"
                    ),
                    color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
                )
                from utils.helpers import get_embed_logo_url
                logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
                embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Check if streak continues (claimed yesterday)
            yesterday = current_date - timedelta(days=1)
            if last_claimed_date == yesterday:
                # Streak continues
                streak = current_streak + 1
            else:
                # Streak broken
                streak = 1
            
            # Calculate XP based on streak: 10, 15, 20, 25, 30, 35, etc. (increases by 5 each day)
            xp = 10 + (streak - 1) * 5
            
            # Update record
            await db.execute(
                "UPDATE daily_claims SET last_claimed = %s, streak = %s WHERE user_id = %s",
                (current_time, streak, user_id)
            )
        
        # Award XP
        lvl_mng = LevelingManager(
            user=interaction.user,
            channel=interaction.channel,
            client=self.bot,
            xp=xp,
            source="Daily Reward",
            game_id=0
        )
        await lvl_mng.update()
        
        # Create success embed
        embed = discord.Embed(
            title="🎁 Daily Reward Claimed!",
            description=(
                f"You've claimed your daily reward!\n\n"
                f"**XP Earned:** {xp} XP\n"
                f"**Current Streak:** {streak} day{'s' if streak != 1 else ''} 🔥\n"
                f"**Next Reward:** {xp + 5} XP (if you maintain your streak)"
            ),
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
        )
        
        if streak >= 7:
            embed.add_field(
                name="🔥 Streak Bonus!",
                value=f"You've maintained a {streak}-day streak! Keep it up!",
                inline=False
            )
        
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @staticmethod
    async def get_daily_streak(user_id: int) -> dict:
        """Get daily streak information for a user"""
        db = await DatabasePool.get_instance()
        daily_data = await db.execute(
            "SELECT streak, last_claimed FROM daily_claims WHERE user_id = %s",
            (str(user_id),)
        )
        
        if not daily_data:
            return {"streak": 0, "last_claimed": None}
        
        return {
            "streak": int(daily_data[0]['streak']),
            "last_claimed": int(daily_data[0]['last_claimed'])
        }


async def setup(bot):
    await bot.add_cog(Daily(bot))

