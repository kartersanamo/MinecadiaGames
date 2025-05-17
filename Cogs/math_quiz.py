from Assets.leveling_manager import LevelingManager
from pylatexenc.latex2text import LatexNodes2Text
from Assets.functions import get_data, chat_games, execute
from discord.ext import commands
from discord import app_commands
import mathgenerator
import datetime
import discord
import asyncio
import random
import json

class MathQuiz(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.data = get_data()
        with open("MinecadiaGames/Assets/Configs/math_quiz.json", "r") as file:
            self.math_quiz_data = json.load(file)
        self.game_length_in_seconds: int = 600

    async def fix_format(self, phrase: str):
        try:
            fixed = await asyncio.wait_for(self._fix_format_async(phrase), timeout=2)
        except asyncio.TimeoutError:
            fixed = "Timeout occurred, alternative value"
        return fixed

    async def _fix_format_async(self, phrase: str):
        fixed = LatexNodes2Text().latex_to_text(phrase)
        fixed = fixed.replace("·", " x ")
        fixed = fixed.replace('[', '')
        fixed = fixed.replace(']', '')
        return fixed

    async def get_wrong(self, id: int, real: str, problem: str):
        wrong = []
        for i in range(3):
            _, solution = mathgenerator.genById(id)
            try:
                fixed_solution = await self.fix_format(solution)
            except:
                fixed_solution = solution
            while (fixed_solution == real) or (fixed_solution in wrong):
                _, solution = mathgenerator.genById(id)
                try:
                    fixed_solution = await self.fix_format(solution)
                except:
                    fixed_solution = solution
            if "Factors of" in problem:
                fixed_solution += ", " + problem.split(' ')[-1]
            wrong.append(fixed_solution)
        return wrong

    async def game(self, channel):
        try:
            refreshed_at: int = int(float(datetime.datetime.now(datetime.timezone.utc).timestamp()))
            await execute(f"INSERT INTO games (game_name, refreshed_at, dm_game) VALUES ('Math Quiz', '{refreshed_at}', {False})")

            guild = self.client.get_guild(self.data['GUILD_ID'])
            role = guild.get_role(self.data['GAMES_ROLE'])
            question = random.choice(self.math_quiz_data['QUESTIONS'])
            problem, solution = mathgenerator.genById(question['ID'])
            try:
                problem = await self.fix_format(problem)
                solution = await self.fix_format(solution)
            except Exception as error:
                chat_games.error(f"Math Quiz Error in Formatted: {error}")
            current_unix: int = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
            double_xp: bool = random.random() <= 0.15
            embed = discord.Embed(
                title = question['Problem Type'] + (" (DOUBLE XP)" if double_xp else ""),
                description = f"This game will end <t:{current_unix + self.game_length_in_seconds}:R>",
                color = discord.Color.from_str(self.data["EMBED_COLOR"]),
                timestamp = datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="Problem", value=problem, inline=False)
            if not channel:
                channel = self.client.get_channel(random.choice(self.math_quiz_data['CHANNELS']))
            chat_games.info(f"Math Quiz '{problem}' | '{solution}' #{channel.name} | {double_xp}")
            view = CountryButtons(double_xp)
            if solution in ["Yes", "No"]:
                answers = [solution, "No" if solution == "Yes" else "Yes"]
                children = view.children[:2]
            elif solution in ["<", ">", "="]:
                s_to_others = {
                    "<": [">", "="],
                    ">": ["<", "="],
                    "=": ["<", ">"]
                }
                answers = [solution] + s_to_others[solution]
                children = view.children[:3]
            else:
                answers = await self.get_wrong(question['ID'], solution, problem)
                answers.insert(0, solution)
                children = view.children
            items = []
            for index, button in enumerate(children):
                button.label = answers[index]
                items.append(button)
            view.clear_items()
            random.shuffle(items)
            for item in items:
                view.add_item(item)
            msg = await channel.send(content=role.mention, embed=embed, view=view)
            await asyncio.sleep(self.game_length_in_seconds)
            if msg.components:
                embed.description = f"This game ended <t:{current_unix + self.game_length_in_seconds}:R>"
                val = ""
                for winner in view.winners:
                    val += f"`+{winner.get('xp')}xp` {winner.get('user')}\n"
                embed.add_field(name="Winners", value = val)
                await msg.edit(view = None, embed = embed)
        except Exception as error:
            chat_games.error(f"Error sending math quiz: '{error}'")

    @app_commands.command(name="math-quiz", description="Sends the math quiz game")
    async def mathquiz(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if interaction.guild is None:
            return await interaction.response.send_message(content="Commands cannot be ran in DMs!", ephemeral=True)
        await interaction.response.send_message(content="Sending the math quiz game!", ephemeral=True)
        await self.game(channel)

class CountryButtons(discord.ui.View):
    def __init__(self, double_xp: bool) -> None:
        super().__init__(timeout = None)
        self.double_xp: bool = double_xp
        self.played = []
        self.winners = []
        with open("MinecadiaGames/Assets/Configs/math_quiz.json", "r") as file:
            self.math_quiz_data = json.load(file)

    @discord.ui.button(label="N/A", style=discord.ButtonStyle.grey, custom_id="math_button_answer")
    async def math_button_answer(self, interaction: discord.Interaction, Button: discord.ui.Button):
        if interaction.user.id in self.played:
            await interaction.response.send_message(content="`❌` You have already played in this game!", ephemeral=True)
            return
        self.played.append(interaction.user.id)
        xp = random.randint(
            self.math_quiz_data['XP_LOWER'][str(len(self.winners) + 1)],
            self.math_quiz_data['XP_LOWER'][str(len(self.winners) + 1)] + self.math_quiz_data['XP_ADD']
        )
        if self.double_xp:
            xp *= 2
        self.winners.append(
            {'user': interaction.user,
             'xp': xp}
            )
        await interaction.response.send_message(content=f"`✅` Correct! You have been awarded `{xp}xp`" + (" (2x XP)" if self.double_xp else "!"), ephemeral=True)
        lvl_mng = LevelingManager(user= interaction.user, channel= interaction.channel, client = interaction.client, xp= xp, source= "Math Quiz")
        await lvl_mng.update()
        if len(self.winners) >= self.math_quiz_data['WINNERS']:
            embed = interaction.message.embeds[0]
            current_unix: int = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
            embed.description = f"This game ended <t:{current_unix}:R>"
            val = ""
            for winner in self.winners:
                val += f"`+{winner.get('xp')}xp` {winner.get('user')}\n"
            embed.add_field(name="Winners", value = val)
            await interaction.message.edit(embed = embed, view = None)
    
    @discord.ui.button(label="N/A", style=discord.ButtonStyle.grey, custom_id="math_button_wrong_0")
    async def math_button_wrong_0(self, interaction: discord.Interaction, Button: discord.ui.Button):
        if interaction.user.id in self.played:
            return await interaction.response.send_message(content=f"`❌` You have already played in this game!", ephemeral=True)
        self.played.append(interaction.user.id)
        await interaction.response.send_message(content="`❌` Incorrect! Try again later!", ephemeral=True)
    
    @discord.ui.button(label="N/A", style=discord.ButtonStyle.grey, custom_id="math_button_wrong_1")
    async def math_button_wrong_1(self, interaction: discord.Interaction, Button: discord.ui.Button):
        if interaction.user.id in self.played:
            return await interaction.response.send_message(content=f"`❌` You have already played in this game!", ephemeral=True)
        self.played.append(interaction.user.id)
        await interaction.response.send_message(content="`❌` Incorrect! Try again later!", ephemeral=True)
    
    @discord.ui.button(label="N/A", style=discord.ButtonStyle.grey, custom_id="math_button_wrong_2")
    async def math_button_wrong_2(self, interaction: discord.Interaction, Button: discord.ui.Button):
        if interaction.user.id in self.played:
            return await interaction.response.send_message(content=f"`❌` You have already played in this game!", ephemeral=True)
        self.played.append(interaction.user.id)
        await interaction.response.send_message(content="`❌` Incorrect! Try again later!", ephemeral=True)

async def setup(client:commands.Bot) -> None:
  await client.add_cog(MathQuiz(client))