import json
import re
import discord
from core.config.manager import ConfigManager
from games.dm.wordle import Wordle
from games.dm.tictactoe import TicTacToe
from games.dm.connect_four import ConnectFour
from games.dm.memory import Memory
from games.dm.twenty_forty_eight import TwentyFortyEight
from games.dm.hangman import Hangman
from utils.helpers import check_dm_game_requirements


class StartWordleView(discord.ui.View):
    def __init__(self, old_interaction: discord.Interaction, bot):
        super().__init__(timeout=None)
        self.old_interaction = old_interaction
        self.bot = bot
    
    @discord.ui.button(label="Click Here to Play!", style=discord.ButtonStyle.grey, custom_id="play_wordle")
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = Wordle(self.bot)
        success = await game.run(interaction.user, 'wordle')
        if success:
            await interaction.response.send_message(
                "`✅` Successfully started a game of Wordle in your DMs!",
                ephemeral=True
            )
        else:
            error_msg = game.last_error or "Failed to start game. Please try again later."
            await interaction.response.send_message(
                f"`❌` {error_msg}",
                ephemeral=True
            )
