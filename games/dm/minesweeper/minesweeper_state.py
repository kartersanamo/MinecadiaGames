import random
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict
import discord
from managers.leveling import LevelingManager
from repositories.game_session_repository import GameSessionRepository
from core.logging.setup import get_logger
ROWS, COLS = 10, 5
TOTAL_CELLS = ROWS * COLS  # 50
TEST_MINESWEEPER_GAMES: Dict[int, dict] = {}  # user_id -> {'state': {...}, 'message1_id': int, 'message2_id': int}
class MinesweeperState:
    """Shared game state for the 2-message board (10x5 grid, 50 cells)."""
    def __init__(self, game_id: int, board: List[List[int]], mine_positions: List[Tuple[int, int]], num_mines: int, bot, config, game_config, test_mode: bool = False, saved_state: dict = None):
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.game_config = game_config
        self.test_mode = test_mode
        self.num_mines = num_mines
        self.player_id: Optional[int] = None
        self.message1: Optional[discord.Message] = None
        self.message2: Optional[discord.Message] = None
        self.message1_id: Optional[int] = None
        self.message2_id: Optional[int] = None
        self.view_top: Optional['MinesweeperButtons'] = None
        self.view_bottom: Optional['MinesweeperButtons'] = None
        self.embed: Optional[discord.Embed] = None
        
        if saved_state:
            self._restore_state_data(saved_state)
        else:
            self.board = [row[:] for row in board]
            self.mine_positions = set(tuple(p) for p in mine_positions)
            self.revealed = set()
            self.flagged = set()
            self.game_over = False
            self.won = False
    
    def _get_state(self) -> dict:
        return {
            'board': [row[:] for row in self.board],
            'mine_positions': list(self.mine_positions),
            'revealed': list(self.revealed),
            'flagged': list(self.flagged),
            'game_over': self.game_over,
            'won': self.won,
            'message1_id': self.message1_id,
            'message2_id': self.message2_id,
        }
    
    def _restore_state_data(self, state: dict):
        default_board = [[0 for _ in range(COLS)] for _ in range(ROWS)]
        self.board = [row[:] for row in state.get('board', default_board)]
        self.mine_positions = set(tuple(p) for p in state.get('mine_positions', []))
        self.revealed = set(tuple(p) for p in state.get('revealed', []))
        self.flagged = set(tuple(p) for p in state.get('flagged', []))
        self.game_over = state.get('game_over', False)
        self.won = state.get('won', False)
        self.message1_id = state.get('message1_id')
        self.message2_id = state.get('message2_id')
    
    async def _save_state(self):
        if not self.player_id:
            return
        if self.test_mode or self.game_id == -999999:
            if self.player_id in TEST_MINESWEEPER_GAMES:
                TEST_MINESWEEPER_GAMES[self.player_id]['state'] = self._get_state()
                TEST_MINESWEEPER_GAMES[self.player_id]['message1_id'] = self.message1_id
                TEST_MINESWEEPER_GAMES[self.player_id]['message2_id'] = self.message2_id
            return
        try:
            await self.bot.app.game_state.save('minesweeper', self.game_id, self.player_id, self._get_state(), self.test_mode)
        except Exception as e:
            get_logger("DMGames").error(f"Error saving Minesweeper game state: {e}")
    
    def reveal_cell(self, row: int, col: int):
        if (row, col) in self.revealed or (row, col) in self.flagged:
            return
        self.revealed.add((row, col))
        if self.board[row][col] == 0:
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    if dr == 0 and dc == 0:
                        continue
                    nr, nc = row + dr, col + dc
                    if 0 <= nr < ROWS and 0 <= nc < COLS and (nr, nc) not in self.revealed and (nr, nc) not in self.flagged:
                        self.reveal_cell(nr, nc)
    
    async def update_both_messages(self, status_value: Optional[str] = None):
        """Refresh both views and edit both messages."""
        if not self.message1 or not self.message2:
            return
        cells_revealed = len(self.revealed)
        mines_found = len([p for p in self.flagged if p in self.mine_positions])
        if status_value is None:
            status_value = f"Cells revealed: {cells_revealed}/{TOTAL_CELLS}\nMines: {self.num_mines}\nFlags: {len(self.flagged)}"
        self.view_top._refresh_button_states()
        self.view_bottom._refresh_button_states()
        emb = self.message1.embeds[0] if self.message1.embeds else self.embed
        if emb:
            emb.set_field_at(0, name="Status", value=status_value, inline=False)
        await self.message1.edit(embed=emb, view=self.view_top)
        await self.message2.edit(view=self.view_bottom)
    
    async def handle_click(self, interaction: discord.Interaction, row: int, col: int):
        if self.game_over:
            await interaction.response.send_message("This game has already ended!", ephemeral=True)
            return
        pos = (row, col)
        if pos in self.flagged:
            self.flagged.remove(pos)
            await interaction.response.defer()
            await self._save_state()
            await self.update_both_messages()
            await interaction.followup.send(f"Unflagged row {row+1}, col {col+1}. Click again to reveal.", ephemeral=True)
            return
        if pos in self.revealed:
            await interaction.response.send_message("This cell is already revealed!", ephemeral=True)
            return
        await interaction.response.defer()
        self.reveal_cell(row, col)
        if (row, col) in self.mine_positions:
            await self._handle_loss(interaction)
        else:
            safe_cells = TOTAL_CELLS - self.num_mines
            if len(self.revealed) >= safe_cells:
                await self._handle_win(interaction)
            else:
                await self._save_state()
                await self.update_both_messages()
    
    async def _handle_loss(self, interaction: discord.Interaction):
        self.game_over = True
        await self._save_state()
        for r, c in self.mine_positions:
            self.revealed.add((r, c))
        self.view_top._refresh_button_states()
        self.view_bottom._refresh_button_states()
        for v in (self.view_top, self.view_bottom):
            for b in v.children:
                if b.custom_id and b.custom_id.startswith("minesweeper_"):
                    b.disabled = True
        emb = self.message1.embeds[0] if self.message1.embeds else self.embed
        if emb:
            emb.set_field_at(0, name="Status", value="❌ **Game Over!** You hit a mine!", inline=False)
        await self.message1.edit(embed=emb, view=self.view_top)
        await self.message2.edit(view=self.view_bottom)
        if not self.test_mode:
            repo = GameSessionRepository()
            await repo.finish_session(
                self.game_id,
                interaction.user.id,
                "minesweeper",
                "lost",
                stats={"cells_revealed": len(self.revealed)},
                ended_at=int(datetime.now(timezone.utc).timestamp()),
            )
        if self.test_mode:
            TEST_MINESWEEPER_GAMES.pop(interaction.user.id, None)
        await interaction.followup.send(f"`❌` Sorry {interaction.user.mention}, you hit a mine!", ephemeral=False)
    
    async def _handle_win(self, interaction: discord.Interaction):
        self.game_over = True
        self.won = True
        for r in range(ROWS):
            for c in range(COLS):
                if (r, c) not in self.revealed and (r, c) not in self.mine_positions:
                    self.revealed.add((r, c))
        self.view_top._refresh_button_states()
        self.view_bottom._refresh_button_states()
        for v in (self.view_top, self.view_bottom):
            for b in v.children:
                if b.custom_id and b.custom_id.startswith("minesweeper_"):
                    b.disabled = True
        cells_revealed = len(self.revealed)
        mines_found = len([p for p in self.flagged if p in self.mine_positions])
        status = f"✅ **You Won!**\nCells revealed: {cells_revealed}/{TOTAL_CELLS}\nMines found: {mines_found}/{self.num_mines}"
        emb = self.message1.embeds[0] if self.message1.embeds else self.embed
        if emb:
            emb.set_field_at(0, name="Status", value=status, inline=False)
        await self.message1.edit(embed=emb, view=self.view_top)
        await self.message2.edit(view=self.view_bottom)
        xp = random.randint(
            self.game_config.get('WIN_XP', {}).get('LOWER', 150),
            self.game_config.get('WIN_XP', {}).get('UPPER', 220)
        )
        await interaction.followup.send(
            f"`✅` Congratulations {interaction.user.mention}! You won! You {'would have earned' if self.test_mode else 'earned'} `{xp}xp`!",
            ephemeral=False
        )
        if not self.test_mode:
            repo = GameSessionRepository()
            await repo.finish_session(
                self.game_id,
                interaction.user.id,
                "minesweeper",
                "won",
                stats={"cells_revealed": cells_revealed, "mines_found": mines_found},
                ended_at=int(datetime.now(timezone.utc).timestamp()),
            )
            lvl_mng = LevelingManager(user=interaction.user, channel=interaction.channel, client=self.bot, xp=xp, source="Minesweeper", game_id=self.game_id, test_mode=self.test_mode)
            await lvl_mng.update()
            await self.bot.app.achievements.check_dm_game_win(interaction.user, "Minesweeper", interaction.channel, self.bot)
        if self.test_mode:
            TEST_MINESWEEPER_GAMES.pop(interaction.user.id, None)
