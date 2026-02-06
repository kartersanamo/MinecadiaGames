from typing import Optional
import discord
from discord.ext import commands
from .game import BaseGame
from core.logging.setup import get_logger


class ChatGame(BaseGame):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.logger = get_logger("ChatGames")
        self.chat_config = self.config.get('chat_games')
    
    def select_channel(self) -> Optional[discord.TextChannel]:
        import random
        # Support both old and new structure
        channels = self.chat_config.get('CHANNELS', {})
        if not channels:
            # Try new structure
            channels = self.chat_config.get('channels', {})
        
        channel_ids = []
        weights = []
        
        for channel_name, info in channels.items():
            # Support both old (CHANNEL_ID, CHANCE) and new (id, weight) structure
            channel_id = info.get('CHANNEL_ID') or info.get('id')
            chance = info.get('CHANCE') or info.get('weight', 0.0)
            if channel_id and chance > 0:
                channel_ids.append(channel_id)
                weights.append(chance)
        
        if not channel_ids:
            return None
        
        selected_id = random.choices(channel_ids, weights=weights, k=1)[0]
        channel = self.bot.get_channel(selected_id)
        
        if not channel:
            for channel_id in channel_ids:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    break
        
        return channel
    
    async def run(self, channel: Optional[discord.TextChannel] = None, test_mode: bool = False, **kwargs) -> Optional[discord.Message]:
        if not channel:
            channel = self.select_channel()
            if not channel:
                self.logger.error("Could not select a valid channel")
                return None
        
        self._test_mode = test_mode
        return await self._run_game(channel, test_mode=test_mode, **kwargs)
    
    async def _run_game(self, channel: discord.TextChannel, **kwargs) -> Optional[discord.Message]:
        raise NotImplementedError("Subclasses must implement _run_game")

