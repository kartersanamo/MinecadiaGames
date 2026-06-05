import random
from datetime import datetime, timedelta, timezone
from typing import Dict, Set
import discord
from managers.leveling import LevelingManager
from repositories.game_session_repository import GameSessionRepository
from core.logging.setup import get_logger
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
            self.max_wrong = self.game_config.get('MAX_WRONG') or self.game_config.get('max_wrong_guesses', 8)
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
        self.max_wrong = state.get('max_wrong', self.game_config.get('MAX_WRONG') or self.game_config.get('max_wrong_guesses', 8))
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
            await self.bot.app.game_state.save('hangman', self.game_id, self.player_id, state, self.test_mode)
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
                    repo = GameSessionRepository()
                    correct_count = len([c for c in word_display if c != "_" and c != " "])
                    await repo.merge_stats(
                        self.game_id,
                        self.player_id,
                        "hangman",
                        {
                            "word": self.word,
                            "wrong_guesses": self.wrong_guesses,
                            "correct_guesses": correct_count,
                        },
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
                        repo = GameSessionRepository()
                        await repo.finish_session(
                            self.game_id,
                            self.player_id,
                            "hangman",
                            "won",
                            stats={
                                "word": self.word,
                                "wrong_guesses": self.wrong_guesses,
                                "correct_guesses": correct_count,
                            },
                            ended_at=current_unix,
                        )
                        
                        # Check for achievements
                        await self.bot.app.achievements.check_dm_game_win(interaction.user, "Hangman", interaction.channel, self.bot)
                        
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
                        repo = GameSessionRepository()
                        await repo.finish_session(
                            self.game_id,
                            self.player_id,
                            "hangman",
                            "lost",
                            stats={
                                "word": self.word,
                                "wrong_guesses": self.wrong_guesses,
                            },
                            ended_at=current_unix,
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
            except Exception:
                pass
        finally:
            self.is_processing = False
