from Assets.functions import get_data, dm_games, chat_games, execute
from Cogs.flag_guesser import FlagGuesser
from Cogs.math_quiz import MathQuiz
from Cogs.trivia import Trivia
from Cogs.unscramble import Unscramble
from Cogs._2048 import _2048
from Cogs.connect_four import ConnectFour
from Cogs.memory import Memory
from Cogs.wordle import Wordle
from discord.ext import commands
from discord import app_commands
from typing import Optional, Union
from Cogs.sendgames import DMGames
import datetime
import asyncio
import discord
import random


class GameManager(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client: commands.Bot = client
        self.data: dict = get_data()

        self.chat_games_data: dict = get_data("chat_games")
        self.dm_games_data: dict = get_data("dm_games")

        self.dm_games_dict: dict = self.dm_games_data.get("GAMES", {})
        self.dm_games_labels: list[str] = list(self.dm_games_dict.keys())

        self.chat_games_dict: dict = self.chat_games_data.get("GAMES", {})
        self.chat_games_labels: list[str] = list(self.chat_games_dict.keys())

        self.chat_game_wait: int = 0
        self.dm_game_wait: int = 0

        self.current_dm_game: str
        self.last_chat_game: str

        self.game_tasks: dict[str, dict[str, Optional[Union[asyncio.Task, object]]]] = {
            "chat": {
                "task": None,
                "games": None
            },
            "dm": {
                "task": None,
                "games": None
            }
        }

        asyncio.create_task(self._async_setup())

    async def _async_setup(self) -> None:
        """Initial setup after Cog is loaded."""
        await self.chat_game_refresh()
        await self.dm_game_refresh()

    # -----------------------------
    # Utility Methods
    # -----------------------------

    async def get_last_game(self, dm_game: bool) -> dict:
        rows = await execute(
            f"SELECT game_name, refreshed_at FROM games WHERE dm_game = {dm_game} ORDER BY refreshed_at DESC LIMIT 1"
        )
        return rows[0]

    async def calc_game_wait(self, dm_game: bool = False) -> int:
        """Calculate wait time based on last refresh timestamp."""
        last_game: dict = await self.get_last_game(dm_game=dm_game)
        self.last_chat_game = last_game["game_name"]

        if not last_game:
            (dm_games if dm_game else chat_games).warning(
                f"No previous {'DM' if dm_game else 'Chat'} Game found."
            )
            return 0

        last = int(last_game['refreshed_at'])
        now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

        if dm_game:
            delay = self.dm_games_data["DELAY"]
        else:
            delay = random.randint(
                self.chat_games_data["DELAY"]["LOWER"],
                self.chat_games_data["DELAY"]["UPPER"]
            )

        wait_time = delay - (now - last)
        return max(wait_time, 0)

    def get_next_dm_game_name(self, last_game_name: str) -> str:
        """Cycle to the next DM game."""
        game_names = list(self.dm_games_dict.keys())
        try:
            index = game_names.index(last_game_name)
            next_index = (index + 1) % len(game_names)
        except ValueError:
            next_index = 0
        return game_names[next_index]

    # -----------------------------
    # Chat Game Logic
    # -----------------------------

    async def chat_game_refresh(self) -> None:
        """Start the next chat game after a delay."""
        self.chat_game_wait = await self.calc_game_wait(dm_game=False)
        self.game_tasks["chat"]["task"] = asyncio.create_task(
            self.send_chat_game(self.chat_game_wait)
        )
        chat_games.info(
            f"Waiting {self.chat_game_wait} seconds before sending a new random chat game."
        )

    async def send_chat_game(self, delay: int) -> None:
        """Randomly send a new chat game."""
        await asyncio.sleep(delay)
        choices: list = [FlagGuesser, MathQuiz, Unscramble, Trivia]
        game = random.choice(choices)(self)
        self.game_tasks["chat"]["class"] = game
        await game.game(None)
        await self.chat_game_refresh()

    # -----------------------------
    # DM Game Logic
    # -----------------------------

    async def dm_game_refresh(self) -> None:
        """Start the next DM game refresh."""
        self.dm_game_wait = await self.calc_game_wait(dm_game=True)
        last_dm_game = await self.get_last_game(dm_game=True)
        self.current_dm_game = last_dm_game["game_name"]
        next_dm_game = self.get_next_dm_game_name(last_dm_game["game_name"])
        self.game_tasks["dm"]["task"] = asyncio.create_task(
            self.refresh_dm_game(next_dm_game, self.dm_game_wait)
        )
        dm_games.info(
            f"Waiting {self.dm_game_wait} seconds before refreshing {last_dm_game['game_name']} → {next_dm_game}."
        )

    async def refresh_dm_game(self, choice: str, delay: int) -> None:
        """Refresh the active DM game in the embed + SQL."""
        await asyncio.sleep(delay)
        dm_games.info(f"Refreshing {choice.title()}...")

        refreshed_at: int = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        await execute(
            f"INSERT INTO games (game_name, refreshed_at, dm_game) VALUES ('{choice.title()}', '{refreshed_at}', {True})"
        )

        guild: discord.Guild = self.client.get_guild(680569558754656280)
        leveling_channel: discord.TextChannel = guild.get_channel(1186036927514812426)
        games_role: discord.Role = guild.get_role(1190635899025891398)

        async for message in leveling_channel.history():
            if "🚨" in message.content:
                await message.delete()
            elif message.embeds and message.author.bot:
                embed: discord.Embed = message.embeds[0]
                if embed.title == "What are levels? <:Minecadia:974713467703545907>":
                    last_section = embed.description.split("\n\n")[-1]
                    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
                    new = now + 7200

                    rotation_display = " → ".join(
                        f"**{g}**" if g.lower().replace(" ", "") == choice.lower().replace(" ", "") else g
                        for g in self.dm_games_labels
                    )

                    new_section = (
                        f"✅ **Active DM Game**: {choice.title()}\n"
                        f"🚨 **New DM Game**: <t:{new}:R>\n"
                        f"-# {rotation_display}"
                    )

                    embed.description = embed.description.replace(last_section, new_section)
                    await message.edit(embed=embed, view=DMGames(self, choice.title()))

        await leveling_channel.send(content=f"🚨 {games_role.mention} {choice.title()} has been refreshed!")
        await self.dm_game_refresh()


    @app_commands.command(name = "game-manager", description = "Manages the chat and dm games")
    async def game_manager(self, interaction: discord.Interaction) -> None:
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


        dm_games_str: str = "\n".join([f"`»` **{label}**" if label == self.current_dm_game else f"`»` {label}" for label in self.dm_games_labels])
        chat_games_str: str = "\n".join([f"`»` **{label}**" if label == self.last_chat_game else f"`»` {label}" for label in self.chat_games_labels])
        embed.add_field(name = "✅ DM Games" if self.game_tasks["dm"]["task"] else "❌ DM Games", value = dm_games_str)
        embed.add_field(name = "✅ Chat Games" if self.game_tasks["chat"]["task"] else "❌ Chat Games", value = chat_games_str)

        await interaction.response.send_message(
            embed = embed,
            view = TypeOfGameView(
                dm_game_info = self.dm_games_data, 
                chat_game_info = self.chat_games_data,
                dm_games_labels = self.dm_games_labels,
                chat_games_labels = self.chat_games_labels,
                game_tasks = self.game_tasks
            )
        )

class TypeOfGameView(discord.ui.View):
    def __init__(self, dm_game_info: dict, chat_game_info: dict, dm_games_labels: list[str], chat_games_labels: list[str], game_tasks: dict) -> None:
        self.dm_games_labels: list[str] = dm_games_labels
        self.chat_games_labels: list[str] = chat_games_labels
        self.game_tasks: dict = game_tasks

        super().__init__(timeout = None)

        # Toggle DM Games Button
        toggle_dm_games_button = discord.ui.Button(
            label = "Disable DM Games",
            style = discord.ButtonStyle.red,
            custom_id = "toggle_dm_games_button_disable"
        ) if self.game_tasks['dm']['task'] else discord.ui.Button(
            label = "Enable DM Games",
            style = discord.ButtonStyle.green,
            custom_id = "toggle_dm_games_button_enable"
        )

        async def toggle_dm_callback(interaction: discord.Interaction) -> None:
            await interaction.response.defer()

        # Toggle Chat Games Button
        toggle_chat_games_button = discord.ui.Button(
            label = "Disable Chat Games",
            style = discord.ButtonStyle.red,
            custom_id = "toggle_chat_games_button_disable"
        ) if self.game_tasks['chat']['task'] else discord.ui.Button(
            label = "Enable Chat Games",
            style = discord.ButtonStyle.green,
            custom_id = "toggle_chat_games_button_enable"
        )

        async def toggle_chat_callback(interaction: discord.Interaction) -> None:
            await interaction.response.defer()

        # DM Games Selector
        dm_selector = discord.ui.Select(
            placeholder = "Select a DM Game to Manage...",
            options = [
                discord.SelectOption(label = label) for label in self.dm_games_labels
            ]
        )

        async def dm_callback(interaction: discord.Interaction):
            selected = dm_selector.values[0]
            await interaction.response.send_message(
                content = f"Selected DM Game: `{selected}`", ephemeral = True
            )

        # Chat Games Selector
        chat_selector = discord.ui.Select(
            placeholder="Select a Chat Game to Manage...",
            options = [
                discord.SelectOption(label = label) for label in self.chat_games_labels
            ]
        )

        async def chat_callback(interaction: discord.Interaction):
            selected = chat_selector.values[0]
            await interaction.response.send_message(
                content = f"Selected Chat Game: `{selected}`", ephemeral = True
            )
        
        dm_selector.callback = dm_callback
        self.add_item(dm_selector)

        chat_selector.callback = chat_callback
        self.add_item(chat_selector)

        toggle_dm_games_button.callback = toggle_dm_callback
        self.add_item(toggle_dm_games_button)

        toggle_chat_games_button.callback = toggle_chat_callback
        self.add_item(toggle_chat_games_button)


async def setup(client:commands.Bot) -> None:
  await client.add_cog(GameManager(client))