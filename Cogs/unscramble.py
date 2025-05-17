from Assets.leveling_manager import LevelingManager
from Assets.functions import get_data, chat_games, execute
from PIL import Image, ImageDraw, ImageFont
from discord.ext import commands
from discord import app_commands
import datetime
import asyncio
import discord
import random
import json
import os

class Unscramble(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.data = get_data()
        with open('MinecadiaGames/Assets/Configs/unscramble.json') as file:
            self.unscramble_data = json.load(file)
        self.game_length_in_seconds: int = 600

    async def get_image(self, scrambled: str):
        with Image.open("MinecadiaGames/Assets/Images/Unscramble_BG_2.png") as image:
            draw = ImageDraw.Draw(image)
            # word_font = ImageFont.truetype("MinecadiaGames/Assets/Fonts/ArcadeAlternate.ttf", 225)
            word_font = ImageFont.truetype("MinecadiaGames/Assets/Fonts/ArcadeRounded.ttf", 130)
            word_bbox = draw.textbbox((0, 0), scrambled, font=word_font, anchor="lt")
            word_middle_x = (image.width - (word_bbox[2] - word_bbox[0])) // 2
            word_middle_y = (image.height - (word_bbox[3] - word_bbox[1])) // 2
            draw.text((word_middle_x, word_middle_y), scrambled, font=word_font, fill="#F2D042", stroke_width=15, stroke_fill="#000000")
            image.save("unscramble.png")

    async def game(self, channel):
        try:
            refreshed_at: int = int(float(datetime.datetime.now(datetime.timezone.utc).timestamp()))
            await execute(f"INSERT INTO games (game_name, refreshed_at, dm_game) VALUES ('Unscramble', '{refreshed_at}', {False})")

            guild = self.client.get_guild(self.data['GUILD_ID'])
            role = guild.get_role(self.data['GAMES_ROLE'])
            if not channel:
                channel = self.client.get_channel(random.choice(self.unscramble_data['CHANNELS']))
            if channel.id in self.unscramble_data['CHANNELS']:
                word = random.choice(self.unscramble_data["WORDS"][str(channel.id)])
            else:
                word = random.choice(self.unscramble_data["WORDS"]["918903892144717915"])
            chat_games.info(f"Unscramble '{word}' #{channel.name}")
            scrambled = " ".join("".join(random.sample(w, len(w))) for w in word.split())
            await self.get_image(scrambled)
            current_unix: int = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
            double_xp: bool = random.random() <= 0.15
            game_embed = discord.Embed(
                title = "Unscramble" + (" (DOUBLE XP)" if double_xp else ""),
                color = discord.Color.from_str(self.data["EMBED_COLOR"]),
                description = f"This game will end <t:{current_unix + self.game_length_in_seconds}:R>",
                timestamp = datetime.datetime.now(datetime.timezone.utc)
            )
            file = discord.File("unscramble.png", filename="unscramble.png")
            game_embed.set_image(url="attachment://unscramble.png")
            game_message: discord.Message = await channel.send(content=role.mention, embed=game_embed, file=file)
            os.remove("unscramble.png")
            def check(m):
                return m.channel == channel and m.content.strip().lower() == word.strip().lower()
            try:
                msg = await self.client.wait_for('message', check = check, timeout = self.game_length_in_seconds)
            except asyncio.TimeoutError:
                game_embed.description = f"This game ended <t:{current_unix + self.game_length_in_seconds}:R>"
                await game_message.edit(embed = game_embed)
                embed = discord.Embed(
                    title = "Failed!",
                    description = f"No one got the answer in time, try again!",
                    color = discord.Color.from_str(self.data["EMBED_COLOR"]),
                    timestamp = datetime.datetime.now(datetime.timezone.utc)
                )
                return await channel.send(embed = embed)
            xp = random.randint(55, 70)
            if double_xp:
                xp *= 2
            
            await msg.reply(content = f"`✅` Correct! You have been awarded `{xp}xp`" + (" (2x XP)" if double_xp else "!"))
            current_unix: int = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
            game_embed.description = f"This game ended <t:{current_unix}:R>"
            game_embed.add_field(name = "Winner", value = f"`+{xp}xp` {msg.author}", inline = False)
            await game_message.edit(embed = game_embed)
            lvl_mng = LevelingManager(user= msg.author, channel= msg.channel, client = self.client, xp= xp, source = "Unscramble")
            await lvl_mng.update()
        except Exception as e:
            chat_games.error(f"Unscramble error {e}")

    @app_commands.command(name="unscramble", description="Sends the unscramble game")
    async def unscramble(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if interaction.guild is None:
            return await interaction.response.send_message(content="Commands cannot be ran in DMs!", ephemeral=True)
        await interaction.response.send_message(content="Sending the unscramble game!", ephemeral=True)
        await self.game(channel)

async def setup(client:commands.Bot) -> None:
  await client.add_cog(Unscramble(client))