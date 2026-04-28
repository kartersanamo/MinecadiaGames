import random
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
from PIL import Image, ImageDraw, ImageFont
import discord
from games.base.dm_game import DMGame
from managers.leveling import LevelingManager
from utils.helpers import get_last_game_id
from core.database.pool import DatabasePool
from core.logging.setup import get_logger


class TicTacToe(DMGame):
    def __init__(self, bot):
        super().__init__(bot)
        # Support both old and new config structure
        games = self.dm_config.get('GAMES', {})
        if not games:
            games = self.dm_config.get('games', {})
        self.game_config = games.get('TicTacToe', {})
        self.logger = get_logger("DMGames")
    
    async def _run_game(self, user: discord.User, game_name: str, test_mode: bool = False) -> bool:
        try:
            if test_mode:
                last_game_id = -999999  # Fake game_id for test mode
            else:
                last_game_id = await get_last_game_id('tictactoe')
                if not last_game_id:
                    return False
            
            test_label = " 🧪 TEST GAME 🧪" if test_mode else ""
            
            view = TicTacToeButtons(last_game_id, self.bot, self.config, self.game_config, test_mode=test_mode)
            # Register view for persistence across bot restarts
            self.bot.add_view(view)
            
            # Generate initial empty board image
            initial_image_path = await view.generate_board_image()
            initial_image_file = discord.File(initial_image_path, filename="tictactoe.png")
            
            embed = discord.Embed(
                title=f"TicTacToe #{last_game_id}{test_label}",
                description="Welcome to TicTacToe! Begin by clicking on any of the center 9 buttons below!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.set_image(url="attachment://tictactoe.png")
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            await user.send(embed=embed, view=view, file=initial_image_file)
            
            # Clean up initial image after sending
            try:
                os.remove(initial_image_path)
            except:
                pass
            
            if not test_mode:
                db = await self._get_db()
                current_unix = int(datetime.now(timezone.utc).timestamp())
                await db.execute_insert(
                    "INSERT INTO users_tictactoe (game_id, user_id, won, ended_at, started_at) VALUES (%s, %s, %s, %s, %s)",
                    (last_game_id, user.id, 'Started', 0, current_unix)
                )
            
            self.logger.info(f"TicTacToe ({user.name}#{user.discriminator})")
            return True
        except Exception as e:
            self.logger.error(f"TicTacToe error: {e}")
            return False


class TicTacToeButtons(discord.ui.View):
    def __init__(self, game_id: int, bot, config, game_config, test_mode: bool = False, saved_state: dict = None):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.game_config = game_config
        self.test_mode = test_mode
        self.dm_config = config.get('dm_games')
        self.button_cooldown = self.dm_config.get('BUTTON_COOLDOWN', 0.8)
        self.message = None  # Store message reference for image updates
        self.cooldowns = {}
        self.logger = get_logger("DMGames")
        
        # Initialize or restore game state
        if saved_state:
            self._restore_state(saved_state)
        else:
            self.board = [['' for _ in range(3)] for _ in range(3)]
            self.game_ended = False
        
        for i in range(9):
            row = i // 3
            col = i % 3
            button = discord.ui.Button(
                label="\u200b",
                style=discord.ButtonStyle.grey,
                custom_id=f"ttt_{i}_{game_id}",
                row=row
            )
            button.callback = self.create_callback(i, row, col)
            self.add_item(button)
    
    def _get_state(self) -> dict:
        """Get current game state as dictionary"""
        return {
            'board': [row[:] for row in self.board],  # Deep copy
            'game_ended': getattr(self, 'game_ended', False)
        }
    
    def _restore_state(self, state: dict):
        """Restore game state from dictionary"""
        self.board = [row[:] for row in state.get('board', [['' for _ in range(3)] for _ in range(3)])]
        self.game_ended = state.get('game_ended', False)
        
        # Update button states to match board
        for i in range(9):
            row = i // 3
            col = i % 3
            button = [b for b in self.children if b.custom_id == f"ttt_{i}_{self.game_id}"][0]
            if self.board[row][col] == 'X':
                button.disabled = True
                button.style = discord.ButtonStyle.green
                button.emoji = "✖️"
            elif self.board[row][col] == 'O':
                button.disabled = True
                button.style = discord.ButtonStyle.red
                button.emoji = "⭕"
            elif self.game_ended:
                button.disabled = True
    
    async def _save_state(self):
        """Save current game state to database"""
        if self.test_mode or self.game_id == -999999 or not hasattr(self, 'player_id'):
            return
        
        try:
            from utils.game_state_manager import save_game_state
            state = self._get_state()
            await save_game_state('tictactoe', self.game_id, self.player_id, state, self.test_mode)
        except Exception as e:
            from core.logging.setup import get_logger
            self.logger.error(f"Error saving TicTacToe game state: {e}")
    
    def create_callback(self, index: int, row: int, col: int):
        async def callback(interaction: discord.Interaction):
            await self.handle_click(interaction, index, row, col)
        return callback
    
    async def handle_click(self, interaction: discord.Interaction, index: int, row: int, col: int):
        user_id = interaction.user.id
        
        if not await self._check_valid_game(interaction):
            return
        
        if user_id in self.cooldowns and datetime.now(timezone.utc) < self.cooldowns[user_id]:
            remaining = (self.cooldowns[user_id] - datetime.now(timezone.utc)).total_seconds()
            await interaction.response.send_message(
                f"❌ You need to wait {remaining:.2f} seconds before using this button again.",
                ephemeral=True
            )
            return
        
        if self.board[row][col] != '':
            await interaction.response.send_message("This position is already taken!", ephemeral=True)
            return
        
        self.cooldowns[user_id] = datetime.now(timezone.utc) + timedelta(seconds=self.button_cooldown)
        
        await interaction.response.defer()
        
        self.board[row][col] = 'X'
        button = [b for b in self.children if b.custom_id == f"ttt_{index}_{self.game_id}"][0]
        button.disabled = True
        button.style = discord.ButtonStyle.green
        button.emoji = "✖️"
        
        check = await self._check_win()
        if check:
            await self._handle_win(interaction, check)
        else:
            await self._computer_turn(interaction)
            check = await self._check_win()
            if check:
                await self._handle_win(interaction, check)
        
        # Generate and update board image
        image_path = await self.generate_board_image()
        image_file = discord.File(image_path, filename="tictactoe.png")
        
        embed = interaction.message.embeds[0]
        embed.set_image(url="attachment://tictactoe.png")
        
        await interaction.message.edit(embed=embed, view=self, attachments=[image_file])
        
        # Save state after move
        await self._save_state()
        
        # Clean up old image file
        try:
            os.remove(image_path)
        except:
            pass
    
    async def _check_valid_game(self, interaction: discord.Interaction) -> bool:
        # Skip validation for test games
        if self.test_mode:
            return True
        
        last_game_id = await get_last_game_id('tictactoe')
        if self.game_id != last_game_id:
            await interaction.response.send_message(
                "`❌` Sorry, but this game has already ended. Please go to the leveling channel to begin another one!",
                ephemeral=True
            )
            return False
        return True
    
    async def _check_win(self) -> Optional[str]:
        for row in self.board:
            if row[0] == row[1] == row[2] != '':
                return row[0]
        
        for col in range(3):
            if self.board[0][col] == self.board[1][col] == self.board[2][col] != '':
                return self.board[0][col]
        
        if self.board[0][0] == self.board[1][1] == self.board[2][2] != '':
            return self.board[0][0]
        
        if self.board[0][2] == self.board[1][1] == self.board[2][0] != '':
            return self.board[0][2]
        
        if all(self.board[i][j] != '' for i in range(3) for j in range(3)):
            return "Full"
        
        return None
    
    async def _computer_turn(self, interaction: discord.Interaction):
        open_spaces = [(i, j) for i in range(3) for j in range(3) if self.board[i][j] == '']
        if not open_spaces:
            return
        
        row, col = random.choice(open_spaces)
        self.board[row][col] = 'O'
        
        index = row * 3 + col
        button = [b for b in self.children if b.custom_id == f"ttt_{index}_{self.game_id}"][0]
        button.disabled = True
        button.style = discord.ButtonStyle.blurple
        button.emoji = "⭕"
    
    async def generate_board_image(self) -> str:
        """Generate TicTacToe board image with X's and O's"""
        from pathlib import Path
        project_root = Path(__file__).resolve().parents[2]
        
        # Try .jpg first, then .png
        board_path = project_root / "assets" / "Images" / "TicTacToeBoard.jpg"
        if not board_path.exists():
            board_path = project_root / "assets" / "Images" / "TicTacToeBoard.png"
        if not board_path.exists():
            board_path = project_root / "assets" / "Images" / "TicTacToe.png"
        
            # Load base image
        with Image.open(str(board_path)) as base_image:
            draw = ImageDraw.Draw(base_image)
            
            board_width = base_image.width
            board_height = base_image.height
            
            # Calculate cell positions (3x3 grid)
            # More precise calculation: grid typically takes up ~70-75% of the image
            # Account for borders by using a percentage of the smaller dimension
            grid_dimension = min(board_width, board_height)
            grid_area_size = grid_dimension * 0.73  # 73% accounts for borders
            cell_size = grid_area_size / 3  # Divide by 3 for 3x3 grid
            # Center the grid, accounting for borders (typically ~13.5% margin on each side)
            margin = (grid_dimension - grid_area_size) / 2
            grid_start_x = margin + (board_width - grid_dimension) / 2
            grid_start_y = margin + (board_height - grid_dimension) / 2
            
            # Load font for X and O - scale font size based on cell_size
            font_path = project_root / "assets" / "Fonts" / "ArcadeRounded.ttf"
            font_size = int(cell_size * 0.58)  # Slightly smaller so edge cells stay visually centered
            try:
                symbol_font = ImageFont.truetype(str(font_path), font_size)
            except:
                symbol_font = ImageFont.load_default()
            
            # Draw X's and O's on the board
            for row in range(3):
                for col in range(3):
                    cell_value = self.board[row][col]
                    if cell_value == '':
                        continue
                    
                    # Calculate center of cell
                    x = grid_start_x + (col + 0.5) * cell_size
                    y = grid_start_y + (row + 0.5) * cell_size
                    
                    if cell_value == 'X':
                        # Draw X in red/green color
                        symbol = 'X'
                        color = "#4CAF50"  # Green for player
                        # Draw X with stroke for visibility (stroke scales with font size)
                        stroke_width = max(2, int(font_size * 0.07))  # ~7% of font size, minimum 2
                        draw.text(
                            (x, y),
                            symbol,
                            font=symbol_font,
                            fill=color,
                            anchor="mm",
                            stroke_width=stroke_width,
                            stroke_fill="#000000"
                        )
                    elif cell_value == 'O':
                        # Draw O in blue color
                        symbol = 'O'
                        color = "#2196F3"  # Blue for bot
                        # Draw O with stroke for visibility (stroke scales with font size)
                        stroke_width = max(2, int(font_size * 0.07))  # ~7% of font size, minimum 2
                        draw.text(
                            (x, y),
                            symbol,
                            font=symbol_font,
                            fill=color,
                            anchor="mm",
                            stroke_width=stroke_width,
                            stroke_fill="#000000"
                        )
            
            # Save image
            output_path = project_root / "assets" / "Images" / f"tictactoe_{self.game_id}_{uuid.uuid4().hex[:8]}.png"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            base_image.save(output_path)
        
        return str(output_path)
    
    async def _handle_win(self, interaction: discord.Interaction, result: str):
        self.game_ended = True
        for button in self.children:
            button.disabled = True
        
        # Save final state
        await self._save_state()
        
        # Generate final board image
        image_path = await self.generate_board_image()
        image_file = discord.File(image_path, filename="tictactoe.png")
        
        embed = interaction.message.embeds[0]
        embed.set_image(url="attachment://tictactoe.png")
        
        # Update message with final board
        await interaction.message.edit(embed=embed, view=self, attachments=[image_file])
        
        # Clean up image
        try:
            os.remove(image_path)
        except:
            self.logger.error(f"Failed to delete the TicTacToe image at {image_path}")
        
        db = await DatabasePool.get_instance()
        current_unix = int(datetime.now(timezone.utc).timestamp())
        
        if result == "X":
            xp = random.randint(
                self.game_config.get('WIN_XP', {}).get('LOWER', 40),
                self.game_config.get('WIN_XP', {}).get('UPPER', 60)
            )
            
            if self.test_mode:
                await interaction.channel.send(
                    f"`✅` Congratulations {interaction.user.mention}! You won! You would have earned `{xp}xp`!"
                )
            else:
                await interaction.channel.send(
                    f"`✅` Congratulations {interaction.user.mention}! You won `{xp}xp`!"
                )
                await db.execute(
                    "UPDATE users_tictactoe SET won = 'Won', ended_at = %s WHERE user_id = %s AND game_id = %s",
                    (current_unix, interaction.user.id, self.game_id)
                )
                lvl_mng = LevelingManager(
                    user=interaction.user,
                    channel=interaction.channel,
                    client=self.bot,
                    xp=xp,
                    source="TicTacToe",
                    game_id=self.game_id
                )
                await lvl_mng.update()
                
                # Check for achievements
                from utils.achievements import check_dm_game_win
                await check_dm_game_win(interaction.user, "TicTacToe", interaction.channel, self.bot)
        elif result == "O":
            await interaction.channel.send(
                f"`❌` Sorry {interaction.user.mention}, the bot has beat you in TicTacToe! Come back later to try again!"
            )
            if not self.test_mode:
                await db.execute(
                    "UPDATE users_tictactoe SET won = 'Lost', ended_at = %s WHERE user_id = %s AND game_id = %s",
                    (current_unix, interaction.user.id, self.game_id)
                )
        elif result == "Full":
            await interaction.channel.send(
                f"`🟰` Uh oh {interaction.user.mention}, you and the bot have tied in TicTacToe! Come back later to try again!"
            )
            if not self.test_mode:
                await db.execute(
                    "UPDATE users_tictactoe SET won = 'Tied', ended_at = %s WHERE user_id = %s AND game_id = %s",
                    (current_unix, interaction.user.id, self.game_id)
                )

