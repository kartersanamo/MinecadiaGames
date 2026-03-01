import random
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict
import discord
from discord.ext import commands
from games.base.dm_game import DMGame
from managers.leveling import LevelingManager
from utils.helpers import get_last_game_id
from core.database.pool import DatabasePool
from core.logging.setup import get_logger

# Grid: 2 messages, 25 buttons each = 50 cells (10 rows x 5 cols). Same mine count = easier.
ROWS, COLS = 10, 5
TOTAL_CELLS = ROWS * COLS  # 50

# In-memory state for test games so the flag command can find them
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
                last_game_id = await get_last_game_id('minesweeper')
                if not last_game_id:
                    return False
            
            test_label = " 🧪 TEST GAME 🧪" if test_mode else ""
            
            # 10x5 board, same mine count = easier
            num_mines = self.game_config.get('NUM_MINES', 4)
            board, mine_positions = self._generate_board(ROWS, COLS, num_mines)
            mine_set = set(mine_positions)
            non_mine_positions = [(r, c) for r in range(ROWS) for c in range(COLS) if (r, c) not in mine_set]
            initial_revealed = random.choice(non_mine_positions)
            
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
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
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
            from utils.game_state_manager import save_game_state
            await save_game_state('minesweeper', self.game_id, self.player_id, self._get_state(), self.test_mode)
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
            db = await DatabasePool.get_instance()
            await db.execute(
                "UPDATE users_minesweeper SET won = 'Lost', cells_revealed = %s, ended_at = %s WHERE user_id = %s AND game_id = %s",
                (len(self.revealed), int(datetime.now(timezone.utc).timestamp()), interaction.user.id, self.game_id)
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
            self.game_config.get('WIN_XP', {}).get('LOWER', 80),
            self.game_config.get('WIN_XP', {}).get('UPPER', 120)
        )
        await interaction.followup.send(
            f"`✅` Congratulations {interaction.user.mention}! You won! You {'would have earned' if self.test_mode else 'earned'} `{xp}xp`!",
            ephemeral=False
        )
        if not self.test_mode:
            db = await DatabasePool.get_instance()
            await db.execute(
                "UPDATE users_minesweeper SET won = 'Won', cells_revealed = %s, mines_found = %s, ended_at = %s WHERE user_id = %s AND game_id = %s",
                (cells_revealed, mines_found, int(datetime.now(timezone.utc).timestamp()), interaction.user.id, self.game_id)
            )
            lvl_mng = LevelingManager(user=interaction.user, channel=interaction.channel, client=self.bot, xp=xp, source="Minesweeper", game_id=self.game_id, test_mode=self.test_mode)
            await lvl_mng.update()
            from utils.achievements import check_dm_game_win
            await check_dm_game_win(interaction.user, "Minesweeper", interaction.channel, self.bot)
        if self.test_mode:
            TEST_MINESWEEPER_GAMES.pop(interaction.user.id, None)


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


class MinesweeperListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.minesweeper_game = None
        self.logger = get_logger("DMGames")
    
    def set_minesweeper_game(self, minesweeper_game):
        self.minesweeper_game = minesweeper_game
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not isinstance(message.channel, discord.DMChannel) or message.author.bot:
            return
        
        if not self.minesweeper_game:
            return
        
        # Check for flag command: "flag [row] [col]" or "flag row col"
        content = message.content.strip().lower()
        if content.startswith('flag '):
            parts = content.split()
            if len(parts) >= 3:
                try:
                    row = int(parts[1]) - 1  # Convert to 0-indexed
                    col = int(parts[2]) - 1  # Convert to 0-indexed
                    
                    if 0 <= row < ROWS and 0 <= col < COLS:
                        try:
                            await message.delete()
                        except (discord.NotFound, discord.Forbidden):
                            pass
                        pos = (row, col)
                        db = await DatabasePool.get_instance()
                        rows_db = await db.execute(
                            "SELECT game_id FROM users_minesweeper WHERE user_id = %s AND won = 'Started' ORDER BY started_at DESC LIMIT 1",
                            (message.author.id,)
                        )
                        
                        if rows_db:
                            game_id = rows_db[0]['game_id']
                            try:
                                from utils.game_state_manager import load_game_state
                                game_state = await load_game_state('minesweeper', game_id, message.author.id)
                                if not game_state:
                                    self.logger.warning(f"Minesweeper game state not found for game_id={game_id}")
                                    await message.reply("Game state not found. Try revealing a cell first, or start a new game.", delete_after=5)
                                    return
                                default_board = [[0 for _ in range(COLS)] for _ in range(ROWS)]
                                board = game_state.get('board', default_board)
                                mine_positions = game_state.get('mine_positions', [])
                                num_mines = len(mine_positions) if mine_positions else 4
                                config = self.minesweeper_game.config
                                game_config = self.minesweeper_game.game_config
                                state = MinesweeperState(game_id, board, mine_positions, num_mines, self.bot, self.minesweeper_game.config, game_config, test_mode=False, saved_state=game_state)
                                state.player_id = message.author.id
                                msg1_id = game_state.get('message1_id')
                                msg2_id = game_state.get('message2_id')
                                if msg1_id and msg2_id:
                                    state.message1 = await message.channel.fetch_message(msg1_id)
                                    state.message2 = await message.channel.fetch_message(msg2_id)
                                    state.message1_id = msg1_id
                                    state.message2_id = msg2_id
                                else:
                                    async for ch_msg in message.channel.history(limit=15):
                                        if ch_msg.embeds and "Minesweeper" in (ch_msg.embeds[0].title or "") and f"#{game_id}" in (ch_msg.embeds[0].title or ""):
                                            state.message1 = ch_msg
                                            state.message1_id = ch_msg.id
                                            state.message2 = None
                                            async for nxt in message.channel.history(limit=5, after=ch_msg):
                                                if nxt.author.bot and not nxt.content and not nxt.embeds:
                                                    state.message2 = nxt
                                                    state.message2_id = nxt.id
                                                    break
                                            break
                                if not state.message1 or not state.message2:
                                    await message.reply("Could not find both game messages.", delete_after=5)
                                    return
                                view_top = MinesweeperButtons(state, row_offset=0)
                                view_bottom = MinesweeperButtons(state, row_offset=5)
                                state.view_top = view_top
                                state.view_bottom = view_bottom
                                if pos in state.revealed:
                                    await message.reply("You cannot flag a revealed cell!", delete_after=5)
                                    return
                                if pos in state.flagged:
                                    state.flagged.remove(pos)
                                    await message.reply(f"Unflagged row {row+1}, col {col+1}.", delete_after=5)
                                else:
                                    state.flagged.add(pos)
                                    await message.reply(f"Flagged row {row+1}, col {col+1}.", delete_after=5)
                                await state._save_state()
                                await state.update_both_messages()
                            except Exception as e:
                                self.logger.error(f"Error handling flag command: {e}", exc_info=True)
                                await message.reply("An error occurred while processing the flag command.", delete_after=5)
                        else:
                            test_data = TEST_MINESWEEPER_GAMES.get(message.author.id)
                            if test_data:
                                try:
                                    game_state = test_data.get('state')
                                    msg1_id = test_data.get('message1_id')
                                    msg2_id = test_data.get('message2_id')
                                    if not game_state or not msg1_id or not msg2_id:
                                        await message.reply("Test game state not found. Try revealing a cell first.", delete_after=5)
                                        return
                                    state = MinesweeperState(-999999, game_state.get('board', [[0]*COLS for _ in range(ROWS)]), game_state.get('mine_positions', []), len(game_state.get('mine_positions', [])) or 4, self.bot, self.minesweeper_game.config, self.minesweeper_game.game_config, test_mode=True, saved_state=game_state)
                                    state.player_id = message.author.id
                                    state.message1 = await message.channel.fetch_message(msg1_id)
                                    state.message2 = await message.channel.fetch_message(msg2_id)
                                    state.message1_id = msg1_id
                                    state.message2_id = msg2_id
                                    view_top = MinesweeperButtons(state, row_offset=0)
                                    view_bottom = MinesweeperButtons(state, row_offset=5)
                                    state.view_top = view_top
                                    state.view_bottom = view_bottom
                                    if pos in state.revealed:
                                        await message.reply("You cannot flag a revealed cell!", delete_after=5)
                                        return
                                    if pos in state.flagged:
                                        state.flagged.remove(pos)
                                        await message.reply(f"Unflagged row {row+1}, col {col+1}.", delete_after=5)
                                    else:
                                        state.flagged.add(pos)
                                        await message.reply(f"Flagged row {row+1}, col {col+1}.", delete_after=5)
                                    await state._save_state()
                                    await state.update_both_messages()
                                except discord.NotFound:
                                    TEST_MINESWEEPER_GAMES.pop(message.author.id, None)
                                    await message.reply("Your test game messages were not found. Start a new test game.", delete_after=5)
                                except Exception as e:
                                    self.logger.error(f"Error handling flag command (test): {e}", exc_info=True)
                                    await message.reply("An error occurred.", delete_after=5)
                            else:
                                await message.reply("You don't have an active Minesweeper game!", delete_after=5)
                    else:
                        await message.reply(f"Invalid row/column! Row 1–{ROWS}, col 1–{COLS}.", delete_after=5)
                except ValueError:
                    await message.reply("Invalid format! Use: `flag [row] [col]` (e.g., `flag 1 2`)", delete_after=5)
            else:
                await message.reply("Invalid format! Use: `flag [row] [col]` (e.g., `flag 1 2`)", delete_after=5)

