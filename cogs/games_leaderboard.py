from discord.ext import commands
from discord import app_commands
import discord

from core.config.manager import ConfigManager
from core.logging.setup import get_logger
from ui.all_time_leaderboard import AllTimeLeaderboardView, LEADERBOARD_TYPE_CHOICES


class GamesLeaderboard(commands.Cog):
    GAMES_CHANNEL_ID = 1456658225964388504

    def __init__(self, bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Commands")

    @app_commands.command(
        name="games-leaderboard",
        description="View all-time game leaderboards",
    )
    @app_commands.describe(
        category="Which all-time leaderboard to view",
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name=label, value=value)
            for value, label in LEADERBOARD_TYPE_CHOICES
        ]
    )
    async def games_leaderboard(
        self,
        interaction: discord.Interaction,
        category: app_commands.Choice[str],
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "`❌` This command can only be used in a server.",
                ephemeral=True,
            )
            return

        if interaction.channel is None or interaction.channel.id != self.GAMES_CHANNEL_ID:
            await interaction.response.send_message(
                f"`❌` This command can only be used in <#{self.GAMES_CHANNEL_ID}>.",
                ephemeral=True,
            )
            return

        try:
            await interaction.response.defer(ephemeral=False)
            view = AllTimeLeaderboardView(interaction.client, interaction.guild)
            await view.send_leaderboard(interaction, category.value, ephemeral=False)
        except Exception as e:
            self.logger.error(f"Error in games-leaderboard command: {e}", exc_info=True)
            message = f"`❌` Error loading leaderboard: {e}"
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)


async def setup(bot):
    await bot.add_cog(GamesLeaderboard(bot))
