from discord.ext import commands
from discord import app_commands
import discord
from core.config.manager import ConfigManager
from managers.game_manager import GameManager
from utils.paginator import Paginator
from utils.helpers import get_recent_games
from core.logging.setup import get_logger
from datetime import datetime, timezone
from typing import Optional
import asyncio
import random


class MainGameManagerView(discord.ui.View):
    """Main view with Chat Games and DM Games buttons"""
    def __init__(self, game_manager: GameManager, config):
        super().__init__(timeout=None)
        self.game_manager = game_manager
        self.config = config
        self.logger = get_logger("Commands")
        
        chat_button = discord.ui.Button(
            label="💬 Chat Games",
            style=discord.ButtonStyle.blurple,
            custom_id="main_chat_games",
            row=0
        )
        chat_button.callback = self.chat_games_callback
        self.add_item(chat_button)
        
        dm_button = discord.ui.Button(
            label="📱 DM Games",
            style=discord.ButtonStyle.green,
            custom_id="main_dm_games",
            row=0
        )
        dm_button.callback = self.dm_games_callback
        self.add_item(dm_button)
    
    async def chat_games_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cog = GameManagerCog(interaction.client)
        embed = await cog.create_chat_games_embed(self.game_manager)
        view = ChatGamesView(self.game_manager, self.config, interaction.client)
        interaction.client.add_view(view)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    async def dm_games_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cog = GameManagerCog(interaction.client)
        embed = await cog.create_dm_games_embed(self.game_manager)
        view = DMGamesManagerView(self.game_manager, self.config, interaction.client)
        interaction.client.add_view(view)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
