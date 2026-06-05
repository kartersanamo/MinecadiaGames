import discord
from core.config.manager import ConfigManager
from managers.game_manager import GameManager
from ui.paginator import Paginator
from core.logging.setup import get_logger

from ui.views.chat_games_manage_view import ChatGamesManageView
from ui.views.main_game_manager_view import MainGameManagerView


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
        logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        interaction.client.add_view(view)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    async def recent_games_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            from core.database.pool import DatabasePool

            games_str, games_list = await self.bot.app.games.get_recent_games()
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
        from cogs.game_manager_cog import GameManagerCog

        cog = GameManagerCog(interaction.client)
        embed = await cog.create_main_embed(self.game_manager)
        view = MainGameManagerView(self.game_manager, self.config)
        interaction.client.add_view(view)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    async def refresh_view(self, interaction: discord.Interaction):
        """Refresh the current view"""
        try:
            if interaction.message:
                from cogs.game_manager_cog import GameManagerCog

                cog = GameManagerCog(interaction.client)
                embed = await cog.create_chat_games_embed(self.game_manager)
                view = ChatGamesView(self.game_manager, self.config, interaction.client)
                interaction.client.add_view(view)
                await interaction.message.edit(embed=embed, view=view)
        except Exception as e:
            self.logger.error(f"Error refreshing view: {e}")
