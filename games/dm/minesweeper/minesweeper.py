import random
from datetime import datetime, timezone
from typing import List, Tuple, Dict
import discord
from games.base.dm_game import DMGame
from core.logging.setup import get_logger
ROWS, COLS = 10, 5
TOTAL_CELLS = ROWS * COLS  # 50
TEST_MINESWEEPER_GAMES: Dict[int, dict] = {}  # user_id -> {'state': {...}, 'message1_id': int, 'message2_id': int}
class Minesweeper(DMGame):
    def __init__(self, bot):
        super().__init__(bot)
        # Support both old and new config structure
        games = self.dm_config.get('GAMES', {})
        if not games:
            games = self.dm_config.get('games', {})
        self.game_config = games.get('Minesweeper', {})
        self.logger = get_logger("DMGames")
    
    async def _run_game(self, user: discord.User, game_name: str, test_mode: bool = False) -> bool:
        try:
            if test_mode:
                last_game_id = -999999  # Fake game_id for test mode
            else:
                last_game_id = await self.bot.app.games.get_last_game_id('minesweeper')
                if not last_game_id:
                    return False
            
            test_label = " 🧪 TEST GAME 🧪" if test_mode else ""
            
            # 10x5 board, same mine count = easier
            num_mines = self.game_config.get('NUM_MINES', 6)  # Default to 6 mines if not configured
            board, mine_positions = self._generate_board(ROWS, COLS, num_mines)
            mine_set = set(mine_positions)
            non_mine_positions = [(r, c) for r in range(ROWS) for c in range(COLS) if (r, c) not in mine_set]
            initial_revealed = random.choice(non_mine_positions)
            
            from games.dm.minesweeper.minesweeper_state import MinesweeperState
            from games.dm.minesweeper.minesweeper_buttons import MinesweeperButtons
            state = MinesweeperState(
                game_id=last_game_id,
                board=board,
                mine_positions=mine_positions,
                num_mines=num_mines,
                bot=self.bot,
                config=self.config,
                game_config=self.game_config,
                test_mode=test_mode,
            )
            state.player_id = user.id
            state.revealed.add(initial_revealed)
            
            view_top = MinesweeperButtons(state, row_offset=0)
            view_bottom = MinesweeperButtons(state, row_offset=5)
            state.view_top = view_top
            state.view_bottom = view_bottom
            self.bot.add_view(view_top)
            self.bot.add_view(view_bottom)
            
            embed = discord.Embed(
                title=f"Minesweeper #{last_game_id}{test_label}",
                description=f"Click any cell to reveal it! **{num_mines}** mines in a 10×5 grid.\n\n**How to play:** Click cells to reveal. Numbers show adjacent mines. Send `flag [row] [col]` to flag (rows 1–10, cols 1–5). Click 🚩 to unflag.",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.add_field(
                name="Status",
                value=f"Cells revealed: 1/{TOTAL_CELLS}\nMines: {num_mines}\nFlags: 0",
                inline=False
            )
            logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            state.embed = embed
            
            message1 = await user.send(embed=embed, view=view_top)
            message2 = await user.send(view=view_bottom)
            state.message1 = message1
            state.message2 = message2
            state.message1_id = message1.id
            state.message2_id = message2.id

            if test_mode:
                TEST_MINESWEEPER_GAMES[user.id] = {
                    'state': state._get_state(),
                    'message1_id': message1.id,
                    'message2_id': message2.id,
                }
            
            if not test_mode:
                db = await self._get_db()
                current_unix = int(datetime.now(timezone.utc).timestamp())
                await db.execute_insert(
                    "INSERT INTO users_minesweeper (game_id, user_id, won, cells_revealed, mines_found, started_at, ended_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (last_game_id, user.id, 'Started', 0, 0, current_unix, 0)
                )
                await state._save_state()
            
            self.logger.info(f"Minesweeper ({user.name}#{user.discriminator})")
            return True
        except Exception as e:
            self.logger.error(f"Minesweeper error: {e}")
            return False
    
    def _generate_board(self, rows: int, cols: int, num_mines: int) -> Tuple[List[List[int]], List[Tuple[int, int]]]:
        """Generate a minesweeper board
        Returns: (board with numbers, list of mine positions)
        """
        board = [[0 for _ in range(cols)] for _ in range(rows)]
        mine_positions = []
        
        # Place mines randomly
        positions = [(r, c) for r in range(rows) for c in range(cols)]
        mine_positions = random.sample(positions, num_mines)
        
        # Mark mines on board (-1 = mine)
        for r, c in mine_positions:
            board[r][c] = -1
        
        # Calculate numbers for each cell
        for r in range(rows):
            for c in range(cols):
                if board[r][c] == -1:
                    continue
                
                # Count adjacent mines
                count = 0
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        if dr == 0 and dc == 0:
                            continue
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < rows and 0 <= nc < cols:
                            if board[nr][nc] == -1:
                                count += 1
                
                board[r][c] = count
        
        return board, mine_positions
