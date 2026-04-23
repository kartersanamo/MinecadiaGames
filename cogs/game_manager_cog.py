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


class GameManagerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Commands")
    
    def _check_admin(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        
        admin_roles = self.config.get('config', 'ADMIN_ROLES', [])
        user_roles = [role.name for role in interaction.user.roles]
        
        if "*" in admin_roles:
            return True
        
        return any(role in admin_roles for role in user_roles)
    
    @app_commands.command(name="game-manager", description="Manages the chat and dm games")
    async def game_manager(self, interaction: discord.Interaction):
        if not self._check_admin(interaction):
            await interaction.response.send_message("`❌` You don't have permission to use this command.", ephemeral=True)
            return
        
        if not interaction.guild:
            await interaction.response.send_message("`❌` This command can only be used in a server.", ephemeral=True)
            return
        
        game_manager = self.bot.game_manager
        if not game_manager:
            await interaction.response.send_message("`❌` Game manager not initialized.", ephemeral=True)
            return
        
        embed = await self.create_main_embed(game_manager)
        view = MainGameManagerView(game_manager, self.config)
        self.bot.add_view(view)
        await interaction.response.send_message(embed=embed, view=view)
    
    async def create_main_embed(self, game_manager: GameManager) -> discord.Embed:
        """Create the main game manager embed"""
        embed = discord.Embed(
            title="🎮 Game Manager",
            description="Manage all chat games and DM games from one place.",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
        )
        
        # Chat Games Status
        chat_status = "✅ **Enabled**" if game_manager.chat_game_running else "❌ **Disabled**"
        embed.add_field(
            name="💬 Chat Games",
            value=f"{chat_status}\nClick the button below to manage chat games.",
            inline=True
        )
        
        # DM Games Status
        dm_status = "✅ **Enabled**" if game_manager.dm_game_running else "❌ **Disabled**"
        embed.add_field(
            name="📱 DM Games",
            value=f"{dm_status}\nClick the button below to manage DM games.",
            inline=True
        )
        
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        return embed


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


class ChatGamesView(discord.ui.View):
    """Detailed Chat Games management view"""
    def __init__(self, game_manager: GameManager, config, bot):
        super().__init__(timeout=None)
        self.game_manager = game_manager
        self.config = config
        self.bot = bot
        self.logger = get_logger("Commands")
        
        # Toggle Chat Games button
        toggle_label = "❌ Disable Chat Games" if game_manager.chat_game_running else "✅ Enable Chat Games"
        toggle_style = discord.ButtonStyle.red if game_manager.chat_game_running else discord.ButtonStyle.green
        toggle_btn = discord.ui.Button(
            label=toggle_label,
            style=toggle_style,
            custom_id="chat_toggle_all",
            row=0
        )
        toggle_btn.callback = self.toggle_all_callback
        self.add_item(toggle_btn)
        
        # Force Send button
        force_btn = discord.ui.Button(
            label="⚡ Force Send Now",
            style=discord.ButtonStyle.blurple,
            custom_id="chat_force_send",
            row=0
        )
        force_btn.callback = self.force_send_callback
        self.add_item(force_btn)
        
        # Test Game button
        test_btn = discord.ui.Button(
            label="🧪 Test Game",
            style=discord.ButtonStyle.grey,
            custom_id="chat_test_game",
            row=0
        )
        test_btn.callback = self.test_game_callback
        self.add_item(test_btn)
        
        # Add Trivia button
        trivia_btn = discord.ui.Button(
            label="➕ Add Trivia",
            style=discord.ButtonStyle.green,
            custom_id="chat_add_trivia",
            row=1
        )
        trivia_btn.callback = self.add_trivia_callback
        self.add_item(trivia_btn)
        
        # Manage Games button (for individual game toggles)
        manage_btn = discord.ui.Button(
            label="⚙️ Manage Games",
            style=discord.ButtonStyle.grey,
            custom_id="chat_manage_games",
            row=1
        )
        manage_btn.callback = self.manage_games_callback
        self.add_item(manage_btn)
        
        # Recent Games button
        recent_btn = discord.ui.Button(
            label="📋 Recent Games",
            style=discord.ButtonStyle.grey,
            custom_id="chat_recent_games",
            row=1
        )
        recent_btn.callback = self.recent_games_callback
        self.add_item(recent_btn)
        
        # Back button
        back_btn = discord.ui.Button(
            label="⬅️ Back",
            style=discord.ButtonStyle.secondary,
            custom_id="chat_back",
            row=2
        )
        back_btn.callback = self.back_callback
        self.add_item(back_btn)
    
    async def toggle_all_callback(self, interaction: discord.Interaction):
        game_manager = getattr(self, 'game_manager', None) or getattr(interaction.client, 'game_manager', None)
        if not game_manager:
            await interaction.response.send_message("`❌` Game manager not available.", ephemeral=True)
            return
        
        if game_manager.chat_game_running:
            game_manager.stop_chat_games()
            await interaction.response.send_message("`❌` Chat games disabled.", ephemeral=True)
        else:
            game_manager.start_chat_games()
            await interaction.response.send_message("`✅` Chat games enabled.", ephemeral=True)
        
        await self.refresh_view(interaction)
    
    async def force_send_callback(self, interaction: discord.Interaction):
        game_manager = getattr(self, 'game_manager', None) or getattr(interaction.client, 'game_manager', None)
        if not game_manager:
            await interaction.response.send_message("`❌` Game manager not available.", ephemeral=True)
            return
        
        if not game_manager.chat_game_running:
            await interaction.response.send_message("`❌` Chat games are disabled. Enable them first.", ephemeral=True)
            return
        
        try:
            modal = ForceChatGameModal(game_manager, self.config, test_mode=False)
            await interaction.response.send_modal(modal)
        except Exception as e:
            self.logger.error(f"Error in force_send_callback: {e}")
            await interaction.response.send_message(f"`❌` Error: {str(e)}", ephemeral=True)
    
    async def test_game_callback(self, interaction: discord.Interaction):
        game_manager = getattr(self, 'game_manager', None) or getattr(interaction.client, 'game_manager', None)
        config = getattr(self, 'config', None) or ConfigManager.get_instance()
        if not game_manager:
            await interaction.response.send_message("`❌` Game manager not available.", ephemeral=True)
            return
        
        try:
            modal = ForceChatGameModal(game_manager, config, test_mode=True)
            await interaction.response.send_modal(modal)
        except Exception as e:
            self.logger.error(f"Error opening test game modal: {e}")
            await interaction.response.send_message(f"`❌` Error: {str(e)}", ephemeral=True)
    
    async def add_trivia_callback(self, interaction: discord.Interaction):
        try:
            config = getattr(self, 'config', None) or ConfigManager.get_instance()
            modal = AddTriviaModal(config)
            await interaction.response.send_modal(modal)
        except Exception as e:
            self.logger.error(f"Error in add_trivia_callback: {e}")
            await interaction.response.send_message(f"`❌` Error: {str(e)}", ephemeral=True)
    
    async def manage_games_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # Create a select menu view for managing individual games
        view = ChatGamesManageView(self.game_manager, self.config, self.bot)
        embed = discord.Embed(
            title="⚙️ Manage Chat Games",
            description="Select a game to enable/disable it from rotation.",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
        )
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        interaction.client.add_view(view)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    async def recent_games_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            from utils.helpers import get_recent_games
            from core.database.pool import DatabasePool
            
            games_str, games_list = await get_recent_games()
            db = await DatabasePool.get_instance()
            game_ids = await db.execute(
                "SELECT game_id, game_name, refreshed_at, dm_game FROM games ORDER BY refreshed_at DESC LIMIT 100"
            )
            
            if not games_str:
                await interaction.followup.send("No recent games found.", ephemeral=True)
                return
            
            paginator = Paginator(timeout=None)
            paginator.title = "Recent Games"
            paginator.data = games_str
            paginator.games = games_list
            paginator.game_ids = game_ids
            paginator.sep = 15
            paginator.ephemeral = True
            paginator.game_manager = self.game_manager
            paginator.config = self.config
            paginator.bot = self.bot
            paginator.timeout = None
            
            msg = await paginator.send(interaction)
            # Note: Don't register ephemeral views as persistent - ephemeral messages are user-specific and temporary
        except Exception as e:
            self.logger.error(f"Error in recent_games_callback: {e}")
            await interaction.followup.send(f"`❌` Error: {str(e)}", ephemeral=True)
    
    async def back_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cog = GameManagerCog(interaction.client)
        embed = await cog.create_main_embed(self.game_manager)
        view = MainGameManagerView(self.game_manager, self.config)
        interaction.client.add_view(view)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    async def refresh_view(self, interaction: discord.Interaction):
        """Refresh the current view"""
        try:
            if interaction.message:
                cog = GameManagerCog(interaction.client)
                embed = await cog.create_chat_games_embed(self.game_manager)
                view = ChatGamesView(self.game_manager, self.config, interaction.client)
                interaction.client.add_view(view)
                await interaction.message.edit(embed=embed, view=view)
        except Exception as e:
            self.logger.error(f"Error refreshing view: {e}")


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


class DMGamesManagerView(discord.ui.View):
    """Detailed DM Games management view"""
    def __init__(self, game_manager: GameManager, config, bot):
        super().__init__(timeout=None)
        self.game_manager = game_manager
        self.config = config
        self.bot = bot
        self.logger = get_logger("Commands")
        
        # Toggle DM Games button
        toggle_label = "❌ Disable DM Games" if game_manager.dm_game_running else "✅ Enable DM Games"
        toggle_style = discord.ButtonStyle.red if game_manager.dm_game_running else discord.ButtonStyle.green
        toggle_btn = discord.ui.Button(
            label=toggle_label,
            style=toggle_style,
            custom_id="dm_toggle_all",
            row=0
        )
        toggle_btn.callback = self.toggle_all_callback
        self.add_item(toggle_btn)
        
        # Force Refresh button
        force_btn = discord.ui.Button(
            label="⚡ Force Refresh Now",
            style=discord.ButtonStyle.blurple,
            custom_id="dm_force_refresh",
            row=0
        )
        force_btn.callback = self.force_refresh_callback
        self.add_item(force_btn)
        
        # Test Game button
        test_btn = discord.ui.Button(
            label="🧪 Test Game",
            style=discord.ButtonStyle.grey,
            custom_id="dm_test_game",
            row=0
        )
        test_btn.callback = self.test_game_callback
        self.add_item(test_btn)
        
        # Manage Games button
        manage_btn = discord.ui.Button(
            label="⚙️ Manage Games",
            style=discord.ButtonStyle.grey,
            custom_id="dm_manage_games",
            row=1
        )
        manage_btn.callback = self.manage_games_callback
        self.add_item(manage_btn)
        
        # Recent Games button
        recent_btn = discord.ui.Button(
            label="📋 Recent Games",
            style=discord.ButtonStyle.grey,
            custom_id="dm_recent_games",
            row=1
        )
        recent_btn.callback = self.recent_games_callback
        self.add_item(recent_btn)
        
        # Back button
        back_btn = discord.ui.Button(
            label="⬅️ Back",
            style=discord.ButtonStyle.secondary,
            custom_id="dm_back",
            row=2
        )
        back_btn.callback = self.back_callback
        self.add_item(back_btn)
    
    async def toggle_all_callback(self, interaction: discord.Interaction):
        game_manager = getattr(self, 'game_manager', None) or getattr(interaction.client, 'game_manager', None)
        if not game_manager:
            await interaction.response.send_message("`❌` Game manager not available.", ephemeral=True)
            return
        
        if game_manager.dm_game_running:
            game_manager.stop_dm_games()
            await interaction.response.send_message("`❌` DM games disabled.", ephemeral=True)
        else:
            game_manager.start_dm_games()
            await interaction.response.send_message("`✅` DM games enabled.", ephemeral=True)
        
        await self.refresh_view(interaction)
    
    async def force_refresh_callback(self, interaction: discord.Interaction):
        game_manager = getattr(self, 'game_manager', None) or getattr(interaction.client, 'game_manager', None)
        if not game_manager:
            await interaction.response.send_message("`❌` Game manager not available.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        if not game_manager.dm_game_running:
            await interaction.followup.send("`❌` DM games are disabled. Enable them first.", ephemeral=True)
            return
        
        next_game = await game_manager.force_cycle_dm_game()
        if next_game:
            await interaction.followup.send(f"`✅` Successfully cycled to: **{next_game}**", ephemeral=True)
        else:
            await interaction.followup.send("`❌` Failed to cycle DM game.", ephemeral=True)
        
        await self.refresh_view(interaction)
    
    async def test_game_callback(self, interaction: discord.Interaction):
        game_manager = getattr(self, 'game_manager', None) or getattr(interaction.client, 'game_manager', None)
        config = getattr(self, 'config', None) or ConfigManager.get_instance()
        if not game_manager:
            await interaction.response.send_message("`❌` Game manager not available.", ephemeral=True)
            return
        
        view = TestDMGameSelectorView(game_manager, config, interaction.client, interaction.user)
        embed = discord.Embed(
            title="🧪 Test DM Game",
            description="Select which DM game you want to test:",
            color=discord.Color.from_str(config.get('config', 'EMBED_COLOR'))
        )
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(config.get('config', 'LOGO'))
        embed.set_footer(text=config.get('config', 'FOOTER'), icon_url=logo_url)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    async def manage_games_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        view = DMGamesManageView(self.game_manager, self.config, self.bot)
        embed = discord.Embed(
            title="⚙️ Manage DM Games",
            description="Select a game to enable/disable it from rotation.",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
        )
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        interaction.client.add_view(view)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    async def recent_games_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            from utils.helpers import get_recent_games
            from core.database.pool import DatabasePool
            
            games_str, games_list = await get_recent_games()
            db = await DatabasePool.get_instance()
            game_ids = await db.execute(
                "SELECT game_id, game_name, refreshed_at, dm_game FROM games ORDER BY refreshed_at DESC LIMIT 100"
            )
            
            if not games_str:
                await interaction.followup.send("No recent games found.", ephemeral=True)
                return
            
            paginator = Paginator(timeout=None)
            paginator.title = "Recent Games"
            paginator.data = games_str
            paginator.games = games_list
            paginator.game_ids = game_ids
            paginator.sep = 15
            paginator.ephemeral = True
            paginator.game_manager = self.game_manager
            paginator.config = self.config
            paginator.bot = self.bot
            paginator.timeout = None
            
            msg = await paginator.send(interaction)
            # Note: Don't register ephemeral views as persistent - ephemeral messages are user-specific and temporary
        except Exception as e:
            self.logger.error(f"Error in recent_games_callback: {e}")
            await interaction.followup.send(f"`❌` Error: {str(e)}", ephemeral=True)
    
    async def back_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cog = GameManagerCog(interaction.client)
        embed = await cog.create_main_embed(self.game_manager)
        view = MainGameManagerView(self.game_manager, self.config)
        interaction.client.add_view(view)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    async def refresh_view(self, interaction: discord.Interaction):
        """Refresh the current view"""
        try:
            if interaction.message:
                cog = GameManagerCog(interaction.client)
                embed = await cog.create_dm_games_embed(self.game_manager)
                view = DMGamesManagerView(self.game_manager, self.config, interaction.client)
                interaction.client.add_view(view)
                await interaction.message.edit(embed=embed, view=view)
        except Exception as e:
            self.logger.error(f"Error refreshing view: {e}")


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


# Add helper methods to GameManagerCog for creating embeds
async def create_chat_games_embed(self, game_manager: GameManager) -> discord.Embed:
    """Create detailed Chat Games embed"""
    chat_config = self.config.get('chat_games')
    db = await game_manager._get_db()
    
    # Get last chat game
    last_chat = await db.execute(
        "SELECT game_name, refreshed_at FROM games WHERE dm_game = FALSE ORDER BY refreshed_at DESC LIMIT 1"
    )
    last_game_name = last_chat[0]['game_name'] if last_chat else "None"
    last_refresh_raw = last_chat[0]['refreshed_at'] if last_chat else 0
    last_refresh = int(last_refresh_raw) if last_refresh_raw else 0
    
    # Calculate next game time
    now = int(datetime.now(timezone.utc).timestamp())
    delay_config = chat_config.get('DELAY', {}) or chat_config.get('delay', {})
    min_delay = delay_config.get('LOWER') or delay_config.get('min_seconds', 1500)
    max_delay = delay_config.get('UPPER') or delay_config.get('max_seconds', 2100)
    avg_delay = int((min_delay + max_delay) / 2)
    
    time_since_last = now - last_refresh if last_refresh else 0
    next_game_time = int(last_refresh + avg_delay) if last_refresh else now
    
    # Status
    status = "✅ **Enabled**" if game_manager.chat_game_running else "❌ **Disabled**"
    
    # Enabled games (all are enabled in code)
    enabled_games = ["Unscramble", "Flag Guesser", "Math Quiz", "Trivia", "Emoji Quiz", "Guess The Number"]
    
    # Channels
    channels_config = chat_config.get('CHANNELS', {}) or chat_config.get('channels', {})
    active_channels = []
    for name, info in channels_config.items():
        weight = info.get('weight', 0.0) or info.get('CHANCE', 0.0)
        if weight > 0:
            channel_id = info.get('id') or info.get('CHANNEL_ID')
            active_channels.append(f"<#{channel_id}> ({weight*100:.0f}%)")
    
    embed = discord.Embed(
        title="💬 Chat Games Management",
        description="Manage all chat game settings and controls.",
        color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
    )
    
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(
        name="Next Game",
        value=f"<t:{int(next_game_time)}:R>" if next_game_time > now else "**Now**",
        inline=True
    )
    embed.add_field(name="Last Game", value=last_game_name, inline=True)
    
    embed.add_field(
        name="Enabled Games",
        value=", ".join(enabled_games),
        inline=False
    )
    
    if active_channels:
        embed.add_field(
            name="Active Channels",
            value="\n".join(active_channels[:5]),  # Limit to 5
            inline=True
        )
    
    delay_text = f"{min_delay//60}-{max_delay//60} minutes"
    game_length = chat_config.get('GAME_LENGTH') or chat_config.get('game_duration', 600)
    embed.add_field(
        name="Settings",
        value=f"Delay: {delay_text}\nDuration: {game_length//60} min",
        inline=True
    )
    
    from utils.helpers import get_embed_logo_url
    logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
    embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
    return embed


async def create_dm_games_embed(self, game_manager: GameManager) -> discord.Embed:
    """Create detailed DM Games embed"""
    config = ConfigManager.get_instance()
    dm_config = config.get('dm_games')
    db = await game_manager._get_db()
    
    # Get last DM game
    last_dm = await db.execute(
        "SELECT game_name, refreshed_at FROM games WHERE dm_game = TRUE ORDER BY refreshed_at DESC LIMIT 1"
    )
    current_game = last_dm[0]['game_name'] if last_dm else "None"
    last_refresh_raw = last_dm[0]['refreshed_at'] if last_dm else 0
    last_refresh = int(last_refresh_raw) if last_refresh_raw else 0
    
    # Calculate next refresh time
    now = int(datetime.now(timezone.utc).timestamp())
    delay = dm_config.get('DELAY') or dm_config.get('rotation_delay', 7200)
    next_refresh_time = last_refresh + delay if last_refresh else now
    
    # Status
    status = "✅ **Enabled**" if game_manager.dm_game_running else "❌ **Disabled**"
    
    # Enabled games
    games_dict = dm_config.get('GAMES', {}) or dm_config.get('games', {})
    enabled_games = []
    disabled_games = []
    for game_name, game_config in games_dict.items():
        if game_config.get('enabled', True):
            enabled_games.append(game_name)
        else:
            disabled_games.append(game_name)
    
    embed = discord.Embed(
        title="📱 DM Games Management",
        description="Manage all DM game settings and controls.",
        color=discord.Color.from_str(config.get('config', 'EMBED_COLOR'))
    )
    
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(
        name="Next Refresh",
        value=f"<t:{int(next_refresh_time)}:R>" if next_refresh_time > now else "**Now**",
        inline=True
    )
    embed.add_field(name="Current Game", value=f"**{current_game}**", inline=True)
    
    if enabled_games:
        embed.add_field(
            name="✅ Enabled Games",
            value=", ".join(enabled_games),
            inline=False
        )
    
    if disabled_games:
        embed.add_field(
            name="❌ Disabled Games",
            value=", ".join(disabled_games),
            inline=False
        )
    
    delay_minutes = delay // 60
    button_cd = dm_config.get('BUTTON_COOLDOWN') or dm_config.get('button_cooldown', 0.8)
    embed.add_field(
        name="Settings",
        value=f"Rotation Delay: {delay_minutes} min\nButton Cooldown: {button_cd}s",
        inline=True
    )
    
    from utils.helpers import get_embed_logo_url
    logo_url = get_embed_logo_url(config.get('config', 'LOGO'))
    embed.set_footer(text=config.get('config', 'FOOTER'), icon_url=logo_url)
    return embed


# Add methods to GameManagerCog class
GameManagerCog.create_chat_games_embed = create_chat_games_embed
GameManagerCog.create_dm_games_embed = create_dm_games_embed


# Missing modal and view classes
class ForceChatGameModal(discord.ui.Modal, title="Force Send Chat Game"):
    def __init__(self, game_manager: GameManager, config, test_mode: bool = False):
        super().__init__()
        self.game_manager = game_manager
        self.config = config
        self.test_mode = test_mode
        if test_mode:
            self.title = "Test Chat Game"
        
        self.game_type = discord.ui.TextInput(
            label="Game Type",
            placeholder="unscramble, flag_guesser, math_quiz, trivia, emoji_quiz, guess_the_number",
            default="trivia",
            required=True,
            max_length=20
        )
        self.add_item(self.game_type)
        
        self.xp_multiplier = discord.ui.TextInput(
            label="XP Multiplier",
            placeholder="1.0 (normal), 2.0 (double), 3.0 (triple), etc.",
            default="1.0",
            required=True,
            max_length=10
        )
        self.add_item(self.xp_multiplier)
        
        default_channel_id = "935016733033525328" if test_mode else ""
        self.channel_id = discord.ui.TextInput(
            label="Channel ID (optional)",
            placeholder="Leave empty to use random channel" if not test_mode else "Test channel ID",
            default=default_channel_id,
            required=False,
            max_length=20
        )
        self.add_item(self.channel_id)
        
        self.custom_data = discord.ui.TextInput(
            label="Custom Game Data (optional)",
            placeholder="Trivia: Q|A,W1,W2,W3 | Emoji: Cat|Emojis|A|W1,W2,W3",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=1000
        )
        self.add_item(self.custom_data)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            from games.chat.unscramble import Unscramble
            from games.chat.flag_guesser import FlagGuesser
            from games.chat.math_quiz import MathQuiz
            from games.chat.trivia import Trivia
            from games.chat.emoji_quiz import EmojiQuiz
            from games.chat.guess_the_number import GuessTheNumber
            
            game_map = {
                "unscramble": Unscramble,
                "flag_guesser": FlagGuesser,
                "math_quiz": MathQuiz,
                "trivia": Trivia,
                "emoji_quiz": EmojiQuiz,
                "guess_the_number": GuessTheNumber
            }
            
            game_type = self.game_type.value.lower().strip()
            game_class = game_map.get(game_type)
            
            if not game_class:
                await interaction.followup.send(
                    f"`❌` Invalid game type. Use: unscramble, flag_guesser, math_quiz, trivia, emoji_quiz, or guess_the_number",
                    ephemeral=True
                )
                return
            
            try:
                xp_mult = float(self.xp_multiplier.value)
            except ValueError:
                await interaction.followup.send("`❌` Invalid XP multiplier. Use a number like 1.0, 2.0, etc.", ephemeral=True)
                return
            
            channel_id = self.channel_id.value.strip() if self.channel_id.value.strip() else None
            channel = None
            if channel_id:
                try:
                    channel = interaction.client.get_channel(int(channel_id))
                    if not channel:
                        await interaction.followup.send(f"`❌` Channel {channel_id} not found.", ephemeral=True)
                        return
                except ValueError:
                    await interaction.followup.send("`❌` Invalid channel ID.", ephemeral=True)
                    return
            
            custom_data = self.custom_data.value.strip() if self.custom_data.value.strip() else None
            
            game = game_class(interaction.client)
            if custom_data and game_type in ["trivia", "emoji_quiz"]:
                if game_type == "trivia":
                    parts = custom_data.split("|")
                    if len(parts) >= 2:
                        question = parts[0].strip()
                        answers_part = parts[1].strip()
                        wrong_answers = [a.strip() for a in answers_part.split(",")]
                        if len(wrong_answers) >= 3:
                            custom_trivia = {
                                "question": question,
                                "answers": [wrong_answers[0]] + wrong_answers[:3]
                            }
                            msg = await game.run(channel, custom_trivia=custom_trivia, xp_multiplier=xp_mult, test_mode=self.test_mode)
                        else:
                            await interaction.followup.send("`❌` Need at least 3 wrong answers (comma-separated).", ephemeral=True)
                            return
                    else:
                        await interaction.followup.send("`❌` Format: Question|CorrectAnswer,Wrong1,Wrong2,Wrong3", ephemeral=True)
                        return
                elif game_type == "emoji_quiz":
                    parts = custom_data.split("|")
                    if len(parts) >= 4:
                        category = parts[0].strip()
                        emojis = parts[1].strip()
                        answer = parts[2].strip()
                        wrong_answers = [a.strip() for a in parts[3].split(",")]
                        if len(wrong_answers) >= 3:
                            custom_question = {
                                "category": category,
                                "emojis": emojis,
                                "answer": answer,
                                "wrong_answers": wrong_answers[:3]
                            }
                            msg = await game.run(channel, custom_question=custom_question, xp_multiplier=xp_mult, test_mode=self.test_mode)
                        else:
                            await interaction.followup.send("`❌` Need at least 3 wrong answers (comma-separated).", ephemeral=True)
                            return
                    else:
                        await interaction.followup.send("`❌` Format: Category|Emojis|Answer|Wrong1,Wrong2,Wrong3", ephemeral=True)
                        return
                else:
                    msg = await game.run(channel, xp_multiplier=xp_mult, test_mode=self.test_mode)
            else:
                msg = await game.run(channel, xp_multiplier=xp_mult, test_mode=self.test_mode)
            
            if msg:
                mode_text = "test " if self.test_mode else ""
                await interaction.followup.send(f"`✅` {mode_text.capitalize()}Chat game sent!", ephemeral=True)
            else:
                await interaction.followup.send(f"`❌` Failed to send chat game.", ephemeral=True)
        except Exception as e:
            logger = get_logger("Commands")
            logger.error(f"Error in ForceChatGameModal: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await interaction.followup.send(f"`❌` Error: {str(e)}", ephemeral=True)


class AddTriviaModal(discord.ui.Modal, title="Add Trivia Question"):
    def __init__(self, config):
        super().__init__()
        self.config = config
        
        self.question = discord.ui.TextInput(
            label="Question",
            placeholder="Enter the trivia question",
            required=True,
            max_length=200
        )
        self.add_item(self.question)
        
        self.answer = discord.ui.TextInput(
            label="Correct Answer",
            placeholder="Enter the correct answer",
            required=True,
            max_length=100
        )
        self.add_item(self.answer)
        
        self.wrong_answers = discord.ui.TextInput(
            label="Wrong Answers (comma-separated)",
            placeholder="Wrong answer 1, Wrong answer 2, Wrong answer 3",
            required=True,
            max_length=300
        )
        self.add_item(self.wrong_answers)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            import json
            from pathlib import Path
            
            question = self.question.value.strip()
            answer = self.answer.value.strip()
            wrong_answers_str = self.wrong_answers.value.strip()
            wrong_answers = [a.strip() for a in wrong_answers_str.split(",")]
            
            if len(wrong_answers) < 3:
                await interaction.followup.send("`❌` Please provide at least 3 wrong answers (comma-separated).", ephemeral=True)
                return
            
            # Load trivia config
            project_root = Path(__file__).parent.parent
            trivia_file = project_root / "assets" / "Configs" / "games" / "trivia.json"
            
            if not trivia_file.exists():
                await interaction.followup.send("`❌` Trivia config file not found.", ephemeral=True)
                return
            
            with open(trivia_file, 'r', encoding='utf-8') as f:
                trivia_data = json.load(f)
            
            questions_dict = trivia_data.get('questions', {})
            
            # Get the first channel ID from questions, or use the first ANNOUNCE_CHANNEL as default
            if not questions_dict:
                # Use first announce channel as default
                announce_channels = self.config.get('config', 'ANNOUNCE_CHANNELS', [])
                default_channel_id = str(announce_channels[0]) if announce_channels else "918903892144717915"
                questions_dict[default_channel_id] = []
            
            # Use the first channel ID in the questions dict
            channel_id = list(questions_dict.keys())[0]
            
            # Get or create the questions list for this channel
            if channel_id not in questions_dict:
                questions_dict[channel_id] = []
            questions_list = questions_dict[channel_id]
            
            new_question = {
                "question": question,
                "answers": [answer] + wrong_answers[:3],
                "difficulty": 1.5  # Default difficulty
            }
            
            questions_list.append(new_question)
            trivia_data['questions'] = questions_dict
            
            with open(trivia_file, 'w', encoding='utf-8') as f:
                json.dump(trivia_data, f, indent=4, ensure_ascii=False)
            
            # Reload config
            self.config.reload('games/trivia')
            
            await interaction.followup.send("`✅` Trivia question added successfully!", ephemeral=True)
        except Exception as e:
            logger = get_logger("Commands")
            logger.error(f"Error in AddTriviaModal: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await interaction.followup.send(f"`❌` Error: {str(e)}", ephemeral=True)


class TestDMGameSelectorView(discord.ui.View):
    def __init__(self, game_manager: GameManager, config: ConfigManager, bot, user: discord.User):
        super().__init__(timeout=300)
        self.game_manager = game_manager
        self.config = config
        self.bot = bot
        self.user = user
        
        options = [
            discord.SelectOption(
                label="Wordle",
                value="wordle",
                description="Test Wordle game",
                emoji="🔤"
            ),
            discord.SelectOption(
                label="TicTacToe",
                value="tictactoe",
                description="Test TicTacToe game",
                emoji="❌"
            ),
            discord.SelectOption(
                label="Connect Four",
                value="connect four",
                description="Test Connect Four game",
                emoji="🔴"
            ),
            discord.SelectOption(
                label="Memory",
                value="memory",
                description="Test Memory game",
                emoji="🧠"
            ),
            discord.SelectOption(
                label="2048",
                value="2048",
                description="Test 2048 game",
                emoji="🔢"
            ),
            discord.SelectOption(
                label="Minesweeper",
                value="minesweeper",
                description="Test Minesweeper game",
                emoji="💣"
            ),
            discord.SelectOption(
                label="Hangman",
                value="hangman",
                description="Test Hangman game",
                emoji="🪢"
            )
        ]
        
        select = TestDMGameSelect(self, options)
        self.add_item(select)


class TestDMGameSelect(discord.ui.Select):
    def __init__(self, parent_view: TestDMGameSelectorView, options: list):
        self.parent_view = parent_view
        super().__init__(
            placeholder="Select a DM game to test...",
            options=options,
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.user.id:
            await interaction.response.send_message("This test game selector is not for you!", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        game_name = self.values[0]
        
        from games.dm.wordle import Wordle
        from games.dm.tictactoe import TicTacToe
        from games.dm.connect_four import ConnectFour
        from games.dm.memory import Memory
        from games.dm.twenty_forty_eight import TwentyFortyEight
        from games.dm.minesweeper import Minesweeper
        from games.dm.hangman import Hangman
        
        game_map = {
            "wordle": ("Wordle", Wordle),
            "tictactoe": ("TicTacToe", TicTacToe),
            "connect four": ("Connect Four", ConnectFour),
            "memory": ("Memory", Memory),
            "2048": ("2048", TwentyFortyEight),
            "minesweeper": ("Minesweeper", Minesweeper),
            "hangman": ("Hangman", Hangman)
        }
        
        game_display_name, game_class = game_map.get(game_name.lower(), (None, None))
        if not game_class:
            await interaction.followup.send(f"`❌` Unknown DM game: {game_name}", ephemeral=True)
            return
        
        try:
            # Use the game manager's instance instead of creating a new one
            # This ensures the game's active_games dict is shared with the listener
            logger = get_logger("Commands")
            if interaction.client.game_manager and hasattr(interaction.client.game_manager, 'dm_games'):
                game = interaction.client.game_manager.dm_games.get(game_display_name)
                logger.info(f"Using game_manager instance for {game_display_name}: {id(game)}")
                if not game:
                    # Fallback: create new instance if not found
                    logger.warning(f"Game not found in game_manager, creating new instance")
                    game = game_class(interaction.client)
            else:
                # Fallback: create new instance if game_manager not available
                logger.warning(f"game_manager not available, creating new instance")
                game = game_class(interaction.client)
            
            success = await game.run(interaction.user, game_display_name, test_mode=True)
            
            if success:
                await interaction.followup.send(f"`✅` Test {game_display_name} game sent to your DMs!", ephemeral=True)
            else:
                error_msg = game.last_error if hasattr(game, 'last_error') and game.last_error else "Failed to start game"
                await interaction.followup.send(f"`❌` {error_msg}", ephemeral=True)
        except Exception as e:
            logger = get_logger("Commands")
            logger.error(f"Error running test DM game {game_name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await interaction.followup.send(f"`❌` Error running test game: {str(e)}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(GameManagerCog(bot))
