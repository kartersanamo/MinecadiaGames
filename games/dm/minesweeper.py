import random
from datetime import datetime, timezone
from typing import Optional, List, Tuple
import discord
from discord.ext import commands
from games.base.dm_game import DMGame
from managers.leveling import LevelingManager
from utils.helpers import get_last_game_id
from core.database.pool import DatabasePool
from core.logging.setup import get_logger


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
            
            # Create a 5x5 board with 4-5 mines (adjustable)
            num_mines = self.game_config.get('NUM_MINES', 4)
            board, mine_positions = self._generate_board(5, 5, num_mines)
            
            view = MinesweeperButtons(last_game_id, board, mine_positions, num_mines, self.bot, self.config, self.game_config, test_mode=test_mode)
            view.player_id = user.id  # Set player_id so _save_state works
            # Register view for persistence across bot restarts
            self.bot.add_view(view)
            
            embed = discord.Embed(
                title=f"Minesweeper #{last_game_id}{test_label}",
                description=f"Click on any cell to reveal it! There are **{num_mines}** mines hidden.\n\n**How to play:** Click cells to reveal them. Numbers show adjacent mines. Click a flagged cell (🚩) to unflag it.",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.add_field(
                name="Status",
                value=f"Cells revealed: 0/25\nMines: {num_mines}\nFlags: 0",
                inline=False
            )
            embed.add_field(
                name="Flagging",
                value="To flag a cell, send: `flag [row] [col]` (e.g., `flag 1 2`). Click a flagged cell (🚩) to unflag it.",
                inline=False
            )
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            message = await user.send(embed=embed, view=view)
            view.message = message  # Store message reference
            
            if not test_mode:
                db = await self._get_db()
                current_unix = int(datetime.now(timezone.utc).timestamp())
                await db.execute_insert(
                    "INSERT INTO users_minesweeper (game_id, user_id, won, cells_revealed, mines_found, started_at, ended_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (last_game_id, user.id, 'Started', 0, 0, current_unix, 0)
                )
                
                # Save initial game state so flagging works immediately
                await view._save_state()
            
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


class MinesweeperButtons(discord.ui.View):
    def __init__(self, game_id: int, board: List[List[int]], mine_positions: List[Tuple[int, int]], num_mines: int, bot, config, game_config, test_mode: bool = False, saved_state: dict = None):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.game_config = game_config
        self.test_mode = test_mode
        self.num_mines = num_mines
        
        # Initialize or restore game state (data only; buttons are added below)
        if saved_state:
            self._restore_state_data(saved_state)
        else:
            self.board = board  # The actual board with numbers
            self.mine_positions = set(mine_positions)  # Set of (row, col) tuples for mines
            # Game state: revealed cells and flagged cells
            self.revealed = set()  # Set of (row, col) tuples
            self.flagged = set()  # Set of (row, col) tuples
            self.game_over = False
            self.won = False
        
        # Create 5x5 grid of buttons (5 rows, 5 columns = 25 buttons)
        # Discord allows 5 rows with 5 buttons each, which is perfect for 5x5
        for row in range(5):
            for col in range(5):
                button = discord.ui.Button(
                    label="\u200b",  # Invisible character
                    emoji="⬛",  # Black square for unvisited cells
                    style=discord.ButtonStyle.grey,
                    custom_id=f"minesweeper_{row}_{col}_{game_id}",
                    row=row
                )
                button.callback = self.create_click_callback(row, col)
                self.add_item(button)
        
        # After buttons exist, refresh their appearance from state (needed for restore)
        if saved_state:
            self._refresh_button_states()
        
        # Note: All 5 rows are used for the 25 game buttons
        # Flagging will be handled via message listener (similar to Wordle)
    
    def _get_state(self) -> dict:
        """Get current game state as dictionary"""
        return {
            'board': [row[:] for row in self.board],  # Deep copy
            'mine_positions': list(self.mine_positions),  # Convert set to list
            'revealed': list(self.revealed),  # Convert set to list
            'flagged': list(self.flagged),  # Convert set to list
            'game_over': self.game_over,
            'won': self.won
        }
    
    def _restore_state_data(self, state: dict):
        """Restore game state data from dictionary (does not update buttons)."""
        self.board = [row[:] for row in state.get('board', [[0 for _ in range(5)] for _ in range(5)])]
        self.mine_positions = set(tuple(p) for p in state.get('mine_positions', []))
        self.revealed = set(tuple(p) for p in state.get('revealed', []))
        self.flagged = set(tuple(p) for p in state.get('flagged', []))
        self.game_over = state.get('game_over', False)
        self.won = state.get('won', False)
    
    def _refresh_button_states(self):
        """Update all button appearances from current state. Call only after buttons are added."""
        for row in range(5):
            for col in range(5):
                self.update_button(row, col)
    
    async def _save_state(self):
        """Save current game state to database"""
        if self.test_mode or self.game_id == -999999 or not hasattr(self, 'player_id'):
            return
        
        try:
            from utils.game_state_manager import save_game_state
            state = self._get_state()
            await save_game_state('minesweeper', self.game_id, self.player_id, state, self.test_mode)
        except Exception as e:
            from core.logging.setup import get_logger
            logger = get_logger("DMGames")
            logger.error(f"Error saving Minesweeper game state: {e}")
    
    def create_click_callback(self, row: int, col: int):
        async def callback(interaction: discord.Interaction):
            await self.handle_click(interaction, row, col)
        return callback
    
    
    async def handle_click(self, interaction: discord.Interaction, row: int, col: int):
        if self.game_over:
            await interaction.response.send_message("This game has already ended!", ephemeral=True)
            return
        
        pos = (row, col)
        
        # Handle reveal: can't reveal flagged cells (click to unflag first)
        if pos in self.flagged:
            # Unflag the cell
            self.flagged.remove(pos)
            await interaction.response.defer()
            await self._save_state()
            await self.update_embed(interaction.message)
            await interaction.followup.send(f"Unflagged cell at row {row+1}, column {col+1}. Click again to reveal.", ephemeral=True)
            return
        
        if pos in self.revealed:
            await interaction.response.send_message("This cell is already revealed!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Reveal the cell
        self.reveal_cell(row, col)
        
        # Check for game over
        if (row, col) in self.mine_positions:
            # Hit a mine - game over
            await self.handle_loss(interaction)
        else:
            # Check for win
            total_cells = 25
            safe_cells = total_cells - self.num_mines
            if len(self.revealed) >= safe_cells:
                await self.handle_win(interaction)
            else:
                await self._save_state()
                await self.update_embed(interaction.message)
    
    def reveal_cell(self, row: int, col: int):
        """Reveal a cell and auto-reveal adjacent cells if they're 0"""
        if (row, col) in self.revealed or (row, col) in self.flagged:
            return
        
        self.revealed.add((row, col))
        
        # Auto-reveal adjacent cells if this cell is 0
        if self.board[row][col] == 0:
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    if dr == 0 and dc == 0:
                        continue
                    nr, nc = row + dr, col + dc
                    if 0 <= nr < 5 and 0 <= nc < 5:
                        if (nr, nc) not in self.revealed and (nr, nc) not in self.flagged:
                            self.reveal_cell(nr, nc)
    
    def update_button(self, row: int, col: int):
        """Update a button's appearance based on game state"""
        button = [b for b in self.children if b.custom_id == f"minesweeper_{row}_{col}_{self.game_id}"][0]
        pos = (row, col)
        
        if pos in self.revealed:
            # Cell is revealed
            value = self.board[row][col]
            if value == -1:
                button.emoji = "💣"
                button.label = "\u200b"
                button.style = discord.ButtonStyle.danger
            elif value == 0:
                button.emoji = None
                button.label = "-"
                button.style = discord.ButtonStyle.secondary
            else:
                # Show number
                number_emojis = {
                    1: "1️⃣",
                    2: "2️⃣",
                    3: "3️⃣",
                    4: "4️⃣",
                    5: "5️⃣",
                    6: "6️⃣",
                    7: "7️⃣",
                    8: "8️⃣"
                }
                button.emoji = number_emojis.get(value, str(value))
                button.label = "\u200b"
                button.style = discord.ButtonStyle.green if value <= 2 else discord.ButtonStyle.blurple
        elif pos in self.flagged:
            button.emoji = "🚩"
            button.label = "\u200b"
            button.style = discord.ButtonStyle.red
        else:
            button.emoji = "⬛"  # Black square for unvisited cells
            button.label = "\u200b"
            button.style = discord.ButtonStyle.grey
    
    async def update_embed(self, message: discord.Message):
        """Update the embed with current game state"""
        embed = message.embeds[0]
        
        # Update all buttons
        for row in range(5):
            for col in range(5):
                self.update_button(row, col)
        
        # Update status field
        cells_revealed = len(self.revealed)
        mines_found = len([p for p in self.flagged if p in self.mine_positions])
        embed.set_field_at(0, name="Status", value=f"Cells revealed: {cells_revealed}/25\nMines: {self.num_mines}\nFlags: {len(self.flagged)}", inline=False)
        
        await message.edit(embed=embed, view=self)
    
    async def handle_loss(self, interaction: discord.Interaction):
        """Handle game loss"""
        self.game_over = True
        
        # Save final state
        await self._save_state()
        
        # Reveal all mines
        for row, col in self.mine_positions:
            self.revealed.add((row, col))
        
        # Update all buttons
        for row in range(5):
            for col in range(5):
                self.update_button(row, col)
        
        # Disable all buttons
        for button in self.children:
            if button.custom_id and button.custom_id.startswith(f"minesweeper_"):
                button.disabled = True
        
        embed = interaction.message.embeds[0]
        embed.set_field_at(0, name="Status", value="❌ **Game Over!** You hit a mine!", inline=False)
        
        await interaction.message.edit(embed=embed, view=self)
        
        # Update database
        if not self.test_mode:
            db = await DatabasePool.get_instance()
            current_unix = int(datetime.now(timezone.utc).timestamp())
            await db.execute(
                "UPDATE users_minesweeper SET won = 'Lost', cells_revealed = %s, ended_at = %s WHERE user_id = %s AND game_id = %s",
                (len(self.revealed), current_unix, interaction.user.id, self.game_id)
            )
        
        await interaction.followup.send(
            f"`❌` Sorry {interaction.user.mention}, you hit a mine! Better luck next time!",
            ephemeral=False
        )
    
    async def handle_win(self, interaction: discord.Interaction):
        """Handle game win"""
        self.game_over = True
        self.won = True
        
        # Reveal all remaining cells
        for row in range(5):
            for col in range(5):
                if (row, col) not in self.revealed and (row, col) not in self.mine_positions:
                    self.revealed.add((row, col))
        
        # Update all buttons
        for row in range(5):
            for col in range(5):
                self.update_button(row, col)
        
        # Disable all buttons
        for button in self.children:
            if button.custom_id and button.custom_id.startswith(f"minesweeper_"):
                button.disabled = True
        
        embed = interaction.message.embeds[0]
        cells_revealed = len(self.revealed)
        mines_found = len([p for p in self.flagged if p in self.mine_positions])
        embed.set_field_at(0, name="Status", value=f"✅ **You Won!**\nCells revealed: {cells_revealed}/25\nMines found: {mines_found}/{self.num_mines}", inline=False)
        
        await interaction.message.edit(embed=embed, view=self)
        
        # Calculate XP (based on cells revealed and mines found)
        xp = random.randint(
            self.game_config.get('WIN_XP', {}).get('LOWER', 40),
            self.game_config.get('WIN_XP', {}).get('UPPER', 60)
        )
        
        await interaction.followup.send(
            f"`✅` Congratulations {interaction.user.mention}! You won! You {'would have earned' if self.test_mode else 'earned'} `{xp}xp`!",
            ephemeral=False
        )
        
        # Update database
        if not self.test_mode:
            db = await DatabasePool.get_instance()
            current_unix = int(datetime.now(timezone.utc).timestamp())
            await db.execute(
                "UPDATE users_minesweeper SET won = 'Won', cells_revealed = %s, mines_found = %s, ended_at = %s WHERE user_id = %s AND game_id = %s",
                (cells_revealed, mines_found, current_unix, interaction.user.id, self.game_id)
            )
            
            lvl_mng = LevelingManager(
                user=interaction.user,
                channel=interaction.channel,
                client=self.bot,
                xp=xp,
                source="Minesweeper",
                game_id=self.game_id,
                test_mode=self.test_mode
            )
            await lvl_mng.update()
            
            # Check for achievements
            from utils.achievements import check_dm_game_win
            await check_dm_game_win(interaction.user, "Minesweeper", interaction.channel, self.bot)


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
                    
                    if 0 <= row < 5 and 0 <= col < 5:
                        # Find the active game for this user
                        db = await DatabasePool.get_instance()
                        rows = await db.execute(
                            "SELECT game_id FROM users_minesweeper WHERE user_id = %s AND won = 'Started' ORDER BY started_at DESC LIMIT 1",
                            (message.author.id,)
                        )
                        
                        if rows:
                            game_id = rows[0]['game_id']
                            
                            # Find the game message and view
                            found_message = None
                            async for channel_message in message.channel.history(limit=10):
                                if channel_message.embeds and channel_message.author.bot:
                                    embed = channel_message.embeds[0]
                                    if "Minesweeper" in embed.title and f"#{game_id}" in embed.title:
                                        found_message = channel_message
                                        break
                            
                            if found_message:
                                # Reconstruct the view from saved game state
                                try:
                                    from utils.game_state_manager import load_game_state
                                    game_state = await load_game_state('minesweeper', game_id, message.author.id)
                                    
                                    if game_state:
                                        # Reconstruct the view from state
                                        board = game_state.get('board', [[0 for _ in range(5)] for _ in range(5)])
                                        mine_positions = game_state.get('mine_positions', [])
                                        num_mines = len(mine_positions) if mine_positions else 4
                                        
                                        # Get config from minesweeper_game instance
                                        config = self.minesweeper_game.config
                                        game_config = self.minesweeper_game.game_config
                                        
                                        view = MinesweeperButtons(
                                            game_id, board, mine_positions, num_mines, 
                                            self.bot, config, game_config,
                                            test_mode=False, saved_state=game_state
                                        )
                                        view.player_id = message.author.id
                                        view.message = found_message
                                        
                                        pos = (row, col)
                                        
                                        if pos in view.revealed:
                                            await message.reply("You cannot flag a revealed cell!", delete_after=5)
                                            return
                                        
                                        # Toggle flag
                                        if pos in view.flagged:
                                            view.flagged.remove(pos)
                                            await message.reply(f"Unflagged cell at row {row+1}, column {col+1}.", delete_after=5)
                                        else:
                                            view.flagged.add(pos)
                                            await message.reply(f"Flagged cell at row {row+1}, column {col+1}.", delete_after=5)
                                        
                                        # Save state after flagging
                                        await view._save_state()
                                        
                                        # Update the embed
                                        await view.update_embed(found_message)
                                    else:
                                        # Game state doesn't exist - this shouldn't happen if initial state was saved
                                        # But handle it gracefully just in case
                                        self.logger.warning(f"Minesweeper game state not found for game_id={game_id}, user_id={message.author.id}")
                                        await message.reply("Game state not found. Please try revealing a cell first, or start a new game.", delete_after=5)
                                except Exception as e:
                                    self.logger.error(f"Error handling flag command: {e}")
                                    import traceback
                                    self.logger.error(traceback.format_exc())
                                    await message.reply("An error occurred while processing the flag command.", delete_after=5)
                        else:
                            await message.reply("You don't have an active Minesweeper game!", delete_after=5)
                    else:
                        await message.reply("Invalid row/column! Use numbers 1-5.", delete_after=5)
                except ValueError:
                    await message.reply("Invalid format! Use: `flag [row] [col]` (e.g., `flag 1 2`)", delete_after=5)
            else:
                await message.reply("Invalid format! Use: `flag [row] [col]` (e.g., `flag 1 2`)", delete_after=5)

