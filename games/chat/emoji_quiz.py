import asyncio
import random
from datetime import datetime, timezone
from typing import Optional, List, Dict
import discord
from games.base.chat_game import ChatGame
from managers.leveling import LevelingManager
from core.logging.setup import get_logger


class EmojiQuiz(ChatGame):
    def __init__(self, bot):
        super().__init__(bot)
        # Support both old and new config structure
        games = self.chat_config.get('GAMES', {})
        if not games:
            emoji_quiz_config = self.config.get('emoji_quiz', {})
            self.game_config = {'QUESTIONS': emoji_quiz_config.get('questions', [])}
        else:
            self.game_config = games.get('Emoji Quiz', {})
        self.logger = get_logger("ChatGames")
    
    async def _run_game(self, channel: discord.TextChannel, custom_question: Optional[dict] = None, xp_multiplier: float = 1.0, test_mode: bool = False) -> Optional[discord.Message]:
        try:
            game_length = self.chat_config.get('GAME_LENGTH') or self.chat_config.get('game_duration', 600)
            current_unix = int(datetime.now(timezone.utc).timestamp())
            end_time = current_unix + game_length
            
            game_id = await self._create_game_entry('Emoji Quiz', False, test_mode=test_mode, end_time=end_time)
            
            guild = self.bot.get_guild(self.config.get('config', 'GUILD_ID'))
            if not guild:
                self.logger.error("Error fetching guild")
                return None
            
            role = guild.get_role(self.config.get('config', 'GAMES_ROLE'))
            if not role:
                self.logger.error("Games role not found")
                return None
            
            # Use custom question if provided, otherwise get from config
            if custom_question:
                question_data = custom_question
                self.logger.info(f"Using custom emoji quiz: '{question_data['answer']}' #{channel.name}")
            else:
                # Support both old (QUESTIONS) and new (questions) structure
                questions = self.game_config.get('QUESTIONS', []) or self.game_config.get('questions', [])
                
                if not questions:
                    self.logger.error("No emoji quiz questions found")
                    return None
                
                question_data = random.choice(questions)
                self.logger.info(f"Emoji Quiz '{question_data['answer']}' (Category: {question_data.get('category', 'General')}) #{channel.name}")
            
            # Use custom XP multiplier if provided, otherwise random 15% chance for 2x
            if xp_multiplier > 1.0:
                xp_mult = xp_multiplier
            else:
                double_xp = random.random() <= 0.15
                xp_mult = 2.0 if double_xp else 1.0
            
            # Build title with XP multiplier and category
            category = question_data.get('category', 'General')
            xp_title = ""
            if xp_mult == 2.0:
                xp_title = " (DOUBLE XP)"
            elif xp_mult == 3.0:
                xp_title = " (TRIPLE XP)"
            elif xp_mult > 1.0:
                xp_title = f" ({xp_mult:.1f}x XP)"
            
            test_label = " 🧪 TEST GAME 🧪" if test_mode else ""
            
            embed = discord.Embed(
                title=f"Emoji Quiz - {category}{test_label}{xp_title}",
                description=f"This game will end <t:{end_time}:R>",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
                timestamp=datetime.now(timezone.utc)
            )
            
            # Display emojis
            emojis = question_data.get('emojis', '')
            embed.add_field(name="What do these emojis represent?", value=emojis, inline=False)
            embed.add_field(
                name="Instructions",
                value="Click the 'Submit Guess' button to enter your answer!",
                inline=False
            )
            
            # Get correct answer
            correct_answer = question_data.get('answer', '').strip()
            
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            view = EmojiQuizButtons(correct_answer, question_data, xp_mult, game_id, self.bot, self.config, self.chat_config, test_mode=test_mode)
            
            # Register view for persistence across bot restarts
            self.bot.add_view(view)
            message = await channel.send(content=role.mention, embed=embed, view=view)
            view.message = message  # Store message reference for real-time updates
            
            # Register game in registry for admin commands
            from utils.chat_game_registry import registry
            original_state = {
                'correct_answer': correct_answer,
                'question': question_data,
                'embed': {
                    'title': embed.title,
                    'description': embed.description,
                    'fields': [{'name': f.name, 'value': f.value, 'inline': f.inline} for f in embed.fields]
                }
            }
            registry.register_game(
                message.id,
                'emoji_quiz',
                game_id,
                view,
                original_state,
                xp_mult,
                test_mode
            )
            
            # Store message and end_time for timer task
            view.message = message
            view.end_time = end_time
            view.game_id = game_id
            
            # Start timer task that will end the game
            asyncio.create_task(self._game_timer(message, view, end_time, game_id))
            
            return message
        except Exception as e:
            self.logger.error(f"Emoji Quiz error: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    async def _game_timer(self, message: discord.Message, view, end_time: int, game_id: int):
        """Timer task that ends the game at the specified time"""
        try:
            current_time = int(datetime.now(timezone.utc).timestamp())
            remaining_time = end_time - current_time
            
            if remaining_time > 0:
                await asyncio.sleep(remaining_time)
            
            # Check if game is still active
            try:
                if message.components:
                    embed = message.embeds[0] if message.embeds else discord.Embed()
                    embed.description = f"This game ended <t:{end_time}:R>"
                    
                    # Remove Answer field if it exists (from admin panel or elsewhere)
                    fields_to_keep = []
                    for field in embed.fields:
                        if field.name != "Answer":
                            fields_to_keep.append(field)
                    
                    # Clear all fields and re-add the ones we want to keep
                    embed.clear_fields()
                    for field in fields_to_keep:
                        embed.add_field(name=field.name, value=field.value, inline=field.inline)
                    
                    # If no Winners field exists, add one
                    has_winners_field = any(field.name == "Winners" for field in embed.fields)
                    if not has_winners_field:
                        if view.winners:
                            winners_text = "\n".join(
                                f"`+{w['xp']}xp` {w['user']} ({w.get('guesses', 1)} guess{'es' if w.get('guesses', 1) != 1 else ''})"
                                for w in view.winners
                            )
                            embed.add_field(name="Winners", value=winners_text, inline=False)
                        else:
                            embed.add_field(name="Winners", value="No winners!", inline=False)
                    
                    await message.edit(view=None, embed=embed)
                    
                    # Update game status to Finished
                    await self._update_game_status('Finished')
                    
                    # Unregister game from registry
                    from utils.chat_game_registry import registry
                    registry.unregister_game(message.id)
            except discord.NotFound:
                # Message was deleted, that's okay
                pass
            except Exception as e:
                self.logger.error(f"Error ending emoji quiz game {game_id}: {e}")
        except asyncio.CancelledError:
            # Timer was cancelled (e.g., game ended manually)
            pass
        except Exception as e:
            self.logger.error(f"Error in emoji quiz timer: {e}")


class EmojiQuizButtons(discord.ui.View):
    def __init__(
        self,
        correct_answer: str,
        question_data: dict,
        xp_multiplier: float,
        game_id: int,
        bot,
        config,
        chat_config,
        test_mode: bool = False
    ):
        super().__init__(timeout=None)
        self.correct_answer = correct_answer
        self.answer_lower = correct_answer.strip().lower()
        self.question_data = question_data
        self.xp_multiplier = xp_multiplier
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.chat_config = chat_config
        self.test_mode = test_mode
        self.winners: List[dict] = []
        self.message: Optional[discord.Message] = None
        self.winner_count = 0
        self.user_guesses: Dict[int, int] = {}  # Track guesses per user (for XP scaling)
        self._user_locks: Dict[int, asyncio.Lock] = {}  # Per-user lock to prevent double-submit
        
        # Support both old and new XP structure
        xp_config = chat_config.get('XP', {})
        if not xp_config:
            xp_section = chat_config.get('xp', {})
            xp_config = {
                'XP_ADD': xp_section.get('base', 10),
                'XP_LOWER': xp_section.get('positions', {})
            }
        self.xp_config = xp_config
        
        # Add Submit Guess button with custom_id for persistence
        guess_button = discord.ui.Button(
            label="Submit Guess",
            style=discord.ButtonStyle.green,
            row=0,
            custom_id=f"emoji_quiz_{game_id}"
        )
        guess_button.callback = self.create_guess_callback()
        self.add_item(guess_button)
    
    def create_guess_callback(self):
        """Create callback for the guess button"""
        async def callback(interaction: discord.Interaction):
            await self.guess_button_callback(interaction)
        return callback
    
    def _get_user_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._user_locks:
            self._user_locks[user_id] = asyncio.Lock()
        return self._user_locks[user_id]

    async def guess_button_callback(self, interaction: discord.Interaction):
        # Create modal for guess submission
        modal = EmojiQuizModal(self)
        await interaction.response.send_modal(modal)
    
    async def handle_guess(self, interaction: discord.Interaction, guess: str):
        """Handle a user's guess (infinite guesses; XP scales by guess count when correct)."""
        user_id = interaction.user.id
        async with self._get_user_lock(user_id):
            await self._handle_guess_impl(interaction, guess, user_id)

    async def _handle_guess_impl(self, interaction: discord.Interaction, guess: str, user_id: int):
        """Implementation of guess handling; must be called with user lock held."""
        # Check if user already won
        if user_id in [w['user_id'] for w in self.winners]:
            await interaction.response.send_message("You've already won this game!", ephemeral=True)
            return

        if user_id not in self.user_guesses:
            self.user_guesses[user_id] = 0
        self.user_guesses[user_id] += 1
        guesses = self.user_guesses[user_id]
        guess_lower = guess.strip().lower()
        
        # Check if guess matches the answer
        if guess_lower == self.answer_lower:
            # Re-check already won (defense in depth)
            if user_id in [w['user_id'] for w in self.winners]:
                await interaction.response.send_message("You've already won this game!", ephemeral=True)
                return
            # User won!
            self.winner_count += 1
            position = self.winner_count
            
            # Base XP by position (same as Guess the Number)
            if position == 1:
                base_xp = random.randint(50, 60)
            elif position == 2:
                base_xp = random.randint(40, 50)
            elif position == 3:
                base_xp = random.randint(30, 40)
            elif position == 4:
                base_xp = random.randint(20, 30)
            elif position == 5:
                base_xp = random.randint(10, 20)
            else:  # 6th place and beyond
                previous_final_xp = self.winners[-1]['xp'] if self.winners else 20 * self.xp_multiplier
                max_base_xp = max(1, int(previous_final_xp / self.xp_multiplier) - 1)
                min_base_xp_required = max(1, int((10 / self.xp_multiplier) + 0.999))
                min_base_xp = max(min_base_xp_required, max_base_xp - 9)
                if min_base_xp >= max_base_xp:
                    min_base_xp = max(1, max_base_xp - 1)
                base_xp = random.randint(min_base_xp, max_base_xp) if min_base_xp < max_base_xp else min_base_xp
            
            # Fewer guesses = more XP (same formula as Guess the Number)
            guess_bonus = max(0, (6 - guesses) * 2)
            guess_penalty = max(0, (guesses - 5) * 2)
            xp = base_xp + guess_bonus - guess_penalty
            xp = max(10, xp)
            xp = int(xp * self.xp_multiplier)
            xp = max(10, xp)
            
            self.winners.append({
                'user': interaction.user.mention,
                'user_id': user_id,
                'xp': xp,
                'guesses': guesses
            })
            
            lvl_mng = LevelingManager(
                user=interaction.user,
                channel=interaction.channel,
                client=self.bot,
                xp=xp,
                source="Emoji Quiz",
                game_id=self.game_id,
                test_mode=self.test_mode
            )
            await lvl_mng.update()
            
            # Log activity
            if self.message:
                from utils.chat_game_registry import registry
                registry.log_activity(
                    self.message.id,
                    user_id,
                    'correct_answer',
                    f'Won {xp} XP (position {position}, {guesses} guesses)',
                    True
                )
            
            # Build XP message
            xp_msg = ""
            if self.xp_multiplier == 2.0:
                xp_msg = " (2x XP)"
            elif self.xp_multiplier == 3.0:
                xp_msg = " (3x XP)"
            elif self.xp_multiplier > 1.0:
                xp_msg = f" ({self.xp_multiplier:.1f}x XP)"
            
            test_prefix = "🧪 [TEST] " if self.test_mode else ""
            xp_display = f"would have been awarded `{xp}xp`" if self.test_mode else f"have been awarded `{xp}xp`"
            
            await interaction.response.send_message(
                f"`✅` {test_prefix}Correct! The answer was **{self.correct_answer}**! You {xp_display}{xp_msg} in {guesses} guess{'es' if guesses != 1 else ''}!",
                ephemeral=True
            )
            
            # Update embed with winners list immediately
            if self.message:
                try:
                    embed = self.message.embeds[0]
                    winners_text = "\n".join(
                        f"`+{w['xp']}xp` {w['user']} ({w['guesses']} guess{'es' if w['guesses'] != 1 else ''})"
                        for w in self.winners
                    )
                    
                    # Check if Winners field exists and update it, otherwise add it
                    found_winners_field = False
                    for i, field in enumerate(embed.fields):
                        if field.name == "Winners":
                            embed.set_field_at(i, name="Winners", value=winners_text, inline=False)
                            found_winners_field = True
                            break
                    if not found_winners_field:
                        embed.add_field(name="Winners", value=winners_text, inline=False)
                    
                    await self.message.edit(embed=embed)
                except Exception as e:
                    from core.logging.setup import get_logger
                    logger = get_logger("ChatGames")
                    logger.error(f"Error updating winners in embed: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
        else:
            # Wrong answer - allow infinite retries (like Guess the Number)
            if self.message:
                from utils.chat_game_registry import registry
                registry.log_activity(
                    self.message.id,
                    user_id,
                    'wrong_answer',
                    f'Guessed: {guess}',
                    False
                )
            
            await interaction.response.send_message(
                "`❌` That's not correct! Try again!",
                ephemeral=True
            )


class EmojiQuizModal(discord.ui.Modal, title="Emoji Quiz Guess"):
    def __init__(self, parent_view: EmojiQuizButtons):
        super().__init__()
        self.parent_view = parent_view
        
        self.guess_input = discord.ui.TextInput(
            label="Enter your answer",
            placeholder="Type what the emojis represent...",
            required=True,
            max_length=200
        )
        self.add_item(self.guess_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        guess = self.guess_input.value.strip()
        await self.parent_view.handle_guess(interaction, guess)
