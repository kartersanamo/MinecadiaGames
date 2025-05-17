from Assets.leveling_manager import LevelingManager
from Assets.functions import get_data, execute
from PIL import Image, ImageDraw, ImageFont
from discord.ext import commands
from discord import app_commands
from io import BytesIO
import requests
import discord
import random
import json
import os

class Level(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.data = get_data()
        with open('MinecadiaGames/Assets/Configs/levels.json') as file:
            self.level_data = json.load(file)

    async def get_stats(self, user_id:int) -> dict:
        rows = await execute(f"SELECT * FROM leveling WHERE `user_id`='{str(user_id)}'")
        if rows:
            return rows[0]
        return {
            "xp": 0,
            "level": 0
        }
    
    @app_commands.command(name="level", description="Sends a rank card for the user")
    @app_commands.describe(user="The user to send the statistics on")
    async def level(self, interaction: discord.Interaction, user: discord.Member=None):
        if interaction.guild is None:
            return await interaction.response.send_message(content="Commands cannot be ran in DMs!", ephemeral=True)
        await interaction.response.send_message(content="Sending your level card", ephemeral=True)
        if not user:
            user = interaction.user
        stats = await self.get_stats(user.id)
        if not stats:
            stats = {
                "xp": "0",
                "level": "0"
            }
        base_image_path = "MinecadiaGames/Assets/Images/RankCard.png"
        output_image_path = "MinecadiaGames/Assets/Images/Level.png"
        with Image.open(base_image_path) as base_image:
            mask = Image.new("L", (343, 343), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.ellipse((0, 0, 343, 343), fill=255, outline="#060e1a", width=12)
            if user.avatar:
                response = requests.get(user.avatar.url)
                if "gif" in user.avatar.url:
                    with Image.open(BytesIO(response.content)) as im:
                        im.seek(0)
                        im.save('MinecadiaGames/Assets/Images/Temp.png')
                    profile_picture = Image.open('MinecadiaGames/Assets/Images/Temp.png')
                else:
                    profile_picture = Image.open(BytesIO(response.content))
            else:
                profile_picture = Image.open('MinecadiaGames/Assets/Images/Default.png')
            profile_picture = profile_picture.convert("RGBA")
            profile_picture = profile_picture.resize(size=(343, 343))
            profile_picture.putalpha(mask)
            base_image.paste(profile_picture, (40, 47), profile_picture)
            draw = ImageDraw.Draw(base_image)
            font = ImageFont.truetype("MinecadiaGames/Assets/Fonts/BarlowCondensed-Black.ttf", 68)
            next_level = int(stats['level'])+1
            required_xp = self.level_data['LEVELS'][str(next_level)]
            draw.text((542, 197), f"{stats['xp']}/{required_xp}", font=font, fill="white", stroke_width=2, stroke_fill="black")
            draw.text((645, 269), f"{stats['level']}", font=font, fill="white", stroke_width=2, stroke_fill="black")
            draw.text((440, 430), f"@{user.name}", font=font, fill="white", stroke_width=2, stroke_fill="black")
            base_image.save(output_image_path)
        file = discord.File(output_image_path, filename="Level.png")
        await interaction.edit_original_response(content=None, attachments=[file])
        os.remove(output_image_path)
        if "gif" in user.avatar.url:
            os.remove("MinecadiaGames/Assets/Images/Temp.png")

    async def get_exp(self, max: int) -> int:
        return random.random() < max

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id in self.data['ANNOUNCE_CHANNELS']:
            if not message.author.bot:
                if await self.get_exp(0.24):
                    lvl_mng = LevelingManager(user= message.author, channel= message.channel, client = self.client, xp= 1, source= "Message Sent")
                    await lvl_mng.update()
    
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.Member):
        if reaction.message.channel.category:
            if reaction.message.channel.category.name == "News":
                if not user.bot:
                    if await self.get_exp(0.49):
                        lvl_mng = LevelingManager(user= reaction.message.author, channel= reaction.message.channel, client = self.client, xp= 3, source= "Reaction Added")
                        await lvl_mng.update()

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction: discord.Reaction, user: discord.Member):
        if reaction.message.channel.category:
            if reaction.message.channel.category.name == "News":
                lvl_mng = LevelingManager(user= reaction.message.author, channel= reaction.message.channel, client = self.client, xp= -3, source= "Reaction Removed")
                await lvl_mng.update()

async def setup(client:commands.Bot) -> None:
  await client.add_cog(Level(client))