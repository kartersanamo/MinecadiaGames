from Assets.functions import get_data, execute, task, log_tasks, dm_games, chat_games
from Cogs.flag_guesser import FlagGuesser
from Cogs.math_quiz import MathQuiz
from Cogs.trivia import Trivia
from Cogs.unscramble import Unscramble
from Cogs.sendgames import DMGames, ViewMore
from Cogs.memory import MemoryButtons
from Cogs.connect_four import ConnectFourButtons
from Cogs._2048 import _2048Buttons
from Cogs.tictactoe import TicTacToeButtons
from discord.ext import commands
from discord import app_commands
import datetime
import random
import discord
import asyncio
import os


COG_FILES = [file.split(".")[0].title() for file in os.listdir("MinecadiaGames/Cogs/") if file.endswith(".py")]


class Client(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix = '.', intents = discord.Intents().all())
        self.data: dict = get_data()
        self.view_list: list[discord.ui.View]
        self.chat_games_delay_lower: int = 1800
        self.chat_games_delay: dict = {
            "lower": 1500,
            "upper": 2100
        }
        self.dm_games_delay: int = 7200
        self.dm_games = ["tictactoe", "memory", "wordle", "connectfour", "2048"]

    async def get_last_game(self, dm_game: bool):
        rows = await execute(f"SELECT game_name, refreshed_at FROM games WHERE dm_game = {dm_game} ORDER BY refreshed_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def send_chat_game(self) -> None:
        choices: list = [
            FlagGuesser, 
            MathQuiz, 
            Unscramble, 
            Trivia
        ]
        choice = random.choice(choices)
        game = choice(self)
        await game.game(None)

    async def check_chat_games(self):
        while True:
            last_game: dict = await self.get_last_game(dm_game=False)
            delay: int = random.randint(self.chat_games_delay["lower"], self.chat_games_delay["upper"])

            if not last_game:
                chat_games.warning("No previous Chat Game found.")
                await self.send_chat_game()
            else:
                last: int = int(last_game['refreshed_at'])
                now: int = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

                if (now - last) > delay:
                    await self.send_chat_game()
                else:
                    waiting_seconds: int = delay - (now - last)
                    if waiting_seconds > 0:
                        chat_games.info(f"Waiting {waiting_seconds} seconds.")
                        await asyncio.sleep(waiting_seconds)
                    await self.send_chat_game()

            dm_games.info(f"Waiting {delay} seconds.")
            await asyncio.sleep(delay)
    
    async def refresh(self, choice: str) -> None:
        dm_games.info(f"Refreshing {choice.title()}...")
        refreshed_at: int = int(float(datetime.datetime.now(datetime.timezone.utc).timestamp()))
        await execute(f"INSERT INTO games (game_name, refreshed_at, dm_game) VALUES ('{choice.title()}', '{refreshed_at}', {True})")

        guild: discord.Guild = self.get_guild(680569558754656280)
        leveling_channel: discord.Channel = guild.get_channel(1186036927514812426)
        games_role: discord.Role = guild.get_role(1190635899025891398)
        async for message in leveling_channel.history():
            if "🚨" in message.content:
                await message.delete()
            elif message.embeds and message.author.bot:
                if message.embeds[0].title == "What are levels? <:Minecadia:974713467703545907>":
                    embed: discord.Embed = message.embeds[0]
                    last_section: str = embed.description.split("\n\n")[-1]
                    now: int = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
                    new: int = now + 7200
                    game_sequence = ["TicTacToe", "Memory", "Wordle", "Connect Four", "2048"]
                    rotation_display = " → ".join(f"**{g}**" if g.lower().replace(" ", "") == choice.lower().replace(" ", "") else g for g in game_sequence)
                    new_section: str = f"✅ **Active DM Game**: {choice.title()}\n🚨 **New DM Game**: <t:{new}:R>\n-# {rotation_display}"
                    embed.description = embed.description.replace(last_section, new_section)
                    await message.edit(embed = embed, view = DMGames(self, choice.title()))
        await leveling_channel.send(content = f"🚨 {games_role.mention} {choice.title()} has been refreshed!")
        #await leveling_channel.send(content = f"🚨 {choice.title()} has been refreshed!")

    async def check_dm_games(self):
        while True:
            last_game: dict = await self.get_last_game(dm_game=True)
            if not last_game:
                dm_games.warning("No previous DM Game found.")
                choice = self.dm_games[0]
                await self.refresh(choice)
            else:
                last: int = int(last_game['refreshed_at'])
                now: int = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
                if (now - last) > self.dm_games_delay:
                    last_name: str = last_game["game_name"].lower()
                    try:
                        index = self.dm_games.index(last_name)
                        next_index = (index + 1) % len(self.dm_games)
                        choice = self.dm_games[next_index]
                    except ValueError:
                        choice = self.dm_games[0]
                    await self.refresh(choice)
                else:
                    delay: int = self.dm_games_delay - (now - last)
                    if delay > 0:
                        dm_games.info(f"Waiting {delay} seconds.")
                        await asyncio.sleep(delay)
                    last_name: str = last_game["game_name"].lower()
                    try:
                        index = self.dm_games.index(last_name)
                        next_index = (index + 1) % len(self.dm_games)
                        choice = self.dm_games[next_index]
                    except ValueError:
                        choice = self.dm_games[0]
                    await self.refresh(choice)
            dm_games.info(f"Waiting {self.dm_games_delay} seconds.")
            await asyncio.sleep(self.dm_games_delay)


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
        asyncio.create_task(self.check_chat_games())
        asyncio.create_task(self.check_dm_games())
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
    await interaction.followup.send(content = error, ephemeral = True) if interaction.response.is_done() else await interaction.response.send_message(content = error, ephemeral = True)


if __name__ == "__main__":
    client.run(client.data['TOKEN'])