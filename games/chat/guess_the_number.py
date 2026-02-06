import asyncio
import random
from datetime import datetime, timezone
from typing import Optional, List, Dict
import discord
from games.base.chat_game import ChatGame
from managers.leveling import LevelingManager
from core.logging.setup import get_logger


class GuessTheNumber(ChatGame):
    def __init__(self, bot):
        super().__init__(bot)
        self.logger = get_logger("ChatGames")
    
    async def _run_game(self, channel: discord.TextChannel, xp_multiplier: float = 1.0, test_mode: bool = False) -> Optional[discord.Message]:
        try:
            game_length = self.chat_config.get('GAME_LENGTH') or self.chat_config.get('game_duration', 600)
            current_unix = int(datetime.now(timezone.utc).timestamp())
            end_time = current_unix + game_length
            
            game_id = await self._create_game_entry('Guess The Number', False, test_mode=test_mode, end_time=end_time)
            
            guild = self.bot.get_guild(self.config.get('config', 'GUILD_ID'))
            if not guild:
                self.logger.error("Error fetching guild")
                return None
            
            role = guild.get_role(self.config.get('config', 'GAMES_ROLE'))
            if not role:
                self.logger.error("Games role not found")
                return None
            
            # Generate random number between 1 and 100
            secret_number = random.randint(1, 100)
            min_range = 1
            max_range = 100
            self.logger.info(f"Guess The Number '{secret_number}' (Range: {min_range}-{max_range}) #{channel.name}")
            
            # Use custom XP multiplier if provided, otherwise random 15% chance for 2x
            if xp_multiplier > 1.0:
                xp_mult = xp_multiplier
            else:
                double_xp = random.random() <= 0.15
                xp_mult = 2.0 if double_xp else 1.0
            
            # Build title with XP multiplier and test mode
            xp_title = ""
            if xp_mult == 2.0:
                xp_title = " (DOUBLE XP)"
            elif xp_mult == 3.0:
                xp_title = " (TRIPLE XP)"
            elif xp_mult > 1.0:
                xp_title = f" ({xp_mult:.1f}x XP)"
            
            test_label = " 🧪 TEST GAME 🧪" if test_mode else ""
            
            embed = discord.Embed(
                title=f"Guess The Number{test_label}{xp_title}",
                description=f"This game will end <t:{end_time}:R>",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(
                name="Range",
                value=f"**{min_range} - {max_range}**",
                inline=False
            )
            embed.add_field(
                name="Instructions",
                value="Click the 'Guess' button to enter your guess! The bot will tell you if the number is higher or lower.",
                inline=False
            )
            
            view = GuessTheNumberButtons(secret_number, min_range, max_range, xp_mult, game_id, self.bot, self.config, self.chat_config, test_mode=test_mode)
            
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            # Register view for persistence across bot restarts
            self.bot.add_view(view)
            message = await channel.send(content=role.mention, embed=embed, view=view)
            view.message = message  # Store message reference for real-time updates
            
            # Register game in registry for admin commands
            from utils.chat_game_registry import registry
            original_state = {
                'secret_number': secret_number,
                'min_range': min_range,
                'max_range': max_range,
                'embed': {
                    'title': embed.title,
                    'description': embed.description,
                    'fields': [{'name': f.name, 'value': f.value, 'inline': f.inline} for f in embed.fields]
                }
            }
            registry.register_game(
                message.id,
                'guess_the_number',
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
            asyncio.create_task(self._game_timer(message, view, end_time, game_id, secret_number))
            
            return message
        except Exception as e:
            self.logger.error(f"Guess The Number error: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    async def _game_timer(self, message: discord.Message, view, end_time: int, game_id: int, secret_number: int):
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
                    # Keep Winners field as-is since it's already updated in real-time
                    fields_to_keep = []
                    for field in embed.fields:
                        if field.name != "Answer":
                            fields_to_keep.append(field)
                    
                    # Clear all fields and re-add the ones we want to keep
                    embed.clear_fields()
                    for field in fields_to_keep:
                        embed.add_field(name=field.name, value=field.value, inline=field.inline)
                    
                    # If no Winners field exists, add one (shouldn't happen, but just in case)
                    has_winners_field = any(field.name == "Winners" for field in embed.fields)
                    if not has_winners_field:
                        if view.winners:
                            winners_text = "\n".join([
                                f"`+{w['xp']}xp` {w['user']} ({w['guesses']} guess{'es' if w['guesses'] != 1 else ''})"
                                for w in view.winners
                            ])
                            embed.add_field(name="Winners", value=winners_text, inline=False)
                        else:
                            embed.add_field(name="Winners", value="No winners!", inline=False)
                    
                    await message.edit(
                        view=None, 
                        embed=embed
                    )
                    
                    # Update game status to Finished
                    await self._update_game_status('Finished')
                    
                    # Unregister game from registry
                    from utils.chat_game_registry import registry
                    registry.unregister_game(message.id)
            except discord.NotFound:
                # Message was deleted, that's okay
                pass
            except Exception as e:
                self.logger.error(f"Error ending guess the number game {game_id}: {e}")
        except asyncio.CancelledError:
            # Timer was cancelled (e.g., game ended manually)
            pass
        except Exception as e:
            self.logger.error(f"Error in guess the number timer: {e}")


class GuessTheNumberButtons(discord.ui.View):
    def __init__(
        self,
        secret_number: int,
        min_range: int,
        max_range: int,
        xp_multiplier: float,
        game_id: int,
        bot,
        config,
        chat_config,
        test_mode: bool = False,
        # Practice-session wiring (used by /practice)
        practice_cog=None,
        practice_user_id: Optional[int] = None,
        practice_session_data: Optional[Dict] = None,
        practice_auto_end: bool = False
    ):
        super().__init__(timeout=None)
        self.secret_number = secret_number
        self.min_range = min_range
        self.max_range = max_range
        self.xp_multiplier = xp_multiplier
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.chat_config = chat_config
        self.test_mode = test_mode
        self.practice_cog = practice_cog
        self.practice_user_id = practice_user_id
        self.practice_session_data = practice_session_data
        self.practice_auto_end = practice_auto_end
        self._practice_counted_played = False
        self.winners: List[Dict] = []
        self.message: Optional[discord.Message] = None
        self.user_ranges: Dict[int, Dict[str, int]] = {}  # Track each user's current range
        self.user_guesses: Dict[int, int] = {}  # Track number of guesses per user
        self._user_locks: Dict[int, asyncio.Lock] = {}  # Per-user lock to prevent double-submit XP bug
        
        # Support both old and new XP structure
        xp_config = chat_config.get('XP', {})
        if not xp_config:
            xp_section = chat_config.get('xp', {})
            xp_config = {
                'XP_ADD': xp_section.get('base', 10),
                'XP_LOWER': xp_section.get('positions', {})
            }
        self.xp_config = xp_config
        self.winner_count = 0
        
        # Add Guess button with custom_id for persistence
        guess_button = discord.ui.Button(
            label="Guess",
            style=discord.ButtonStyle.green,
            row=0,
            custom_id=f"guess_the_number_{game_id}"
        )
        guess_button.callback = self.create_guess_callback()
        self.add_item(guess_button)
    
    def create_guess_callback(self):
        """Create callback for the guess button"""
        async def callback(interaction: discord.Interaction):
            await self.guess_button_callback(interaction)
        return callback
    
    async def guess_button_callback(self, interaction: discord.Interaction):
        # Get user's current range (or default to game range)
        user_id = interaction.user.id
        if user_id not in self.user_ranges:
            self.user_ranges[user_id] = {'min': self.min_range, 'max': self.max_range}
            self.user_guesses[user_id] = 0
        
        user_range = self.user_ranges[user_id]
        
        # Create modal with current range
        modal = GuessModal(self, user_range['min'], user_range['max'])
        await interaction.response.send_modal(modal)
    
    def update_user_range(self, user_id: int, guess: int, is_higher: bool):
        """Update the user's range based on their guess"""
        if user_id not in self.user_ranges:
            self.user_ranges[user_id] = {'min': self.min_range, 'max': self.max_range}
        
        user_range = self.user_ranges[user_id]
        
        if is_higher:
            # Number is higher, so new min is guess + 1
            user_range['min'] = max(user_range['min'], guess + 1)
        else:
            # Number is lower, so new max is guess - 1
            user_range['max'] = min(user_range['max'], guess - 1)
    
    def _get_user_lock(self, user_id: int) -> asyncio.Lock:
        """Get or create an asyncio lock for a user to prevent concurrent guess handling (infinite XP bug)."""
        if user_id not in self._user_locks:
            self._user_locks[user_id] = asyncio.Lock()
        return self._user_locks[user_id]

    async def handle_guess(self, interaction: discord.Interaction, guess: int):
        """Handle a user's guess"""
        user_id = interaction.user.id

        # Serialize per-user so rapid double-submit (e.g. 5 then 1 during delay) cannot award XP twice
        async with self._get_user_lock(user_id):
            await self._handle_guess_impl(interaction, guess, user_id)

    async def _handle_guess_impl(self, interaction: discord.Interaction, guess: int, user_id: int):
        """Implementation of guess handling; must be called with user lock held."""

        # Practice bookkeeping: count "game played" on first interaction from the owner
        if (
            self.test_mode
            and self.practice_session_data is not None
            and self.practice_user_id == user_id
            and not self._practice_counted_played
        ):
            self.practice_session_data['games_played'] = int(self.practice_session_data.get('games_played', 0)) + 1
            self._practice_counted_played = True
        
        # Check if user already won
        if user_id in [w['user_id'] for w in self.winners]:
            await interaction.response.send_message("You've already won this game!", ephemeral=True)
            return
        
        # Initialize user tracking if needed
        if user_id not in self.user_ranges:
            self.user_ranges[user_id] = {'min': self.min_range, 'max': self.max_range}
            self.user_guesses[user_id] = 0
        
        self.user_guesses[user_id] += 1
        user_range = self.user_ranges[user_id]
        
        # Validate guess is within current range
        if guess < user_range['min'] or guess > user_range['max']:
            await interaction.response.send_message(
                f"`❌` Your guess must be between {user_range['min']} and {user_range['max']}!",
                ephemeral=True
            )
            return
        
        # Check if guess is correct
        if guess == self.secret_number:
            # Re-check already won before awarding (defense in depth against race conditions)
            if user_id in [w['user_id'] for w in self.winners]:
                await interaction.response.send_message("You've already won this game!", ephemeral=True)
                return
            # User won!
            self.winner_count += 1
            position = self.winner_count
            guesses = self.user_guesses[user_id]
            
            # Calculate XP: Base on position, then adjust for guesses
            # Position 1: 50-60, Position 2: 40-50, Position 3: 30-40, Position 4: 20-30, Position 5: 10-20
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
            else:
                # 6th place and beyond - must be less than previous winner
                previous_final_xp = self.winners[-1]['xp'] if self.winners else 20 * self.xp_multiplier
                max_base_xp = max(1, int(previous_final_xp / self.xp_multiplier) - 1)
                min_base_xp_required = max(1, int((10 / self.xp_multiplier) + 0.999))
                min_base_xp = max(min_base_xp_required, max_base_xp - 9)
                # Ensure min_base_xp < max_base_xp for randint
                if min_base_xp >= max_base_xp:
                    min_base_xp = max(1, max_base_xp - 1)
                base_xp = random.randint(min_base_xp, max_base_xp) if min_base_xp < max_base_xp else min_base_xp
            
            # Adjust for number of guesses (fewer guesses = bonus, more guesses = penalty)
            # Perfect guess (1 guess) gets +5 bonus
            # Each additional guess reduces by 2 XP (minimum 0 reduction)
            guess_bonus = max(0, (6 - guesses) * 2)  # 1 guess = +10, 2 = +8, 3 = +6, etc.
            guess_penalty = max(0, (guesses - 5) * 2)  # 6+ guesses = -2, 7+ = -4, etc.
            
            xp = base_xp + guess_bonus - guess_penalty
            xp = max(10, xp)  # Ensure minimum 10 XP
            
            # Apply XP multiplier
            xp = int(xp * self.xp_multiplier)
            xp = max(10, xp)  # Ensure minimum 10 XP after multiplier
            
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
                source="Guess The Number",
                game_id=self.game_id,
                test_mode=self.test_mode
            )
            await lvl_mng.update()
            
            # Practice session stats (only for the owner)
            if self.test_mode and self.practice_session_data is not None and self.practice_user_id == user_id:
                self.practice_session_data['games_won'] = int(self.practice_session_data.get('games_won', 0)) + 1
                self.practice_session_data['total_xp_would_have'] = int(self.practice_session_data.get('total_xp_would_have', 0)) + int(xp)

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
                f"`✅` {test_prefix}Correct! The number was **{self.secret_number}**! You {xp_display}{xp_msg} in {guesses} guess{'es' if guesses != 1 else ''}!",
                ephemeral=True
            )
            
            # Update embed with winners list immediately
            if self.message:
                try:
                    embed = self.message.embeds[0]
                    winners_text = "\n".join([
                        f"`+{w['xp']}xp` {w['user']} ({w['guesses']} guess{'es' if w['guesses'] != 1 else ''})"
                        for w in self.winners
                    ])
                    
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
                    self.logger.error(f"Error updating winners in embed: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())

            # Practice auto-end: always clear the active session so /practice can be used again
            if (
                self.test_mode
                and self.practice_auto_end
                and self.practice_cog is not None
                and self.practice_user_id == user_id
            ):
                try:
                    await self.practice_cog.end_practice_session(self.practice_user_id)
                except Exception:
                    # Never block the game flow on cleanup
                    pass
        else:
            # Guess is wrong, tell user if higher or lower
            is_higher = guess < self.secret_number
            self.update_user_range(user_id, guess, is_higher)
            
            user_range = self.user_ranges[user_id]
            
            # Log activity
            if self.message:
                from utils.chat_game_registry import registry
                registry.log_activity(
                    self.message.id,
                    user_id,
                    'wrong_answer',
                    f'Guessed: {guess} ({"Higher" if is_higher else "Lower"})',
                    False
                )
            
            direction = "higher" if is_higher else "lower"
            await interaction.response.send_message(
                f"`❌` The number is **{direction}** than {guess}!\n"
                f"New range: **{user_range['min']} - {user_range['max']}**",
                ephemeral=True
            )


class GuessModal(discord.ui.Modal, title="Guess The Number"):
    def __init__(self, parent_view: GuessTheNumberButtons, min_range: int, max_range: int):
        super().__init__()
        self.parent_view = parent_view
        
        self.guess_input = discord.ui.TextInput(
            label=f"Enter your guess ({min_range} - {max_range})",
            placeholder=f"Enter a number between {min_range} and {max_range}",
            required=True,
            max_length=10
        )
        self.add_item(self.guess_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            guess = int(self.guess_input.value.strip())
            await self.parent_view.handle_guess(interaction, guess)
        except ValueError:
            await interaction.response.send_message(
                "`❌` Please enter a valid number!",
                ephemeral=True
            )

