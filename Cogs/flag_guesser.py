from Assets.functions import execute
import asyncio
import datetime
import json
import os
import random
import requests
import uuid
import urllib.request

import discord
from discord import app_commands
from discord.ext import commands

from Assets.functions import get_data, chat_games
from Assets.leveling_manager import LevelingManager


class FlagGuesser(commands.Cog):
    """
    Cog for running the Flag Guesser game on a Discord server.
    """
    def __init__(self, client: commands.Bot):
        self.client: commands.Bot = client
        self.data: dict = get_data()
        self.flag_guesser_data: dict = self._load_config()
        self.countries: dict = self._fetch_countries()
        self.game_length_in_seconds: int = 600

    def _load_config(self) -> dict:
        """Load configuration data from JSON file."""
        with open("MinecadiaGames/Assets/Configs/flag_guesser.json", "r") as file:
            return json.load(file)

    def _fetch_countries(self) -> dict:
        """Fetch country data from API, excluding certain keys."""
        request = urllib.request.Request(
            url=self.flag_guesser_data['API_URL'],
            headers=self.flag_guesser_data['REQUEST_HEADERS']
        )
        with urllib.request.urlopen(request) as response:
            countries: dict = json.loads(response.read())
        return {key: value for key, value in countries.items() if not key.startswith('us-')}

    async def _select_country_and_answers(self) -> tuple:
        """Select a random country and generate multiple-choice answers."""
        country_code: str = random.choice(list(self.countries.keys()))
        correct_answer: str = self.countries[country_code]
        answers: list[str] = [correct_answer]

        while len(answers) < 4:
            choice: str = random.choice(list(self.countries.values()))
            if choice not in answers:
                answers.append(choice)

        random.shuffle(answers)
        return country_code, correct_answer, answers

    async def _build_embed(self, country_code: str, double_xp: bool, current_unix: int) -> tuple:
        """Create an embed with the flag image and attach the image file."""
        response: requests.Response = requests.get(f"https://flagcdn.com/w2560/{country_code}.png")
        filename: str = f"{uuid.uuid4()}.png"
        with open(filename, 'wb') as file:
            file.write(response.content)

        embed: discord.Embed = discord.Embed(
            title=f"Flag Guesser{' (DOUBLE XP)' if double_xp else ''}",
            description=f"This game will end <t:{current_unix + self.game_length_in_seconds}:R>",
            color=discord.Color.from_str(self.data["EMBED_COLOR"]),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_image(url=f"attachment://{filename}")

        file: discord.File = discord.File(filename, filename=filename)
        os.remove(filename)
        return embed, file

    async def game(self, channel: discord.TextChannel) -> None:
        """Run the Flag Guesser game in the given channel."""
        try:
            refreshed_at: int = int(float(datetime.datetime.now(datetime.timezone.utc).timestamp()))
            await execute(f"INSERT INTO games (game_name, refreshed_at, dm_game) VALUES ('Flag Guesser', '{refreshed_at}', {False})")

            guild: discord.Guild = self.client.get_guild(self.data['GUILD_ID'])
            role: discord.Role = guild.get_role(self.data['GAMES_ROLE'])
            if not channel:
                channel: discord.TextChannel = self.client.get_channel(random.choice(self.flag_guesser_data['CHANNELS']))

            current_unix: int = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
            double_xp: bool = random.random() <= 0.15
            country_code, correct_answer, answers = await self._select_country_and_answers()

            chat_games.info(f"Flag Guesser '{correct_answer}' #{channel.name}")

            view: CountryButtons = CountryButtons(correct_answer, answers, double_xp)
            embed, file = await self._build_embed(country_code, double_xp, current_unix)

            message: discord.Message = await channel.send(
                content=role.mention,
                embed=embed,
                file=file,
                view=view
            )

            await asyncio.sleep(self.game_length_in_seconds)

            if message.components:
                embed.description = f"This game ended <t:{current_unix + self.game_length_in_seconds}:R>"
                winners_text = "\n".join(f"`+{w['xp']}xp` {w['user']}" for w in view.winners) or "No winners!"
                embed.add_field(name="Winners", value=winners_text)
                await message.edit(view=None, embed=embed, attachments=[])

        except Exception as error:
            chat_games.error(f"Error sending flag guesser: '{error}'")

    @app_commands.command(name="flag-guesser", description="Sends the flag guesser game")
    async def flagguesser(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        """Slash command to start the Flag Guesser game."""
        if interaction.guild is None:
            return await interaction.response.send_message("Commands cannot be ran in DMs!", ephemeral=True)

        await interaction.response.send_message("Sending the Flag Guesser game!", ephemeral=True)
        await self.game(channel)


class CountryButtons(discord.ui.View):
    """
    A Discord UI view containing buttons for multiple-choice flag guessing.
    """
    def __init__(self, correct_answer: str, answers: list[str], double_xp: bool) -> None:
        super().__init__(timeout=None)
        self.correct_answer = correct_answer
        self.double_xp = double_xp
        self.played: list[int] = []
        self.winners: list[dict] = []

        with open("MinecadiaGames/Assets/Configs/flag_guesser.json", "r") as file:
            self.flag_guesser_data: dict = json.load(file)

        for answer in answers:
            self.add_item(self.CountryButton(answer, answer == correct_answer))

    def has_played(self, user_id: int) -> bool:
        return user_id in self.played

    async def _respond_if_played(self, interaction: discord.Interaction) -> bool:
        if self.has_played(interaction.user.id):
            await interaction.response.send_message("`❌` You have already played in this game!", ephemeral=True)
            return True
        self.played.append(interaction.user.id)
        return False

    async def handle_correct(self, interaction: discord.Interaction) -> None:
        xp = random.randint(
            self.flag_guesser_data['XP_LOWER'][str(len(self.winners) + 1)],
            self.flag_guesser_data['XP_LOWER'][str(len(self.winners) + 1)] + self.flag_guesser_data['XP_ADD']
        )
        if self.double_xp:
            xp *= 2

        self.winners.append({'user': interaction.user, 'xp': xp})
        await interaction.response.send_message(
            f"`✅` Correct! You have been awarded `{xp}xp`" + (" (2x XP)" if self.double_xp else "!"),
            ephemeral=True
        )

        lvl_mng = LevelingManager(
            user=interaction.user,
            channel=interaction.channel,
            client=interaction.client,
            xp=xp,
            source="Flag Guesser"
        )
        await lvl_mng.update()

        if len(self.winners) >= self.flag_guesser_data['WINNERS']:
            embed: discord.Embed = interaction.message.embeds[0]
            current_unix: int = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
            embed.description = f"This game ended <t:{current_unix}:R>"
            winners_text: str = "\n".join(f"`+{w['xp']}xp` {w['user']}" for w in self.winners)
            embed.add_field(name="Winners", value=winners_text)
            await interaction.message.edit(embed=embed, view=None, attachments=[])

    async def handle_wrong(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("`❌` Incorrect! Try again later!", ephemeral=True)

    class CountryButton(discord.ui.Button):
        def __init__(self, label: str, is_correct: bool):
            super().__init__(label = label, style = discord.ButtonStyle.grey)
            self.is_correct = is_correct

        async def callback(self, interaction: discord.Interaction):
            view: CountryButtons = self.view
            if await view._respond_if_played(interaction):
                return

            if self.is_correct:
                await view.handle_correct(interaction)
            else:
                await view.handle_wrong(interaction)


async def setup(client: commands.Bot) -> None:
    """Setup function to add the FlagGuesser cog to the bot."""
    await client.add_cog(FlagGuesser(client))