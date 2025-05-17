from Assets.leveling_manager import LevelingManager
from Assets.functions import get_data, chat_games, execute
from discord.ext import commands
from discord import app_commands
import datetime
import discord
import asyncio
import random
import json


class Trivia(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client: commands.Bot = client
        self.data: dict = get_data()
        self.trivia_data: dict = get_data("trivia")
        self.game_length_in_seconds: int = 600

    async def game(self, channel):
        try:
            refreshed_at: int = int(float(datetime.datetime.now(datetime.timezone.utc).timestamp()))
            await execute(f"INSERT INTO games (game_name, refreshed_at, dm_game) VALUES ('Trivia', '{refreshed_at}', {False})")

            guild = self.client.get_guild(self.data['GUILD_ID'])
            role = guild.get_role(self.data['GAMES_ROLE'])
            if not channel:
                channel = self.client.get_channel(random.choice(self.trivia_data['CHANNELS']))
            if channel.id == 935016733033525328:
                trivia = random.choice(self.trivia_data["QUESTIONS"]["918903892144717915"])
            else:
                trivia = random.choice(self.trivia_data["QUESTIONS"][str(channel.id)])
            chat_games.info(f"Trivia '{trivia['question']}' | '{trivia['answers'][0]}' #{channel.name}")
            current_unix: int = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
            double_xp: bool = random.random() <= 0.15
            embed = discord.Embed(
                title = "Trivia Question" + (" (DOUBLE XP)" if double_xp else ""),
                description = f"This game will end <t:{current_unix + self.game_length_in_seconds}:R>",
                color = discord.Color.from_str(self.data["EMBED_COLOR"]),
                timestamp = datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name = "Question", value = trivia["question"])
            view = TriviaButtons(trivia, double_xp)
            answers = [trivia['answers'][0], trivia['answers'][1], trivia['answers'][2], trivia['answers'][3]]
            items = []
            for index, button in enumerate(view.children):
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
                embed.add_field(name="Winners", value = val, inline = False)
                await msg.edit(view = None, embed = embed)
        except Exception as e:
            print(e)

    @app_commands.command(name="trivia", description="Sends the trivia game")
    async def trivia(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if interaction.guild is None:
            return await interaction.response.send_message(content="Commands cannot be ran in DMs!", ephemeral=True)
        await interaction.response.send_message(content="Sending the trivia game!", ephemeral=True)
        await self.game(channel)

class TriviaButtons(discord.ui.View):
    def __init__(self, trivia, double_xp) -> None:
        self.trivia = trivia
        self.double_xp: bool = double_xp
        super().__init__(timeout=None)
        self.played = []
        self.winners = []
        with open("MinecadiaGames/Assets/Configs/trivia.json", "r") as file:
            self.trivia_data = json.load(file)

    @discord.ui.button(label="N/A", style=discord.ButtonStyle.grey, custom_id="trivia_answer")
    async def trivia_button_answer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.played:
            await interaction.response.send_message(content="`❌` You have already played in this game!", ephemeral=True)
            return
        self.played.append(interaction.user.id)
        xp = random.randint(
            self.trivia_data['XP_LOWER'][str(len(self.winners) + 1)],
            self.trivia_data['XP_LOWER'][str(len(self.winners) + 1)] + self.trivia_data['XP_ADD']
        )
        if self.double_xp:
            xp *= 2
        self.winners.append(
            {'user': interaction.user,
             'xp': xp}
            )
        await interaction.response.send_message(content=f"`✅` Correct! You have been awarded `{xp}xp`" + (" (2x XP)" if self.double_xp else "!"), ephemeral=True)
        lvl_mng = LevelingManager(user= interaction.user, channel= interaction.channel, client = interaction.client, xp= xp, source= "Trivia")
        await lvl_mng.update()
        if len(self.winners) >= self.trivia_data['WINNERS']:
            embed = interaction.message.embeds[0]
            current_unix: int = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
            embed.description = f"This game ended <t:{current_unix}:R>"
            val = ""
            for winner in self.winners:
                val += f"`+{winner.get('xp')}xp` {winner.get('user')}\n"
            embed.add_field(name="Winners", value = val, inline = False)
            await interaction.message.edit(embed = embed, view = None)
    
    @discord.ui.button(label="N/A", style=discord.ButtonStyle.grey, custom_id="trivia_button_wrong_0")
    async def trivia_button_wrong_0(self, interaction: discord.Interaction, Button: discord.ui.Button):
        if interaction.user.id in self.played:
            return await interaction.response.send_message(content=f"`❌` You have already played in this game!", ephemeral=True)
        self.played.append(interaction.user.id)
        await interaction.response.send_message(content="`❌` Incorrect! Try again later!", ephemeral=True)
    
    @discord.ui.button(label="N/A", style=discord.ButtonStyle.grey, custom_id="trivia_button_wrong_1")
    async def trivia_button_wrong_1(self, interaction: discord.Interaction, Button: discord.ui.Button):
        if interaction.user.id in self.played:
            return await interaction.response.send_message(content=f"`❌` You have already played in this game!", ephemeral=True)
        self.played.append(interaction.user.id)
        await interaction.response.send_message(content="`❌` Incorrect! Try again later!", ephemeral=True)
    
    @discord.ui.button(label="N/A", style=discord.ButtonStyle.grey, custom_id="trivia_button_wrong_2")
    async def trivia_button_wrong_2(self, interaction: discord.Interaction, Button: discord.ui.Button):
        if interaction.user.id in self.played:
            return await interaction.response.send_message(content=f"`❌` You have already played in this game!", ephemeral=True)
        self.played.append(interaction.user.id)
        await interaction.response.send_message(content="`❌` Incorrect! Try again later!", ephemeral=True)

async def setup(client:commands.Bot) -> None:
  await client.add_cog(Trivia(client))