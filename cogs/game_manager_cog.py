from discord.ext import commands
from discord import app_commands
import discord
from core.config.manager import ConfigManager
from managers.game_manager import GameManager
from core.logging.setup import get_logger
from ui.views.main_game_manager_view import MainGameManagerView

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
        
        logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        return embed


async def setup(bot):
    await bot.add_cog(GameManagerCog(bot))
