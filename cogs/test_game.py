from discord.ext import commands
from discord import app_commands
import discord
from core.config.manager import ConfigManager
from managers.game_manager import GameManager
from core.logging.setup import get_logger
from typing import Optional


class TestGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Commands")
    
    def _check_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user has admin permissions"""
        if not interaction.guild:
            return False
        
        admin_roles = self.config.get('config', 'ADMIN_ROLES', [])
        user_roles = [role.name for role in interaction.user.roles]
        
        if "*" in admin_roles:
            return True
        
        return any(role in admin_roles for role in user_roles)
    
    @app_commands.command(name="test-game", description="Test a game (chat or DM game)")
    @app_commands.describe(
        game_type="The type of game to test",
        channel="Channel to send chat game to (optional, leave empty for random)",
        xp_multiplier="XP multiplier (default: 1.0)"
    )
    @app_commands.choices(game_type=[
        app_commands.Choice(name="Trivia", value="trivia"),
        app_commands.Choice(name="Math Quiz", value="math_quiz"),
        app_commands.Choice(name="Flag Guesser", value="flag_guesser"),
        app_commands.Choice(name="Unscramble", value="unscramble"),
        app_commands.Choice(name="Emoji Quiz", value="emoji_quiz"),
        app_commands.Choice(name="Guess The Number", value="guess_the_number"),
        app_commands.Choice(name="Wordle", value="wordle"),
        app_commands.Choice(name="TicTacToe", value="tictactoe"),
        app_commands.Choice(name="Connect Four", value="connect_four"),
        app_commands.Choice(name="Memory", value="memory"),
        app_commands.Choice(name="2048", value="2048"),
        app_commands.Choice(name="Minesweeper", value="minesweeper"),
        app_commands.Choice(name="Hangman", value="hangman"),
    ])
    async def test_game(
        self,
        interaction: discord.Interaction,
        game_type: app_commands.Choice[str],
        channel: Optional[discord.TextChannel] = None,
        xp_multiplier: Optional[float] = 1.0
    ):
        if not self._check_admin(interaction):
            await interaction.response.send_message("`❌` You don't have permission to use this command.", ephemeral=True)
            return
        
        if interaction.guild is None:
            await interaction.response.send_message("`❌` This command can only be used in a server.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        game_value = game_type.value
        game_name_map = {
            "trivia": "Trivia",
            "math_quiz": "Math Quiz",
            "flag_guesser": "Flag Guesser",
            "unscramble": "Unscramble",
            "emoji_quiz": "Emoji Quiz",
            "guess_the_number": "Guess The Number",
            "wordle": "Wordle",
            "tictactoe": "TicTacToe",
            "connect_four": "Connect Four",
            "memory": "Memory",
            "2048": "2048",
            "minesweeper": "Minesweeper",
            "hangman": "Hangman"
        }
        
        game_display_name = game_name_map.get(game_value, game_value)
        
        # Determine if it's a chat game or DM game
        chat_games = ["trivia", "math_quiz", "flag_guesser", "unscramble", "emoji_quiz"]
        is_chat_game = game_value in chat_games
        
        try:
            if is_chat_game:
                # Handle chat games
                if not channel:
                    # Use the channel where command was run
                    channel = interaction.channel
                    if not isinstance(channel, discord.TextChannel):
                        await interaction.followup.send("`❌` Please specify a text channel for chat games.", ephemeral=True)
                        return
                
                # Import chat game classes
                from games.chat.trivia import Trivia
                from games.chat.math_quiz import MathQuiz
                from games.chat.flag_guesser import FlagGuesser
                from games.chat.unscramble import Unscramble
                from games.chat.emoji_quiz import EmojiQuiz
                from games.chat.guess_the_number import GuessTheNumber
                
                game_map = {
                    "trivia": Trivia,
                    "math_quiz": MathQuiz,
                    "flag_guesser": FlagGuesser,
                    "unscramble": Unscramble,
                    "emoji_quiz": EmojiQuiz,
                    "guess_the_number": GuessTheNumber
                }
                
                game_class = game_map.get(game_value)
                if not game_class:
                    await interaction.followup.send(f"`❌` Unknown chat game: {game_value}", ephemeral=True)
                    return
                
                # Create and run game in test mode
                game = game_class(self.bot)
                msg = await game.run(channel, xp_multiplier=xp_multiplier, test_mode=True)
                
                if msg:
                    await interaction.followup.send(
                        f"`✅` Test {game_display_name} game sent to {channel.mention}!",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"`❌` Failed to send test {game_display_name} game. Check logs for details.",
                        ephemeral=True
                    )
            else:
                # Handle DM games
                # Import DM game classes
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
                    "connect_four": ("Connect Four", ConnectFour),
                    "memory": ("Memory", Memory),
                    "2048": ("2048", TwentyFortyEight),
                    "minesweeper": ("Minesweeper", Minesweeper),
                    "hangman": ("Hangman", Hangman)
                }
                
                game_display, game_class = game_map.get(game_value, (None, None))
                if not game_class:
                    await interaction.followup.send(f"`❌` Unknown DM game: {game_value}", ephemeral=True)
                    return
                
                # Create and run game in test mode
                game = game_class(self.bot)
                success = await game.run(interaction.user, game_display, test_mode=True)
                
                if success:
                    await interaction.followup.send(
                        f"`✅` Test {game_display} game sent to your DMs!",
                        ephemeral=True
                    )
                else:
                    error_msg = game.last_error if hasattr(game, 'last_error') and game.last_error else "Failed to start game"
                    await interaction.followup.send(
                        f"`❌` {error_msg}",
                        ephemeral=True
                    )
        
        except Exception as e:
            import traceback
            self.logger.error(f"Error running test game {game_value}: {e}\n{traceback.format_exc()}")
            await interaction.followup.send(
                f"`❌` Error running test game: {str(e)}",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(TestGame(bot))

