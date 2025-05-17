from Assets.functions import get_data
from discord.ext import commands
from discord import app_commands
import discord


class MineSweeper(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client: commands.Bot = client

async def setup(client:commands.Bot) -> None:
  await client.add_cog(MineSweeper(client))