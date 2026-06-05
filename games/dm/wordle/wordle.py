from services.asset_path_service import AssetPathService
import random
import os
from datetime import datetime, timezone
from typing import List
from PIL import Image, ImageDraw, ImageFont
import discord
from games.base.dm_game import DMGame
from core.logging.setup import get_logger
class Wordle(DMGame):
    def __init__(self, bot):
        super().__init__(bot)
        # Support both old and new config structure
        games = self.dm_config.get('GAMES', {})
        if not games:
            games = self.dm_config.get('games', {})
        self.game_config = games.get('Wordle', {})
        self.logger = get_logger("DMGames")
        self.active_games = {}
        self.words_list = []  # Store words list for validation
        self.guesses = {}  # Store guesses per user: {user_id: [{'word': 'STARE', 'colors': ['green', 'yellow', ...]}, ...]}
        self.letter_states = {}  # Store letter states per user: {user_id: {'A': 'gray', 'B': 'yellow', ...}}
    
    async def _run_game(self, user: discord.User, game_name: str, test_mode: bool = False) -> bool:
        try:
            if test_mode:
                last_game_id = -999999  # Fake game_id for test mode
            else:
                last_game_id = await self.bot.app.games.get_last_game_id('wordle')
                if not last_game_id:
                    return False
            
            # Calculate project root: games/dm/wordle.py -> games/dm/ -> games/ -> project_root/
            project_root = AssetPathService.PROJECT_ROOT
            # Check for both uppercase and lowercase config keys
            words_file_config = self.game_config.get('WORDS_FILE') or self.game_config.get('words_file', 'assets/Configs/data/words.txt')
            if words_file_config.startswith('assets/'):
                words_file = str(project_root / words_file_config)
            else:
                words_file = words_file_config
            
            with open(words_file, 'r') as f:
                words = [line.strip().upper() for line in f if line.strip()]
            
            if not words:
                return False
            
            # Store words list for validation
            self.words_list = words
            
            word = random.choice(words)
            
            if not test_mode:
                db = await self._get_db()
                current_unix = int(datetime.now(timezone.utc).timestamp())
                
                # Clean up any old active games for this user before creating a new one
                # This prevents old games from interfering with new ones
                old_games = await db.execute(
                    "SELECT game_id FROM users_wordle WHERE user_id = %s AND won = 'Started' AND game_id != -999999",
                    (user.id,)
                )
                if old_games:
                    self.logger.info(f"Wordle: Cleaning up {len(old_games)} old active game(s) for user {user.id} before creating new game")
                    await db.execute(
                        "UPDATE users_wordle SET won = 'Lost', ended_at = %s WHERE user_id = %s AND won = 'Started' AND game_id != -999999",
                        (current_unix, user.id)
                    )
                    # Also clean up from active_games and guesses if present
                    if user.id in self.active_games:
                        old_game_id = self.active_games[user.id].get('game_id')
                        if old_game_id and old_game_id != last_game_id:
                            del self.active_games[user.id]
                            self.logger.debug(f"Wordle: Removed old game {old_game_id} from active_games")
                    if user.id in self.guesses:
                        del self.guesses[user.id]
                    if user.id in self.letter_states:
                        del self.letter_states[user.id]
                
                await db.execute_insert(
                    "INSERT INTO users_wordle (game_id, user_id, word, won, attempts, started_at, ended_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (last_game_id, user.id, word, 'Started', 0, current_unix, 0)
                )
            
            self.active_games[user.id] = {
                'game_id': last_game_id,
                'word': word,
                'channel': None,
                'test_mode': test_mode
            }
            self.logger.info(f"Wordle instance {id(self)}: Stored game in active_games for user {user.id}: game_id={last_game_id}, test_mode={test_mode}, word={word}")
            self.logger.info(f"Wordle instance {id(self)}: active_games now contains: {list(self.active_games.keys())}")
            
            # Initialize guesses and letter states for this user
            self.guesses[user.id] = []
            self.letter_states[user.id] = {}
            
            # Generate initial empty board
            initial_image_path = await self.generate_wordle_image(user.id, last_game_id)
            initial_image_file = discord.File(initial_image_path, filename="wordle.png")
            
            test_label = " 🧪 TEST GAME 🧪" if test_mode else ""
            embed = discord.Embed(
                title=f"Wordle #{last_game_id}{test_label}",
                description="Attempt 0/6\nBegin by typing a five-letter word!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.set_image(url="attachment://wordle.png")
            logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            await user.send(embed=embed, file=initial_image_file)
            
            # Clean up initial image after sending
            try:
                os.remove(initial_image_path)
            except Exception:
                pass
            
            self.logger.info(f"Wordle '{word}' ({user.name}#{user.discriminator})")
            return True
        except Exception as e:
            self.logger.error(f"Wordle error: {e}")
            return False
    
    async def _load_words_list(self):
        """Load words list if it's empty"""
        if self.words_list:
            return  # Already loaded
        
        try:
            project_root = AssetPathService.PROJECT_ROOT
            words_file_config = self.game_config.get('WORDS_FILE') or self.game_config.get('words_file', 'assets/Configs/data/words.txt')
            if words_file_config.startswith('assets/'):
                words_file = str(project_root / words_file_config)
            else:
                words_file = words_file_config
            
            with open(words_file, 'r') as f:
                words = [line.strip().upper() for line in f if line.strip()]
            
            if words:
                self.words_list = words
                self.logger.info(f"Loaded {len(words)} words for Wordle validation")
        except Exception as e:
            self.logger.error(f"Error loading words list: {e}")
    
    async def check_word(self, message: str) -> bool:
        """Check if word is valid: 5 letters, alphabetic, and in the words list"""
        if not message.isalpha() or len(message) != 5:
            return False
        
        # Load words list if empty (e.g., after bot restart)
        await self._load_words_list()
        
        # Check if word is in the words list
        message_upper = message.upper()
        return message_upper in self.words_list
    
    def get_letter_colors(self, guess: str, solution: str) -> List[str]:
        """Get color for each letter: 'green', 'yellow', or 'gray'"""
        colors = [""] * 5
        solution_list = list(solution)
        
        # First pass: mark exact matches (green)
        for index, letter in enumerate(list(guess)):
            if letter == solution[index]:
                colors[index] = "green"
                solution_list[index] = "_"
        
        # Second pass: mark letters in word but wrong position (yellow)
        for index, letter in enumerate(list(guess)):
            if colors[index] == "green":
                continue
            if letter in solution_list:
                colors[index] = "yellow"
                solution_list[solution_list.index(letter)] = "_"
            else:
                colors[index] = "gray"
        
        return colors
    
    async def generate_wordle_image(self, user_id: int, game_id: int) -> str:
        """Generate Wordle board image with guesses (no keyboard)"""
        project_root = AssetPathService.PROJECT_ROOT
        board_path = project_root / "assets" / "Images" / "WordleBoard.png"
        
        # Get user's guesses
        guesses = self.guesses.get(user_id, [])
        
        # Load base image
        with Image.open(str(board_path)) as base_image:
            draw = ImageDraw.Draw(base_image)
            
            # Load font - smaller for the new board size
            font_path = project_root / "assets" / "fonts" / "ArcadeRounded.ttf"
            try:
                letter_font = ImageFont.truetype(str(font_path), 36)
            except Exception:
                letter_font = ImageFont.load_default()
            
            # Grid positions (6 rows x 5 columns)
            # Image is now 449x533, so we need to adjust positioning
            # Based on the cropped board, squares are approximately:
            square_size = 77   # Size of each square
            square_spacing = 8  # Spacing between squares horizontally
            row_spacing = 9    # Spacing between rows vertically
            
            # Calculate grid width and center it
            grid_width = 5 * square_size + 4 * square_spacing # = 417
            # Adjusted positioning to align with background boxes
            grid_start_x = ((base_image.width - grid_width) // 2)
            grid_start_y = 11
            
            # Draw guesses on the grid
            for row_idx, guess_data in enumerate(guesses[:6]):  # Max 6 guesses
                word = guess_data['word']
                colors = guess_data['colors']
                
                for col_idx in range(5):
                    x = grid_start_x + col_idx * (square_size + square_spacing)
                    y = grid_start_y + row_idx * (square_size + row_spacing)
                    
                    # Get color
                    color = colors[col_idx]
                    if color == "green":
                        fill_color = "#6AAA64"  # Wordle green
                    elif color == "yellow":
                        fill_color = "#C9B458"  # Wordle yellow
                    else:
                        fill_color = "#787C7E"  # Wordle gray
                    
                    # Draw colored square
                    draw.rectangle(
                        [x, y, x + square_size, y + square_size],
                        fill=fill_color,
                        outline="#D3D6DA",
                        width=2
                    )
                    
                    # Draw letter centered in the square
                    letter = word[col_idx]
                    # Add 1px offset to better center the text visually
                    center_x = x + (square_size // 2) + 1
                    center_y = y + (square_size // 2) + 1
                    
                    draw.text(
                        (center_x, center_y),
                        letter,
                        font=letter_font,
                        fill="white",
                        anchor="mm",  # Middle-middle anchor for perfect centering
                        stroke_width=2,
                        stroke_fill="black"
                    )
            

            output_path = self.bot.app.paths.generated_image_path(f"wordle_{user_id}", game_id)
            base_image.save(output_path)

        return str(output_path)
    
    async def update_letter_states(self, user_id: int, guess: str, colors: List[str]):
        """Update letter states based on guess colors (green > yellow > gray)"""
        if user_id not in self.letter_states:
            self.letter_states[user_id] = {}
        
        for letter, color in zip(guess, colors):
            current_state = self.letter_states[user_id].get(letter)
            
            # Priority: green > yellow > gray
            if color == "green":
                self.letter_states[user_id][letter] = "green"
            elif color == "yellow":
                if current_state != "green":
                    self.letter_states[user_id][letter] = "yellow"
            elif color == "gray":
                if current_state not in ["green", "yellow"]:
                    self.letter_states[user_id][letter] = "gray"
