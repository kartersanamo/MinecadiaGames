from Assets.functions import get_data, task, log_tasks, execute
from Cogs.sendgames import DMGames, ViewMore
from Cogs.memory import MemoryButtons
from Cogs.connect_four import ConnectFourButtons
from Cogs._2048 import _2048Buttons
from Cogs.tictactoe import TicTacToeButtons
from discord.ext import commands
from discord import app_commands
import discord
import asyncio
import os


COG_FILES = [file.split(".")[0].title() for file in os.listdir("MinecadiaGames/Cogs/") if file.endswith(".py")]


class Client(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix = '.', intents = discord.Intents().all())
        self.data: dict = get_data()
        self.view_list: list[discord.ui.View]

    async def get_last_game(self, dm_game: bool):
        rows = await execute(f"SELECT game_name, refreshed_at FROM games WHERE dm_game = {dm_game} ORDER BY refreshed_at DESC LIMIT 1")
        return rows[0]
    
    @task("Setup Cogs")
    async def setup_cogs(self):
        for ext in COG_FILES:
            log_tasks.info(f"Loaded cog {ext}.py")
            await self.load_extension("Cogs." + ext.lower())

    @task("Add Views")
    async def add_views(self):
        last_game: dict = await self.get_last_game(dm_game = True)
        last: str = last_game['game_name']
        self.view_list = [
            DMGames(self, last),
            ViewMore(),
            MemoryButtons(),
            TicTacToeButtons(),
            ConnectFourButtons(),
            _2048Buttons()
        ]
        for view in self.view_list:
            log_tasks.info(f"Added view {view.__class__.__name__}")
            self.add_view(view)

    @task("Update Presence")
    async def update_presence(self):
        presence = self.data["PRESENCE"]
        await client.change_presence(activity = discord.Game(name = presence))
        log_tasks.info(f"Updated the bot's presence to {presence}")

    @task("Remove Help")
    async def remove_help(self):
        client.remove_command("help")

    @task("Sync Command Tree")
    async def sync_command_tree(self):
        commands: list[discord.app_commands.AppCommand] = await self.tree.sync()
        command_list: str = ', '.join([command.name for command in commands])
        log_tasks.info(f"Synced {len(commands)} commands {command_list}")

    @task("Setup Hook")
    async def setup_hook(self):
        await self.setup_cogs()
        await self.add_views()
    
    @task("Logging in")
    async def on_ready(self):
        await self.update_presence()
        await self.remove_help()
        await self.sync_command_tree()
        if client.user:
            log_tasks.info(f"Logged in as {client.user} ({client.user.id})")


client = Client()


@task("Games Reload Command", True)
async def games_reload_command(interaction: discord.Interaction, cog: str):
    """
    This function is responsible for reloading a specific Cog class.

    Parameters:
    - interaction (discord.Interaction): The Discord interaction object that triggered the command.
    - cog (str): The name of the Cog class to be reloaded.

    Returns:
    - None. This function is asynchronous and does not return any value.

    Raises:
    - discord.app_commands.AppCommandError: If there is an error while reloading the Cog class.
    """
    if interaction.guild is None:
        return await interaction.response.send_message(content = "Commands cannot be ran in DMs!", ephemeral = True)
    if cog not in COG_FILES:
        await interaction.response.send_message(f"Invalid cog name **{cog}.py**", ephemeral = True)
        return
    await client.reload_extension(f"Cogs.{cog.lower()}")
    await interaction.response.send_message(f"Successfully reloaded **{cog}.py**", ephemeral = True)

async def cog_autocomplete(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name = cog, value = cog)
        for cog in COG_FILES if current.lower() in cog.lower()
    ]

@client.tree.command(name = "games-reload", description = "Reloads a Cog Class")
@app_commands.autocomplete(cog = cog_autocomplete)
async def gamesreload(interaction: discord.Interaction, cog: str):
    """
    This function is responsible for triggering the reload of a specific Cog class based on the user's interaction.

    Parameters:
    - interaction (discord.Interaction): The Discord interaction object that triggered the command.
    - cog (str): The name of the Cog class to be reloaded. The input is restricted to a specific set of strings as determined by the 'cog_autocomplete' function.

    Returns:
    - None. This function is asynchronous and does not return any value. It triggers the reload of the specified Cog class.

    Raises:
    - discord.app_commands.AppCommandError: If there is an error while reloading the Cog class.
    """
    await games_reload_command(interaction, cog)

@gamesreload.error
async def gamesreload_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    await interaction.followup.send(content = str(error), ephemeral = True) if interaction.response.is_done() else await interaction.response.send_message(content = error, ephemeral = True)


if __name__ == "__main__":
    client.run(client.data['TOKEN'])