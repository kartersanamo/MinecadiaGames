import discord
from managers.game_manager import GameManager
from core.logging.setup import get_logger


class ForceChatGameModal(discord.ui.Modal, title="Force Send Chat Game"):
    def __init__(self, game_manager: GameManager, config, test_mode: bool = False):
        super().__init__()
        self.game_manager = game_manager
        self.config = config
        self.test_mode = test_mode
        if test_mode:
            self.title = "Test Chat Game"
        
        self.game_type = discord.ui.TextInput(
            label="Game Type",
            placeholder="unscramble, flag_guesser, math_quiz, trivia, emoji_quiz, guess_the_number, fill_in_the_blank",
            default="trivia",
            required=True,
            max_length=20
        )
        self.add_item(self.game_type)
        
        self.xp_multiplier = discord.ui.TextInput(
            label="XP Multiplier",
            placeholder="1.0 (normal), 2.0 (double), 3.0 (triple), etc.",
            default="1.0",
            required=True,
            max_length=10
        )
        self.add_item(self.xp_multiplier)
        
        default_channel_id = "935016733033525328" if test_mode else ""
        self.channel_id = discord.ui.TextInput(
            label="Channel ID (optional)",
            placeholder="Leave empty to use random channel" if not test_mode else "Test channel ID",
            default=default_channel_id,
            required=False,
            max_length=20
        )
        self.add_item(self.channel_id)
        
        self.custom_data = discord.ui.TextInput(
            label="Custom Game Data (optional)",
            placeholder="Trivia: Q|A,W1,W2,W3 | Emoji: Cat|Emojis|A|W1,W2,W3",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=1000
        )
        self.add_item(self.custom_data)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            from games.chat.unscramble import Unscramble
            from games.chat.flag_guesser import FlagGuesser
            from games.chat.math_quiz import MathQuiz
            from games.chat.trivia import Trivia
            from games.chat.emoji_quiz import EmojiQuiz
            from games.chat.guess_the_number import GuessTheNumber
            from games.chat.fill_in_the_blank import FillInTheBlank
            
            game_map = {
                "unscramble": Unscramble,
                "flag_guesser": FlagGuesser,
                "math_quiz": MathQuiz,
                "trivia": Trivia,
                "emoji_quiz": EmojiQuiz,
                "guess_the_number": GuessTheNumber,
                "fill_in_the_blank": FillInTheBlank,
            }
            
            game_type = self.game_type.value.lower().strip()
            game_class = game_map.get(game_type)
            
            if not game_class:
                await interaction.followup.send(
                    f"`❌` Invalid game type. Use: unscramble, flag_guesser, math_quiz, trivia, emoji_quiz, guess_the_number, or fill_in_the_blank",
                    ephemeral=True
                )
                return
            
            try:
                xp_mult = float(self.xp_multiplier.value)
            except ValueError:
                await interaction.followup.send("`❌` Invalid XP multiplier. Use a number like 1.0, 2.0, etc.", ephemeral=True)
                return
            
            channel_id = self.channel_id.value.strip() if self.channel_id.value.strip() else None
            channel = None
            if channel_id:
                try:
                    channel = interaction.client.get_channel(int(channel_id))
                    if not channel:
                        await interaction.followup.send(f"`❌` Channel {channel_id} not found.", ephemeral=True)
                        return
                except ValueError:
                    await interaction.followup.send("`❌` Invalid channel ID.", ephemeral=True)
                    return
            
            custom_data = self.custom_data.value.strip() if self.custom_data.value.strip() else None
            
            game = game_class(interaction.client)
            if custom_data and game_type in ["trivia", "emoji_quiz"]:
                if game_type == "trivia":
                    parts = custom_data.split("|")
                    if len(parts) >= 2:
                        question = parts[0].strip()
                        answers_part = parts[1].strip()
                        wrong_answers = [a.strip() for a in answers_part.split(",")]
                        if len(wrong_answers) >= 3:
                            custom_trivia = {
                                "question": question,
                                "answers": [wrong_answers[0]] + wrong_answers[:3]
                            }
                            msg = await game.run(channel, custom_trivia=custom_trivia, xp_multiplier=xp_mult, test_mode=self.test_mode)
                        else:
                            await interaction.followup.send("`❌` Need at least 3 wrong answers (comma-separated).", ephemeral=True)
                            return
                    else:
                        await interaction.followup.send("`❌` Format: Question|CorrectAnswer,Wrong1,Wrong2,Wrong3", ephemeral=True)
                        return
                elif game_type == "emoji_quiz":
                    parts = custom_data.split("|")
                    if len(parts) >= 4:
                        category = parts[0].strip()
                        emojis = parts[1].strip()
                        answer = parts[2].strip()
                        wrong_answers = [a.strip() for a in parts[3].split(",")]
                        if len(wrong_answers) >= 3:
                            custom_question = {
                                "category": category,
                                "emojis": emojis,
                                "answer": answer,
                                "wrong_answers": wrong_answers[:3]
                            }
                            msg = await game.run(channel, custom_question=custom_question, xp_multiplier=xp_mult, test_mode=self.test_mode)
                        else:
                            await interaction.followup.send("`❌` Need at least 3 wrong answers (comma-separated).", ephemeral=True)
                            return
                    else:
                        await interaction.followup.send("`❌` Format: Category|Emojis|Answer|Wrong1,Wrong2,Wrong3", ephemeral=True)
                        return
                else:
                    msg = await game.run(channel, xp_multiplier=xp_mult, test_mode=self.test_mode)
            else:
                msg = await game.run(channel, xp_multiplier=xp_mult, test_mode=self.test_mode)
            
            if msg:
                mode_text = "test " if self.test_mode else ""
                await interaction.followup.send(f"`✅` {mode_text.capitalize()}Chat game sent!", ephemeral=True)
            else:
                await interaction.followup.send(f"`❌` Failed to send chat game.", ephemeral=True)
        except Exception as e:
            logger = get_logger("Commands")
            logger.error(f"Error in ForceChatGameModal: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await interaction.followup.send(f"`❌` Error: {str(e)}", ephemeral=True)
