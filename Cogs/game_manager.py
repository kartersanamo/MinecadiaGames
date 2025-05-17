from Assets.functions import get_data
from discord.ext import commands
from discord import app_commands
import discord


class GameManager(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client: commands.Bot = client
        self.data: dict = get_data()

    @app_commands.command(name = "game-manager", description = "Manages the chat and dm games")
    async def add_xp(self, interaction: discord.Interaction) -> None:
        """Command handler for /game-manager."""
        if interaction.guild is None:
            await interaction.response.send_message(
                content = "Commands cannot be run in DMs!", 
                ephemeral = True
            )
            return
        embed: discord.Embed = discord.Embed(
            title = "Main Menu",
            color = discord.Color.from_str(self.data["EMBED_COLOR"]),
            description = "Please make a selection below."
        )
        embed.add_field(name = "DM Games", value = "`»` TicTacToe\n`»` Memory\n`»` Wordle\n`»` Connect Four\n`»` 2048")
        embed.add_field(name = "Chat Games", value = "`»` Math Quiz\n`»` Unscramble\n`»` Flag Guesser\n`»` Trivia")

class TypeOfGameView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout = None)
        self.add_item(DMGameSelector())
    
class DMGameSelector(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__()


async def setup(client:commands.Bot) -> None:
  await client.add_cog(GameManager(client))