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
