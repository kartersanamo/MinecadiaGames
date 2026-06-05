import discord
from core.config.manager import ConfigManager
from managers.game_manager import GameManager


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
            ),
            discord.SelectOption(
                label="Filler",
                value="filler",
                description="Test Filler game",
                emoji="🟦"
            )
        ]
        
        from ui.views.test_d_m_game_select_view import TestDMGameSelect

        select = TestDMGameSelect(self, options)
        self.add_item(select)
