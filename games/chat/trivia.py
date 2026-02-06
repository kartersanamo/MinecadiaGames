import asyncio
import random
from datetime import datetime, timezone
from typing import Optional, List
import discord
from games.base.chat_game import ChatGame
from managers.leveling import LevelingManager
from core.logging.setup import get_logger


class Trivia(ChatGame):
    def __init__(self, bot):
        super().__init__(bot)
        # Support both old and new config structure
        games = self.chat_config.get('GAMES', {})
        if not games:
            trivia_config = self.config.get('trivia', {})
            self.game_config = {'QUESTIONS': trivia_config.get('questions', {})}
        else:
            self.game_config = games.get('Trivia', {})
        self.logger = get_logger("ChatGames")
    
    async def _run_game(self, channel: discord.TextChannel, custom_trivia: Optional[dict] = None, xp_multiplier: float = 1.0, test_mode: bool = False) -> Optional[discord.Message]:
        try:
            game_length = self.chat_config.get('GAME_LENGTH') or self.chat_config.get('game_duration', 600)
            current_unix = int(datetime.now(timezone.utc).timestamp())
            end_time = current_unix + game_length
            
            game_id = await self._create_game_entry('Trivia', False, test_mode=test_mode, end_time=end_time)
            
            guild = self.bot.get_guild(self.config.get('config', 'GUILD_ID'))
            if not guild:
                self.logger.error("Error fetching guild")
                return None
            
            role = guild.get_role(self.config.get('config', 'GAMES_ROLE'))
            if not role:
                self.logger.error("Games role not found")
                return None
            
            # Use custom trivia if provided, otherwise get from config
            if custom_trivia:
                trivia = custom_trivia
                self.logger.info(f"Using custom trivia: '{trivia['question']}' | '{trivia['answers'][0]}' #{channel.name}")
            else:
                # Support both old (QUESTIONS) and new (questions) structure
                questions_dict = self.game_config.get('QUESTIONS', {}) or self.game_config.get('questions', {})
                
                # Collect all questions from all channels/realms into one list
                all_questions = []
                for channel_id, questions_list in questions_dict.items():
                    if isinstance(questions_list, list):
                        all_questions.extend(questions_list)
                
                if not all_questions:
                    self.logger.error("No trivia questions found in any channel")
                    return None
                
                trivia = random.choice(all_questions)
                self.logger.info(f"Trivia '{trivia['question']}' | '{trivia['answers'][0]}' #{channel.name} (from all realms)")
            
            # Use custom XP multiplier if provided, otherwise random 15% chance for 2x
            if xp_multiplier > 1.0:
                double_xp = True
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
                title=f"Trivia Question{test_label}{xp_title}",
                description=f"This game will end <t:{end_time}:R>",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Question", value=trivia["question"], inline=False)
            
            view = TriviaButtons(trivia, xp_mult, game_id, self.bot, self.config, self.chat_config, test_mode=test_mode)
            answers = trivia['answers'][:4]
            
            items = []
            for index, button in enumerate(view.children):
                if index < len(answers):
                    button.label = answers[index]
                    items.append(button)
            
            view.clear_items()
            random.shuffle(items)
            for item in items:
                view.add_item(item)
            
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
                'correct_answer': trivia['answers'][0],
                'question': trivia['question'],
                'answers': trivia['answers'],
                'embed': {
                    'title': embed.title,
                    'description': embed.description,
                    'fields': [{'name': f.name, 'value': f.value, 'inline': f.inline} for f in embed.fields]
                }
            }
            registry.register_game(
                message.id,
                'trivia',
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
            self.logger.error(f"Trivia error: {e}")
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
                    # Winners are already added in real-time, no need to add again
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
                self.logger.error(f"Error ending trivia game {game_id}: {e}")
        except asyncio.CancelledError:
            # Timer was cancelled (e.g., game ended manually)
            pass
        except Exception as e:
            self.logger.error(f"Error in trivia timer: {e}")


class TriviaButtons(discord.ui.View):
    def __init__(self, trivia: dict, xp_multiplier: float, game_id: int, bot, config, chat_config, test_mode: bool = False):
        super().__init__(timeout=None)
        self.correct_answer = trivia['answers'][0]
        self.all_answers = trivia['answers'][:4]
        self.xp_multiplier = xp_multiplier
        self.double_xp = xp_multiplier >= 2.0  # For display purposes
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.chat_config = chat_config
        self.test_mode = test_mode
        self.winners: List[dict] = []
        self.message: Optional[discord.Message] = None  # Store message reference
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
        self.answer_map = {}
        self.failed_users: set = set()  # Track users who have answered incorrectly
        
        for i in range(4):
            answer = self.all_answers[i] if i < len(self.all_answers) else f"Answer {i+1}"
            button = discord.ui.Button(
                label=answer,
                style=discord.ButtonStyle.grey,
                custom_id=f"trivia_{i}_{game_id}"
            )
            self.answer_map[f"trivia_{i}_{game_id}"] = answer
            button.callback = self.create_callback(answer)
            self.add_item(button)
    
    def create_callback(self, answer: str):
        async def callback(interaction: discord.Interaction):
            # Check if user has already answered incorrectly
            if interaction.user.id in self.failed_users:
                from utils.chat_game_registry import registry
                if self.message:
                    registry.log_activity(
                        self.message.id,
                        interaction.user.id,
                        'denied',
                        'Already failed - cannot retry',
                        False
                    )
                await interaction.response.send_message("You've already answered incorrectly and cannot try again!", ephemeral=True)
                return
            
            # Log activity
            from utils.chat_game_registry import registry
            if self.message:
                registry.log_activity(
                    self.message.id,
                    interaction.user.id,
                    'click',
                    f'Clicked: {answer[:50]}',
                    True
                )
            
            if answer == self.correct_answer:
                if interaction.user.id in [w['user_id'] for w in self.winners]:
                    if self.message:
                        registry.log_activity(
                            self.message.id,
                            interaction.user.id,
                            'denied',
                            'Already won',
                            False
                        )
                    await interaction.response.send_message("You've already won this game!", ephemeral=True)
                    return
                
                self.winner_count += 1
                
                # New XP system: random ranges based on position
                position = self.winner_count
                if position == 1:
                    xp = random.randint(50, 60)
                elif position == 2:
                    xp = random.randint(40, 50)
                elif position == 3:
                    xp = random.randint(30, 40)
                elif position == 4:
                    xp = random.randint(20, 30)
                elif position == 5:
                    xp = random.randint(10, 20)
                else:  # 6th place and beyond - must be less than previous winner
                    # Get previous winner's final XP (after multiplier)
                    previous_final_xp = self.winners[-1]['xp'] if self.winners else 20 * self.xp_multiplier
                    # Get base XP that would result in less final XP
                    # We need: (base_xp * multiplier) < previous_final_xp
                    # So: base_xp < previous_final_xp / multiplier
                    max_base_xp = max(1, int(previous_final_xp / self.xp_multiplier) - 1)
                    # Ensure minimum base XP results in at least 10 XP after multiplier
                    # Calculate minimum base XP needed: base_xp * multiplier >= 10, so base_xp >= 10 / multiplier
                    min_base_xp_required = max(1, int((10 / self.xp_multiplier) + 0.999))  # Round up
                    min_base_xp = max(min_base_xp_required, max_base_xp - 9)  # Keep range reasonable (up to 10 XP range)
                    # Ensure min_base_xp < max_base_xp for randint
                    if min_base_xp >= max_base_xp:
                        min_base_xp = max(1, max_base_xp - 1)
                    xp = random.randint(min_base_xp, max_base_xp) if min_base_xp < max_base_xp else min_base_xp
                
                # Apply XP multiplier
                xp = int(xp * self.xp_multiplier)
                # Ensure minimum XP is 10 (safety check)
                xp = max(10, xp)
                
                self.winners.append({
                    'user': interaction.user.mention,
                    'user_id': interaction.user.id,
                    'xp': xp
                })
                
                lvl_mng = LevelingManager(
                    user=interaction.user,
                    channel=interaction.channel,
                    client=self.bot,
                    xp=xp,
                    source="Trivia",
                    game_id=self.game_id,
                    test_mode=self.test_mode
                )
                await lvl_mng.update()
                
                # Log correct answer
                if self.message:
                    registry.log_activity(
                        self.message.id,
                        interaction.user.id,
                        'correct_answer',
                        f'Won {xp} XP (position {position})',
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
                    f"`✅` {test_prefix}Correct! You {xp_display}{xp_msg}!",
                    ephemeral=True
                )
                
                # Update embed with winners list immediately
                if self.message:
                    try:
                        embed = self.message.embeds[0]
                        winners_text = "\n".join(f"`+{w['xp']}xp` {w['user']}" for w in self.winners)
                        
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
                        # If updating fails, log but don't break the game
                        import traceback
                        from core.logging.setup import get_logger
                        logger = get_logger("ChatGames")
                        logger.error(f"Error updating winners in embed: {e}\n{traceback.format_exc()}")
            else:
                # Mark user as failed - they cannot try again
                self.failed_users.add(interaction.user.id)
                
                # Log wrong answer
                if self.message:
                    registry.log_activity(
                        self.message.id,
                        interaction.user.id,
                        'wrong_answer',
                        f'Selected: {answer[:50]}',
                        False
                    )
                await interaction.response.send_message("`❌` Incorrect answer! You cannot try again.", ephemeral=True)
        
        return callback

