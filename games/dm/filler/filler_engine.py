import random
from collections import deque
from typing import List, Optional, Tuple

OWNER_NONE = None
OWNER_PLAYER = "P"
OWNER_BOT = "B"

DEFAULT_COLORS = ["🟥", "🟦", "🟩", "🟨", "🟧", "🟣"]
DEFAULT_GRID_SIZE = 6
NUM_COLORS = 6

DIRECTIONS = [(0, 1), (0, -1), (1, 0), (-1, 0)]


class FillerState:
    def __init__(
        self,
        grid_size: int = DEFAULT_GRID_SIZE,
        colors: Optional[List[str]] = None,
        grid: Optional[List[List[int]]] = None,
        owner: Optional[List[List[Optional[str]]]] = None,
        player_color: Optional[int] = None,
        bot_color: Optional[int] = None,
        turns: int = 0,
        game_ended: bool = False,
        is_player_turn: bool = True,
    ):
        self.grid_size = grid_size
        self.colors = colors or DEFAULT_COLORS[:NUM_COLORS]
        self.player_row = grid_size - 1
        self.player_col = 0
        self.bot_row = 0
        self.bot_col = grid_size - 1
        self.turns = turns
        self.game_ended = game_ended
        self.is_player_turn = is_player_turn

        if grid is not None and owner is not None:
            self.grid = grid
            self.owner = owner
            self.player_color = player_color if player_color is not None else grid[self.player_row][self.player_col]
            self.bot_color = bot_color if bot_color is not None else grid[self.bot_row][self.bot_col]
        else:
            self.grid, self.owner = self._generate_board()
            self.player_color = self.grid[self.player_row][self.player_col]
            self.bot_color = self.grid[self.bot_row][self.bot_col]

    def _generate_board(self) -> Tuple[List[List[int]], List[List[Optional[str]]]]:
        for _ in range(100):
            grid = [[random.randint(0, NUM_COLORS - 1) for _ in range(self.grid_size)] for _ in range(self.grid_size)]
            owner: List[List[Optional[str]]] = [[OWNER_NONE for _ in range(self.grid_size)] for _ in range(self.grid_size)]
            owner[self.player_row][self.player_col] = OWNER_PLAYER
            owner[self.bot_row][self.bot_col] = OWNER_BOT
            player_c = grid[self.player_row][self.player_col]
            bot_c = grid[self.bot_row][self.bot_col]
            if player_c != bot_c:
                return grid, owner
            grid[self.player_row][self.player_col] = (player_c + 1) % NUM_COLORS
        grid = [[random.randint(0, NUM_COLORS - 1) for _ in range(self.grid_size)] for _ in range(self.grid_size)]
        owner = [[OWNER_NONE for _ in range(self.grid_size)] for _ in range(self.grid_size)]
        owner[self.player_row][self.player_col] = OWNER_PLAYER
        owner[self.bot_row][self.bot_col] = OWNER_BOT
        return grid, owner

    def count_cells(self, side: str) -> int:
        return sum(1 for row in self.owner for cell in row if cell == side)

    @property
    def player_cells(self) -> int:
        return self.count_cells(OWNER_PLAYER)

    @property
    def bot_cells(self) -> int:
        return self.count_cells(OWNER_BOT)

    def _territory_cells(self, side: str) -> List[Tuple[int, int]]:
        return [
            (r, c)
            for r in range(self.grid_size)
            for c in range(self.grid_size)
            if self.owner[r][c] == side
        ]

    def _is_capturable(self, row: int, col: int, chosen_color: int) -> bool:
        """Only neutral cells matching the chosen palette color can be captured."""
        return self.owner[row][col] == OWNER_NONE and self.grid[row][col] == chosen_color

    def _is_selectable_color(self, side: str, chosen_color: int) -> bool:
        if side == OWNER_PLAYER:
            current = self.player_color
            opponent_color = self.bot_color
        else:
            current = self.bot_color
            opponent_color = self.player_color
        return chosen_color != current and chosen_color != opponent_color

    def simulate_capture(self, side: str, chosen_color: int) -> int:
        if not self._is_selectable_color(side, chosen_color):
            return 0

        territory = set(self._territory_cells(side))
        if not territory:
            return 0

        captured = set()
        queue = deque()
        for r, c in territory:
            for dr, dc in DIRECTIONS:
                nr, nc = r + dr, c + dc
                if (
                    0 <= nr < self.grid_size
                    and 0 <= nc < self.grid_size
                    and self._is_capturable(nr, nc, chosen_color)
                    and (nr, nc) not in captured
                ):
                    captured.add((nr, nc))
                    queue.append((nr, nc))

        while queue:
            r, c = queue.popleft()
            for dr, dc in DIRECTIONS:
                nr, nc = r + dr, c + dc
                if (
                    0 <= nr < self.grid_size
                    and 0 <= nc < self.grid_size
                    and self._is_capturable(nr, nc, chosen_color)
                    and (nr, nc) not in captured
                ):
                    captured.add((nr, nc))
                    queue.append((nr, nc))
        return len(captured)

    def apply_move(self, side: str, chosen_color: int) -> int:
        if not self._is_selectable_color(side, chosen_color):
            return -1

        captured_count = self.simulate_capture(side, chosen_color)

        if captured_count > 0:
            territory = set(self._territory_cells(side))
            queue = deque()
            for r, c in territory:
                for dr, dc in DIRECTIONS:
                    nr, nc = r + dr, c + dc
                    if (
                        0 <= nr < self.grid_size
                        and 0 <= nc < self.grid_size
                        and self._is_capturable(nr, nc, chosen_color)
                    ):
                        queue.append((nr, nc))

            while queue:
                r, c = queue.popleft()
                if self.owner[r][c] != OWNER_NONE:
                    continue
                if self.grid[r][c] != chosen_color:
                    continue
                self.owner[r][c] = side
                for dr, dc in DIRECTIONS:
                    nr, nc = r + dr, c + dc
                    if (
                        0 <= nr < self.grid_size
                        and 0 <= nc < self.grid_size
                        and self._is_capturable(nr, nc, chosen_color)
                    ):
                        queue.append((nr, nc))

        if side == OWNER_PLAYER:
            self.player_color = chosen_color
        else:
            self.bot_color = chosen_color
        self.turns += 1
        return captured_count

    def legal_moves(self, side: str) -> List[int]:
        return [
            color_idx
            for color_idx in range(NUM_COLORS)
            if self._is_selectable_color(side, color_idx)
        ]

    def greedy_move(self, side: str) -> Optional[int]:
        legal = self.legal_moves(side)
        if not legal:
            return None
        return max(legal, key=lambda c: self.simulate_capture(side, c))

    def check_game_over(self) -> bool:
        return all(cell != OWNER_NONE for row in self.owner for cell in row)

    def winner(self) -> Optional[str]:
        p = self.player_cells
        b = self.bot_cells
        if p > b:
            return OWNER_PLAYER
        if b > p:
            return OWNER_BOT
        return None

    def render_grid(self) -> str:
        lines = []
        for r in range(self.grid_size):
            row_emojis = []
            for c in range(self.grid_size):
                cell_owner = self.owner[r][c]
                if cell_owner == OWNER_PLAYER:
                    row_emojis.append(self.colors[self.player_color])
                elif cell_owner == OWNER_BOT:
                    row_emojis.append(self.colors[self.bot_color])
                else:
                    row_emojis.append(self.colors[self.grid[r][c]])
            lines.append("".join(row_emojis))
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "grid": self.grid,
            "owner": self.owner,
            "player_color": self.player_color,
            "bot_color": self.bot_color,
            "turns": self.turns,
            "game_ended": self.game_ended,
            "is_player_turn": self.is_player_turn,
            "grid_size": self.grid_size,
        }

    @classmethod
    def from_dict(cls, data: dict, colors: Optional[List[str]] = None) -> "FillerState":
        grid_size = data.get("grid_size", DEFAULT_GRID_SIZE)
        state = cls(
            grid_size=grid_size,
            colors=colors,
            grid=data["grid"],
            owner=data["owner"],
            player_color=data.get("player_color"),
            bot_color=data.get("bot_color"),
            turns=data.get("turns", 0),
            game_ended=data.get("game_ended", False),
            is_player_turn=data.get("is_player_turn", True),
        )
        return state


def calculate_xp(player_cells: int, total_cells: int, win_min: int, win_max: int) -> int:
    if total_cells <= 0:
        return win_min
    share = player_cells / total_cells
    return round(win_min + share * (win_max - win_min))
