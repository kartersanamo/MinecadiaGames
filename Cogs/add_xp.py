from Assets.functions import get_data, execute
from discord.ext import commands
from discord import app_commands
import discord


class AddXP(commands.Cog):
    """Cog for the /add-xp command to manually adjust a user's XP."""

    def __init__(self, client: commands.Bot):
        self.client: commands.Bot = client
        self.data: dict = get_data()

    @app_commands.command(name = "add-xp", description = "Adds/Removes XP from a member")
    async def add_xp(self, interaction: discord.Interaction, member: discord.Member, xp: str) -> None:
        """Command handler for /add-xp."""
        if interaction.guild is None:
            return await interaction.response.send_message(
                content = "Commands cannot be run in DMs!", 
                ephemeral = True
            )

        xp_value: int = self._parse_xp_input(xp)
        if xp_value is None:
            return await interaction.response.send_message(
                content = "`❌` Failed! Please provide a positive or negative number.",
                ephemeral = True
            )

        current_xp: int = await self._get_current_xp(member.id)
        if current_xp is None:
            return await interaction.response.send_message(
                content = "`❌` Failed! This user is not in the database. They must gain XP first!",
                ephemeral = True
            )

        new_xp: int = current_xp + xp_value
        if new_xp < 0:
            return await interaction.response.send_message(
                content = "`❌` Failed! This action would result in a negative XP value!",
                ephemeral = True
            )

        await self._update_user_xp(member.id, new_xp)

        await interaction.response.send_message(
            content = f"`✅` Successfully added `{xp_value}` XP to {member.mention} `{current_xp}` → `{new_xp}`.",
            ephemeral = True
        )

    def _parse_xp_input(self, xp: str) -> int:
        """
        Attempts to parse XP input to an integer.

        Returns:
            int if successful, else None.
        """
        try:
            return int(xp)
        except (ValueError, TypeError):
            return None

    async def _get_current_xp(self, user_id: int) -> int:
        """
        Fetches current XP for a user from the database.

        Returns:
            int if found, else None.
        """
        result = await execute(f"SELECT xp FROM `leveling` WHERE `user_id` = '{user_id}'")
        if not result:
            return None
        return int(result[0]['xp'])

    async def _update_user_xp(self, user_id: int, new_xp: int) -> None:
        """
        Updates a user's XP in the database.
        """
        await execute(f"UPDATE `leveling` SET `xp` = '{new_xp}' WHERE `user_id` = '{user_id}'")


async def setup(client: commands.Bot) -> None:
    """Loads the AddXP cog."""
    await client.add_cog(AddXP(client))