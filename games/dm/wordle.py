import random
import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict
from PIL import Image, ImageDraw, ImageFont
import discord
from discord.ext import commands
from games.base.dm_game import DMGame
from managers.leveling import LevelingManager
from utils.helpers import get_last_game_id
from core.database.pool import DatabasePool
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
                last_game_id = await get_last_game_id('wordle')
                if not last_game_id:
                    return False
            
            from pathlib import Path
            # Calculate project root: games/dm/wordle.py -> games/dm/ -> games/ -> project_root/
            project_root = Path(__file__).parent.parent.parent
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
            self.logger.info(f"Wordle: Stored game in active_games for user {user.id}: game_id={last_game_id}, test_mode={test_mode}, word={word}")
            
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
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            await user.send(embed=embed, file=initial_image_file)
            
            # Clean up initial image after sending
            try:
                os.remove(initial_image_path)
            except:
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
            from pathlib import Path
            project_root = Path(__file__).parent.parent.parent
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
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent
        board_path = project_root / "assets" / "Images" / "WordleBoard.png"
        
        # Get user's guesses
        guesses = self.guesses.get(user_id, [])
        
        # Load base image
        with Image.open(str(board_path)) as base_image:
            draw = ImageDraw.Draw(base_image)
            
            # Load font - smaller for the new board size
            font_path = project_root / "assets" / "Fonts" / "ArcadeRounded.ttf"
            try:
                letter_font = ImageFont.truetype(str(font_path), 36)
            except:
                letter_font = ImageFont.load_default()
            
            # Grid positions (6 rows x 5 columns)
            # Image is now 449x533, so we need to adjust positioning
            # Based on the cropped board, squares are approximately:
            square_size = 52   # Size of each square
            square_spacing = 6  # Spacing between squares horizontally
            row_spacing = 6    # Spacing between rows vertically
            
            # Calculate grid width and center it
            grid_width = 5 * square_size + 4 * square_spacing
            grid_start_x = (base_image.width - grid_width) // 2  # Center horizontally (~85px from left)
            grid_start_y = 18  # Starting Y position of grid (top margin)
            
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
                    center_x = x + square_size // 2
                    center_y = y + square_size // 2
                    
                    draw.text(
                        (center_x, center_y),
                        letter,
                        font=letter_font,
                        fill="white",
                        anchor="mm",  # Middle-middle anchor for perfect centering
                        stroke_width=2,
                        stroke_fill="black"
                    )
            
            # Save image
            output_path = f"wordle_{user_id}_{game_id}_{uuid.uuid4().hex[:8]}.png"
            base_image.save(output_path)
        
        return output_path
    
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


class WordleListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.wordle_game = None
        self.logger = get_logger("DMGames")
        self._cleanup_done = False
        self._cleanup_in_progress = set()  # Track games currently being cleaned up to prevent race conditions
    
    def set_wordle_game(self, wordle_game):
        self.wordle_game = wordle_game
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Clean up stale Wordle games on bot startup"""
        if self._cleanup_done:
            return
        
        self._cleanup_done = True
        
        try:
            await self._cleanup_stale_games()
        except Exception as e:
            self.logger.error(f"Error cleaning up stale Wordle games: {e}")
    
    async def _cleanup_stale_games(self):
        """Clean up Wordle games that have been 'Started' for too long (likely stale)"""
        try:
            db = await DatabasePool.get_instance()
            current_unix = int(datetime.now(timezone.utc).timestamp())
            
            # Mark games as 'Lost' if they've been 'Started' for more than 24 hours (86400 seconds)
            # This handles cases where messages were deleted or bot restarted
            stale_time = current_unix - 86400  # 24 hours ago
            
            rows = await db.execute(
                "SELECT game_id, user_id, started_at FROM users_wordle WHERE won = 'Started' AND started_at < %s AND game_id != -999999",
                (stale_time,)
            )
            
            if rows:
                self.logger.info(f"WordleListener: Found {len(rows)} stale Wordle games to clean up")
                
                for row in rows:
                    game_id = row['game_id']
                    user_id = row['user_id']
                    
                    try:
                        await db.execute(
                            "UPDATE users_wordle SET won = 'Lost', ended_at = %s WHERE game_id = %s AND user_id = %s AND won = 'Started'",
                            (current_unix, game_id, user_id)
                        )
                        
                        # Clean up from active_games if present
                        if self.wordle_game and user_id in self.wordle_game.active_games:
                            game_data = self.wordle_game.active_games[user_id]
                            if game_data.get('game_id') == game_id:
                                del self.wordle_game.active_games[user_id]
                        
                        # Clean up guesses and letter states
                        if self.wordle_game:
                            if user_id in self.wordle_game.guesses:
                                del self.wordle_game.guesses[user_id]
                            if user_id in self.wordle_game.letter_states:
                                del self.wordle_game.letter_states[user_id]
                        
                        self.logger.info(f"WordleListener: Cleaned up stale game {game_id} for user {user_id}")
                    except Exception as e:
                        self.logger.error(f"WordleListener: Error cleaning up game {game_id}: {e}")
                
                self.logger.info(f"WordleListener: Cleaned up {len(rows)} stale Wordle games")
            else:
                self.logger.debug("WordleListener: No stale Wordle games found to clean up")
        except Exception as e:
            self.logger.error(f"WordleListener: Error in _cleanup_stale_games: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not isinstance(message.channel, discord.DMChannel) or message.author.bot:
            return
        
        if not self.wordle_game:
            self.logger.warning("WordleListener: wordle_game is None")
            return
        
        self.logger.debug(f"WordleListener: Received message from {message.author.id}: {message.content[:20]}")
        
        # Log active_games state for debugging
        self.logger.debug(f"WordleListener: active_games keys: {list(self.wordle_game.active_games.keys())}")
        
        # Check active_games FIRST (this includes test games that aren't in database)
        if message.author.id in self.wordle_game.active_games:
            game_data = self.wordle_game.active_games[message.author.id]
            game_id = game_data['game_id']
            word = game_data['word']
            test_mode = game_data.get('test_mode', False)
            self.logger.debug(f"WordleListener: Found game in active_games dict: game_id={game_id}, test_mode={test_mode}, word={word}")
            
            # For test games, we don't query the database - just use attempts from guesses
            if test_mode or game_id == -999999:
                attempts = len(self.wordle_game.guesses.get(message.author.id, []))
                self.logger.debug(f"WordleListener: Test game detected, using attempts from guesses: {attempts}")
            else:
                # For real games, get attempts from database
                db = await DatabasePool.get_instance()
                rows = await db.execute(
                    "SELECT attempts FROM users_wordle WHERE user_id = %s AND game_id = %s",
                    (message.author.id, game_id)
                )
                if rows:
                    attempts = rows[0].get('attempts', 0)
                else:
                    attempts = len(self.wordle_game.guesses.get(message.author.id, []))
        else:
            # Not in active_games, check database (bot restart scenario)
            # BUT: Test games are NOT in database, so if user has a test game, it MUST be in active_games
            # If not in active_games, query database but exclude test games
            self.logger.debug(f"WordleListener: User {message.author.id} not in active_games, checking database (excluding test games)")
            db = await DatabasePool.get_instance()
            
            # First, find all active games for this user
            all_active_games = await db.execute(
                "SELECT game_id, user_id, word, won, attempts, started_at FROM users_wordle WHERE user_id = %s AND won = 'Started' AND game_id != -999999 ORDER BY started_at DESC",
                (message.author.id,)
            )
            
            self.logger.debug(f"WordleListener: Database query returned {len(all_active_games) if all_active_games else 0} active games")
            
            if not all_active_games:
                self.logger.debug(f"WordleListener: No active game found for user {message.author.id} (neither in active_games nor database)")
                return
            
            # Find the most recent Wordle message in the channel and match it to a game
            # This ensures we use the game that the user is actually looking at
            found_game = None
            found_existing_message = None
            most_recent_message_time = None
            games_with_messages = {}  # Track which games have messages: {game_id: message}
            
            # First pass: find all Wordle messages and match them to active games
            async for channel_message in message.channel.history(limit=100):
                if channel_message.embeds and channel_message.author.bot and channel_message.embeds[0].title:
                    title = channel_message.embeds[0].title
                    if "Wordle" in title:
                        # Extract game_id from title (format: "Wordle #12345")
                        try:
                            if "#" in title:
                                msg_game_id = int(title.split("#")[1].strip())
                                # Check if this game_id is in our active games list
                                for game_row in all_active_games:
                                    if game_row['game_id'] == msg_game_id:
                                        # Store this message for this game
                                        if msg_game_id not in games_with_messages or channel_message.created_at > games_with_messages[msg_game_id].created_at:
                                            games_with_messages[msg_game_id] = channel_message
                                        # Use the most recent one as the found game
                                        if most_recent_message_time is None or channel_message.created_at > most_recent_message_time:
                                            found_game = game_row
                                            found_existing_message = channel_message
                                            most_recent_message_time = channel_message.created_at
                                        break
                        except (ValueError, IndexError):
                            continue
            
            # If we found a game with an existing message, use it
            if found_game and found_existing_message:
                game_id = found_game['game_id']
                word = found_game['word']
                attempts = found_game.get('attempts', 0)
                self.logger.debug(f"WordleListener: Found game in database with existing message: game_id={game_id}, word={word}, attempts={attempts}")
            else:
                # No message found for any active game - mark all games without messages as stale
                current_unix = int(datetime.now(timezone.utc).timestamp())
                for game_row in all_active_games:
                    game_id = game_row['game_id']
                    # Check if this game has a message (we already checked above)
                    if game_id not in games_with_messages:
                        # Mark stale game as Lost
                        cleanup_key = f"{message.author.id}_{game_id}"
                        if cleanup_key not in self._cleanup_in_progress:
                            self._cleanup_in_progress.add(cleanup_key)
                            try:
                                async with db.acquire() as conn:
                                    async with conn.cursor() as cursor:
                                        await cursor.execute(
                                            "UPDATE users_wordle SET won = 'Lost', ended_at = %s WHERE game_id = %s AND user_id = %s AND won = 'Started'",
                                            (current_unix, message.author.id, game_id)
                                        )
                                self.logger.debug(f"WordleListener: Marked stale game {game_id} as Lost (no message found)")
                            except Exception as e:
                                self.logger.error(f"WordleListener: Error marking stale game {game_id} as Lost: {e}")
                            finally:
                                async def cleanup_after_delay():
                                    await asyncio.sleep(1)
                                    self._cleanup_in_progress.discard(cleanup_key)
                                asyncio.create_task(cleanup_after_delay())
                
                # After cleaning up stale games, check if we have any remaining active games with messages
                if games_with_messages:
                    # Use the most recent game that has a message
                    most_recent_game_id = max(games_with_messages.keys(), key=lambda gid: games_with_messages[gid].created_at)
                    for game_row in all_active_games:
                        if game_row['game_id'] == most_recent_game_id:
                            found_game = game_row
                            found_existing_message = games_with_messages[most_recent_game_id]
                            break
                
                if not found_game:
                    # No games with messages found - check if any active games remain
                    remaining_games = await db.execute(
                        "SELECT game_id, user_id, word, won, attempts FROM users_wordle WHERE user_id = %s AND won = 'Started' AND game_id != -999999 ORDER BY started_at DESC LIMIT 1",
                        (message.author.id,)
                    )
                    
                    if not remaining_games:
                        self.logger.debug(f"WordleListener: No active games remaining after cleanup for user {message.author.id}")
                        return
                    
                    # Use the most recent remaining game (but it has no message, so it will be marked as stale later)
                    found_game = remaining_games[0]
                    self.logger.debug(f"WordleListener: Using most recent game after cleanup: game_id={found_game['game_id']}, but no message found")
                
                game_id = found_game['game_id']
                word = found_game['word']
                attempts = found_game.get('attempts', 0)
            
            # Restore to active_games if not already there (this is a real game, not test)
            test_mode = False  # Database games are always real games
            
            # If we didn't find a message, check one more time for this specific game
            if not found_existing_message:
                async for channel_message in message.channel.history(limit=100):
                    if channel_message.embeds and channel_message.author.bot and channel_message.embeds[0].title:
                        title = channel_message.embeds[0].title
                        if "Wordle" in title and f"#{game_id}" in title:
                            found_existing_message = channel_message
                            break
                
                if not found_existing_message:
                    # Check if we're already cleaning up this game (prevent race conditions)
                    cleanup_key = f"{message.author.id}_{game_id}"
                    if cleanup_key in self._cleanup_in_progress:
                        # Another message handler is already cleaning this up - skip to avoid duplicate warnings/logs
                        return
                
                # Mark this game as being cleaned up (prevent concurrent cleanups)
                self._cleanup_in_progress.add(cleanup_key)
                
                try:
                    # Message doesn't exist - mark game as ended
                    # Only log warning if we actually update the row (first time cleanup)
                    current_unix = int(datetime.now(timezone.utc).timestamp())
                    
                    try:
                        # Use execute with direct connection to check rowcount
                        async with db.acquire() as conn:
                            async with conn.cursor() as cursor:
                                await cursor.execute(
                                    "UPDATE users_wordle SET won = 'Lost', ended_at = %s WHERE game_id = %s AND user_id = %s AND won = 'Started'",
                                    (current_unix, message.author.id, game_id)
                                )
                                rows_affected = cursor.rowcount
                                
                        if rows_affected > 0:
                            # Successfully updated - log warning only once
                            self.logger.warning(f"WordleListener: Game {game_id} found in database but message not found - marked as Lost ({rows_affected} row(s) updated)")
                        else:
                            # Game was already updated by another handler - don't log as warning, just debug
                            # This happens when multiple messages come in rapidly
                            self.logger.debug(f"WordleListener: Game {game_id} was already cleaned up by another handler (no rows affected)")
                    except Exception as e:
                        self.logger.error(f"WordleListener: Error marking stale game {game_id} as Lost: {e}")
                        import traceback
                        self.logger.error(traceback.format_exc())
                finally:
                    # Remove from cleanup tracking after a short delay to handle rapid messages
                    # This prevents the same game from being checked multiple times within 1 second
                    async def cleanup_after_delay():
                        await asyncio.sleep(1)
                        self._cleanup_in_progress.discard(cleanup_key)
                    asyncio.create_task(cleanup_after_delay())
                
                # Don't restore the game - it's stale
                return
            
            # Message exists, restore the game
            self.wordle_game.active_games[message.author.id] = {
                'game_id': game_id,
                'word': word,
                'channel': None,
                'test_mode': test_mode
            }
            # Initialize guesses and letter states if not already initialized
            if message.author.id not in self.wordle_game.guesses:
                self.wordle_game.guesses[message.author.id] = []
            if message.author.id not in self.wordle_game.letter_states:
                self.wordle_game.letter_states[message.author.id] = {}
            
            # Load words list if empty (needed for validation)
            await self.wordle_game._load_words_list()
        
        if attempts >= 6:
            self.logger.debug(f"WordleListener: User has already used all 6 attempts")
            return
        
        self.logger.debug(f"WordleListener: Processing guess: {message.content.strip()}")
        
        guess = message.content.strip().upper()
        
        # Validate guess length and format
        if len(guess) != 5 or not guess.isalpha():
            error = await message.reply(
                "`❌` Failed! That is an invalid word. Please make sure that your word only contains letters and is five letters long!"
            )
            await asyncio.sleep(4)
            try:
                await error.delete()
            except:
                pass
            return
        
        if not await self.wordle_game.check_word(guess):
            error = await message.reply(
                "`❌` Failed! That is not a valid word. Please try a different word!"
            )
            await asyncio.sleep(4)
            try:
                await error.delete()
            except:
                pass
            return
        
        # Get colors for this guess
        colors = self.wordle_game.get_letter_colors(guess, word)
        
        # Store guess
        if message.author.id not in self.wordle_game.guesses:
            self.wordle_game.guesses[message.author.id] = []
        self.wordle_game.guesses[message.author.id].append({
            'word': guess,
            'colors': colors
        })
        
        # Update letter states
        await self.wordle_game.update_letter_states(message.author.id, guess, colors)
        
        # Generate image
        self.logger.debug(f"WordleListener: Generating image for user {message.author.id}, game {game_id}")
        image_path = await self.wordle_game.generate_wordle_image(message.author.id, game_id)
        image_file = discord.File(image_path, filename="wordle.png")
        
        found_wordle_message = None
        message_count = 0
        async for channel_message in message.channel.history(limit=50):
            message_count += 1
            if channel_message.embeds and channel_message.author.bot and channel_message.embeds[0].title:
                title = channel_message.embeds[0].title
                if "Wordle" in title and f"#{game_id}" in title:
                    found_wordle_message = channel_message
                    self.logger.debug(f"WordleListener: Found Wordle message with game_id {game_id}")
                    break
        
        if not found_wordle_message:
            # Check if we're already cleaning up this game (prevent race conditions)
            cleanup_key = f"{message.author.id}_{game_id}"
            if cleanup_key in self._cleanup_in_progress:
                # Another message handler is already cleaning this up - skip to avoid duplicate warnings/logs
                # Clean up image file before returning
                try:
                    os.remove(image_path)
                except:
                    pass
                return
            
            # Mark this game as being cleaned up
            self._cleanup_in_progress.add(cleanup_key)
            
            try:
                self.logger.warning(f"WordleListener: Could not find Wordle message for game_id {game_id} (searched {message_count} messages) - cleaning up stale game")
                
                # Clean up stale game - mark as lost and remove from active_games
                current_unix = int(datetime.now(timezone.utc).timestamp())
                
                # Only update database for non-test games
                if not test_mode and game_id != -999999:
                    try:
                        db = await DatabasePool.get_instance()
                        # Use direct cursor to check rowcount
                        async with db.acquire() as conn:
                            async with conn.cursor() as cursor:
                                await cursor.execute(
                                    "UPDATE users_wordle SET won = 'Lost', ended_at = %s WHERE user_id = %s AND game_id = %s AND won = 'Started'",
                                    (current_unix, message.author.id, game_id)
                                )
                                rows_affected = cursor.rowcount
                        
                        if rows_affected > 0:
                            self.logger.info(f"WordleListener: Marked stale game {game_id} as Lost for user {message.author.id} ({rows_affected} row(s) updated)")
                        else:
                            self.logger.debug(f"WordleListener: Game {game_id} was already cleaned up by another handler (no rows affected)")
                    except Exception as e:
                        self.logger.error(f"WordleListener: Error cleaning up stale game {game_id}: {e}")
                        import traceback
                        self.logger.error(traceback.format_exc())
                
                # Clean up from active_games and guesses
                if message.author.id in self.wordle_game.active_games:
                    del self.wordle_game.active_games[message.author.id]
                if message.author.id in self.wordle_game.guesses:
                    del self.wordle_game.guesses[message.author.id]
                if message.author.id in self.wordle_game.letter_states:
                    del self.wordle_game.letter_states[message.author.id]
                
                # Notify user about the stale game
                try:
                    await message.reply("`⚠️` Your previous Wordle game message was not found. The game has been ended. Start a new game using `/dm-games` or the DM games panel.", delete_after=10)
                except:
                    pass
            finally:
                # Remove from cleanup tracking after a delay
                async def cleanup_after_delay():
                    await asyncio.sleep(1)
                    self._cleanup_in_progress.discard(cleanup_key)
                asyncio.create_task(cleanup_after_delay())
                
                # Clean up image file after all processing
                try:
                    os.remove(image_path)
                except:
                    pass
            
            # Return after cleanup
            return
        
        try:
            wordle_embed = found_wordle_message.embeds[0]
            new_attempts = attempts + 1
            wordle_embed.description = f"Attempt {new_attempts}/6"
            wordle_embed.set_image(url="attachment://wordle.png")
            
            self.logger.debug(f"WordleListener: Editing message with new image")
            await found_wordle_message.edit(embed=wordle_embed, attachments=[image_file])
            self.logger.debug(f"WordleListener: Successfully updated Wordle message")
            
            # Clean up image file after sending
            try:
                os.remove(image_path)
            except:
                pass
        except Exception as e:
            self.logger.error(f"WordleListener: Error editing message: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            # Clean up image file on error
            try:
                os.remove(image_path)
            except:
                pass
            return
        
        # Update database only for non-test games
        if not test_mode and game_id != -999999:
            db = await DatabasePool.get_instance()
            await db.execute(
                "UPDATE users_wordle SET attempts = %s WHERE user_id = %s AND game_id = %s",
                (attempts + 1, message.author.id, game_id)
            )
        
        if guess == word:
            current_unix = int(datetime.now(timezone.utc).timestamp())
            final_attempts = attempts + 1
            xp = random.randint((7 - final_attempts) * 30, (7 - final_attempts) * 40)
            
            if test_mode:
                await message.channel.send(
                    f"`✅` Congratulations {message.author.mention}! You won! You would have earned `{xp}xp`!"
                )
            else:
                await message.channel.send(
                    f"`✅` Congratulations {message.author.mention}! You won `{xp}xp`!"
                )
                
                await db.execute(
                    "UPDATE users_wordle SET won = 'Won', ended_at = %s WHERE user_id = %s AND game_id = %s",
                    (current_unix, message.author.id, game_id)
                )
                
                # Check for achievements first
                from utils.achievements import check_dm_game_win
                await check_dm_game_win(message.author, "Wordle", message.channel, self.bot)
                
                lvl_mng = LevelingManager(
                    user=message.author,
                    channel=message.channel,
                    client=self.bot,
                    xp=xp,
                    source="Wordle",
                    game_id=game_id
                )
                await lvl_mng.update()
            
            # Clean up guesses and letter states
            if message.author.id in self.wordle_game.guesses:
                del self.wordle_game.guesses[message.author.id]
            if message.author.id in self.wordle_game.letter_states:
                del self.wordle_game.letter_states[message.author.id]
            
            if message.author.id in self.wordle_game.active_games:
                del self.wordle_game.active_games[message.author.id]
        else:
            if attempts == 5:
                # Generate final image showing the answer
                final_image_path = await self.wordle_game.generate_wordle_image(message.author.id, game_id)
                final_image_file = discord.File(final_image_path, filename="wordle_final.png")
                
                await message.channel.send(
                    f"`❌` Sorry, but you did not guess the word. The correct word was `{word}`.",
                    file=final_image_file
                )
                
                # Clean up image
                try:
                    os.remove(final_image_path)
                except:
                    pass
                
                # Update database only for non-test games
                if not test_mode and game_id != -999999:
                    db = await DatabasePool.get_instance()
                    current_unix = int(datetime.now(timezone.utc).timestamp())
                    await db.execute(
                        "UPDATE users_wordle SET won = 'Lost', ended_at = %s WHERE user_id = %s AND game_id = %s",
                        (current_unix, message.author.id, game_id)
                    )
                
                # Clean up guesses and letter states
                if message.author.id in self.wordle_game.guesses:
                    del self.wordle_game.guesses[message.author.id]
                if message.author.id in self.wordle_game.letter_states:
                    del self.wordle_game.letter_states[message.author.id]
                
                if message.author.id in self.wordle_game.active_games:
                    del self.wordle_game.active_games[message.author.id]

