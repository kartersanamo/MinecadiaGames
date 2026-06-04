import random
from datetime import datetime, timedelta, timezone
from typing import Dict
import discord
from managers.leveling import LevelingManager
from core.database.pool import DatabasePool
from core.logging.setup import get_logger
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
                        'max_wrong': self.game_config.get('MAX_WRONG') or self.game_config.get('max_wrong_guesses', 8),
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
            max_wrong = state.get('max_wrong', self.game_config.get('MAX_WRONG') or self.game_config.get('max_wrong_guesses', 8))
        
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
                                await self.bot.app.achievements.check_dm_game_win(interaction.user, "Hangman", interaction.channel, self.bot)
                                
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
