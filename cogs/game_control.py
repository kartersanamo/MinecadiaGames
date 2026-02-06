from discord.ext import commands
from discord import app_commands
import discord
from core.config.manager import ConfigManager
from managers.game_manager import GameManager
from core.logging.setup import get_logger


class GameControl(commands.Cog):
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
    
    @app_commands.command(name="toggle-chat-games", description="Toggle chat games on/off")
    async def toggle_chat_games(self, interaction: discord.Interaction):
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
        
        if game_manager.chat_game_running:
            game_manager.stop_chat_games()
            await interaction.response.send_message("`❌` Chat games have been stopped.", ephemeral=True)
        else:
            game_manager.start_chat_games()
            await interaction.response.send_message("`✅` Chat games have been started.", ephemeral=True)
    
    @app_commands.command(name="toggle-dm-games", description="Toggle DM games on/off")
    async def toggle_dm_games(self, interaction: discord.Interaction):
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
        
        if game_manager.dm_game_running:
            game_manager.stop_dm_games()
            await interaction.response.send_message("`❌` DM games have been stopped.", ephemeral=True)
        else:
            game_manager.start_dm_games()
            await interaction.response.send_message("`✅` DM games have been started.", ephemeral=True)
    
    @app_commands.command(name="game-status", description="View current game status")
    async def game_status(self, interaction: discord.Interaction):
        if not self._check_admin(interaction):
            await interaction.response.send_message("`❌` You don't have permission to use this command.", ephemeral=True)
            return
        
        game_manager = self.bot.game_manager
        if not game_manager:
            await interaction.response.send_message("`❌` Game manager not initialized.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="Game Status",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
        )
        embed.add_field(
            name="Chat Games",
            value="✅ Running" if game_manager.chat_game_running else "❌ Stopped",
            inline=False
        )
        embed.add_field(
            name="DM Games",
            value="✅ Running" if game_manager.dm_game_running else "❌ Stopped",
            inline=False
        )
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="force-chat-game", description="Force start a chat game immediately")
    @app_commands.describe(game="Which game to start")
    async def force_chat_game(
        self,
        interaction: discord.Interaction,
        game: str
    ):
        if not self._check_admin(interaction):
            await interaction.response.send_message("`❌` You don't have permission to use this command.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
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
        
        game_class = game_map.get(game.lower())
        if not game_class:
            await interaction.followup.send(f"`❌` Invalid game: {game}", ephemeral=True)
            return
        
        game_instance = game_class(self.bot)
        channel = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None
        msg = await game_instance.run(channel)
        
        if msg:
            await interaction.followup.send(f"`✅` Started {game} game!", ephemeral=True)
        else:
            await interaction.followup.send(f"`❌` Failed to start {game} game.", ephemeral=True)
    
    @force_chat_game.autocomplete('game')
    async def force_chat_game_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        games = ["unscramble", "flag_guesser", "math_quiz", "trivia", "emoji_quiz", "guess_the_number"]
        return [
            app_commands.Choice(name=game.replace('_', ' ').title(), value=game)
            for game in games if current.lower() in game.lower()
        ]


async def setup(bot):
    await bot.add_cog(GameControl(bot))

