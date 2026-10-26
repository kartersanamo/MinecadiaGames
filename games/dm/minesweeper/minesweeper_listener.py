from typing import Dict
import discord
from discord.ext import commands
from repositories.game_session_repository import GameSessionRepository
from core.logging.setup import get_logger
from games.dm.minesweeper.minesweeper_buttons import MinesweeperButtons
from games.dm.minesweeper.minesweeper_state import MinesweeperState
ROWS, COLS = 10, 5
TOTAL_CELLS = ROWS * COLS  # 50
TEST_MINESWEEPER_GAMES: Dict[int, dict] = {}  # user_id -> {'state': {...}, 'message1_id': int, 'message2_id': int}
class MinesweeperListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.minesweeper_game = None
        self.logger = get_logger("DMGames")
    
    def set_minesweeper_game(self, minesweeper_game):
        self.minesweeper_game = minesweeper_game
    
    # Minesweeper input is handled by buttons and the flag modal.
