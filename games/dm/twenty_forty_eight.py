import random
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
import discord
from games.base.dm_game import DMGame
from managers.leveling import LevelingManager
from utils.helpers import get_last_game_id
from core.database.pool import DatabasePool
from core.logging.setup import get_logger
import pymysql
import asyncio


class TwentyFortyEight(DMGame):
    def __init__(self, bot):
        super().__init__(bot)
        # Support both old and new config structure
        games = self.dm_config.get('GAMES', {})
        if not games:
            games = self.dm_config.get('games', {})
        self.game_config = games.get('2048', {}) or games.get('Twenty Forty Eight', {})
        self.logger = get_logger("DMGames")
    
    async def _run_game(self, user: discord.User, game_name: str, test_mode: bool = False) -> bool:
        try:
            if test_mode:
                last_game_id = -999999  # Fake game_id for test mode
            else:
                # Game name in database is "2048"
                last_game_id = await get_last_game_id('2048')
                if not last_game_id:
                    return False
            
            test_label = " 🧪 TEST GAME 🧪" if test_mode else ""
            
            embed = discord.Embed(
                title=f"2048 #{last_game_id}{test_label}",
                description="Welcome to 2048! Use the direction buttons to move tiles. Combine tiles with the same number to reach 2048!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.add_field(name="Score", value="0", inline=True)
            embed.add_field(name="Moves", value="0", inline=True)
            embed.add_field(name="Highest Tile", value="2", inline=True)
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            view = TwentyFortyEightButtons(last_game_id, self.bot, self.config, self.game_config, self.dm_config, user.id, test_mode=test_mode)
            # Register view for persistence across bot restarts
            self.bot.add_view(view)
            await user.send(embed=embed, view=view)
            
            # Save initial state
            if not test_mode:
                await view._save_state()
            
            if not test_mode:
                db = await self._get_db()
                current_unix = int(datetime.now(timezone.utc).timestamp())
                # Table name is users_2048 (numbers are allowed in MySQL table names)
                # Check if user already has a record for this game_id to avoid duplicate key errors
                existing = await db.execute(
                    "SELECT game_id FROM users_2048 WHERE game_id = %s AND user_id = %s",
                    (last_game_id, user.id)
                )
                if not existing:
                    try:
                        # Use INSERT IGNORE to handle duplicate key errors gracefully
                        # This allows multiple users to play the same game_id
                        await db.execute(
                            "INSERT IGNORE INTO users_2048 (game_id, user_id, status, score, moves, highest_tile, started_at, ended_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                            (last_game_id, user.id, 'Started', 0, 0, 2, current_unix, 0)
                        )
                    except pymysql.err.IntegrityError as e:
                        # Handle duplicate key error gracefully (race condition when multiple users start at same time)
                        error_code = e.args[0] if e.args else 0
                        if error_code == 1062:  # Duplicate entry
                            # Try to update existing record if it exists (in case game_id is primary key)
                            try:
                                await db.execute(
                                    "UPDATE users_2048 SET status = 'Started', score = 0, moves = 0, highest_tile = 2, started_at = %s, ended_at = 0 WHERE game_id = %s AND user_id = %s",
                                    (current_unix, last_game_id, user.id)
                                )
                            except Exception as update_error:
                                self.logger.warning(f"Could not update users_2048 for game_id {last_game_id}, user {user.id}: {update_error}")
                        else:
                            raise
                    except Exception as e:
                        # Re-raise other exceptions
                        self.logger.error(f"Error inserting into users_2048: {e}")
                        raise
            
            self.logger.info(f"2048 ({user.name}#{user.discriminator}){' [TEST MODE]' if test_mode else ''}")
            return True
        except Exception as e:
            self.logger.error(f"2048 error: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return False


class TwentyFortyEightButtons(discord.ui.View):
    def __init__(self, game_id: int, bot, config, game_config, dm_config, player_id: int, test_mode: bool = False, saved_state: dict = None):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.game_config = game_config
        self.dm_config = dm_config
        self.player_id = player_id
        self.test_mode = test_mode
        self.logger = get_logger("DMGames")
        
        # Button cooldown
        self.button_cooldown = self.dm_config.get('BUTTON_COOLDOWN', 0.5)
        self.cooldowns: dict = {}
        
        # Initialize or restore game state
        if saved_state:
            self._restore_state(saved_state)
        else:
            # Initialize 4x4 board (0 = empty)
            self.board = [[0 for _ in range(4)] for _ in range(4)]
            self.score = 0
            self.moves = 0
            self.highest_tile = 2
            self.game_ended = False
            self.game_won = False
            
            # Spawn 2 initial tiles
            self._spawn_tile()
            self._spawn_tile()
        
        # Create 16 grid buttons (4x4) - rows 0-3
        for row in range(4):
            for col in range(4):
                button = discord.ui.Button(
                    label=" ",
                    style=discord.ButtonStyle.grey,
                    custom_id=f"2048_grid_{row}_{col}_{game_id}",
                    row=row,
                    disabled=True  # Grid buttons are display-only
                )
                self.add_item(button)
        
        # Create direction buttons on row 4
        up_button = discord.ui.Button(
            emoji="⬆️",
            style=discord.ButtonStyle.blurple,
            custom_id=f"2048_up_{game_id}",
            row=4
        )
        up_button.callback = lambda i: self.handle_move(i, 'up')
        self.add_item(up_button)
        
        left_button = discord.ui.Button(
            emoji="⬅️",
            style=discord.ButtonStyle.blurple,
            custom_id=f"2048_left_{game_id}",
            row=4
        )
        left_button.callback = lambda i: self.handle_move(i, 'left')
        self.add_item(left_button)
        
        right_button = discord.ui.Button(
            emoji="➡️",
            style=discord.ButtonStyle.blurple,
            custom_id=f"2048_right_{game_id}",
            row=4
        )
        right_button.callback = lambda i: self.handle_move(i, 'right')
        self.add_item(right_button)
        
        down_button = discord.ui.Button(
            emoji="⬇️",
            style=discord.ButtonStyle.blurple,
            custom_id=f"2048_down_{game_id}",
            row=4
        )
        down_button.callback = lambda i: self.handle_move(i, 'down')
        self.add_item(down_button)
        
        # Add Cash Out button on row 4
        cash_out_button = discord.ui.Button(
            label="Cash Out",
            emoji="💰",
            style=discord.ButtonStyle.green,
            custom_id=f"2048_cashout_{game_id}",
            row=4
        )
        cash_out_button.callback = self.handle_cash_out
        self.add_item(cash_out_button)
        
        # Update display
        self._update_display()
        
        # Start periodic database update task (every 30 seconds)
        self._periodic_update_task = None
        if not self.test_mode and self.game_id != -999999:
            self._periodic_update_task = asyncio.create_task(self._periodic_database_update())
    
    async def _periodic_database_update(self):
        """Periodically update database with current game state (every 30 seconds)"""
        while not self.game_ended:
            try:
                await asyncio.sleep(30)  # Wait 30 seconds
                
                # Only update if game hasn't ended
                if not self.game_ended:
                    try:
                        db = await DatabasePool.get_instance()
                        await db.execute(
                            "UPDATE users_2048 SET score = %s, moves = %s, highest_tile = %s WHERE user_id = %s AND game_id = %s AND status = 'Started'",
                            (self.score, self.moves, self.highest_tile, self.player_id, self.game_id)
                        )
                    except Exception as e:
                        self.logger.error(f"Error in periodic 2048 database update: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in periodic database update loop: {e}")
                # Continue the loop even if there's an error
                continue
    
    def _get_state(self) -> dict:
        """Get current game state as dictionary"""
        return {
            'board': [row[:] for row in self.board],  # Deep copy
            'score': self.score,
            'moves': self.moves,
            'highest_tile': self.highest_tile,
            'game_ended': self.game_ended,
            'game_won': self.game_won
        }
    
    def _restore_state(self, state: dict):
        """Restore game state from dictionary"""
        self.board = [row[:] for row in state.get('board', [[0 for _ in range(4)] for _ in range(4)])]
        self.score = state.get('score', 0)
        self.moves = state.get('moves', 0)
        self.highest_tile = state.get('highest_tile', 2)
        self.game_ended = state.get('game_ended', False)
        self.game_won = state.get('game_won', False)
        
        # Start periodic database update task if game is not ended
        self._periodic_update_task = None
        if not self.game_ended and not self.test_mode and self.game_id != -999999:
            self._periodic_update_task = asyncio.create_task(self._periodic_database_update())
    
    async def _save_state(self):
        """Save current game state to database"""
        if self.test_mode or self.game_id == -999999:
            return
        
        try:
            from utils.game_state_manager import save_game_state
            state = self._get_state()
            await save_game_state('2048', self.game_id, self.player_id, state, self.test_mode)
        except Exception as e:
            self.logger.error(f"Error saving 2048 game state: {e}")
    
    def _spawn_tile(self):
        """Spawn a new tile (2 or 4) in a random empty cell"""
        empty_cells = [(r, c) for r in range(4) for c in range(4) if self.board[r][c] == 0]
        if not empty_cells:
            return False
        
        row, col = random.choice(empty_cells)
        # 90% chance for 2, 10% chance for 4
        self.board[row][col] = 2 if random.random() < 0.9 else 4
        return True
    
    def _move_left(self) -> bool:
        """Move tiles left and merge. Returns True if board changed."""
        changed = False
        for row in self.board:
            # Remove zeros
            new_row = [x for x in row if x != 0]
            # Merge adjacent equal tiles
            merged = []
            i = 0
            while i < len(new_row):
                if i < len(new_row) - 1 and new_row[i] == new_row[i + 1]:
                    merged_value = new_row[i] * 2
                    merged.append(merged_value)
                    self.score += merged_value
                    self.highest_tile = max(self.highest_tile, merged_value)
                    i += 2
                else:
                    merged.append(new_row[i])
                    i += 1
            # Pad with zeros
            new_row = merged + [0] * (4 - len(merged))
            if new_row != row:
                changed = True
            row[:] = new_row
        return changed
    
    def _move_right(self) -> bool:
        """Move tiles right and merge. Returns True if board changed."""
        changed = False
        for row in self.board:
            # Remove zeros
            new_row = [x for x in row if x != 0]
            # Merge adjacent equal tiles (from right)
            merged = []
            i = len(new_row) - 1
            while i >= 0:
                if i > 0 and new_row[i] == new_row[i - 1]:
                    merged_value = new_row[i] * 2
                    merged.insert(0, merged_value)
                    self.score += merged_value
                    self.highest_tile = max(self.highest_tile, merged_value)
                    i -= 2
                else:
                    merged.insert(0, new_row[i])
                    i -= 1
            # Pad with zeros on left
            new_row = [0] * (4 - len(merged)) + merged
            if new_row != row:
                changed = True
            row[:] = new_row
        return changed
    
    def _move_up(self) -> bool:
        """Move tiles up and merge. Returns True if board changed."""
        changed = False
        for col in range(4):
            # Get column
            column = [self.board[r][col] for r in range(4)]
            # Remove zeros
            new_col = [x for x in column if x != 0]
            # Merge adjacent equal tiles
            merged = []
            i = 0
            while i < len(new_col):
                if i < len(new_col) - 1 and new_col[i] == new_col[i + 1]:
                    merged_value = new_col[i] * 2
                    merged.append(merged_value)
                    self.score += merged_value
                    self.highest_tile = max(self.highest_tile, merged_value)
                    i += 2
                else:
                    merged.append(new_col[i])
                    i += 1
            # Pad with zeros
            new_col = merged + [0] * (4 - len(merged))
            # Update column
            old_col = [self.board[r][col] for r in range(4)]
            if new_col != old_col:
                changed = True
            for r in range(4):
                self.board[r][col] = new_col[r]
        return changed
    
    def _move_down(self) -> bool:
        """Move tiles down and merge. Returns True if board changed."""
        changed = False
        for col in range(4):
            # Get column
            column = [self.board[r][col] for r in range(4)]
            # Remove zeros
            new_col = [x for x in column if x != 0]
            # Merge adjacent equal tiles (from bottom)
            merged = []
            i = len(new_col) - 1
            while i >= 0:
                if i > 0 and new_col[i] == new_col[i - 1]:
                    merged_value = new_col[i] * 2
                    merged.insert(0, merged_value)
                    self.score += merged_value
                    self.highest_tile = max(self.highest_tile, merged_value)
                    i -= 2
                else:
                    merged.insert(0, new_col[i])
                    i -= 1
            # Pad with zeros on top
            new_col = [0] * (4 - len(merged)) + merged
            # Update column
            old_col = [self.board[r][col] for r in range(4)]
            if new_col != old_col:
                changed = True
            for r in range(4):
                self.board[r][col] = new_col[r]
        return changed
    
    def _can_move(self) -> bool:
        """Check if any moves are possible"""
        # Check for empty cells
        for r in range(4):
            for c in range(4):
                if self.board[r][c] == 0:
                    return True
        
        # Check for possible merges
        for r in range(4):
            for c in range(4):
                val = self.board[r][c]
                # Check right
                if c < 3 and self.board[r][c + 1] == val:
                    return True
                # Check down
                if r < 3 and self.board[r + 1][c] == val:
                    return True
        
        return False
    
    def _get_tile_emoji(self, value: int) -> str:
        """Get text representation for tile value"""
        if value == 0:
            return "⬛"
        
        # Return number as text (no emojis)
        return str(value)
    
    def _update_display(self):
        """Update all grid button labels to reflect current board state"""
        for row in range(4):
            for col in range(4):
                button_index = row * 4 + col
                button = self.children[button_index]
                value = self.board[row][col]
                button.label = self._get_tile_emoji(value)
                
                # Color coding based on value
                if value == 0:
                    button.style = discord.ButtonStyle.grey
                elif value == 2:
                    button.style = discord.ButtonStyle.grey
                elif value == 4:
                    button.style = discord.ButtonStyle.grey
                elif value == 8:
                    button.style = discord.ButtonStyle.blurple
                elif value == 16:
                    button.style = discord.ButtonStyle.blurple
                elif value == 32:
                    button.style = discord.ButtonStyle.green
                elif value == 64:
                    button.style = discord.ButtonStyle.green
                elif value == 128:
                    button.style = discord.ButtonStyle.green
                elif value == 256:
                    button.style = discord.ButtonStyle.green
                elif value == 512:
                    button.style = discord.ButtonStyle.green
                elif value == 1024:
                    button.style = discord.ButtonStyle.green
                elif value == 2048:
                    button.style = discord.ButtonStyle.green  # Special color for 2048
                else:
                    button.style = discord.ButtonStyle.red
    
    async def handle_move(self, interaction: discord.Interaction, direction: str):
        """Handle a move in the specified direction"""
        if interaction.user.id != self.player_id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        
        if self.game_ended:
            await interaction.response.send_message("This game has ended!", ephemeral=True)
            return
        
        # Check cooldown
        user_id = interaction.user.id
        if user_id in self.cooldowns and datetime.now(timezone.utc) < self.cooldowns[user_id]:
            remaining = (self.cooldowns[user_id] - datetime.now(timezone.utc)).total_seconds()
            await interaction.response.send_message(
                f"❌ You need to wait {remaining:.2f} seconds before moving again.",
                ephemeral=True
            )
            return
        
        # Defer immediately for faster response
        await interaction.response.defer()
        
        # Perform move (fast, synchronous operation)
        if direction == 'left':
            changed = self._move_left()
        elif direction == 'right':
            changed = self._move_right()
        elif direction == 'up':
            changed = self._move_up()
        elif direction == 'down':
            changed = self._move_down()
        else:
            return
        
        if changed:
            self.moves += 1
            # Spawn new tile
            if not self._spawn_tile():
                # Board is full, check if game is over
                if not self._can_move():
                    await self._handle_loss(interaction)
                    return
            
            # Update display immediately (fast operation)
            self._update_display()
            
            # Check for win (reached 2048) - do this in background to not block UI
            win_check_needed = not self.game_won and self.highest_tile >= 2048
            if win_check_needed:
                self.game_won = True
                # Run database/achievement checks in background (non-blocking)
                if not self.test_mode:
                    import asyncio
                    asyncio.create_task(self._handle_win_async(interaction))
            
            # Update embed immediately (fast operation)
            await self._update_embed(interaction)
            
            # Save state to database
            await self._save_state()
            
            # Update cooldown
            self.cooldowns[user_id] = datetime.now(timezone.utc) + timedelta(seconds=self.button_cooldown)
        else:
            # Move didn't change anything
            await interaction.followup.send("That move isn't possible!", ephemeral=True)
    
    async def _handle_win_async(self, interaction: discord.Interaction):
        """Handle win checks in background (non-blocking)"""
        try:
            db = await DatabasePool.get_instance()
            await db.execute(
                "UPDATE users_2048 SET status = 'Won', score = %s, moves = %s, highest_tile = %s WHERE user_id = %s AND game_id = %s",
                (self.score, self.moves, self.highest_tile, self.player_id, self.game_id)
            )
            
            # Check for achievements (non-blocking)
            from utils.achievements import check_dm_game_win
            await check_dm_game_win(interaction.user, "2048", interaction.channel, self.bot)
            
            # Also check for best score achievement
            from managers.milestones import MilestonesManager
            milestones_manager = MilestonesManager()
            await milestones_manager.check_achievements(self.player_id, "2048", "best_score", self.score)
        except Exception as e:
            self.logger.error(f"Error in _handle_win_async: {e}")
    
    async def _update_embed(self, interaction: discord.Interaction):
        """Update the embed with current game state"""
        try:
            embed = interaction.message.embeds[0]
            embed.set_field_at(0, name="Score", value=str(self.score), inline=True)
            embed.set_field_at(1, name="Moves", value=str(self.moves), inline=True)
            embed.set_field_at(2, name="Highest Tile", value=str(self.highest_tile), inline=True)
            
            if self.game_won and not self.game_ended:
                embed.description = "🎉 **You reached 2048!** Continue playing to get a higher score!"
            
            # Use followup.edit_message for faster updates if available, otherwise use message.edit
            if hasattr(interaction, 'followup') and hasattr(interaction.followup, 'edit_message'):
                try:
                    await interaction.followup.edit_message(interaction.message.id, embed=embed, view=self)
                except:
                    await interaction.message.edit(embed=embed, view=self)
            else:
                await interaction.message.edit(embed=embed, view=self)
        except Exception as e:
            self.logger.error(f"Error updating embed: {e}")
            # Try to update just the view if embed update fails
            try:
                await interaction.message.edit(view=self)
            except:
                pass
    
    async def _handle_loss(self, interaction: discord.Interaction):
        """Handle game loss"""
        self.game_ended = True
        
        # Cancel periodic update task
        if hasattr(self, '_periodic_update_task') and self._periodic_update_task:
            self._periodic_update_task.cancel()
        
        # Disable all direction buttons
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id.startswith("2048_"):
                if item.custom_id.startswith("2048_grid_"):
                    continue  # Keep grid buttons visible
                item.disabled = True
        
        embed = interaction.message.embeds[0]
        win_text = "🎉 **You reached 2048!** " if self.game_won else ""
        embed.description = f"{win_text}❌ **Game Over!** No more moves possible.\n\n**Final Score:** {self.score}\n**Total Moves:** {self.moves}\n**Highest Tile:** {self.highest_tile}"
        
        # Calculate XP based on score and highest tile
        xp = self._calculate_xp()
        
        # Update UI immediately
        await interaction.message.edit(embed=embed, view=self)
        win_msg = "🎉 You reached 2048! " if self.game_won else ""
        await interaction.followup.send(
            f"`{'✅' if self.game_won else '❌'}` {win_msg}Game Over! You scored **{self.score}** points with **{self.moves}** moves. Highest tile: **{self.highest_tile}**. {'You would have earned' if self.test_mode else 'You earned'} `{xp}xp`!",
            ephemeral=False
        )
        
        # Save final state
        await self._save_state()
        
        # Handle database/XP in background (non-blocking)
        if not self.test_mode:
            import asyncio
            asyncio.create_task(self._handle_loss_async(interaction, xp))
        else:
            # Test mode - just log
            self.logger.info(f"[TEST MODE] 2048 game {self.game_id} {'won' if self.game_won else 'lost'} by {interaction.user.name}. Score: {self.score}, XP would have been: {xp}")
    
    async def _handle_loss_async(self, interaction: discord.Interaction, xp: int):
        """Handle loss database operations in background (non-blocking)"""
        try:
            # Award XP
            lvl_mng = LevelingManager(
                user=interaction.user,
                channel=interaction.channel,
                client=self.bot,
                xp=xp,
                source="2048",
                game_id=self.game_id,
                test_mode=False
            )
            await lvl_mng.update()
            
            # Update database - if they won (reached 2048), keep status as 'Won', otherwise 'Lost'
            db = await DatabasePool.get_instance()
            current_unix = int(datetime.now(timezone.utc).timestamp())
            status = 'Won' if self.game_won else 'Lost'
            await db.execute(
                "UPDATE users_2048 SET status = %s, score = %s, moves = %s, highest_tile = %s, ended_at = %s WHERE user_id = %s AND game_id = %s",
                (status, self.score, self.moves, self.highest_tile, current_unix, self.player_id, self.game_id)
            )
            
            # Check for best score achievement
            from managers.milestones import MilestonesManager
            milestones_manager = MilestonesManager()
            await milestones_manager.check_achievements(self.player_id, "2048", "best_score", self.score)
        except Exception as e:
            self.logger.error(f"Error in _handle_loss_async: {e}")
    
    def _calculate_xp(self) -> int:
        """Calculate XP based on score and highest tile (scaled: 500xp for 2048)"""
        # For reaching 2048, award 500xp (with some variation)
        if self.highest_tile >= 2048:
            import random
            return random.randint(480, 520)  # 480-520 XP for reaching 2048
        
        # For other tiles, use scaled system similar to cash out
        # Base XP from score (capped)
        score_xp = min(self.score // 100, 50)  # Max 50 XP from score
        
        # Bonus XP from highest tile (scaled)
        tile_bonus = 0
        if self.highest_tile >= 1024:
            tile_bonus = 350  # 350-390 range for 1024
        elif self.highest_tile >= 512:
            tile_bonus = 240  # 240-260 range for 512
        elif self.highest_tile >= 256:
            tile_bonus = 170  # 170-185 range for 256
        elif self.highest_tile >= 128:
            tile_bonus = 100  # 100-115 range for 128
        elif self.highest_tile >= 64:
            tile_bonus = 60
        elif self.highest_tile >= 32:
            tile_bonus = 35
        elif self.highest_tile >= 16:
            tile_bonus = 20
        else:
            tile_bonus = 10
        
        # Moves bonus (efficiency) - smaller bonus since tile bonus is now higher
        moves_bonus = max(0, 10 - (self.moves // 20))  # Fewer moves = more bonus (capped at 10)
        
        total_xp = score_xp + tile_bonus + moves_bonus
        return max(10, min(total_xp, 400))  # Between 10 and 400 XP (2048 handled separately above)
    
    def _calculate_cash_out_xp(self) -> int:
        """Calculate XP for cash out based only on highest tile (scaled: 100xp at 128, 500xp at 2048)"""
        import random
        
        # XP ranges based on highest tile
        # Scale: 100xp at 128, 500xp at 2048, with appropriate scaling between
        if self.highest_tile >= 2048:
            base_xp = 480
            range_size = 40  # 480-520 XP
        elif self.highest_tile >= 1024:
            base_xp = 360
            range_size = 30  # 360-390 XP
        elif self.highest_tile >= 512:
            base_xp = 240
            range_size = 20  # 240-260 XP
        elif self.highest_tile >= 256:
            base_xp = 170
            range_size = 15  # 170-185 XP
        elif self.highest_tile >= 128:
            base_xp = 100
            range_size = 15  # 100-115 XP
        elif self.highest_tile >= 64:
            base_xp = 60
            range_size = 10  # 60-70 XP
        elif self.highest_tile >= 32:
            base_xp = 35
            range_size = 8  # 35-43 XP
        elif self.highest_tile >= 16:
            base_xp = 20
            range_size = 5  # 20-25 XP
        else:
            base_xp = 10
            range_size = 5  # 10-15 XP
        
        # Return random XP within the range
        return random.randint(base_xp, base_xp + range_size)
    
    async def handle_cash_out(self, interaction: discord.Interaction):
        """Handle cash out - end game early and award XP based on highest tile"""
        if interaction.user.id != self.player_id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        
        if self.game_ended:
            await interaction.response.send_message("This game has already ended!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        self.game_ended = True
        
        # Cancel periodic update task
        if hasattr(self, '_periodic_update_task') and self._periodic_update_task:
            self._periodic_update_task.cancel()
        
        # Disable all buttons except grid buttons
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id.startswith("2048_"):
                if item.custom_id.startswith("2048_grid_"):
                    continue  # Keep grid buttons visible
                item.disabled = True
        
        # Calculate cash out XP
        xp = self._calculate_cash_out_xp()
        
        embed = interaction.message.embeds[0]
        embed.description = f"💰 **Cashed Out!**\n\n**Final Score:** {self.score}\n**Total Moves:** {self.moves}\n**Highest Tile:** {self.highest_tile}\n**XP Earned:** {xp}"
        
        # Update UI immediately
        await interaction.message.edit(embed=embed, view=self)
        await interaction.followup.send(
            f"`💰` Cashed Out! You {'would have earned' if self.test_mode else 'earned'} **{xp} XP** based on your highest tile of **{self.highest_tile}**!",
            ephemeral=False
        )
        
        # Save final state
        await self._save_state()
        
        # Handle database/XP in background (non-blocking)
        if not self.test_mode:
            import asyncio
            asyncio.create_task(self._handle_cash_out_async(interaction, xp))
        else:
            # Test mode - just log
            self.logger.info(f"[TEST MODE] 2048 game {self.game_id} cashed out by {interaction.user.name}. Score: {self.score}, XP would have been: {xp}")
    
    async def _handle_cash_out_async(self, interaction: discord.Interaction, xp: int):
        """Handle cash out database operations in background (non-blocking)"""
        try:
            # Award XP
            lvl_mng = LevelingManager(
                user=interaction.user,
                channel=interaction.channel,
                client=self.bot,
                xp=xp,
                source="2048",
                game_id=self.game_id,
                test_mode=False
            )
            await lvl_mng.update()
            
            # Update database with 'Cashed Out' status
            db = await DatabasePool.get_instance()
            current_unix = int(datetime.now(timezone.utc).timestamp())
            await db.execute(
                "UPDATE users_2048 SET status = 'Cashed Out', score = %s, moves = %s, highest_tile = %s, ended_at = %s WHERE user_id = %s AND game_id = %s",
                (self.score, self.moves, self.highest_tile, current_unix, self.player_id, self.game_id)
            )
            
            # Check for best score achievement
            from managers.milestones import MilestonesManager
            milestones_manager = MilestonesManager()
            await milestones_manager.check_achievements(self.player_id, "2048", "best_score", self.score)
        except Exception as e:
            self.logger.error(f"Error in _handle_cash_out_async: {e}")
    
    async def _check_valid_game(self, interaction: discord.Interaction) -> bool:
        """Check if this game is still valid"""
        if self.test_mode:
            return True
        
        last_game_id = await get_last_game_id('2048')
        if not last_game_id or self.game_id != last_game_id:
            await interaction.response.send_message(
                "`❌` Sorry, but this game has already ended. Please go to the leveling channel to begin another one!",
                ephemeral=True
            )
            return False
        return True

