import asyncio
import random
from datetime import datetime, timezone
from typing import Optional, List, Tuple
import discord
import mathgenerator
from pylatexenc.latex2text import LatexNodes2Text
from games.base.chat_game import ChatGame
from managers.leveling import LevelingManager
from core.logging.setup import get_logger


class MathQuiz(ChatGame):
    def __init__(self, bot):
        super().__init__(bot)
        try:
            # Support both old and new config structure
            self.logger.debug(f"chat_config type: {type(self.chat_config)}, value: {self.chat_config}")
            games = self.chat_config.get('GAMES', {}) if isinstance(self.chat_config, dict) else {}
            self.logger.debug(f"games type: {type(games)}, value: {games}")
            if not games:
                math_config = self.config.get('math_quiz', {})
                self.logger.debug(f"math_config type: {type(math_config)}, value: {math_config}")
                self.game_config = {'QUESTIONS': math_config.get('problem_types', []) if isinstance(math_config, dict) else []}
            else:
                self.game_config = games.get('Math Quiz', {}) if isinstance(games, dict) else {}
            self.logger.debug(f"game_config type: {type(self.game_config)}, value: {self.game_config}")
            self.logger = get_logger("ChatGames")
        except Exception as e:
            import traceback
            self.logger.error(f"Error in MathQuiz.__init__: {e}")
            self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise
    
    def _fix_format_sync(self, phrase: str) -> str:
        """Synchronous version of format fixing - used as fallback"""
        if not isinstance(phrase, str):
            phrase = str(phrase)
        try:
            fixed = LatexNodes2Text().latex_to_text(phrase)
            fixed = fixed.replace("·", " x ")
            fixed = fixed.replace('[', '')
            fixed = fixed.replace(']', '')
            return fixed
        except Exception:
            return phrase
    
    async def _fix_format(self, phrase: str) -> str:
        # Ensure phrase is a string
        if not isinstance(phrase, str):
            phrase = str(phrase)
        
        # Check if there's a running event loop - if not, use sync version
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running event loop (e.g., during shutdown), use sync fallback
            return self._fix_format_sync(phrase)
        
        try:
            fixed = await self._fix_format_async(phrase)
        except asyncio.TimeoutError:
            fixed = phrase
        except Exception as e:
            # Only log if we're not shutting down
            try:
                self.logger.error(f"Error in _fix_format: {e}")
            except Exception:
                pass  # Ignore logging errors during shutdown
            fixed = str(phrase) if not isinstance(phrase, str) else phrase
        return fixed
    
    def _latex_to_text_sync(self, phrase: str) -> str:
        """Synchronous LaTeX-to-text conversion. Run in thread to avoid blocking the event loop."""
        return LatexNodes2Text().latex_to_text(phrase)

    async def _fix_format_async(self, phrase: str) -> str:
        # Ensure phrase is a string
        if not isinstance(phrase, str):
            phrase = str(phrase)
        # Run CPU-bound pylatexenc in thread to avoid blocking Discord heartbeat
        fixed = await asyncio.to_thread(self._latex_to_text_sync, phrase)
        fixed = fixed.replace("·", " x ")
        fixed = fixed.replace('[', '')
        fixed = fixed.replace(']', '')
        return fixed
    
    async def _get_wrong_answers(self, question_id: int, real: str, problem: str) -> List[str]:
        # Ensure problem is a string - handle all possible types
        if not isinstance(problem, str):
            self.logger.warning(f"Problem is not a string in _get_wrong_answers: {type(problem)}, value: {problem}")
            if isinstance(problem, dict):
                problem = str(problem.get('problem', problem.get('text', str(problem))))
            elif isinstance(problem, (list, tuple)):
                problem = str(problem[0]) if problem else ''
            else:
                problem = str(problem) if problem is not None else ''
        
        # Final safety check
        if not isinstance(problem, str):
            self.logger.error(f"Failed to convert problem to string: {type(problem)}, value: {problem}")
            problem = ''
        
        wrong = []
        for _ in range(3):
            try:
                result = mathgenerator.genById(question_id)
                # Handle case where genById might return different structures
                if isinstance(result, tuple) and len(result) >= 2:
                    _, solution = result[0], result[1]
                elif isinstance(result, dict):
                    solution = result.get('solution', result.get('answer', ''))
                else:
                    self.logger.warning(f"Unexpected result from mathgenerator.genById in _get_wrong_answers: {type(result)}")
                    solution = str(result) if result else ''
                
                # Ensure solution is a string
                if not isinstance(solution, str):
                    solution = str(solution)
            except Exception as e:
                self.logger.error(f"Error generating wrong answer: {e}")
                continue
            
            # Check if event loop is still running before async operations
            try:
                asyncio.get_running_loop()
                try:
                    fixed_solution = await self._fix_format(solution)
                except Exception:
                    fixed_solution = solution
            except RuntimeError:
                # No event loop (shutdown), use sync fallback
                fixed_solution = self._fix_format_sync(solution)
            
            while (fixed_solution == real) or (fixed_solution in wrong):
                try:
                    result = mathgenerator.genById(question_id)
                    # Handle case where genById might return different structures
                    if isinstance(result, tuple) and len(result) >= 2:
                        _, solution = result[0], result[1]
                    elif isinstance(result, dict):
                        solution = result.get('solution', result.get('answer', ''))
                    else:
                        try:
                            self.logger.warning(f"Unexpected result from mathgenerator.genById in while loop: {type(result)}")
                        except Exception:
                            pass
                        solution = str(result) if result else ''
                    
                    # Ensure solution is a string
                    if not isinstance(solution, str):
                        solution = str(solution)
                except Exception as e:
                    try:
                        self.logger.error(f"Error generating wrong answer: {e}")
                    except Exception:
                        pass
                    break
                
                # Check if event loop is still running before async operations
                try:
                    asyncio.get_running_loop()
                    try:
                        fixed_solution = await self._fix_format(solution)
                    except Exception:
                        fixed_solution = solution
                except RuntimeError:
                    # No event loop (shutdown), use sync fallback
                    fixed_solution = self._fix_format_sync(solution)
            
            # Ensure problem is a string before calling split
            # Double-check that problem is a string (it should have been converted at the start of the function)
            if not isinstance(problem, str):
                self.logger.warning(f"Problem is not a string before split check: {type(problem)} - {problem}")
                if isinstance(problem, dict):
                    problem = str(problem.get('problem', problem.get('text', str(problem))))
                else:
                    problem = str(problem)
            
            # Now safely check and split
            if isinstance(problem, str) and "Factors of" in problem:
                try:
                    fixed_solution += ", " + problem.split(' ')[-1]
                except AttributeError as e:
                    self.logger.error(f"Error splitting problem string: {e}, problem type: {type(problem)}, value: {problem}")
                    # Skip adding the factor part if split fails
            
            wrong.append(fixed_solution)
        return wrong
    
    async def _run_game(self, channel: discord.TextChannel, xp_multiplier: float = 1.0, test_mode: bool = False) -> Optional[discord.Message]:
        try:
            game_length = self.chat_config.get('GAME_LENGTH') or self.chat_config.get('game_duration', 600)
            current_unix = int(datetime.now(timezone.utc).timestamp())
            end_time = current_unix + game_length
            
            game_id = await self._create_game_entry('Math Quiz', False, test_mode=test_mode, end_time=end_time)
            
            guild = self.bot.get_guild(self.config.get('config', 'GUILD_ID'))
            if not guild:
                self.logger.error("Error fetching guild")
                return None
            
            role = guild.get_role(self.config.get('config', 'GAMES_ROLE'))
            if not role:
                self.logger.error("Games role not found")
                return None
            
            # Support both old (QUESTIONS) and new (problem_types) structure
            questions = self.game_config.get('QUESTIONS', []) or self.game_config.get('problem_types', [])
            if not questions:
                self.logger.error("No math questions found")
                return None
            
            # Handle case where questions might be a dict
            if isinstance(questions, dict):
                questions = list(questions.values()) if questions else []
            
            if not questions:
                self.logger.error("No math questions found after processing")
                return None
            
            question = random.choice(questions)
            
            # Ensure question has 'ID' or 'id' key and it's valid
            if not isinstance(question, dict):
                self.logger.error(f"Invalid question format: {question}")
                return None
            
            # Support both 'ID' (old) and 'id' (new) keys
            question_id = question.get('ID') or question.get('id')
            if question_id is None:
                self.logger.error(f"Invalid question format - missing ID/id: {question}")
                return None
            
            if not isinstance(question_id, int):
                self.logger.error(f"Invalid question ID: {question_id}")
                return None
            
            try:
                result = mathgenerator.genById(question_id)
                # Handle case where genById might return different structures
                if isinstance(result, tuple) and len(result) >= 2:
                    problem, solution = result[0], result[1]
                elif isinstance(result, dict):
                    problem = result.get('problem', result.get('text', ''))
                    solution = result.get('solution', result.get('answer', ''))
                else:
                    self.logger.error(f"Unexpected result from mathgenerator.genById: {type(result)}")
                    return None
                
                # Ensure problem and solution are strings
                if not isinstance(problem, str):
                    problem = str(problem)
                if not isinstance(solution, str):
                    solution = str(solution)
            except Exception as e:
                self.logger.error(f"Error generating math problem: {e}")
                return None
            
            try:
                problem = await self._fix_format(problem)
                solution = await self._fix_format(solution)
                # Double-check that problem is still a string after formatting
                if not isinstance(problem, str):
                    self.logger.warning(f"Problem is not a string after formatting: {type(problem)}")
                    if isinstance(problem, dict):
                        problem = str(problem.get('problem', problem.get('text', str(problem))))
                    else:
                        problem = str(problem)
                if not isinstance(solution, str):
                    solution = str(solution)
            except Exception as e:
                self.logger.error(f"Math Quiz format error: {e}")
                return None
            
            # Final check before passing to _get_wrong_answers
            if not isinstance(problem, str):
                self.logger.error(f"Problem is not a string before passing to _get_wrong_answers: {type(problem)}")
                problem = str(problem) if not isinstance(problem, dict) else str(problem.get('problem', problem.get('text', str(problem))))
            
            # Use the question_id we already extracted
            wrong_answers = await self._get_wrong_answers(question_id, solution, problem)
            answers = [solution] + wrong_answers
            random.shuffle(answers)
            
            # Log the answer
            question_name = question.get('name') or question.get('NAME') or f'Math Problem #{question_id}'
            self.logger.info(f"Math Quiz '{question_name}' | Answer: '{solution}' #{channel.name}")
            
            current_unix = int(datetime.now(timezone.utc).timestamp())
            # Use custom XP multiplier if provided, otherwise random 15% chance for 2x
            if xp_multiplier > 1.0:
                xp_mult = xp_multiplier
            else:
                double_xp = random.random() <= 0.15
                xp_mult = 2.0 if double_xp else 1.0
            
            game_length = self.chat_config.get('GAME_LENGTH') or self.chat_config.get('game_duration', 600)
            
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
                title=f"Math Quiz{test_label}{xp_title}",
                description=f"This game will end <t:{end_time}:R>",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
                timestamp=datetime.now(timezone.utc)
            )
            
            # Get question type name (support both 'name' and 'NAME' keys)
            question_type = question.get('name') or question.get('NAME') or 'Math Problem'
            embed.add_field(name=f"{question_type}", value=problem, inline=False)
            
            view = MathQuizButtons(solution, answers, xp_mult, game_id, self.bot, self.config, self.chat_config, test_mode=test_mode)
            
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
                'correct_answer': solution,
                'problem': problem,
                'question': question,
                'answers': answers,
                'embed': {
                    'title': embed.title,
                    'description': embed.description,
                    'fields': [{'name': f.name, 'value': f.value, 'inline': f.inline} for f in embed.fields]
                }
            }
            registry.register_game(
                message.id,
                'math_quiz',
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
            self.logger.error(f"Math Quiz error: {e}")
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
                self.logger.error(f"Error ending math quiz game {game_id}: {e}")
        except asyncio.CancelledError:
            # Timer was cancelled (e.g., game ended manually)
            pass
        except Exception as e:
            self.logger.error(f"Error in math quiz timer: {e}")


class MathQuizButtons(discord.ui.View):
    def __init__(self, correct_answer: str, answers: List[str], xp_multiplier: float, game_id: int, bot, config, chat_config, test_mode: bool = False):
        super().__init__(timeout=None)
        self.correct_answer = correct_answer
        self.answers = answers
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
        self.failed_users: set = set()  # Track users who have answered incorrectly
        
        for idx, answer in enumerate(answers):
            button = discord.ui.Button(
                label=answer[:80],
                style=discord.ButtonStyle.grey,
                custom_id=f"math_{game_id}_{idx}"
            )
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
                    source="Math Quiz",
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

