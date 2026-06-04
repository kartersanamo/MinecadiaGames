from __future__ import annotations

from typing import Dict, TYPE_CHECKING
import discord

if TYPE_CHECKING:
    from games.dm.minesweeper.minesweeper_state import MinesweeperState
ROWS, COLS = 10, 5
TOTAL_CELLS = ROWS * COLS  # 50
TEST_MINESWEEPER_GAMES: Dict[int, dict] = {}  # user_id -> {'state': {...}, 'message1_id': int, 'message2_id': int}
class MinesweeperButtons(discord.ui.View):
    """One of the two button grids (top rows 0-4 or bottom rows 5-9). 25 buttons each."""
    def __init__(self, state: MinesweeperState, row_offset: int):
        super().__init__(timeout=None)
        self.state = state
        self.row_offset = row_offset  # 0 or 5
        for r in range(row_offset, row_offset + 5):
            for c in range(COLS):
                btn = discord.ui.Button(
                    label="\u200b",
                    emoji="⬛",
                    style=discord.ButtonStyle.grey,
                    custom_id=f"minesweeper_{r}_{c}_{state.game_id}",
                    row=r - row_offset
                )
                btn.callback = self._make_callback(r, c)
                self.add_item(btn)
        self._refresh_button_states()
    
    def _make_callback(self, row: int, col: int):
        async def cb(interaction: discord.Interaction):
            await self.state.handle_click(interaction, row, col)
        return cb
    
    def _refresh_button_states(self):
        for r in range(self.row_offset, self.row_offset + 5):
            for c in range(COLS):
                self._update_button(r, c)
    
    def _update_button(self, row: int, col: int):
        button = [b for b in self.children if b.custom_id == f"minesweeper_{row}_{col}_{self.state.game_id}"][0]
        pos = (row, col)
        s = self.state
        if pos in s.revealed:
            val = s.board[row][col]
            if val == -1:
                button.emoji, button.label, button.style = "💣", "\u200b", discord.ButtonStyle.danger
            elif val == 0:
                button.emoji, button.label, button.style = None, "-", discord.ButtonStyle.secondary
            else:
                number_emojis = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣"}
                button.emoji, button.label, button.style = number_emojis.get(val, str(val)), "\u200b", discord.ButtonStyle.green if val <= 2 else discord.ButtonStyle.blurple
        elif pos in s.flagged:
            button.emoji, button.label, button.style = "🚩", "\u200b", discord.ButtonStyle.red
        else:
            button.emoji, button.label, button.style = "⬛", "\u200b", discord.ButtonStyle.grey
