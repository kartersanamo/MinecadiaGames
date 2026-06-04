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


class DMGamesManageView(discord.ui.View):
    """View for managing individual DM games"""
    def __init__(self, game_manager: GameManager, config, bot):
        super().__init__(timeout=None)
        self.game_manager = game_manager
        self.config = config
        self.bot = bot
        self.logger = get_logger("Commands")
        
        dm_config = config.get('dm_games')
        games_dict = dm_config.get('GAMES', {}) or dm_config.get('games', {})
        
        options = []
        for game_name in games_dict.keys():
            game_config = games_dict[game_name]
            enabled = game_config.get('enabled', True)
            status = "✅ Enabled" if enabled else "❌ Disabled"
            options.append(
                discord.SelectOption(
                    label=f"{game_name} ({status})",
                    value=game_name,
                    description=f"Toggle {game_name} in rotation"
                )
            )
        
        if options:
            select = discord.ui.Select(
                placeholder="Select a game to toggle...",
                options=options,
                custom_id="dm_games_manage_select",
                row=0
            )
            select.callback = self.game_select_callback
            self.add_item(select)
    
    async def game_select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        game_name = self.values[0]
        config = getattr(self, 'config', None) or ConfigManager.get_instance()
        dm_config = config.get('dm_games')
        games_dict = dm_config.get('GAMES', {}) or dm_config.get('games', {})
        
        if game_name not in games_dict:
            await interaction.followup.send(f"`❌` Game {game_name} not found.", ephemeral=True)
            return
        
        game_config = games_dict[game_name]
        current_enabled = game_config.get('enabled', True)
        new_enabled = not current_enabled
        
        # Update config
        if 'GAMES' in dm_config:
            config.set('dm_games', f'GAMES.{game_name}.enabled', new_enabled)
        else:
            config.set('dm_games', f'games.{game_name}.enabled', new_enabled)
        
        # Reload config
        config.reload('dm_games')
        self.game_manager.dm_config = config.get('dm_games')
        
        status = "enabled" if new_enabled else "disabled"
        await interaction.followup.send(f"`✅` {game_name} has been {status}.", ephemeral=True)
        
        # Refresh the manage view
        view = DMGamesManageView(self.game_manager, config, self.bot)
        embed = discord.Embed(
            title="⚙️ Manage DM Games",
            description="Select a game to enable/disable it from rotation.",
            color=discord.Color.from_str(config.get('config', 'EMBED_COLOR'))
        )
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(config.get('config', 'LOGO'))
        embed.set_footer(text=config.get('config', 'FOOTER'), icon_url=logo_url)
        if interaction.message:
            await interaction.message.edit(embed=embed, view=view)
