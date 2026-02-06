from discord.ext import commands
from discord import app_commands
import discord
from core.config.manager import ConfigManager
from core.logging.setup import get_logger
from utils.chat_game_registry import registry
from datetime import datetime, timezone
from typing import Optional
import asyncio


def _check_admin(interaction: discord.Interaction) -> bool:
    """Check if user has admin permissions"""
    if not interaction.guild:
        return False
    
    config = ConfigManager.get_instance()
    admin_roles = config.get('config', 'ADMIN_ROLES', [])
    user_roles = [role.name for role in interaction.user.roles]
    
    if "*" in admin_roles:
        return True
    
    return any(role in admin_roles for role in user_roles)


@app_commands.context_menu(name="Manage Chat Game")
async def manage_chat_game(interaction: discord.Interaction, message: discord.Message):
    """Context menu to manage chat games"""
    if not _check_admin(interaction):
        await interaction.response.send_message("`❌` You don't have permission to use this.", ephemeral=True)
        return
    
    # Check if this is a chat game message
    if not message.embeds:
        await interaction.response.send_message("`❌` This message doesn't appear to be a chat game.", ephemeral=True)
        return
    
    embed = message.embeds[0]
    title = embed.title or ""
    
    # Detect game type from title
    game_type = None
    if "Trivia Question" in title:
        game_type = "trivia"
    elif "Math Quiz" in title:
        game_type = "math_quiz"
    elif "Flag Guesser" in title:
        game_type = "flag_guesser"
    elif "Unscramble" in title:
        game_type = "unscramble"
    elif "Emoji Quiz" in title:
        game_type = "emoji_quiz"
    elif "Guess The Number" in title:
        game_type = "guess_the_number"
    
    if not game_type:
        await interaction.response.send_message("`❌` This doesn't appear to be a chat game message.", ephemeral=True)
        return
    
    # Get game data from registry (may be None if game has ended)
    game_data = registry.get_game(message.id)
    
    # Detect if game has ended - game not in registry means it has ended
    game_ended = game_data is None
    if game_ended:
        # Create minimal game_data structure for ended games
        game_data = {
            'game_type': game_type,
            'game_id': 0,  # Unknown
            'view': None,
            'original_state': {},
            'xp_multiplier': 1.0,
            'test_mode': False,
            'ended': True
        }
        
        # Try to extract answer from embed if possible
        # Check for "Answer" field (might be added by admin panel)
        for field in embed.fields:
            if field.name == "Answer":
                answer = field.value
                if game_type == "unscramble":
                    game_data['original_state'] = {'word': answer}
                elif game_type == "guess_the_number":
                    game_data['original_state'] = {'secret_number': answer}
                else:
                    game_data['original_state'] = {'correct_answer': answer}
                break
    
    # Get bot and config
    bot = interaction.client
    config = ConfigManager.get_instance()
    
    # Create admin view (pass game_ended flag)
    view = ChatGameAdminView(message, game_type, game_data, bot, config, game_ended=game_ended)
    
    # Get game info for the embed
    game_name_map = {
        "trivia": "Trivia",
        "math_quiz": "Math Quiz",
        "flag_guesser": "Flag Guesser",
        "unscramble": "Unscramble",
        "emoji_quiz": "Emoji Quiz",
        "guess_the_number": "Guess The Number"
    }
    game_name = game_name_map.get(game_type, game_type.title())
    
    # Get game status info
    xp_mult = game_data.get('xp_multiplier', 1.0) if game_data else 1.0
    test_mode = game_data.get('test_mode', False) if game_data else False
    winners_count = 0
    if game_data:
        view_obj = game_data.get('view')
        if view_obj and hasattr(view_obj, 'winners'):
            winners_count = len(view_obj.winners)
        elif game_data.get('winners'):
            winners_count = len(game_data.get('winners', []))
        
        # Try to count winners from embed if game has ended
        if game_ended:
            for field in embed.fields:
                if field.name == "Winners":
                    # Count winners from the field value
                    winners_text = field.value
                    if winners_text and winners_text != "No winners!":
                        winners_count = len([line for line in winners_text.split('\n') if line.strip()])
                    break
    
    # Create beautiful embed
    embed = discord.Embed(
        title="🎮 Chat Game Admin Panel",
        description=f"Manage the **{game_name}** game below.",
        color=discord.Color.from_str(config.get('config', 'EMBED_COLOR')),
        timestamp=datetime.now(timezone.utc)
    )
    
    # Add game information fields
    embed.add_field(
        name="📋 Game Information",
        value=(
            f"**Type:** {game_name}\n"
            f"**XP Multiplier:** {xp_mult:.1f}x\n"
            f"**Test Mode:** {'Yes' if test_mode else 'No'}\n"
            f"**Winners:** {winners_count}"
        ),
        inline=True
    )
    
    # Add button descriptions (show note if game has ended)
    actions_value = (
        "**Show Answer** - View the correct answer\n"
        "**Reset** - Reset game to original state\n"
        "**Reroll** - Get a new question/word\n"
        "**Toggle 2x** - Switch XP multiplier\n"
        "**End Game Now** - Immediately end the game\n"
        "**Show Activity** - View activity log"
    )
    if game_ended:
        actions_value += "\n\n*⚠️ Game has ended. Some actions may be limited.*"
    
    embed.add_field(
        name="🔧 Available Actions",
        value=actions_value,
        inline=True
    )
    
    # Add message link
    embed.add_field(
        name="🔗 Game Message",
        value=f"[Jump to Game Message]({message.jump_url})",
        inline=False
    )
    
    from utils.helpers import get_embed_logo_url
    logo_url = get_embed_logo_url(config.get('config', 'LOGO'))
    embed.set_footer(text=config.get('config', 'FOOTER'), icon_url=logo_url)
    
    await interaction.response.send_message(
        embed=embed,
        view=view,
        ephemeral=True
    )


class ChatGameAdmin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Commands")


class ChatGameAdminView(discord.ui.View):
    def __init__(self, message: discord.Message, game_type: str, game_data: Optional[dict], bot, config, game_ended: bool = False):
        super().__init__(timeout=None)
        self.message = message
        self.game_type = game_type
        self.game_data = game_data
        self.bot = bot
        self.config = config
        self.game_ended = game_ended
        self.logger = get_logger("Commands")
    
    def _get_game_data(self) -> Optional[dict]:
        """Get game data, trying registry first, then stored data"""
        # Try registry first (if game was registered after restart)
        game_data = registry.get_game(self.message.id)
        if game_data:
            return game_data
        # Fall back to stored data (from context menu initialization)
        if self.game_data:
            return self.game_data
        return None
    
    @discord.ui.button(label="Show Answer", style=discord.ButtonStyle.green, row=0, custom_id="chat_admin_show_answer")
    async def show_answer(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show the correct answer"""
        await interaction.response.defer(ephemeral=True)
        
        game_data = self._get_game_data()
        original_state = game_data.get('original_state', {}) if game_data else {}
        answer = None
        
        # Try to get answer from original_state first
        if self.game_type == "trivia":
            answer = original_state.get('correct_answer')
        elif self.game_type == "math_quiz":
            answer = original_state.get('correct_answer')
        elif self.game_type == "flag_guesser":
            answer = original_state.get('correct_answer')
        elif self.game_type == "unscramble":
            answer = original_state.get('word')
        elif self.game_type == "emoji_quiz":
            answer = original_state.get('correct_answer')
        elif self.game_type == "guess_the_number":
            answer = original_state.get('secret_number')
            if answer:
                answer = f"The number is **{answer}**"
        
        # If answer not in original_state and game has ended, try to extract from embed
        if not answer and self.game_ended:
            embed_msg = self.message.embeds[0] if self.message.embeds else None
            if embed_msg:
                # Check for "Answer" field (might have been added)
                for field in embed_msg.fields:
                    if field.name == "Answer":
                        answer = field.value
                        break
                
                # If still no answer, try to get from description or other fields
                if not answer:
                    if self.game_type == "unscramble":
                        # Try to get from scrambled word display or other hints
                        answer = "Answer not available in ended game"
                    else:
                        answer = "Answer not available in ended game"
        
        if not answer:
            answer = "Answer not available"
        
        embed = discord.Embed(
            title="🔍 Correct Answer",
            description=f"**Answer:** {answer}",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
        )
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        
        # Log activity (will silently fail if game not in registry, which is fine)
        try:
            registry.log_activity(self.message.id, interaction.user.id, 'show_answer', f'Viewed correct answer: {answer}', True)
        except:
            pass
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="Reset", style=discord.ButtonStyle.blurple, row=0, custom_id="chat_admin_reset")
    async def reset_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Reset game to original state"""
        await interaction.response.defer(ephemeral=True)
        
        if self.game_ended:
            await interaction.followup.send("`❌` Cannot reset a game that has already ended.", ephemeral=True)
            return
        
        game_data = self._get_game_data()
        if not game_data:
            await interaction.followup.send("`❌` Game data not found. The game may have ended.", ephemeral=True)
            return
        
        try:
            # Reset winners and state
            view = game_data.get('view')
            if view and hasattr(view, 'winners'):
                view.winners = []
                view.winner_count = 0
            
            # For games without views (Unscramble, Emoji Quiz), reset in game_data
            if self.game_type in ['unscramble', 'emoji_quiz']:
                game_data['winners'] = []
                game_data['winner_count'] = 0
                if 'game_active' in game_data:
                    game_data['game_active'] = True
            
            # Reset embed to original state
            original_state = game_data.get('original_state', {})
            original_embed = original_state.get('embed')
            
            if original_embed:
                # Recreate original embed
                embed = discord.Embed(
                    title=original_embed.get('title', 'Game'),
                    description=original_embed.get('description', ''),
                    color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
                    timestamp=datetime.now(timezone.utc)
                )
                
                # Add original fields
                for field in original_embed.get('fields', []):
                    embed.add_field(
                        name=field.get('name', ''),
                        value=field.get('value', ''),
                        inline=field.get('inline', False)
                    )
                
                from utils.helpers import get_embed_logo_url
                logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
                embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
                
                # Check if view is a real Discord view (not DummyView)
                # DummyView is used for games without buttons (Unscramble, Emoji Quiz)
                is_real_view = view and isinstance(view, discord.ui.View)
                
                # Update message
                if self.message.attachments or game_data.get('image_file'):
                    # Re-attach image if it exists
                    image_file = game_data.get('image_file')
                    if image_file:
                        if is_real_view:
                            await self.message.edit(embed=embed, view=view, attachments=[image_file])
                        else:
                            await self.message.edit(embed=embed, attachments=[image_file])
                    else:
                        if is_real_view:
                            await self.message.edit(embed=embed, view=view)
                        else:
                            await self.message.edit(embed=embed)
                else:
                    if is_real_view:
                        await self.message.edit(embed=embed, view=view)
                    else:
                        await self.message.edit(embed=embed)
                
                # Reset current state
                game_data['current_state'] = original_state.copy()
                
                registry.log_activity(self.message.id, interaction.user.id, 'reset', 'Game reset to original state', True)
                
                await interaction.followup.send("`✅` Game reset to original state!", ephemeral=True)
            else:
                await interaction.followup.send("`❌` Could not find original game state.", ephemeral=True)
        except Exception as e:
            self.logger.error(f"Error resetting game: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            await interaction.followup.send(f"`❌` Error resetting game: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="Reroll", style=discord.ButtonStyle.blurple, row=0, custom_id="chat_admin_reroll")
    async def reroll_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Reroll to get a new question/word/etc"""
        await interaction.response.defer(ephemeral=True)
        
        if self.game_ended:
            await interaction.followup.send("`❌` Cannot reroll a game that has already ended.", ephemeral=True)
            return
        
        game_data = self._get_game_data()
        if not game_data:
            await interaction.followup.send("`❌` Game data not found. The game may have ended.", ephemeral=True)
            return
        
        try:
            # Import game classes
            from games.chat.trivia import Trivia
            from games.chat.math_quiz import MathQuiz
            from games.chat.flag_guesser import FlagGuesser
            from games.chat.unscramble import Unscramble
            from games.chat.emoji_quiz import EmojiQuiz
            from games.chat.guess_the_number import GuessTheNumber
            
            game_map = {
                "trivia": Trivia,
                "math_quiz": MathQuiz,
                "flag_guesser": FlagGuesser,
                "unscramble": Unscramble,
                "emoji_quiz": EmojiQuiz,
                "guess_the_number": GuessTheNumber
            }
            
            game_class = game_map.get(self.game_type)
            if not game_class:
                await interaction.followup.send(f"`❌` Unknown game type: {self.game_type}", ephemeral=True)
                return
            
            # Get current XP multiplier and test mode
            xp_mult = game_data.get('xp_multiplier', 1.0)
            test_mode = game_data.get('test_mode', False)
            
            # Create new game instance and get new question/data
            game = game_class(self.bot)
            channel = self.message.channel
            
            # For each game type, get new data
            if self.game_type == "trivia":
                # Get new trivia question
                import random
                questions_dict = game.game_config.get('QUESTIONS', {}) or game.game_config.get('questions', {})
                all_questions = []
                for channel_id, questions_list in questions_dict.items():
                    if isinstance(questions_list, list):
                        all_questions.extend(questions_list)
                
                if all_questions:
                    trivia = random.choice(all_questions)
                else:
                    trivia = None
                
                if trivia:
                    # Update embed with new question
                    embed = self.message.embeds[0]
                    embed.set_field_at(0, name="Question", value=trivia["question"], inline=False)
                    
                    # Update view with new answers
                    view = game_data.get('view')
                    if view:
                        view.correct_answer = trivia['answers'][0]
                        view.all_answers = trivia['answers'][:4]
                        view.winners = []
                        view.winner_count = 0
                        
                        # Update button labels
                        answers = trivia['answers'][:4]
                        items = []
                        for index, button in enumerate(view.children):
                            if index < len(answers):
                                button.label = answers[index]
                                items.append(button)
                        
                        view.clear_items()
                        import random
                        random.shuffle(items)
                        for item in items:
                            view.add_item(item)
                        
                        # Update answer map
                        view.answer_map = {}
                        for i in range(4):
                            answer = answers[i] if i < len(answers) else f"Answer {i+1}"
                            view.answer_map[f"trivia_{i}_{game_data['game_id']}"] = answer
                    
                    # Update original state
                    original_state = game_data.get('original_state', {})
                    original_state['correct_answer'] = trivia['answers'][0]
                    original_state['question'] = trivia['question']
                    original_state['answers'] = trivia['answers']
                    
                    await self.message.edit(embed=embed, view=view)
                    await interaction.followup.send("`✅` Game rerolled with new question!", ephemeral=True)
                else:
                    await interaction.followup.send("`❌` Could not get new trivia question.", ephemeral=True)
            
            elif self.game_type == "math_quiz":
                # Get new math question
                import random
                questions = game.game_config.get('QUESTIONS', []) or game.game_config.get('problem_types', [])
                if questions:
                    question = random.choice(questions)
                else:
                    question = None
                
                if question:
                    solution = str(question['solution'])
                    problem = question['problem']
                    # Generate wrong answers
                    wrong_answers = []
                    for _ in range(3):
                        wrong = str(int(solution) + random.randint(-50, 50))
                        if wrong != solution and wrong not in wrong_answers:
                            wrong_answers.append(wrong)
                    answers = wrong_answers
                    answers.append(solution)
                    import random
                    random.shuffle(answers)
                    
                    # Update embed
                    embed = self.message.embeds[0]
                    question_type = question.get('name') or question.get('NAME') or 'Math Problem'
                    embed.set_field_at(0, name=f"{question_type}", value=problem, inline=False)
                    
                    # Update view
                    view = game_data.get('view')
                    if view:
                        view.correct_answer = solution
                        view.answers = answers
                        view.winners = []
                        view.winner_count = 0
                        
                        # Update button labels
                        view.clear_items()
                        for answer in answers:
                            button = discord.ui.Button(
                                label=answer[:80],
                                style=discord.ButtonStyle.grey,
                                custom_id=f"math_{answer}_{game_data['game_id']}"
                            )
                            button.callback = view.create_callback(answer)
                            view.add_item(button)
                    
                    # Update original state
                    original_state = game_data.get('original_state', {})
                    original_state['correct_answer'] = solution
                    original_state['problem'] = problem
                    original_state['question'] = question
                    
                    await self.message.edit(embed=embed, view=view)
                    await interaction.followup.send("`✅` Game rerolled with new math question!", ephemeral=True)
                else:
                    await interaction.followup.send("`❌` Could not get new math question.", ephemeral=True)
            
            elif self.game_type == "flag_guesser":
                # Get new country
                country_code, correct_answer, answers = await game._select_country_and_answers()
                
                # Rebuild embed and file
                from datetime import datetime, timezone
                current_unix = int(datetime.now(timezone.utc).timestamp())
                embed, file = await game._build_embed(country_code, xp_mult, current_unix, test_mode)
                from utils.helpers import get_embed_logo_url
                logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
                embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
                
                # Update view
                view = game_data.get('view')
                if view:
                    view.correct_answer = correct_answer
                    view.answers = answers
                    view.winners = []
                    view.winner_count = 0
                    
                    # Update button labels
                    view.clear_items()
                    for answer in answers:
                        button = discord.ui.Button(
                            label=answer,
                            style=discord.ButtonStyle.grey,
                            custom_id=f"flag_{answer}_{game_data['game_id']}"
                        )
                        button.callback = view.create_callback(answer)
                        view.add_item(button)
                    
                    # Store new file
                    game_data['image_file'] = file
                    view.current_image_file = file
                
                # Update original state
                original_state = game_data.get('original_state', {})
                original_state['correct_answer'] = correct_answer
                original_state['country_code'] = country_code
                
                await self.message.edit(embed=embed, view=view, attachments=[file])
                await interaction.followup.send("`✅` Game rerolled with new flag!", ephemeral=True)
            
            elif self.game_type == "unscramble":
                # Get new word
                import random
                channel_id_str = str(channel.id)
                words_dict = game.game_config.get('WORDS', {}) or game.game_config.get('words', {})
                words = words_dict.get(channel_id_str, [])
                if not words:
                    # Try to get from any channel
                    for channel_words in words_dict.values():
                        if isinstance(channel_words, list):
                            words.extend(channel_words)
                
                if words:
                    word = random.choice(words)
                else:
                    word = None
                
                if word:
                    # Scramble word
                    word_list = list(word)
                    random.shuffle(word_list)
                    scrambled = ''.join(word_list)
                    image_path = await game._get_image(scrambled)
                    file = discord.File(image_path, filename="unscramble.png")
                    
                    # Update embed
                    embed = self.message.embeds[0]
                    
                    # Update original state
                    original_state = game_data.get('original_state', {})
                    original_state['word'] = word
                    original_state['scrambled'] = scrambled
                    
                    # Update game_data
                    game_data['word'] = word
                    game_data['scrambled'] = scrambled
                    game_data['image_file'] = file
                    game_data['image_path'] = image_path
                    
                    await self.message.edit(embed=embed, attachments=[file])
                    await interaction.followup.send("`✅` Game rerolled with new word!", ephemeral=True)
                else:
                    await interaction.followup.send("`❌` Could not get new word.", ephemeral=True)
            
            elif self.game_type == "emoji_quiz":
                # Get new question
                import random
                questions = game.game_config.get('QUESTIONS', []) or game.game_config.get('questions', [])
                if questions:
                    question_data = random.choice(questions)
                else:
                    question_data = None
                
                if question_data:
                    category = question_data.get('category', 'General')
                    emojis = question_data.get('emojis', '')
                    correct_answer = question_data.get('answer', '').strip()
                    
                    # Update embed
                    embed = self.message.embeds[0]
                    embed.title = f"Emoji Quiz - {category}"
                    embed.set_field_at(0, name="What do these emojis represent?", value=emojis, inline=False)
                    
                    # Update original state
                    original_state = game_data.get('original_state', {})
                    original_state['correct_answer'] = correct_answer
                    original_state['question'] = question_data
                    
                    # Update game_data
                    game_data['correct_answer'] = correct_answer
                    game_data['question'] = question_data
                    
                    await self.message.edit(embed=embed)
                    await interaction.followup.send("`✅` Game rerolled with new emoji question!", ephemeral=True)
                else:
                    await interaction.followup.send("`❌` Could not get new emoji question.", ephemeral=True)
            
            registry.log_activity(self.message.id, interaction.user.id, 'reroll', f'Game rerolled', True)
        
        except Exception as e:
            self.logger.error(f"Error rerolling game: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            await interaction.followup.send(f"`❌` Error rerolling game: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="Toggle 2x", style=discord.ButtonStyle.blurple, row=1, custom_id="chat_admin_toggle_2x")
    async def toggle_2x(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle XP multiplier between 2x and 1x"""
        await interaction.response.defer(ephemeral=True)
        
        if self.game_ended:
            await interaction.followup.send("`❌` Cannot toggle XP multiplier for a game that has already ended.", ephemeral=True)
            return
        
        game_data = self._get_game_data()
        if not game_data:
            await interaction.followup.send("`❌` Game data not found. The game may have ended.", ephemeral=True)
            return
        
        try:
            current_mult = game_data.get('xp_multiplier', 1.0)
            new_mult = 2.0 if current_mult == 1.0 else 1.0
            
            # Update multiplier in registry
            registry.update_xp_multiplier(self.message.id, new_mult)
            
            # Update view multiplier
            view = game_data.get('view')
            if view and hasattr(view, 'xp_multiplier'):
                view.xp_multiplier = new_mult
            
            # Update embed title
            embed = self.message.embeds[0]
            title = embed.title or ""
            
            # Remove existing XP multiplier from title
            import re
            title = re.sub(r'\s*\(.*?XP\)', '', title)
            title = re.sub(r'\s*🧪 TEST GAME 🧪', '', title)
            
            # Add new multiplier
            if new_mult == 2.0:
                title += " (DOUBLE XP)"
            elif new_mult > 1.0:
                title += f" ({new_mult:.1f}x XP)"
            
            # Re-add test label if needed
            if game_data.get('test_mode'):
                title += " 🧪 TEST GAME 🧪"
            
            embed.title = title
            
            # Check if view is a real Discord view (not DummyView)
            # DummyView is used for games without buttons (Unscramble, Emoji Quiz)
            is_real_view = view and isinstance(view, discord.ui.View)
            
            # Update message
            if self.message.attachments:
                image_file = game_data.get('image_file')
                if is_real_view:
                    await self.message.edit(embed=embed, view=view, attachments=[image_file] if image_file else [])
                else:
                    await self.message.edit(embed=embed, attachments=[image_file] if image_file else [])
            else:
                if is_real_view:
                    await self.message.edit(embed=embed, view=view)
                else:
                    await self.message.edit(embed=embed)
            
            registry.log_activity(self.message.id, interaction.user.id, 'toggle_2x', f'XP multiplier changed to {new_mult}x', True)
            
            await interaction.followup.send(f"`✅` XP multiplier set to {new_mult}x!", ephemeral=True)
        
        except Exception as e:
            self.logger.error(f"Error toggling 2x: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            await interaction.followup.send(f"`❌` Error toggling multiplier: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="End Game Now", style=discord.ButtonStyle.red, row=1, custom_id="chat_admin_end_game")
    async def end_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        """End the game immediately"""
        await interaction.response.defer(ephemeral=True)
        
        if self.game_ended:
            await interaction.followup.send("`ℹ️` This game has already ended.", ephemeral=True)
            return
        
        game_data = self._get_game_data()
        if not game_data:
            await interaction.followup.send("`❌` Game data not found. The game may have already ended.", ephemeral=True)
            return
        
        try:
            view = game_data.get('view')
            
            # Check if view is a real Discord view (not DummyView)
            is_real_view = view and isinstance(view, discord.ui.View)
            
            # Disable all buttons (only for real views)
            if is_real_view:
                for item in view.children:
                    item.disabled = True
            
            # Update embed
            embed = self.message.embeds[0]
            embed.description = f"This game ended <t:{int(datetime.now(timezone.utc).timestamp())}:R>"
            
            # Check if Winners field already exists
            winners_field_exists = False
            for i, field in enumerate(embed.fields):
                if field.name == "Winners":
                    winners_field_exists = True
                    # Update existing field if we have winners data
                    if view and hasattr(view, 'winners') and view.winners:
                        winners_text = "\n".join(f"`+{w['xp']}xp` {w['user']}" for w in view.winners)
                        embed.set_field_at(i, name="Winners", value=winners_text, inline=False)
                    elif game_data.get('winners'):
                        winners_text = "\n".join(f"`+{w['xp']}xp` {w['user']}" for w in game_data.get('winners', []))
                        embed.set_field_at(i, name="Winners", value=winners_text, inline=False)
                    break
            
            # Only add Winners field if it doesn't already exist
            if not winners_field_exists:
                if view and hasattr(view, 'winners') and view.winners:
                    winners_text = "\n".join(f"`+{w['xp']}xp` {w['user']}" for w in view.winners)
                    embed.add_field(name="Winners", value=winners_text, inline=False)
                elif game_data.get('winners'):
                    winners_text = "\n".join(f"`+{w['xp']}xp` {w['user']}" for w in game_data.get('winners', []))
                    embed.add_field(name="Winners", value=winners_text, inline=False)
                else:
                    embed.add_field(name="Winners", value="No winners!", inline=False)
            
            # Update message
            if self.message.attachments:
                image_file = game_data.get('image_file')
                if is_real_view:
                    await self.message.edit(embed=embed, view=view, attachments=[image_file] if image_file else [])
                else:
                    await self.message.edit(embed=embed, attachments=[image_file] if image_file else [])
            else:
                if is_real_view:
                    await self.message.edit(embed=embed, view=view)
                else:
                    await self.message.edit(embed=embed)
            
            # Unregister game
            registry.unregister_game(self.message.id)
            
            registry.log_activity(self.message.id, interaction.user.id, 'end_game', 'Game ended by admin', True)
            
            await interaction.followup.send("`✅` Game ended!", ephemeral=True)
        
        except Exception as e:
            self.logger.error(f"Error ending game: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            await interaction.followup.send(f"`❌` Error ending game: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="Show Activity", style=discord.ButtonStyle.grey, row=1, custom_id="chat_admin_show_activity")
    async def show_activity(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show activity log"""
        await interaction.response.defer(ephemeral=True)
        
        activity_log = registry.get_activity_log(self.message.id)
        
        if not activity_log:
            if self.game_ended:
                await interaction.followup.send("`ℹ️` Activity log is not available for ended games.", ephemeral=True)
            else:
                await interaction.followup.send("`ℹ️` No activity logged yet.", ephemeral=True)
            return
        
        # Format activity log
        log_lines = []
        for entry in activity_log[-50:]:  # Last 50 entries
            timestamp = entry.get('timestamp', 0)
            user_id = entry.get('user_id', 0)
            action = entry.get('action', 'unknown')
            details = entry.get('details', '')
            success = entry.get('success', True)
            
            # Get user mention
            user = self.bot.get_user(user_id)
            user_mention = user.mention if user else f"<@{user_id}>"
            
            # Format timestamp
            time_str = f"<t:{int(timestamp)}:T>"
            
            # Format action
            status = "✅" if success else "❌"
            log_line = f"{status} {time_str} - {user_mention}: **{action}**"
            if details:
                log_line += f" ({details})"
            
            log_lines.append(log_line)
        
        # Create embed
        embed = discord.Embed(
            title="📊 Activity Log",
            description="\n".join(log_lines) if log_lines else "No activity",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
        )
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=f"Total entries: {len(activity_log)}", icon_url=logo_url)
        
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ChatGameAdmin(bot))
    # Register context menu at module level
    bot.tree.add_command(manage_chat_game)

