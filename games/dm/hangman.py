import random
import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Set
import discord
from discord.ext import commands
from games.base.dm_game import DMGame
from managers.leveling import LevelingManager
from utils.helpers import get_last_game_id
from core.database.pool import DatabasePool
from core.logging.setup import get_logger
from utils.game_state_manager import save_game_state


class Hangman(DMGame):
    def __init__(self, bot):
        super().__init__(bot)
        # Support both old and new config structure
        games = self.dm_config.get('GAMES', {})
        if not games:
            games = self.dm_config.get('games', {})
        self.game_config = games.get('Hangman', {})
        self.logger = get_logger("DMGames")
    
    async def _run_game(self, user: discord.User, game_name: str, test_mode: bool = False) -> bool:
        try:
            if test_mode:
                last_game_id = -999999  # Fake game_id for test mode
            else:
                last_game_id = await get_last_game_id('hangman')
                if not last_game_id:
                    return False
            
            from pathlib import Path
            # Calculate project root: games/dm/hangman.py -> games/dm/ -> games/ -> project_root/
            project_root = Path(__file__).parent.parent.parent
            # Check for both uppercase and lowercase config keys
            # Use same default as Wordle (assets/Configs/data/words.txt)
            words_file_config = self.game_config.get('WORDS_FILE') or self.game_config.get('words_file', 'assets/Configs/data/words.txt')
            if words_file_config.startswith('assets/'):
                words_file = str(project_root / words_file_config)
            else:
                words_file = words_file_config
            
            # Load all words from file (same as Wordle)
            with open(words_file, 'r') as f:
                words = [line.strip().upper() for line in f if line.strip()]
            
            if not words:
                return False
            
            # Filter words to reasonable length for Hangman (4-10 letters for better gameplay)
            # But use all words from the same file as Wordle
            reasonable_words = [w for w in words if 4 <= len(w) <= 10]
            if reasonable_words:
                word = random.choice(reasonable_words)
            else:
                # Fallback to any word if no reasonable length words found
                word = random.choice(words)
            
            # Check if user already has an active game for this game_id (prevent duplicates)
            saved_state = None
            if not test_mode and last_game_id != -999999:
                try:
                    db = await self._get_db()
                    # Check if game already exists (user already started this game)
                    rows = await db.execute(
                        "SELECT word, wrong_guesses, correct_guesses FROM users_hangman WHERE game_id = %s AND user_id = %s AND won = 'Started'",
                        (last_game_id, user.id)
                    )
                    if rows and len(rows) > 0:
                        # Game already exists - return False to prevent duplicate
                        self.logger.warning(f"User {user.id} already has an active Hangman game {last_game_id}")
                        return False
                except Exception as e:
                    self.logger.debug(f"Could not check existing Hangman game: {e}")
            
            if not test_mode:
                db = await self._get_db()
                current_unix = int(datetime.now(timezone.utc).timestamp())
                max_wrong = self.game_config.get('MAX_WRONG') or self.game_config.get('max_wrong_guesses', 6)
                await db.execute_insert(
                    "INSERT INTO users_hangman (game_id, user_id, word, won, wrong_guesses, correct_guesses, started_at, ended_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (last_game_id, user.id, word, 'Started', 0, 0, current_unix, 0)
                )
            
            max_wrong = self.game_config.get('MAX_WRONG') or self.game_config.get('max_wrong_guesses', 6)
            test_label = " 🧪 TEST GAME 🧪" if test_mode else ""
            
            # Create button view
            view = HangmanButtons(
                last_game_id, 
                self.bot, 
                self.config, 
                self.game_config, 
                self.dm_config, 
                word,
                user.id,
                test_mode=test_mode,
                saved_state=saved_state
            )
            # Register view for persistence across bot restarts
            self.bot.add_view(view)
            
            # Initial word display (all blanks)
            word_display = ' '.join(['_'] * len(word))
            
            embed = discord.Embed(
                title=f"Hangman #{last_game_id}{test_label}",
                description=f"Wrong Guesses: 0/{max_wrong}\nWord: `{word_display}`\nGuessed Letters: `None`\n\nClick a letter button below to guess!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            main_message = await user.send(embed=embed, view=view)
            
            # Store main message reference in view for Z button to update
            view.main_message = main_message
            
            # Create and send Z button in separate message
            z_view = HangmanZButton(last_game_id, self.bot, self.config, self.game_config, self.dm_config, word, user.id, main_message, view, test_mode=test_mode)
            self.bot.add_view(z_view)
            
            # Send message with just Z button (send without embed to avoid description requirement)
            z_message = await user.send(content="\u200b", view=z_view)
            
            # Store references for coordination
            view.z_view = z_view
            view.z_message = z_message
            z_view.z_message = z_message
            z_view.main_view = view  # Store reference to main view for state sharing
            
            # Save initial state
            if not test_mode:
                await view._save_state()
            
            self.logger.info(f"Hangman '{word}' ({user.name}#{user.discriminator})")
            return True
        except Exception as e:
            self.logger.error(f"Hangman error: {e}")
            import traceback
            self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
            return False
    

class HangmanButtons(discord.ui.View):
    def __init__(self, game_id: int, bot, config, game_config, dm_config, word: str, user_id: int, test_mode: bool = False, saved_state: dict = None, main_message: discord.Message = None):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.game_config = game_config
        self.dm_config = dm_config
        self.word = word.upper()
        self.player_id = user_id
        self.test_mode = test_mode
        self.main_message = main_message  # Reference to main message for Z button to update
        self.z_view = None  # Reference to Z button view (set after creation)
        self.z_message = None  # Reference to Z message (set after creation)
        self.logger = get_logger("DMGames")
        
        self.button_cooldown = self.dm_config.get('BUTTON_COOLDOWN', 0.8) or self.dm_config.get('button_cooldown', 0.8)
        self.cooldowns: Dict[int, datetime] = {}
        self.is_processing = False  # Lock to prevent concurrent clicks
        
        # Initialize or restore game state
        if saved_state:
            self._restore_state(saved_state)
        else:
            self.guessed_letters: Set[str] = set()
            self.wrong_guesses = 0
            self.max_wrong = self.game_config.get('MAX_WRONG') or self.game_config.get('max_wrong_guesses', 6)
            self.game_ended = False
            self.game_won = False
        
        # Create buttons for all 26 letters (A-Z)
        # Discord allows max 5 buttons per row and max 5 rows (0-4) = 25 buttons max
        # We have 26 letters, so we'll use A-Y (25 letters) and handle Z as a special case
        # Words with Z will still work, but Z won't be clickable via button (very rare anyway)
        # Arrange as: A-E (row 0), F-J (row 1), K-O (row 2), P-T (row 3), U-Y (row 4)
        letters = [chr(ord('A') + i) for i in range(25)]  # A-Y (25 letters)
        for i, letter in enumerate(letters):
            if i < 5:  # A-E
                row = 0
            elif i < 10:  # F-J
                row = 1
            elif i < 15:  # K-O
                row = 2
            elif i < 20:  # P-T
                row = 3
            else:  # U-Y
                row = 4
            
            button = discord.ui.Button(
                label=letter,
                style=discord.ButtonStyle.grey,
                custom_id=f"hang_{letter}_{game_id}",
                row=row
            )
            button.callback = self.create_callback(letter)
            self.add_item(button)
        
        # Update button states based on current game state
        self._update_button_states()
    
    def _get_state(self) -> dict:
        """Get current game state as dictionary"""
        return {
            'word': self.word,
            'guessed_letters': list(self.guessed_letters),  # Convert set to list
            'wrong_guesses': self.wrong_guesses,
            'max_wrong': self.max_wrong,
            'game_ended': self.game_ended,
            'game_won': self.game_won
        }
    
    def _restore_state(self, state: dict):
        """Restore game state from dictionary"""
        self.word = state.get('word', '')
        self.guessed_letters = set(state.get('guessed_letters', []))
        self.wrong_guesses = state.get('wrong_guesses', 0)
        self.max_wrong = state.get('max_wrong', self.game_config.get('MAX_WRONG') or self.game_config.get('max_wrong_guesses', 6))
        self.game_ended = state.get('game_ended', False)
        self.game_won = state.get('game_won', False)
    
    def _update_button_states(self):
        """Update button states based on guessed letters"""
        for button in self.children:
            if isinstance(button, discord.ui.Button) and button.custom_id:
                if button.custom_id.startswith(f"hang_") and f"_{self.game_id}" in button.custom_id:
                    letter = button.label
                    if letter in self.guessed_letters:
                        # Letter already guessed - disable and style based on correct/wrong
                        button.disabled = True
                        if letter in self.word:
                            button.style = discord.ButtonStyle.green  # Correct guess
                        else:
                            button.style = discord.ButtonStyle.red  # Wrong guess
                    elif self.game_ended:
                        # Game ended - disable all buttons
                        button.disabled = True
                    else:
                        # Letter not guessed yet - enable
                        button.disabled = False
                        button.style = discord.ButtonStyle.grey
    
    async def _save_state(self):
        """Save current game state to database"""
        if self.test_mode or self.game_id == -999999 or not hasattr(self, 'player_id'):
            return
        
        try:
            state = self._get_state()
            await save_game_state('hangman', self.game_id, self.player_id, state, self.test_mode)
        except Exception as e:
            from core.logging.setup import get_logger
            logger = get_logger("DMGames")
            logger.error(f"Error saving Hangman game state: {e}")
    
    def create_callback(self, letter: str):
        async def callback(interaction: discord.Interaction):
            await self.handle_letter_guess(interaction, letter)
        return callback
    
    def get_word_display(self) -> str:
        """Get word display with guessed letters revealed"""
        display_list = []
        for char in self.word:
            if char in self.guessed_letters:
                display_list.append(char)
            else:
                display_list.append('_')
        return ' '.join(display_list)
    
    async def _check_valid_game(self, interaction: discord.Interaction) -> bool:
        """Check if this interaction is for a valid active game"""
        if interaction.user.id != self.player_id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return False
        
        if self.game_ended:
            await interaction.response.send_message("This game has already ended!", ephemeral=True)
            return False
        
        return True
    
    async def handle_letter_guess(self, interaction: discord.Interaction, letter: str):
        """Handle a letter guess from button click"""
        if not await self._check_valid_game(interaction):
            return
        
        # Check cooldown
        user_id = interaction.user.id
        if user_id in self.cooldowns and datetime.now(timezone.utc) < self.cooldowns[user_id]:
            remaining = (self.cooldowns[user_id] - datetime.now(timezone.utc)).total_seconds()
            await interaction.response.send_message(
                f"❌ You need to wait {remaining:.2f} seconds before guessing again.",
                ephemeral=True
            )
            return
        
        # Check if letter already guessed
        if letter in self.guessed_letters:
            await interaction.response.send_message(
                f"⚠️ You already guessed the letter `{letter}`! Try a different letter.",
                ephemeral=True
            )
            return
        
        # Prevent concurrent processing
        if self.is_processing:
            await interaction.response.send_message("Processing previous guess, please wait...", ephemeral=True)
            return
        
        self.is_processing = True
        await interaction.response.defer()
        
        try:
            # Add letter to guessed set
            self.guessed_letters.add(letter)
            
            # Check if letter is in word
            is_correct = letter in self.word
            
            if not is_correct:
                self.wrong_guesses += 1
            
            # Update cooldown
            self.cooldowns[user_id] = datetime.now(timezone.utc) + timedelta(seconds=self.button_cooldown)
            
            # Update button states
            self._update_button_states()
            
            # Get word display
            word_display = self.get_word_display()
            guessed_text = ', '.join(sorted(self.guessed_letters)) if self.guessed_letters else 'None'
            
            # Update database for non-test games
            if not self.test_mode and self.game_id != -999999:
                try:
                    db = await DatabasePool.get_instance()
                    correct_count = len([c for c in word_display if c != '_' and c != ' '])
                    await db.execute(
                        "UPDATE users_hangman SET wrong_guesses = %s, correct_guesses = %s WHERE user_id = %s AND game_id = %s",
                        (self.wrong_guesses, correct_count, self.player_id, self.game_id)
                    )
                except Exception as e:
                    self.logger.error(f"Error updating Hangman game state in database: {e}")
            
            # Check win/loss conditions
            word_complete = '_' not in word_display
            game_lost = self.wrong_guesses >= self.max_wrong
            
            if word_complete:
                # Player won!
                self.game_ended = True
                self.game_won = True
                self._update_button_states()  # Disable all buttons
                
                xp = random.randint(
                    self.game_config.get('WIN_XP', {}).get('LOWER', 80),
                    self.game_config.get('WIN_XP', {}).get('UPPER', 120)
                )
                current_unix = int(datetime.now(timezone.utc).timestamp())
                correct_count = len([c for c in word_display if c != '_' and c != ' '])
                
                embed = interaction.message.embeds[0]
                embed.description = (
                    f"✅ **Game Won!**\n\n"
                    f"Wrong Guesses: {self.wrong_guesses}/{self.max_wrong}\n"
                    f"Word: `{word_display.replace(' ', '')}`\n"
                    f"Guessed Letters: `{guessed_text}`\n\n"
                    f"Congratulations! You guessed the word!"
                )
                embed.color = discord.Color.green()
                
                await interaction.message.edit(embed=embed, view=self)
                
                # Update Z button view if it exists
                if self.z_view and self.z_message:
                    try:
                        # Disable Z button if game ended
                        button = [b for b in self.z_view.children if isinstance(b, discord.ui.Button) and b.label == "Z"]
                        if button:
                            button[0].disabled = True
                        await self.z_message.edit(view=self.z_view)
                    except Exception as e:
                        self.logger.debug(f"Could not update Z button: {e}")
                
                # Update database and award XP for non-test games
                if not self.test_mode and self.game_id != -999999:
                    try:
                        db = await DatabasePool.get_instance()
                        await db.execute(
                            "UPDATE users_hangman SET won = 'Won', ended_at = %s, correct_guesses = %s WHERE user_id = %s AND game_id = %s",
                            (current_unix, correct_count, self.player_id, self.game_id)
                        )
                        
                        # Check for achievements
                        from utils.achievements import check_dm_game_win
                        await check_dm_game_win(interaction.user, "Hangman", interaction.channel, self.bot)
                        
                        # Award XP
                        lvl_mng = LevelingManager(
                            user=interaction.user,
                            channel=interaction.channel,
                            client=self.bot,
                            xp=xp,
                            source="Hangman",
                            game_id=self.game_id
                        )
                        await lvl_mng.update()
                        
                        await interaction.followup.send(
                            f"`✅` Congratulations {interaction.user.mention}! You guessed the word `{self.word}`! You won `{xp}xp`!",
                            ephemeral=False
                        )
                    except Exception as e:
                        self.logger.error(f"Error awarding Hangman win: {e}")
                else:
                    await interaction.followup.send(
                        f"`✅` Congratulations {interaction.user.mention}! You won! You would have earned `{xp}xp`!",
                        ephemeral=False
                    )
                
                # Save final state
                if not self.test_mode:
                    await self._save_state()
                    
            elif game_lost:
                # Player lost
                self.game_ended = True
                self.game_won = False
                self._update_button_states()  # Disable all buttons
                
                current_unix = int(datetime.now(timezone.utc).timestamp())
                
                embed = interaction.message.embeds[0]
                embed.description = (
                    f"❌ **Game Over!**\n\n"
                    f"Wrong Guesses: {self.wrong_guesses}/{self.max_wrong}\n"
                    f"Word: `{self.word}`\n"
                    f"Guessed Letters: `{guessed_text}`\n\n"
                    f"You ran out of guesses! The correct word was `{self.word}`."
                )
                embed.color = discord.Color.red()
                
                await interaction.message.edit(embed=embed, view=self)
                
                # Update Z button view if it exists
                if self.z_view and self.z_message:
                    try:
                        # Disable Z button if game ended
                        button = [b for b in self.z_view.children if isinstance(b, discord.ui.Button) and b.label == "Z"]
                        if button:
                            button[0].disabled = True
                        await self.z_message.edit(view=self.z_view)
                    except Exception as e:
                        self.logger.debug(f"Could not update Z button: {e}")
                
                # Update database for non-test games
                if not self.test_mode and self.game_id != -999999:
                    try:
                        db = await DatabasePool.get_instance()
                        await db.execute(
                            "UPDATE users_hangman SET won = 'Lost', ended_at = %s WHERE user_id = %s AND game_id = %s",
                            (current_unix, self.player_id, self.game_id)
                        )
                    except Exception as e:
                        self.logger.error(f"Error updating Hangman loss: {e}")
                    
                    await interaction.followup.send(
                        f"`❌` Sorry, but you ran out of guesses! The correct word was `{self.word}`.",
                        ephemeral=False
                    )
                else:
                    await interaction.followup.send(
                        f"`❌` Sorry, but you ran out of guesses! The correct word was `{self.word}`.",
                        ephemeral=False
                    )
                
                # Save final state
                if not self.test_mode:
                    await self._save_state()
                    
            else:
                # Game continues - update embed
                result_text = f"`✅` Good guess! The letter `{letter}` is in the word!" if is_correct else f"`❌` Wrong guess! The letter `{letter}` is not in the word."
                
                embed = interaction.message.embeds[0]
                embed.description = (
                    f"Wrong Guesses: {self.wrong_guesses}/{self.max_wrong}\n"
                    f"Word: `{word_display}`\n"
                    f"Guessed Letters: `{guessed_text}`\n\n"
                    f"{result_text}"
                )
                
                await interaction.message.edit(embed=embed, view=self)
                
                # Update Z button view if it exists and Z hasn't been guessed yet
                if self.z_view and self.z_message and 'Z' not in self.guessed_letters:
                    try:
                        # Check if Z should be disabled (already guessed via main buttons)
                        button = [b for b in self.z_view.children if isinstance(b, discord.ui.Button) and b.label == "Z"]
                        if button and 'Z' in self.guessed_letters:
                            button[0].disabled = True
                            if 'Z' in self.word:
                                button[0].style = discord.ButtonStyle.green
                            else:
                                button[0].style = discord.ButtonStyle.red
                            await self.z_message.edit(view=self.z_view)
                    except Exception as e:
                        self.logger.debug(f"Could not update Z button: {e}")
                
                # Save state after each guess
                if not self.test_mode:
                    await self._save_state()
        
        except Exception as e:
            self.logger.error(f"Error handling Hangman letter guess: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            try:
                await interaction.followup.send(
                    "`❌` An error occurred while processing your guess. Please try again.",
                    ephemeral=True
                )
            except:
                pass
        finally:
            self.is_processing = False


class HangmanZButton(discord.ui.View):
    """Separate view for Z button that coordinates with main HangmanButtons view"""
    def __init__(self, game_id: int, bot, config, game_config, dm_config, word: str, user_id: int, main_message: discord.Message, main_view: 'HangmanButtons' = None, test_mode: bool = False):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.game_config = game_config
        self.dm_config = dm_config
        self.word = word.upper()
        self.player_id = user_id
        self.main_message = main_message
        self.main_view = main_view  # Reference to main HangmanButtons view for state sharing
        self.test_mode = test_mode
        self.z_message = None  # Reference to this message (set after creation)
        self.logger = get_logger("DMGames")
        
        self.button_cooldown = self.dm_config.get('BUTTON_COOLDOWN', 0.8) or self.dm_config.get('button_cooldown', 0.8)
        self.cooldowns: Dict[int, datetime] = {}
        self.is_processing = False
        
        # Create Z button
        button = discord.ui.Button(
            label="Z",
            style=discord.ButtonStyle.grey,
            custom_id=f"hang_z_{game_id}",
            row=0
        )
        button.callback = self.handle_z_guess
        self.add_item(button)
    
    async def _get_game_state(self):
        """Get current game state from main view or database"""
        # First, try to get state from main view if available (most accurate)
        if self.main_view:
            try:
                return {
                    'word': self.main_view.word,
                    'guessed_letters': list(self.main_view.guessed_letters),
                    'wrong_guesses': self.main_view.wrong_guesses,
                    'max_wrong': self.main_view.max_wrong,
                    'game_ended': self.main_view.game_ended,
                    'game_won': getattr(self.main_view, 'game_won', False)
                }
            except Exception as e:
                self.logger.debug(f"Could not get state from main view: {e}")
        
        # Fallback: try to get from database
        try:
            if not self.test_mode and self.game_id != -999999:
                db = await DatabasePool.get_instance()
                rows = await db.execute(
                    "SELECT wrong_guesses, correct_guesses, game_state, won FROM users_hangman WHERE game_id = %s AND user_id = %s",
                    (self.game_id, self.player_id)
                )
                if rows and len(rows) > 0:
                    row = rows[0]
                    # Try to get game_state first (most complete)
                    if row.get('game_state'):
                        import json
                        try:
                            state = json.loads(row['game_state'])
                            return state
                        except Exception as e:
                            self.logger.debug(f"Could not parse game_state JSON: {e}")
                    
                    # Fallback: reconstruct from database fields
                    # This happens when game_state is NULL (game just started)
                    return {
                        'word': self.word,
                        'guessed_letters': [],  # Can't reconstruct from wrong_guesses/correct_guesses alone
                        'wrong_guesses': row.get('wrong_guesses', 0),
                        'correct_guesses': row.get('correct_guesses', 0),
                        'max_wrong': self.game_config.get('MAX_WRONG') or self.game_config.get('max_wrong_guesses', 6),
                        'game_ended': row.get('won', 'Started') != 'Started',
                        'game_won': row.get('won', '') == 'Won'
                    }
        except Exception as e:
            self.logger.error(f"Error getting game state from database: {e}")
        
        return None
    
    async def _update_button_state(self):
        """Update Z button state based on game state"""
        state = await self._get_game_state()
        if state:
            guessed_letters = set(state.get('guessed_letters', []))
            game_ended = state.get('game_ended', False)
            
            button = [b for b in self.children if isinstance(b, discord.ui.Button) and b.label == "Z"][0]
            if 'Z' in guessed_letters:
                button.disabled = True
                if 'Z' in self.word:
                    button.style = discord.ButtonStyle.green
                else:
                    button.style = discord.ButtonStyle.red
            elif game_ended:
                button.disabled = True
            else:
                button.disabled = False
                button.style = discord.ButtonStyle.grey
    
    async def handle_z_guess(self, interaction: discord.Interaction):
        """Handle Z button click"""
        user_id = interaction.user.id
        
        if user_id != self.player_id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        
        # Get current game state
        state = await self._get_game_state()
        if not state:
            # If we can't get state, try to use main view directly or use defaults
            if self.main_view:
                guessed_letters = self.main_view.guessed_letters.copy()
                game_ended = self.main_view.game_ended
                wrong_guesses = self.main_view.wrong_guesses
                max_wrong = self.main_view.max_wrong
            else:
                await interaction.response.send_message("Could not load game state. Please start a new game.", ephemeral=True)
                return
        else:
            guessed_letters = set(state.get('guessed_letters', []))
            game_ended = state.get('game_ended', False)
            wrong_guesses = state.get('wrong_guesses', 0)
            max_wrong = state.get('max_wrong', self.game_config.get('MAX_WRONG') or self.game_config.get('max_wrong_guesses', 6))
        
        if game_ended:
            await interaction.response.send_message("This game has already ended!", ephemeral=True)
            return
        
        if 'Z' in guessed_letters:
            await interaction.response.send_message(
                f"⚠️ You already guessed the letter `Z`! Try a different letter.",
                ephemeral=True
            )
            return
        
        # Check cooldown
        if user_id in self.cooldowns and datetime.now(timezone.utc) < self.cooldowns[user_id]:
            remaining = (self.cooldowns[user_id] - datetime.now(timezone.utc)).total_seconds()
            await interaction.response.send_message(
                f"❌ You need to wait {remaining:.2f} seconds before guessing again.",
                ephemeral=True
            )
            return
        
        if self.is_processing:
            await interaction.response.send_message("Processing previous guess, please wait...", ephemeral=True)
            return
        
        self.is_processing = True
        await interaction.response.defer()
        
        try:
            # Ensure guessed_letters is a set
            if not isinstance(guessed_letters, set):
                guessed_letters = set(guessed_letters) if guessed_letters else set()
            
            # Add Z to guessed letters
            guessed_letters.add('Z')
            is_correct = 'Z' in self.word
            
            if not is_correct:
                wrong_guesses += 1
            
            # Update main view state if available (keep them in sync)
            if self.main_view:
                try:
                    self.main_view.guessed_letters.add('Z')
                    if not is_correct:
                        self.main_view.wrong_guesses = wrong_guesses
                    self.main_view._update_button_states()
                except Exception as e:
                    self.logger.debug(f"Could not update main view state: {e}")
            
            # Update database
            if not self.test_mode and self.game_id != -999999:
                try:
                    db = await DatabasePool.get_instance()
                    # Update game state
                    new_state = {
                        'word': self.word,
                        'guessed_letters': list(guessed_letters),
                        'wrong_guesses': wrong_guesses,
                        'max_wrong': max_wrong,
                        'game_ended': False,
                        'game_won': False
                    }
                    import json
                    state_json = json.dumps(new_state)
                    
                    word_display = ' '.join([char if char in guessed_letters else '_' for char in self.word])
                    correct_count = len([c for c in word_display if c != '_' and c != ' '])
                    
                    await db.execute(
                        "UPDATE users_hangman SET wrong_guesses = %s, correct_guesses = %s, game_state = %s WHERE user_id = %s AND game_id = %s",
                        (wrong_guesses, correct_count, state_json, self.player_id, self.game_id)
                    )
                except Exception as e:
                    self.logger.error(f"Error updating Hangman game state in database: {e}")
            
            # Update Z button
            button = [b for b in self.children if isinstance(b, discord.ui.Button) and b.label == "Z"][0]
            button.disabled = True
            if is_correct:
                button.style = discord.ButtonStyle.green
            else:
                button.style = discord.ButtonStyle.red
            
            # Update main message by finding it
            try:
                # Find main message if we don't have direct reference
                if not self.main_message:
                    async for msg in interaction.channel.history(limit=50):
                        if msg.embeds and msg.embeds[0].title and f"Hangman #{self.game_id}" in msg.embeds[0].title:
                            self.main_message = msg
                            break
                
                if self.main_message:
                    # Get updated game state
                    word_display = ' '.join([char if char in guessed_letters else '_' for char in self.word])
                    guessed_text = ', '.join(sorted(guessed_letters))
                    word_complete = '_' not in word_display
                    game_lost = wrong_guesses >= max_wrong
                    
                    result_text = f"`✅` Good guess! The letter `Z` is in the word!" if is_correct else f"`❌` Wrong guess! The letter `Z` is not in the word."
                    
                    embed = self.main_message.embeds[0]
                    if word_complete:
                        # Game won
                        embed.description = (
                            f"✅ **Game Won!**\n\n"
                            f"Wrong Guesses: {wrong_guesses}/{max_wrong}\n"
                            f"Word: `{word_display.replace(' ', '')}`\n"
                            f"Guessed Letters: `{guessed_text}`\n\n"
                            f"Congratulations! You guessed the word!"
                        )
                        embed.color = discord.Color.green()
                        
                        # Update database to mark as won
                        if not self.test_mode and self.game_id != -999999:
                            current_unix = int(datetime.now(timezone.utc).timestamp())
                            correct_count = len([c for c in word_display if c != '_' and c != ' '])
                            try:
                                db = await DatabasePool.get_instance()
                                await db.execute(
                                    "UPDATE users_hangman SET won = 'Won', ended_at = %s, correct_guesses = %s WHERE user_id = %s AND game_id = %s",
                                    (current_unix, correct_count, self.player_id, self.game_id)
                                )
                                
                                # Award XP and achievements
                                from utils.achievements import check_dm_game_win
                                await check_dm_game_win(interaction.user, "Hangman", interaction.channel, self.bot)
                                
                                xp = random.randint(
                                    self.game_config.get('WIN_XP', {}).get('LOWER', 80),
                                    self.game_config.get('WIN_XP', {}).get('UPPER', 120)
                                )
                                lvl_mng = LevelingManager(
                                    user=interaction.user,
                                    channel=interaction.channel,
                                    client=self.bot,
                                    xp=xp,
                                    source="Hangman",
                                    game_id=self.game_id
                                )
                                await lvl_mng.update()
                                
                                await interaction.followup.send(
                                    f"`✅` Congratulations {interaction.user.mention}! You guessed the word `{self.word}`! You won `{xp}xp`!",
                                    ephemeral=False
                                )
                            except Exception as e:
                                self.logger.error(f"Error awarding Hangman win: {e}")
                        
                    elif game_lost:
                        # Game lost
                        embed.description = (
                            f"❌ **Game Over!**\n\n"
                            f"Wrong Guesses: {wrong_guesses}/{max_wrong}\n"
                            f"Word: `{self.word}`\n"
                            f"Guessed Letters: `{guessed_text}`\n\n"
                            f"You ran out of guesses! The correct word was `{self.word}`."
                        )
                        embed.color = discord.Color.red()
                        
                        # Update database to mark as lost
                        if not self.test_mode and self.game_id != -999999:
                            current_unix = int(datetime.now(timezone.utc).timestamp())
                            try:
                                db = await DatabasePool.get_instance()
                                await db.execute(
                                    "UPDATE users_hangman SET won = 'Lost', ended_at = %s WHERE user_id = %s AND game_id = %s",
                                    (current_unix, self.player_id, self.game_id)
                                )
                                await interaction.followup.send(
                                    f"`❌` Sorry, but you ran out of guesses! The correct word was `{self.word}`.",
                                    ephemeral=False
                                )
                            except Exception as e:
                                self.logger.error(f"Error updating Hangman loss: {e}")
                    else:
                        # Game continues
                        embed.description = (
                            f"Wrong Guesses: {wrong_guesses}/{max_wrong}\n"
                            f"Word: `{word_display}`\n"
                            f"Guessed Letters: `{guessed_text}`\n\n"
                            f"{result_text}"
                        )
                    
                    await self.main_message.edit(embed=embed)
            except Exception as e:
                self.logger.error(f"Error updating main message: {e}")
            
            # Update Z message
            await interaction.message.edit(view=self)
            self.cooldowns[user_id] = datetime.now(timezone.utc) + timedelta(seconds=self.button_cooldown)
            
        except Exception as e:
            self.logger.error(f"Error handling Z guess: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            try:
                await interaction.followup.send(
                    "`❌` An error occurred while processing your guess. Please try again.",
                    ephemeral=True
                )
            except:
                pass
        finally:
            self.is_processing = False


# Keep the HangmanListener for cleanup purposes but remove the on_message handler
class HangmanListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.hangman_game = None
        self.logger = get_logger("DMGames")
        self._cleanup_done = False
    
    def set_hangman_game(self, hangman_game):
        self.hangman_game = hangman_game
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Clean up stale Hangman games on bot startup"""
        if self._cleanup_done:
            return
        
        self._cleanup_done = True
        
        try:
            await self._cleanup_stale_games()
        except Exception as e:
            self.logger.error(f"Error cleaning up stale Hangman games: {e}")
    
    async def _cleanup_stale_games(self):
        """Clean up Hangman games that have been 'Started' for too long (likely stale)"""
        try:
            db = await DatabasePool.get_instance()
            current_unix = int(datetime.now(timezone.utc).timestamp())
            
            # Mark games as 'Lost' if they've been 'Started' for more than 24 hours (86400 seconds)
            stale_time = current_unix - 86400  # 24 hours ago
            
            rows = await db.execute(
                "SELECT game_id, user_id, started_at FROM users_hangman WHERE won = 'Started' AND started_at < %s AND game_id != -999999",
                (stale_time,)
            )
            
            if rows:
                self.logger.info(f"HangmanListener: Found {len(rows)} stale Hangman games to clean up")
                
                for row in rows:
                    game_id = row['game_id']
                    user_id = row['user_id']
                    
                    try:
                        await db.execute(
                            "UPDATE users_hangman SET won = 'Lost', ended_at = %s WHERE game_id = %s AND user_id = %s AND won = 'Started'",
                            (current_unix, game_id, user_id)
                        )
                        self.logger.info(f"HangmanListener: Cleaned up stale game {game_id} for user {user_id}")
                    except Exception as e:
                        self.logger.error(f"HangmanListener: Error cleaning up game {game_id}: {e}")
                
                self.logger.info(f"HangmanListener: Cleaned up {len(rows)} stale Hangman games")
            else:
                self.logger.debug("HangmanListener: No stale Hangman games found to clean up")
        except Exception as e:
            self.logger.error(f"HangmanListener: Error in _cleanup_stale_games: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
