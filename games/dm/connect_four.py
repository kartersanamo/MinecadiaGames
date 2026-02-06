import asyncio
import random
import math
from datetime import datetime, timedelta, timezone
from typing import Optional
from PIL import Image
import discord
from games.base.dm_game import DMGame
from managers.leveling import LevelingManager
from utils.helpers import get_last_game_id
from core.database.pool import DatabasePool
from core.logging.setup import get_logger


class ConnectFour(DMGame):
    def __init__(self, bot):
        super().__init__(bot)
        # Support both old and new config structure
        games = self.dm_config.get('GAMES', {})
        if not games:
            games = self.dm_config.get('games', {})
        self.game_config = games.get('Connect Four', {})
        self.logger = get_logger("DMGames")
    
    async def _run_game(self, user: discord.User, game_name: str, test_mode: bool = False) -> bool:
        try:
            last_game_id = await get_last_game_id('connect four')
            if not last_game_id:
                return False
            
            embed = discord.Embed(
                title=f"Connect Four #{last_game_id}",
                description="Welcome to Connect Four! Begin by choosing a position below!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.add_field(name="Number of Moves", value="0")
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            from pathlib import Path
            # Calculate project root: games/dm/connect_four.py -> games/dm/ -> games/ -> project_root/
            project_root = Path(__file__).parent.parent.parent
            # Support both old and new structure
            assets = self.game_config.get('assets', {})
            base_image_path = self.game_config.get("base_image_path") or assets.get("board", "assets/Images/ConnectFourBoard.png")
            base_path = project_root / base_image_path
            file = discord.File(str(base_path), filename="ConnectFourBoard.png")
            embed.set_image(url="attachment://ConnectFourBoard.png")
            
            view = ConnectFourButtons(last_game_id, self.bot, self.config, self.game_config, test_mode=test_mode)
            view.player_id = user.id  # Store player_id for state saving
            # Register view for persistence across bot restarts
            self.bot.add_view(view)
            await user.send(file=file, embed=embed, view=view)
            
            # Save initial state
            if not test_mode:
                await view._save_state()
            
            db = await self._get_db()
            current_unix = int(datetime.now(timezone.utc).timestamp())
            await db.execute_insert(
                "INSERT INTO users_connectfour (game_id, user_id, status, moves, ended_at, started_at) VALUES (%s, %s, %s, %s, %s, %s)",
                (last_game_id, user.id, 'Started', 0, 0, current_unix)
            )
            
            self.logger.info(f"Connect Four ({user.name}#{user.discriminator})")
            return True
        except Exception as e:
            self.logger.error(f"Connect Four error: {e}")
            return False


class ConnectFourButtons(discord.ui.View):
    def __init__(self, game_id: int, bot, config, game_config, test_mode: bool = False, saved_state: dict = None):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.game_config = game_config
        self.test_mode = test_mode
        self.dm_config = config.get('dm_games')
        self.button_cooldown = self.dm_config.get('BUTTON_COOLDOWN', 0.8)
        self.cooldowns = {}
        self._move_lock = asyncio.Lock()  # Prevent concurrent moves / double XP on win
        
        # Initialize or restore game state
        if saved_state:
            self._restore_state(saved_state)
        else:
            self.board = [['' for _ in range(7)] for _ in range(6)]
            self.moves = 0
            self.full = []
            self.game_ended = False
        
        positions = [0, 1, 2, 3, 4, 5, 6]
        for i, pos in enumerate(positions):
            row = i // 4
            button = discord.ui.Button(
                label=str(pos + 1),
                style=discord.ButtonStyle.grey,
                custom_id=f"cf_{pos}_{game_id}",
                row=row
            )
            button.callback = self.create_callback(pos)
            self.add_item(button)
    
    def _get_state(self) -> dict:
        """Get current game state as dictionary"""
        return {
            'board': [row[:] for row in self.board],  # Deep copy
            'moves': self.moves,
            'full': self.full[:],  # Copy list
            'game_ended': getattr(self, 'game_ended', False)
        }
    
    def _restore_state(self, state: dict):
        """Restore game state from dictionary"""
        self.board = [row[:] for row in state.get('board', [['' for _ in range(7)] for _ in range(6)])]
        self.moves = state.get('moves', 0)
        self.full = state.get('full', [])
        self.game_ended = state.get('game_ended', False)
        
        # Update button states
        for button in self.children:
            if button.custom_id in self.full:
                button.disabled = True
            elif self.game_ended:
                button.disabled = True
            else:
                button.disabled = False  # Ensure buttons are enabled if not full and game hasn't ended
    
    async def _save_state(self):
        """Save current game state to database"""
        if self.test_mode or self.game_id == -999999 or not hasattr(self, 'player_id'):
            return
        
        try:
            from utils.game_state_manager import save_game_state
            state = self._get_state()
            await save_game_state('connectfour', self.game_id, self.player_id, state, self.test_mode)
        except Exception as e:
            from core.logging.setup import get_logger
            logger = get_logger("DMGames")
            logger.error(f"Error saving Connect Four game state: {e}")
    
    def create_callback(self, position: int):
        async def callback(interaction: discord.Interaction):
            await self.handle_click(interaction, position)
        return callback
    
    async def handle_click(self, interaction: discord.Interaction, index: int):
        user_id = interaction.user.id
        
        if not await self._check_valid_game(interaction):
            return
        
        if self.game_ended:
            await interaction.response.send_message(
                "`❌` This game has already ended.",
                ephemeral=True
            )
            return
        
        if user_id in self.cooldowns and datetime.now(timezone.utc) < self.cooldowns[user_id]:
            remaining = (self.cooldowns[user_id] - datetime.now(timezone.utc)).total_seconds()
            await interaction.response.send_message(
                f"❌ You need to wait {remaining:.2f} seconds before using this button again.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        
        async with self._move_lock:
            # Re-check after acquiring lock (another click may have ended the game)
            if self.game_ended:
                try:
                    await interaction.followup.send("`❌` This game has already ended.", ephemeral=True)
                except discord.NotFound:
                    pass
                return
            
            highest_row = await self.get_highest_row(index)
            if highest_row == -1:
                button = [b for b in self.children if b.custom_id == f"cf_{index}_{self.game_id}"][0]
                button.disabled = True
                self.full.append(button.custom_id)
                await interaction.edit_original_response(view=self)
                return
            
            self.board[highest_row][index] = "R"
            self.moves += 1
            
            if highest_row == 0:
                button = [b for b in self.children if b.custom_id == f"cf_{index}_{self.game_id}"][0]
                button.disabled = True
                self.full.append(button.custom_id)
            
            self.cooldowns[user_id] = datetime.now(timezone.utc) + timedelta(seconds=self.button_cooldown)
            
            await self.update_image(interaction)
            won = await self.check_wins()
            
            if won:
                self.game_ended = True
                await self.disable_all()
                await interaction.edit_original_response(view=self)  # Disable buttons immediately so no double XP
                await self._save_state()
                await self.send_winner(interaction, won)
                return
            
            await self.bot_play(index)
            won = await self.check_wins()
            if won:
                self.game_ended = True
                await self.disable_all()
                await interaction.edit_original_response(view=self)  # Disable buttons immediately
                await self._save_state()
                await self.send_winner(interaction, won)
            else:
                # Save state after move
                await self._save_state()
            
            await self.update_image(interaction)
    
    async def _check_valid_game(self, interaction: discord.Interaction) -> bool:
        # Skip validation for test games
        if self.test_mode:
            return True
        
        last_game_id = await get_last_game_id('connect four')
        if self.game_id != last_game_id:
            await interaction.response.send_message(
                "`❌` Sorry, but this game has already ended. Please go to the leveling channel to begin another one!",
                ephemeral=True
            )
            return False
        return True
    
    async def get_highest_row(self, column: int) -> int:
        for row in reversed(range(len(self.board))):
            if not self.board[row][column]:
                return row
        return -1
    
    async def bot_play(self, index: int):
        max_offset = 6
        initial_offsets = [-1, 0, 1]
        random.shuffle(initial_offsets)
        
        for delta in initial_offsets:
            position = index + delta
            if 0 <= position <= 6:
                highest_row = await self.get_highest_row(position)
                if highest_row != -1:
                    self.board[highest_row][position] = "Y"
                    if highest_row == 0:
                        button = [b for b in self.children if b.custom_id == f"cf_{position}_{self.game_id}"][0]
                        button.disabled = True
                        self.full.append(button.custom_id)
                    return
        
        for offset in range(2, max_offset + 1):
            offsets = [-offset, offset]
            random.shuffle(offsets)
            for delta in offsets:
                position = index + delta
                if 0 <= position <= 6:
                    highest_row = await self.get_highest_row(position)
                    if highest_row != -1:
                        self.board[highest_row][position] = "Y"
                        if highest_row == 0:
                            button = [b for b in self.children if b.custom_id == f"cf_{position}_{self.game_id}"][0]
                            button.disabled = True
                            self.full.append(button.custom_id)
                        return
    
    async def check_wins(self) -> Optional[str]:
        rows = len(self.board)
        cols = len(self.board[0])
        directions = [(0, 1), (1, 0), (1, 1), (-1, 1)]
        
        for row in range(rows):
            for col in range(cols):
                current = self.board[row][col]
                if current not in ("R", "Y"):
                    continue
                
                for dr, dc in directions:
                    try:
                        if all(
                            0 <= row + dr * i < rows and
                            0 <= col + dc * i < cols and
                            self.board[row + dr * i][col + dc * i] == current
                            for i in range(4)
                        ):
                            return current
                    except IndexError:
                        continue
        
        return None
    
    async def generate_image(self) -> discord.File:
        from pathlib import Path
        # Calculate project root: games/dm/connect_four.py -> games/dm/ -> games/ -> project_root/
        project_root = Path(__file__).parent.parent.parent
        # Support both old and new structure
        assets = self.game_config.get('assets', {})
        base_image_path = project_root / (self.game_config.get("base_image_path") or assets.get("board", "assets/Images/ConnectFourBoard.png"))
        output_image_path = project_root / (self.game_config.get("output_image_path") or assets.get("output", "assets/Images/ConnectFourOutput.png"))
        red_piece_path = project_root / (self.game_config.get("red_piece_path") or assets.get("red_piece", "assets/Images/RedPiece.png"))
        yellow_piece_path = project_root / (self.game_config.get("yellow_piece_path") or assets.get("yellow_piece", "assets/Images/YellowPiece.png"))
        
        with Image.open(str(base_image_path)) as base_image:
            red_piece = Image.open(str(red_piece_path))
            yellow_piece = Image.open(str(yellow_piece_path))
            
            cell_width = 110
            cell_height = 110
            start_x = 101
            start_y = 136
            cell_spacing = 17
            
            rows = len(self.board)
            cols = len(self.board[0])
            
            for row in range(rows):
                for col in range(cols):
                    value = self.board[row][col]
                    if value == "R":
                        piece = red_piece
                    elif value == "Y":
                        piece = yellow_piece
                    else:
                        continue
                    
                    x = start_x + col * (cell_width + cell_spacing)
                    y = start_y + row * (cell_height + cell_spacing)
                    
                    piece_resized = piece.resize((cell_width, cell_height), Image.Resampling.LANCZOS)
                    base_image.paste(piece_resized, (x, y), piece_resized)
            
            base_image.save(str(output_image_path))
        
        return discord.File(str(output_image_path), filename="ConnectFourOutput.png")
    
    async def update_image(self, interaction: discord.Interaction):
        embed = interaction.message.embeds[0]
        embed.set_image(url="attachment://ConnectFourOutput.png")
        embed.set_field_at(0, name="Number of Moves", value=str(self.moves))
        
        image = await self.generate_image()
        await self.swap_buttons()
        await interaction.edit_original_response(attachments=[image], embed=embed, view=self)
    
    async def swap_buttons(self):
        # Enable all buttons that aren't full, disable buttons that are full
        for child in self.children:
            if child.custom_id in self.full:
                child.disabled = True
            elif self.game_ended:
                child.disabled = True
            else:
                child.disabled = False
    
    async def disable_all(self):
        self.game_ended = True
        for child in self.children:
            child.disabled = True
    
    async def calculate_xp(self) -> int:
        min_xp = 50
        max_xp = 150
        decay_rate = 0.1
        xp = max_xp * math.exp(-decay_rate * (self.moves - 1)) + min_xp
        return round(min(xp, max_xp))
    
    async def send_winner(self, interaction: discord.Interaction, won: str):
        db = await DatabasePool.get_instance()
        current_unix = int(datetime.now(timezone.utc).timestamp())
        
        if won == "R":
            xp = await self.calculate_xp()
            
            if self.test_mode:
                await interaction.channel.send(
                    content=f"`✅` Congratulations {interaction.user.mention}! You won! You would have earned `{xp}xp`!"
                )
            else:
                lvl_mng = LevelingManager(
                    user=interaction.user,
                    channel=interaction.channel,
                    client=self.bot,
                    xp=xp,
                    source="Connect Four",
                    game_id=self.game_id
                )
                await lvl_mng.update()
                await interaction.channel.send(
                    content=f"`✅` Congratulations {interaction.user.mention}! You won `{xp}xp`!"
                )
                
                # Check for achievements
                from utils.achievements import check_dm_game_win
                await check_dm_game_win(interaction.user, "Connect Four", interaction.channel, self.bot)
            
            if not self.test_mode:
                await db.execute(
                    "UPDATE users_connectfour SET status = 'Won', ended_at = %s WHERE user_id = %s AND game_id = %s",
                    (current_unix, interaction.user.id, self.game_id)
                )
        elif won == "Y":
            await interaction.channel.send(
                content=f"`❌` Sorry {interaction.user.mention}! You lost against the bot!"
            )
            if not self.test_mode:
                await db.execute(
                    "UPDATE users_connectfour SET status = 'Lost', ended_at = %s WHERE user_id = %s AND game_id = %s",
                    (current_unix, interaction.user.id, self.game_id)
                )

