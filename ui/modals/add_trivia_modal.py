from discord.ext import commands
from discord import app_commands
import discord
from core.config.manager import ConfigManager
from managers.game_manager import GameManager
from utils.paginator import Paginator
from utils.helpers import get_recent_games
from core.logging.setup import get_logger
from datetime import datetime, timezone
from typing import Optional
import asyncio
import random


class AddTriviaModal(discord.ui.Modal, title="Add Trivia Question"):
    def __init__(self, config):
        super().__init__()
        self.config = config
        
        self.question = discord.ui.TextInput(
            label="Question",
            placeholder="Enter the trivia question",
            required=True,
            max_length=200
        )
        self.add_item(self.question)
        
        self.answer = discord.ui.TextInput(
            label="Correct Answer",
            placeholder="Enter the correct answer",
            required=True,
            max_length=100
        )
        self.add_item(self.answer)
        
        self.wrong_answers = discord.ui.TextInput(
            label="Wrong Answers (comma-separated)",
            placeholder="Wrong answer 1, Wrong answer 2, Wrong answer 3",
            required=True,
            max_length=300
        )
        self.add_item(self.wrong_answers)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            import json
            from pathlib import Path
            
            question = self.question.value.strip()
            answer = self.answer.value.strip()
            wrong_answers_str = self.wrong_answers.value.strip()
            wrong_answers = [a.strip() for a in wrong_answers_str.split(",")]
            
            if len(wrong_answers) < 3:
                await interaction.followup.send("`❌` Please provide at least 3 wrong answers (comma-separated).", ephemeral=True)
                return
            
            # Load trivia config
            project_root = Path(__file__).parent.parent
            trivia_file = project_root / "assets" / "configs" / "games" / "trivia.json"
            
            if not trivia_file.exists():
                await interaction.followup.send("`❌` Trivia config file not found.", ephemeral=True)
                return
            
            with open(trivia_file, 'r', encoding='utf-8') as f:
                trivia_data = json.load(f)
            
            questions_dict = trivia_data.get('questions', {})
            
            # Get the first channel ID from questions, or use the first ANNOUNCE_CHANNEL as default
            if not questions_dict:
                # Use first announce channel as default
                announce_channels = self.config.get('config', 'ANNOUNCE_CHANNELS', [])
                default_channel_id = str(announce_channels[0]) if announce_channels else "918903892144717915"
                questions_dict[default_channel_id] = []
            
            # Use the first channel ID in the questions dict
            channel_id = list(questions_dict.keys())[0]
            
            # Get or create the questions list for this channel
            if channel_id not in questions_dict:
                questions_dict[channel_id] = []
            questions_list = questions_dict[channel_id]
            
            new_question = {
                "question": question,
                "answers": [answer] + wrong_answers[:3],
                "difficulty": 1.5  # Default difficulty
            }
            
            questions_list.append(new_question)
            trivia_data['questions'] = questions_dict
            
            with open(trivia_file, 'w', encoding='utf-8') as f:
                json.dump(trivia_data, f, indent=4, ensure_ascii=False)
            
            # Reload config
            self.config.reload('games/trivia')
            
            await interaction.followup.send("`✅` Trivia question added successfully!", ephemeral=True)
        except Exception as e:
            logger = get_logger("Commands")
            logger.error(f"Error in AddTriviaModal: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await interaction.followup.send(f"`❌` Error: {str(e)}", ephemeral=True)
