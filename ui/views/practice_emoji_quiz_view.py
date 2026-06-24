import discord
from typing import Optional, Dict


class PracticeEmojiQuizView(discord.ui.View):
    """Practice view for Emoji Quiz - message-based"""
    def __init__(
        self,
        correct_answer: str,
        question_data: dict,
        game_id: int,
        bot,
        config,
        chat_config,
        user_id: int,
        session_data: Dict,
        practice_cog,
    ):
        super().__init__(timeout=None)
        from games.chat.emoji_quiz import build_accepted_answers

        self.correct_answer = correct_answer.strip()
        self.accepted_answers = build_accepted_answers(correct_answer, question_data)
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
        if any(accepted in answer for accepted in self.accepted_answers):
            try:
                await msg.delete()
            except Exception:
                pass
        
        # Check if exact match (canonical or alternate spelling)
        if answer in self.accepted_answers:
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
        except Exception:
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
