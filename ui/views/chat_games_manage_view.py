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


class ChatGamesManageView(discord.ui.View):
    """View for managing individual chat games"""
    def __init__(self, game_manager: GameManager, config, bot):
        super().__init__(timeout=None)
        self.game_manager = game_manager
        self.config = config
        self.bot = bot
        self.logger = get_logger("Commands")
        
        # Chat games are hardcoded in the loop, so we show them all as enabled
        # This is a placeholder - individual game toggling would require code changes
        games = ["Unscramble", "Flag Guesser", "Math Quiz", "Trivia", "Emoji Quiz", "Guess The Number"]
        
        select = discord.ui.Select(
            placeholder="Select a game to toggle...",
            options=[
                discord.SelectOption(
                    label=game,
                    value=game.lower().replace(" ", "_"),
                    description=f"Toggle {game} in rotation"
                ) for game in games
            ],
            custom_id="chat_games_manage_select",
            row=0
        )
        select.callback = self.game_select_callback
        self.add_item(select)
    
    async def game_select_callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "`ℹ️` Individual game toggling is not yet implemented. All chat games are always enabled in rotation.",
            ephemeral=True
        )
