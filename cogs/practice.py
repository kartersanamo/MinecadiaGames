from discord.ext import commands
from discord import app_commands
import discord
from core.config.manager import ConfigManager
from core.logging.setup import get_logger
from typing import Optional, Dict, List
import random
import os
import asyncio
from datetime import datetime, timezone


class Practice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Commands")
        self.GAMES_CHANNEL_ID = 1456658225964388504  # #games channel
        self.active_practice_sessions: Dict[int, Dict] = {}  # user_id -> session data
    
    @app_commands.command(name="practice", description="Practice games in test mode (only in #games)")
    @app_commands.describe(
        game_type="The type of game to practice"
    )
    @app_commands.choices(game_type=[
        app_commands.Choice(name="Trivia", value="trivia"),
        app_commands.Choice(name="Math Quiz", value="math_quiz"),
        app_commands.Choice(name="Flag Guesser", value="flag_guesser"),
        app_commands.Choice(name="Unscramble", value="unscramble"),
        app_commands.Choice(name="Emoji Quiz", value="emoji_quiz"),
        app_commands.Choice(name="Guess The Number", value="guess_the_number"),
        app_commands.Choice(name="Wordle", value="wordle"),
        app_commands.Choice(name="TicTacToe", value="tictactoe"),
        app_commands.Choice(name="Connect Four", value="connect four"),
        app_commands.Choice(name="Memory", value="memory"),
        app_commands.Choice(name="2048", value="2048"),
        app_commands.Choice(name="Minesweeper", value="minesweeper"),
        app_commands.Choice(name="Hangman", value="hangman"),
    ])
    async def practice(
        self,
        interaction: discord.Interaction,
        game_type: app_commands.Choice[str]
    ):
        # Check if in #games channel
        if interaction.channel.id != self.GAMES_CHANNEL_ID:
            await interaction.response.send_message(
                f"`❌` This command can only be used in <#{self.GAMES_CHANNEL_ID}>.",
                ephemeral=True
            )
            return
        
        # If user already has an active practice session, auto-end it so they can start a new one
        ended_previous_session = False
        if interaction.user.id in self.active_practice_sessions:
            try:
                await self.end_practice_session(interaction.user.id)
                ended_previous_session = True
            except Exception:
                # Never block starting a new practice session due to cleanup issues
                try:
                    del self.active_practice_sessions[interaction.user.id]
                except Exception:
                    pass
                ended_previous_session = True
        
        # Defer response so we can send a public message
        await interaction.response.defer(ephemeral=False)
        
        game_value = game_type.value
        
        # Map game values to display names
        game_name_map = {
            "trivia": "Trivia",
            "math_quiz": "Math Quiz",
            "flag_guesser": "Flag Guesser",
            "unscramble": "Unscramble",
            "emoji_quiz": "Emoji Quiz",
            "guess_the_number": "Guess The Number",
            "wordle": "Wordle",
            "tictactoe": "TicTacToe",
            "connect four": "Connect Four",
            "memory": "Memory",
            "2048": "2048",
            "minesweeper": "Minesweeper",
            "hangman": "Hangman",
        }
        
        game_display_name = game_name_map.get(game_value, game_value)
        
        # Send public message
        await interaction.followup.send(
            f"`✅` {interaction.user.mention} has started a practice {game_display_name} session",
            ephemeral=False
        )

        if ended_previous_session:
            await interaction.followup.send(
                "`ℹ️` Your previous practice session was automatically ended so you could start a new one.",
                ephemeral=True
            )
        
        # Determine if it's a chat game or DM game
        chat_games = ["trivia", "math_quiz", "flag_guesser", "unscramble", "emoji_quiz", "guess_the_number"]
        dm_games = ["wordle", "tictactoe", "connect four", "memory", "2048", "twenty forty eight", "minesweeper", "hangman"]
        
        if game_value in chat_games:
            await self.start_chat_practice(interaction, game_value)
        elif game_value in dm_games:
            await self.start_dm_practice(interaction, game_value)
        else:
            await interaction.followup.send("`❌` Unknown game type.", ephemeral=True)
    
    async def start_chat_practice(self, interaction: discord.Interaction, game_type: str):
        """Start a chat game practice session in DMs"""
        try:
            # Try to create DM channel
            try:
                dm_channel = await interaction.user.create_dm()
            except discord.Forbidden as e:
                if e.code == 50007:
                    await interaction.followup.send(
                        "`❌` I cannot send you DMs! Please enable DMs from server members in your Discord privacy settings to use practice mode.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "`❌` I cannot send you a DM! Please enable DMs to practice.",
                        ephemeral=True
                    )
                return
            
            # Initialize practice session
            session_data = {
                'game_type': game_type,
                'games_played': 0,
                'games_won': 0,
                'total_xp_would_have': 0,
                'start_time': datetime.now(timezone.utc),
                'dm_channel': dm_channel
            }
            self.active_practice_sessions[interaction.user.id] = session_data
            
            # Send first game
            try:
                await self._send_chat_practice_game(interaction.user, game_type, session_data)
            except discord.Forbidden as e:
                if e.code == 50007:
                    await self._handle_dm_error(e, interaction.user, interaction)
                    # Clean up session
                    if interaction.user.id in self.active_practice_sessions:
                        try:
                            del self.active_practice_sessions[interaction.user.id]
                        except:
                            pass
                    return
                raise
            
            # Note: Public message already sent in the main command handler
        except discord.Forbidden as e:
            if e.code == 50007:
                await self._handle_dm_error(e, interaction.user, interaction)
                # Clean up session
                if interaction.user.id in self.active_practice_sessions:
                    try:
                        del self.active_practice_sessions[interaction.user.id]
                    except:
                        pass
            else:
                self.logger.error(f"Error starting chat practice: {e}", exc_info=True)
                await interaction.followup.send(
                    f"`❌` Error starting practice session: {str(e)}",
                    ephemeral=True
                )
        except Exception as e:
            self.logger.error(f"Error starting chat practice: {e}", exc_info=True)
            await interaction.followup.send(
                f"`❌` Error starting practice session: {str(e)}",
                ephemeral=True
            )
    
    async def start_dm_practice(self, interaction: discord.Interaction, game_type: str):
        """Start a DM game practice session"""
        try:
            # Import DM game classes
            from games.dm.wordle import Wordle
            from games.dm.tictactoe import TicTacToe
            from games.dm.connect_four import ConnectFour
            from games.dm.memory import Memory
            from games.dm.twenty_forty_eight import TwentyFortyEight
            from games.dm.minesweeper import Minesweeper
            from games.dm.hangman import Hangman
            
            game_map = {
                "wordle": Wordle,
                "tictactoe": TicTacToe,
                "connect four": ConnectFour,
                "memory": Memory,
                "2048": TwentyFortyEight,
                "twenty forty eight": TwentyFortyEight,
                "minesweeper": Minesweeper,
                "hangman": Hangman
            }
            
            game_class = game_map.get(game_type.lower())
            if not game_class:
                await interaction.followup.send(f"`❌` Unknown DM game: {game_type}", ephemeral=True)
                return
            
            # Use the game manager's instance instead of creating a new one
            # This ensures the game's active_games dict is shared with the listener
            # Map lowercase game_type to the dm_games key (capitalized display name)
            dm_game_key_map = {
                "wordle": "Wordle",
                "tic tac toe": "TicTacToe",
                "tictactoe": "TicTacToe",
                "connect four": "Connect Four",
                "memory": "Memory",
                "twenty forty eight": "2048",
                "2048": "2048",
                "minesweeper": "Minesweeper",
                "hangman": "Hangman"
            }
            
            if self.bot.game_manager and hasattr(self.bot.game_manager, 'dm_games'):
                dm_game_key = dm_game_key_map.get(game_type.lower())
                game = self.bot.game_manager.dm_games.get(dm_game_key) if dm_game_key else None
                self.logger.info(f"Using game_manager instance for {game_type} (key={dm_game_key}): {id(game)}")
                if not game:
                    # Fallback: create new instance if not found
                    self.logger.warning(f"Game not found in game_manager, creating new instance")
                    game = game_class(self.bot)
            else:
                # Fallback: create new instance if game_manager not available
                self.logger.warning(f"game_manager not available, creating new instance")
                game = game_class(self.bot)
            
            success = await game.run(interaction.user, game_type, test_mode=True)
            
            if not success:
                await interaction.followup.send(
                    "`❌` Failed to send practice game. Check logs for details.",
                    ephemeral=True
                )
            # Note: Public message already sent in the main command handler
        except Exception as e:
            self.logger.error(f"Error starting DM practice: {e}", exc_info=True)
            await interaction.followup.send(
                f"`❌` Error starting practice session: {str(e)}",
                ephemeral=True
            )
    
    async def _send_chat_practice_game(self, user: discord.User, game_type: str, session_data: Dict):
        """Send a chat game to user's DMs for practice"""
        try:
            # Import chat game classes
            from games.chat.unscramble import Unscramble
            from games.chat.flag_guesser import FlagGuesser
            from games.chat.math_quiz import MathQuiz
            from games.chat.trivia import Trivia
            from games.chat.emoji_quiz import EmojiQuiz
            from games.chat.guess_the_number import GuessTheNumber
            
            game_map = {
                "unscramble": Unscramble,
                "flag_guesser": FlagGuesser,
                "math_quiz": MathQuiz,
                "trivia": Trivia,
                "emoji_quiz": EmojiQuiz,
                "guess_the_number": GuessTheNumber
            }
            
            game_class = game_map.get(game_type.lower())
            if not game_class:
                return
            
            # Create game instance
            game = game_class(self.bot)
            
            # Create a fake DM channel object for the game
            # We'll need to modify chat games to work in DMs
            dm_channel = session_data['dm_channel']
            
            # Run game in test mode in DMs
            await self._run_chat_game_in_dm(game, game_type, dm_channel, session_data)
            
        except Exception as e:
            self.logger.error(f"Error sending chat practice game: {e}", exc_info=True)
            try:
                await session_data['dm_channel'].send(
                    f"`❌` Error loading practice game: {str(e)}"
                )
            except discord.Forbidden as dm_error:
                if dm_error.code == 50007:
                    user_id = None
                    for uid, sess in self.active_practice_sessions.items():
                        if sess == session_data:
                            user_id = uid
                            break
                    if user_id:
                        user = self.bot.get_user(user_id)
                        if user:
                            await self._handle_dm_error(dm_error, user)
                            try:
                                del self.active_practice_sessions[user_id]
                            except:
                                pass
                raise
    
    async def _handle_dm_error(self, error: Exception, user: discord.User, interaction: Optional[discord.Interaction] = None):
        """Handle DM-related errors and send appropriate error messages"""
        if isinstance(error, discord.Forbidden) and error.code == 50007:
            error_msg = "`❌` I cannot send you DMs! Please enable DMs from server members in your Discord privacy settings to use practice mode."
            if interaction:
                try:
                    await interaction.followup.send(error_msg, ephemeral=True)
                except:
                    pass
            # Try to send in the games channel as fallback
            try:
                games_channel = self.bot.get_channel(self.GAMES_CHANNEL_ID)
                if games_channel:
                    await games_channel.send(f"{user.mention} {error_msg}", delete_after=30)
            except:
                pass
            return True
        return False
    
    async def _safe_dm_send(self, dm_channel: discord.DMChannel, content: str = None, embed: discord.Embed = None, file: discord.File = None, view: discord.ui.View = None):
        """Safely send a message to a DM channel, handling Forbidden errors"""
        try:
            return await dm_channel.send(content=content, embed=embed, file=file, view=view)
        except discord.Forbidden as e:
            if e.code == 50007:
                user = dm_channel.recipient if hasattr(dm_channel, 'recipient') else None
                if user:
                    await self._handle_dm_error(e, user)
                    # Clean up session
                    if user.id in self.active_practice_sessions:
                        try:
                            del self.active_practice_sessions[user.id]
                        except:
                            pass
            raise
    
    async def _run_chat_game_in_dm(self, game, game_type: str, dm_channel: discord.DMChannel, session_data: Dict):
        """Run a chat game in DMs with practice controls"""
        try:
            if game_type == "trivia":
                await self._run_trivia_practice(dm_channel, session_data)
            elif game_type == "math_quiz":
                await self._run_math_quiz_practice(dm_channel, session_data)
            elif game_type == "flag_guesser":
                await self._run_flag_guesser_practice(dm_channel, session_data)
            elif game_type == "unscramble":
                await self._run_unscramble_practice(dm_channel, session_data)
            elif game_type == "emoji_quiz":
                await self._run_emoji_quiz_practice(dm_channel, session_data)
            elif game_type == "guess_the_number":
                await self._run_guess_the_number_practice(dm_channel, session_data)
        except discord.Forbidden as e:
            if e.code == 50007:
                user = dm_channel.recipient if hasattr(dm_channel, 'recipient') else None
                if user:
                    await self._handle_dm_error(e, user)
                # Clean up session
                if user and user.id in self.active_practice_sessions:
                    try:
                        del self.active_practice_sessions[user.id]
                    except:
                        pass
            else:
                self.logger.error(f"Error running chat game practice: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Error running chat game practice: {e}", exc_info=True)
    
    async def _run_trivia_practice(self, dm_channel: discord.DMChannel, session_data: Dict):
        """Run a trivia practice game in DMs"""
        from games.chat.trivia import Trivia
        import random
        from datetime import datetime, timezone
        
        game = Trivia(self.bot)
        game_type = session_data['game_type']
        user = dm_channel.recipient
        
        # Get a random trivia question
        questions_dict = game.game_config.get('QUESTIONS', {}) or game.game_config.get('questions', {})
        all_questions = []
        for channel_id, questions_list in questions_dict.items():
            if isinstance(questions_list, list):
                all_questions.extend(questions_list)
        
        if not all_questions:
            await self._safe_dm_send(dm_channel, "`❌` No trivia questions found.")
            return
        
        trivia = random.choice(all_questions)
        game_id = -999999  # Fake game_id for practice
        
        # Create practice view with Next and End Practice buttons
        view = PracticeTriviaView(
            trivia, 
            game_id, 
            self.bot, 
            self.config, 
            game.chat_config, 
            user.id,
            session_data,
            self
        )
        
        embed = discord.Embed(
            title="🧪 Practice Trivia Question",
            description="Click an answer below!",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Question", value=trivia["question"], inline=False)
        
        answers = trivia['answers'][:4]
        items = []
        for index, button in enumerate(view.children[:-2]):  # Exclude Next and End Practice buttons
            if index < len(answers):
                button.label = answers[index]
                items.append(button)
        
        # Remove answer buttons temporarily
        for item in items:
            view.remove_item(item)
        
        # Shuffle and re-add
        random.shuffle(items)
        for item in items:
            view.add_item(item)
        
        try:
            message = await dm_channel.send(embed=embed, view=view)
            view.message = message
            session_data['current_message'] = message
            
            # Register view as persistent
            self.bot.add_view(view)
        except discord.Forbidden as e:
            if e.code == 50007:
                user = dm_channel.recipient
                await self._handle_dm_error(e, user)
                # Clean up session
                if user.id in self.active_practice_sessions:
                    try:
                        del self.active_practice_sessions[user.id]
                    except:
                        pass
            raise
    
    async def _run_math_quiz_practice(self, dm_channel: discord.DMChannel, session_data: Dict):
        """Run a math quiz practice game in DMs"""
        from games.chat.math_quiz import MathQuiz
        import random
        from datetime import datetime, timezone
        
        game = MathQuiz(self.bot)
        game_type = session_data['game_type']
        user = dm_channel.recipient
        
        # Get a random math problem
        questions_dict = game.game_config.get('QUESTIONS', {}) or game.game_config.get('questions', {})
        if isinstance(questions_dict, list):
            questions_list = questions_dict
        else:
            questions_list = []
            for key, value in questions_dict.items():
                if isinstance(value, list):
                    questions_list.extend(value)
                elif isinstance(value, dict):
                    questions_list.append(value)
        
        if not questions_list:
            await self._safe_dm_send(dm_channel, "`❌` No math problems found.")
            return
        
        question_data = random.choice(questions_list)
        
        # Extract question ID
        question_id = question_data.get('ID') or question_data.get('id')
        if not question_id:
            await self._safe_dm_send(dm_channel, "`❌` Invalid math problem format.")
            return
        
        # Generate problem and solution
        try:
            import mathgenerator
            result = mathgenerator.genById(question_id)
            if isinstance(result, tuple) and len(result) >= 2:
                problem, solution = result[0], result[1]
            elif isinstance(result, dict):
                problem = result.get('problem', result.get('text', ''))
                solution = result.get('solution', result.get('answer', ''))
            else:
                await self._safe_dm_send(dm_channel, "`❌` Error generating math problem.")
                return
            
            # Format problem and solution
            problem = await game._fix_format(problem)
            solution = await game._fix_format(solution)
            
            # Get wrong answers
            wrong_answers = await game._get_wrong_answers(question_id, solution, problem)
            answers = [solution] + wrong_answers[:3]
            random.shuffle(answers)
        except Exception as e:
            self.logger.error(f"Error generating math problem: {e}")
            await dm_channel.send("`❌` Error generating math problem.")
            return
        
        game_id = -999999  # Fake game_id for practice
        
        # Create practice view
        view = PracticeMathQuizView(
            problem,
            solution,
            answers,
            game_id,
            self.bot,
            self.config,
            game.chat_config,
            user.id,
            session_data,
            self
        )
        
        embed = discord.Embed(
            title="🧪 Practice Math Quiz",
            description="Click an answer below!",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Problem", value=problem, inline=False)
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        
        # Set button labels
        items = []
        for index, button in enumerate(view.children[:-2]):  # Exclude Next and End Practice buttons
            if index < len(answers):
                button.label = answers[index]
                items.append(button)
        
        # Remove answer buttons temporarily
        for item in items:
            view.remove_item(item)
        
        # Shuffle and re-add
        random.shuffle(items)
        for item in items:
            view.add_item(item)
        
        try:
            message = await dm_channel.send(embed=embed, view=view)
            view.message = message
            session_data['current_message'] = message
            
            # Register view as persistent
            self.bot.add_view(view)
        except discord.Forbidden as e:
            if e.code == 50007:
                user = dm_channel.recipient
                await self._handle_dm_error(e, user)
                # Clean up session
                if user.id in self.active_practice_sessions:
                    try:
                        del self.active_practice_sessions[user.id]
                    except:
                        pass
            raise
    
    async def _run_flag_guesser_practice(self, dm_channel: discord.DMChannel, session_data: Dict):
        """Run a flag guesser practice game in DMs"""
        from games.chat.flag_guesser import FlagGuesser
        import random
        from datetime import datetime, timezone
        
        game = FlagGuesser(self.bot)
        game_type = session_data['game_type']
        user = dm_channel.recipient
        
        # Select country and answers
        country_code, correct_answer, answers = await game._select_country_and_answers()
        game_id = -999999  # Fake game_id for practice
        
        # Build embed with flag image
        current_unix = int(datetime.now(timezone.utc).timestamp())
        embed, file = await game._build_embed(country_code, 1.0, current_unix, test_mode=True)
        embed.title = "🧪 Practice Flag Guesser"
        embed.description = "Click an answer below!"
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        
        # Create practice view
        view = PracticeFlagGuesserView(
            correct_answer,
            answers,
            game_id,
            self.bot,
            self.config,
            game.chat_config,
            user.id,
            session_data,
            self
        )
        
        # Set button labels
        items = []
        for index, button in enumerate(view.children[:-2]):  # Exclude Next and End Practice buttons
            if index < len(answers):
                button.label = answers[index]
                items.append(button)
        
        # Remove answer buttons temporarily
        for item in items:
            view.remove_item(item)
        
        # Shuffle and re-add
        random.shuffle(items)
        for item in items:
            view.add_item(item)
        
        try:
            message = await dm_channel.send(embed=embed, file=file, view=view)
            view.message = message
            session_data['current_message'] = message
        except discord.Forbidden as e:
            if e.code == 50007:
                user = dm_channel.recipient
                await self._handle_dm_error(e, user)
                # Clean up session
                if user.id in self.active_practice_sessions:
                    try:
                        del self.active_practice_sessions[user.id]
                    except:
                        pass
            raise
        
        # Clean up file
        try:
            os.remove(file.filename)
        except:
            pass
        
        # Register view as persistent
        self.bot.add_view(view)
    
    async def _run_unscramble_practice(self, dm_channel: discord.DMChannel, session_data: Dict):
        """Run an unscramble practice game in DMs"""
        from games.chat.unscramble import Unscramble
        import random
        from datetime import datetime, timezone
        
        game = Unscramble(self.bot)
        game_type = session_data['game_type']
        user = dm_channel.recipient
        
        # Get a random word
        words_dict = game.game_config.get('WORDS', {}) or game.game_config.get('words', {})
        all_words = []
        for channel_id, words_list in words_dict.items():
            if isinstance(words_list, list):
                all_words.extend(words_list)
            elif isinstance(words_list, dict):
                all_words.extend(list(words_list.values()))
        
        if not all_words:
            await self._safe_dm_send(dm_channel, "`❌` No words found for unscramble.")
            return
        
        word = random.choice(all_words)
        if not isinstance(word, str):
            await self._safe_dm_send(dm_channel, "`❌` Invalid word format.")
            return
        
        scrambled = " ".join("".join(random.sample(w, len(w))) for w in word.split())
        
        # Get image
        image_path = await game._get_image(scrambled)
        game_id = -999999  # Fake game_id for practice
        
        # Create practice view
        view = PracticeUnscrambleView(
            word,
            game_id,
            self.bot,
            self.config,
            game.chat_config,
            user.id,
            session_data,
            self
        )
        
        embed = discord.Embed(
            title="🧪 Practice Unscramble",
            description="Type the unscrambled word below!",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.now(timezone.utc)
        )
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        
        file = discord.File(image_path, filename="unscramble.png")
        embed.set_image(url="attachment://unscramble.png")
        
        try:
            message = await dm_channel.send(embed=embed, file=file, view=view)
            view.message = message
            session_data['current_message'] = message
        except discord.Forbidden as e:
            if e.code == 50007:
                user = dm_channel.recipient
                await self._handle_dm_error(e, user)
                # Clean up session
                if user.id in self.active_practice_sessions:
                    try:
                        del self.active_practice_sessions[user.id]
                    except:
                        pass
            raise
        
        # Clean up file
        try:
            os.remove(image_path)
        except:
            pass
        
        # Register view and message listener
        self.bot.add_view(view)
        
        # Set up message listener
        def check(msg: discord.Message):
            return (
                msg.channel == dm_channel and
                msg.author.id == user.id and
                not msg.author.bot and
                view.game_active
            )
        
        try:
            # Wait for answer with timeout
            answer_msg = await self.bot.wait_for('message', check=check, timeout=300.0)
            await view.handle_message(answer_msg)
        except asyncio.TimeoutError:
            # Timeout - disable buttons
            view.game_active = False
            for item in view.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            await message.edit(view=view)
    
    async def _run_emoji_quiz_practice(self, dm_channel: discord.DMChannel, session_data: Dict):
        """Run an emoji quiz practice game in DMs"""
        from games.chat.emoji_quiz import EmojiQuiz
        import random
        from datetime import datetime, timezone
        
        game = EmojiQuiz(self.bot)
        game_type = session_data['game_type']
        user = dm_channel.recipient
        
        # Get a random emoji quiz question
        questions = game.game_config.get('QUESTIONS', []) or game.game_config.get('questions', [])
        
        if not questions:
            await self._safe_dm_send(dm_channel, "`❌` No emoji quiz questions found.")
            return
        
        question_data = random.choice(questions)
        category = question_data.get('category', 'General')
        emojis = question_data.get('emojis', '')
        correct_answer = question_data.get('answer', '').strip()
        
        game_id = -999999  # Fake game_id for practice
        
        # Create practice view
        view = PracticeEmojiQuizView(
            correct_answer,
            game_id,
            self.bot,
            self.config,
            game.chat_config,
            user.id,
            session_data,
            self
        )
        
        embed = discord.Embed(
            title=f"🧪 Practice Emoji Quiz - {category}",
            description="Type your answer below!",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="What do these emojis represent?", value=emojis, inline=False)
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        
        message = await dm_channel.send(embed=embed, view=view)
        view.message = message
        session_data['current_message'] = message
        
        # Register view and message listener
        self.bot.add_view(view)
        
        # Set up message listener - keep listening until answer is correct or timeout
        def check(msg: discord.Message):
            return (
                msg.channel == dm_channel and
                msg.author.id == user.id and
                not msg.author.bot and
                view.game_active and
                not view.answered
            )
        
        try:
            # Keep waiting for messages until answer is correct or timeout
            while view.game_active and not view.answered:
                answer_msg = await self.bot.wait_for('message', check=check, timeout=300.0)
                await view.handle_message(answer_msg)
        except asyncio.TimeoutError:
            # Timeout - disable buttons
            view.game_active = False
            for item in view.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            await message.edit(view=view)
    
    async def _run_guess_the_number_practice(self, dm_channel: discord.DMChannel, session_data: Dict):
        """Run a Guess The Number practice game in DMs"""
        from games.chat.guess_the_number import GuessTheNumber
        import random
        from datetime import datetime, timezone
        
        game = GuessTheNumber(self.bot)
        user = dm_channel.recipient
        
        # Generate random number between 1 and 100
        secret_number = random.randint(1, 100)
        min_range = 1
        max_range = 100
        
        game_id = -999999  # Fake game_id for practice
        
        # Create practice view (reuse the actual game view in test mode)
        from games.chat.guess_the_number import GuessTheNumberButtons
        view = GuessTheNumberButtons(
            secret_number,
            min_range,
            max_range,
            1.0,  # No XP multiplier for practice
            game_id,
            self.bot,
            self.config,
            game.chat_config,
            test_mode=True,
            practice_cog=self,
            practice_user_id=user.id,
            practice_session_data=session_data,
            practice_auto_end=True
        )
        
        embed = discord.Embed(
            title="🧪 Practice Guess The Number",
            description="Click the 'Guess' button to enter your guess! The bot will tell you if the number is higher or lower.",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(
            name="Range",
            value=f"**{min_range} - {max_range}**",
            inline=False
        )
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        
        message = await dm_channel.send(embed=embed, view=view)
        view.message = message
        session_data['current_message'] = message
        
        # Register view
        self.bot.add_view(view)
        # Stats + cleanup are handled by the view itself when the game ends
    
    async def end_practice_session(self, user_id: int):
        """End a practice session and show summary"""
        if user_id not in self.active_practice_sessions:
            return
        try:
            session = self.active_practice_sessions[user_id]
            dm_channel = session.get('dm_channel')
            
            # Calculate session stats
            start_time = session.get('start_time', datetime.now(timezone.utc))
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            
            games_played = int(session.get('games_played', 0) or 0)
            games_won = int(session.get('games_won', 0) or 0)
            total_xp = int(session.get('total_xp_would_have', 0) or 0)
            win_rate = (games_won / games_played * 100) if games_played > 0 else 0
            
            embed = discord.Embed(
                title="🧪 Practice Session Summary",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
                description=(
                    f"**Game Type:** {str(session.get('game_type', 'Unknown')).replace('_', ' ').title()}\n"
                    f"**Duration:** {minutes}m {seconds}s\n"
                    f"**Games Played:** {games_played}\n"
                    f"**Games Won:** {games_won}\n"
                    f"**Win Rate:** {win_rate:.1f}%\n"
                    f"**Total XP Would Have Earned:** {total_xp}"
                )
            )
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            if dm_channel:
                try:
                    await dm_channel.send(embed=embed)
                except discord.Forbidden as e:
                    if e.code == 50007:
                        # User has DMs disabled, silently fail (session is ending anyway)
                        pass
                except Exception:
                    pass
        finally:
            # Always remove session (even if sending summary fails)
            try:
                del self.active_practice_sessions[user_id]
            except Exception:
                pass


class PracticeTriviaView(discord.ui.View):
    def __init__(self, trivia: dict, game_id: int, bot, config, chat_config, user_id: int, session_data: Dict, practice_cog):
        super().__init__(timeout=None)
        self.correct_answer = trivia['answers'][0]
        self.all_answers = trivia['answers'][:4]
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.chat_config = chat_config
        self.test_mode = True
        self.user_id = user_id
        self.session_data = session_data
        self.practice_cog = practice_cog
        self.winners: List[dict] = []
        self.message: Optional[discord.Message] = None
        self.winner_count = 0
        self.answered = False
        
        # Create answer buttons
        for i in range(4):
            answer = self.all_answers[i] if i < len(self.all_answers) else f"Answer {i+1}"
            button = discord.ui.Button(
                label=answer,
                style=discord.ButtonStyle.grey,
                custom_id=f"practice_trivia_{i}_{game_id}"
            )
            button.callback = self.create_callback(answer)
            self.add_item(button)
        
        # Add Next and End Practice buttons
        next_button = discord.ui.Button(
            label="Next Question",
            style=discord.ButtonStyle.blurple,
            emoji="➡️",
            custom_id=f"practice_next_{game_id}",
            row=2
        )
        next_button.callback = self.next_callback
        self.add_item(next_button)
        
        end_button = discord.ui.Button(
            label="End Practice",
            style=discord.ButtonStyle.red,
            emoji="🛑",
            custom_id=f"practice_end_{game_id}",
            row=2
        )
        end_button.callback = self.end_callback
        self.add_item(end_button)
    
    def create_callback(self, answer: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("This is not your practice session!", ephemeral=True)
                return
            
            if self.answered:
                await interaction.response.send_message("You've already answered this question!", ephemeral=True)
                return
            
            self.answered = True
            self.session_data['games_played'] += 1
            
            if answer == self.correct_answer:
                self.winner_count += 1
                self.session_data['games_won'] += 1
                
                # Calculate XP (1st place XP for practice)
                import random
                xp = random.randint(50, 60)
                self.session_data['total_xp_would_have'] += xp
                
                self.winners.append({
                    'user': interaction.user.mention,
                    'user_id': interaction.user.id,
                    'xp': xp
                })
                
                # Update embed
                embed = self.message.embeds[0]
                embed.add_field(name="Result", value=f"`✅` Correct! You would have earned `{xp}xp`!", inline=False)
                
                # Disable all answer buttons
                for item in self.children:
                    if isinstance(item, discord.ui.Button) and item.custom_id.startswith("practice_trivia_"):
                        item.disabled = True
                        if item.label == self.correct_answer:
                            item.style = discord.ButtonStyle.green
                        else:
                            item.style = discord.ButtonStyle.grey
                
                await self.message.edit(embed=embed, view=self)
                await interaction.response.send_message(f"`✅` Correct! You would have earned `{xp}xp`!", ephemeral=True)
            else:
                # Update embed
                embed = self.message.embeds[0]
                embed.add_field(name="Result", value=f"`❌` Incorrect! The correct answer was: **{self.correct_answer}**", inline=False)
                
                # Disable all answer buttons
                for item in self.children:
                    if isinstance(item, discord.ui.Button) and item.custom_id.startswith("practice_trivia_"):
                        item.disabled = True
                        if item.label == self.correct_answer:
                            item.style = discord.ButtonStyle.green
                        elif item.label == answer:
                            item.style = discord.ButtonStyle.red
                        else:
                            item.style = discord.ButtonStyle.grey
                
                await self.message.edit(embed=embed, view=self)
                await interaction.response.send_message(f"`❌` Incorrect! The correct answer was: **{self.correct_answer}**", ephemeral=True)
        
        return callback
    
    async def next_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your practice session!", ephemeral=True)
            return
        
        if not self.answered:
            await interaction.response.send_message("Please answer the current question first!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Delete old message if it exists
        try:
            if self.message:
                await self.message.delete()
        except:
            pass
        
        # Send new question
        await self.practice_cog._send_chat_practice_game(
            interaction.user,
            self.session_data['game_type'],
            self.session_data
        )
    
    async def end_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your practice session!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Disable all buttons
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        await self.message.edit(view=self)
        
        # End practice session and show summary
        await self.practice_cog.end_practice_session(self.user_id)


class PracticeMathQuizView(discord.ui.View):
    """Practice view for Math Quiz - similar to PracticeTriviaView"""
    def __init__(self, problem: str, solution: str, answers: List[str], game_id: int, bot, config, chat_config, user_id: int, session_data: Dict, practice_cog):
        super().__init__(timeout=None)
        self.problem = problem
        self.correct_answer = solution
        self.all_answers = answers
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.chat_config = chat_config
        self.test_mode = True
        self.user_id = user_id
        self.session_data = session_data
        self.practice_cog = practice_cog
        self.message: Optional[discord.Message] = None
        self.answered = False
        
        # Create answer buttons (will be set by parent)
        for i in range(4):
            answer = self.all_answers[i] if i < len(self.all_answers) else f"Answer {i+1}"
            button = discord.ui.Button(
                label=answer[:80],
                style=discord.ButtonStyle.grey,
                custom_id=f"practice_math_{i}_{game_id}"
            )
            button.callback = self.create_callback(answer)
            self.add_item(button)
        
        # Add Next and End Practice buttons
        next_button = discord.ui.Button(label="Next Problem", style=discord.ButtonStyle.blurple, emoji="➡️", custom_id=f"practice_next_{game_id}", row=2)
        next_button.callback = self.next_callback
        self.add_item(next_button)
        
        end_button = discord.ui.Button(label="End Practice", style=discord.ButtonStyle.red, emoji="🛑", custom_id=f"practice_end_{game_id}", row=2)
        end_button.callback = self.end_callback
        self.add_item(end_button)
    
    def create_callback(self, answer: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("This is not your practice session!", ephemeral=True)
                return
            
            if self.answered:
                await interaction.response.send_message("You've already answered this problem!", ephemeral=True)
                return
            
            self.answered = True
            self.session_data['games_played'] += 1
            
            if answer == self.correct_answer:
                self.session_data['games_won'] += 1
                import random
                xp = random.randint(50, 60)
                self.session_data['total_xp_would_have'] += xp
                
                embed = self.message.embeds[0]
                embed.add_field(name="Result", value=f"`✅` Correct! You would have earned `{xp}xp`!", inline=False)
                
                for item in self.children:
                    if isinstance(item, discord.ui.Button) and item.custom_id.startswith("practice_math_"):
                        item.disabled = True
                        if item.label == self.correct_answer:
                            item.style = discord.ButtonStyle.green
                        else:
                            item.style = discord.ButtonStyle.grey
                
                await self.message.edit(embed=embed, view=self)
                await interaction.response.send_message(f"`✅` Correct! You would have earned `{xp}xp`!", ephemeral=True)
            else:
                embed = self.message.embeds[0]
                embed.add_field(name="Result", value=f"`❌` Incorrect! The correct answer was: **{self.correct_answer}**", inline=False)
                
                for item in self.children:
                    if isinstance(item, discord.ui.Button) and item.custom_id.startswith("practice_math_"):
                        item.disabled = True
                        if item.label == self.correct_answer:
                            item.style = discord.ButtonStyle.green
                        elif item.label == answer:
                            item.style = discord.ButtonStyle.red
                        else:
                            item.style = discord.ButtonStyle.grey
                
                await self.message.edit(embed=embed, view=self)
                await interaction.response.send_message(f"`❌` Incorrect! The correct answer was: **{self.correct_answer}**", ephemeral=True)
        
        return callback
    
    async def next_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your practice session!", ephemeral=True)
            return
        
        if not self.answered:
            await interaction.response.send_message("Please answer the current problem first!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            if self.message:
                await self.message.delete()
        except:
            pass
        
        await self.practice_cog._send_chat_practice_game(interaction.user, self.session_data['game_type'], self.session_data)
    
    async def end_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your practice session!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        await self.message.edit(view=self)
        await self.practice_cog.end_practice_session(self.user_id)


class PracticeFlagGuesserView(discord.ui.View):
    """Practice view for Flag Guesser - similar to PracticeTriviaView"""
    def __init__(self, correct_answer: str, answers: List[str], game_id: int, bot, config, chat_config, user_id: int, session_data: Dict, practice_cog):
        super().__init__(timeout=None)
        self.correct_answer = correct_answer
        self.all_answers = answers
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.chat_config = chat_config
        self.test_mode = True
        self.user_id = user_id
        self.session_data = session_data
        self.practice_cog = practice_cog
        self.message: Optional[discord.Message] = None
        self.answered = False
        
        # Create answer buttons (will be set by parent)
        for i in range(4):
            answer = self.all_answers[i] if i < len(self.all_answers) else f"Answer {i+1}"
            button = discord.ui.Button(
                label=answer,
                style=discord.ButtonStyle.grey,
                custom_id=f"practice_flag_{i}_{game_id}"
            )
            button.callback = self.create_callback(answer)
            self.add_item(button)
        
        # Add Next and End Practice buttons
        next_button = discord.ui.Button(label="Next Flag", style=discord.ButtonStyle.blurple, emoji="➡️", custom_id=f"practice_next_{game_id}", row=2)
        next_button.callback = self.next_callback
        self.add_item(next_button)
        
        end_button = discord.ui.Button(label="End Practice", style=discord.ButtonStyle.red, emoji="🛑", custom_id=f"practice_end_{game_id}", row=2)
        end_button.callback = self.end_callback
        self.add_item(end_button)
    
    def create_callback(self, answer: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("This is not your practice session!", ephemeral=True)
                return
            
            if self.answered:
                await interaction.response.send_message("You've already answered this flag!", ephemeral=True)
                return
            
            self.answered = True
            self.session_data['games_played'] += 1
            
            if answer == self.correct_answer:
                self.session_data['games_won'] += 1
                import random
                xp = random.randint(50, 60)
                self.session_data['total_xp_would_have'] += xp
                
                embed = self.message.embeds[0]
                embed.add_field(name="Result", value=f"`✅` Correct! You would have earned `{xp}xp`!", inline=False)
                
                for item in self.children:
                    if isinstance(item, discord.ui.Button) and item.custom_id.startswith("practice_flag_"):
                        item.disabled = True
                        if item.label == self.correct_answer:
                            item.style = discord.ButtonStyle.green
                        else:
                            item.style = discord.ButtonStyle.grey
                
                await self.message.edit(embed=embed, view=self)
                await interaction.response.send_message(f"`✅` Correct! You would have earned `{xp}xp`!", ephemeral=True)
            else:
                embed = self.message.embeds[0]
                embed.add_field(name="Result", value=f"`❌` Incorrect! The correct answer was: **{self.correct_answer}**", inline=False)
                
                for item in self.children:
                    if isinstance(item, discord.ui.Button) and item.custom_id.startswith("practice_flag_"):
                        item.disabled = True
                        if item.label == self.correct_answer:
                            item.style = discord.ButtonStyle.green
                        elif item.label == answer:
                            item.style = discord.ButtonStyle.red
                        else:
                            item.style = discord.ButtonStyle.grey
                
                await self.message.edit(embed=embed, view=self)
                await interaction.response.send_message(f"`❌` Incorrect! The correct answer was: **{self.correct_answer}**", ephemeral=True)
        
        return callback
    
    async def next_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your practice session!", ephemeral=True)
            return
        
        if not self.answered:
            await interaction.response.send_message("Please answer the current flag first!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            if self.message:
                await self.message.delete()
        except:
            pass
        
        await self.practice_cog._send_chat_practice_game(interaction.user, self.session_data['game_type'], self.session_data)
    
    async def end_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your practice session!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        await self.message.edit(view=self)
        await self.practice_cog.end_practice_session(self.user_id)


class PracticeUnscrambleView(discord.ui.View):
    """Practice view for Unscramble - message-based"""
    def __init__(self, correct_answer: str, game_id: int, bot, config, chat_config, user_id: int, session_data: Dict, practice_cog):
        super().__init__(timeout=None)
        self.correct_answer = correct_answer.lower().strip()
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.chat_config = chat_config
        self.test_mode = True
        self.user_id = user_id
        self.session_data = session_data
        self.practice_cog = practice_cog
        self.message: Optional[discord.Message] = None
        self.answered = False
        self.game_active = True
        
        # Add Next and End Practice buttons
        next_button = discord.ui.Button(label="Next Word", style=discord.ButtonStyle.blurple, emoji="➡️", custom_id=f"practice_next_{game_id}", row=0)
        next_button.callback = self.next_callback
        self.add_item(next_button)
        
        end_button = discord.ui.Button(label="End Practice", style=discord.ButtonStyle.red, emoji="🛑", custom_id=f"practice_end_{game_id}", row=0)
        end_button.callback = self.end_callback
        self.add_item(end_button)
    
    async def handle_message(self, msg: discord.Message):
        if self.answered or not self.game_active:
            return
        
        answer = msg.content.strip().lower()
        
        # Delete message if it contains the answer
        if self.correct_answer in answer:
            try:
                await msg.delete()
            except:
                pass
        
        # Check if exact match
        if answer == self.correct_answer:
            self.answered = True
            self.session_data['games_played'] += 1
            self.session_data['games_won'] += 1
            
            import random
            xp = random.randint(50, 60)
            self.session_data['total_xp_would_have'] += xp
            
            embed = self.message.embeds[0]
            embed.add_field(name="Result", value=f"`✅` Correct! You would have earned `{xp}xp`!", inline=False)
            
            # Don't disable buttons - user needs "Next Word" and "End Practice" to continue
            await self.message.edit(embed=embed, view=self)
            await msg.channel.send(f"`✅` {msg.author.mention} Correct! You would have earned `{xp}xp`!")
    
    async def next_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your practice session!", ephemeral=True)
            return
        
        if not self.answered:
            await interaction.response.send_message("Please answer the current word first!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            if self.message:
                await self.message.delete()
        except:
            pass
        
        await self.practice_cog._send_chat_practice_game(interaction.user, self.session_data['game_type'], self.session_data)
    
    async def end_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your practice session!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        self.game_active = False
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        await self.message.edit(view=self)
        await self.practice_cog.end_practice_session(self.user_id)


class PracticeEmojiQuizView(discord.ui.View):
    """Practice view for Emoji Quiz - message-based"""
    def __init__(self, correct_answer: str, game_id: int, bot, config, chat_config, user_id: int, session_data: Dict, practice_cog):
        super().__init__(timeout=None)
        self.correct_answer = correct_answer.lower().strip()
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.chat_config = chat_config
        self.test_mode = True
        self.user_id = user_id
        self.session_data = session_data
        self.practice_cog = practice_cog
        self.message: Optional[discord.Message] = None
        self.answered = False
        self.game_active = True
        
        # Add Next and End Practice buttons
        next_button = discord.ui.Button(label="Next Question", style=discord.ButtonStyle.blurple, emoji="➡️", custom_id=f"practice_next_{game_id}", row=0)
        next_button.callback = self.next_callback
        self.add_item(next_button)
        
        end_button = discord.ui.Button(label="End Practice", style=discord.ButtonStyle.red, emoji="🛑", custom_id=f"practice_end_{game_id}", row=0)
        end_button.callback = self.end_callback
        self.add_item(end_button)
    
    async def handle_message(self, msg: discord.Message):
        if self.answered or not self.game_active:
            return
        
        answer = msg.content.strip().lower()
        
        # Delete message if it contains the answer
        if self.correct_answer in answer:
            try:
                await msg.delete()
            except:
                pass
        
        # Check if exact match
        if answer == self.correct_answer:
            self.answered = True
            self.session_data['games_played'] += 1
            self.session_data['games_won'] += 1
            
            import random
            xp = random.randint(50, 60)
            self.session_data['total_xp_would_have'] += xp
            
            embed = self.message.embeds[0]
            embed.add_field(name="Result", value=f"`✅` Correct! You would have earned `{xp}xp`!", inline=False)
            
            # Don't disable buttons - user needs "Next Question" and "End Practice" to continue
            await self.message.edit(embed=embed, view=self)
            await msg.channel.send(f"`✅` {msg.author.mention} Correct! You would have earned `{xp}xp`!")
    
    async def next_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your practice session!", ephemeral=True)
            return
        
        if not self.answered:
            await interaction.response.send_message("Please answer the current question first!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            if self.message:
                await self.message.delete()
        except:
            pass
        
        await self.practice_cog._send_chat_practice_game(interaction.user, self.session_data['game_type'], self.session_data)
    
    async def end_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your practice session!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        self.game_active = False
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        await self.message.edit(view=self)
        await self.practice_cog.end_practice_session(self.user_id)


async def setup(bot: commands.Bot):
    await bot.add_cog(Practice(bot))

