from discord.ext import commands
from discord import app_commands
import discord
from core.config.manager import ConfigManager
from core.logging.setup import get_logger
from services.daily_service import claim_daily, get_daily_streak


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
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            result = await claim_daily(self.bot, interaction.user, interaction.channel)
        except Exception as exc:
            self.logger.error("Daily claim failed: %s", exc, exc_info=True)
            await interaction.followup.send(
                "`❌` Something went wrong claiming your daily reward. Please try again.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(embed=result.embed, ephemeral=result.ephemeral)

    get_daily_streak = staticmethod(get_daily_streak)


async def setup(bot):
    await bot.add_cog(Daily(bot))
