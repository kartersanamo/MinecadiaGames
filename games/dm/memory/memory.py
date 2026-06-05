from datetime import datetime, timezone
import discord
from games.base.dm_game import DMGame
from core.logging.setup import get_logger
from repositories.game_session_repository import GameSessionRepository
class Memory(DMGame):
    def __init__(self, bot):
        super().__init__(bot)
        # Support both old and new config structure
        games = self.dm_config.get('GAMES', {})
        if not games:
            games = self.dm_config.get('games', {})
        self.game_config = games.get('Memory', {})
        self.logger = get_logger("DMGames")
    
    async def _run_game(self, user: discord.User, game_name: str, test_mode: bool = False) -> bool:
        try:
            if test_mode:
                last_game_id = -999999  # Fake game_id for test mode
            else:
                last_game_id = await self.bot.app.games.get_last_game_id('memory')
                if not last_game_id:
                    return False
            
            # Support both old and new structure
            tries = self.game_config.get('TRIES') or self.game_config.get('max_tries', 7)
            image_url = self.game_config.get('IMAGE') or self.game_config.get('image_url')
            
            test_label = " 🧪 TEST GAME 🧪" if test_mode else ""
            
            embed = discord.Embed(
                title=f"Memory #{last_game_id}{test_label}",
                description="Welcome to Memory! Begin by clicking on any two buttons below to try to match!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.add_field(name="Tries Remaining", value=str(tries))
            embed.add_field(name="Matches Found", value="0/10", inline=True)
            if image_url:
                embed.set_image(url=image_url)
            logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            from games.dm.memory.memory_buttons import MemoryButtons
            view = MemoryButtons(last_game_id, self.bot, self.config, self.game_config, self.dm_config, test_mode=test_mode)
            view.player_id = user.id  # Store player_id for state saving
            # Register view for persistence across bot restarts
            self.bot.add_view(view)
            await user.send(embed=embed, view=view)
            
            # Save initial state
            if not test_mode:
                await view._save_state()
            
            if not test_mode:
                current_unix = int(datetime.now(timezone.utc).timestamp())
                await GameSessionRepository().start_session(
                    last_game_id,
                    user.id,
                    "memory",
                    stats={"attempts": 0, "matches": 0},
                    started_at=current_unix,
                )
            
            self.logger.info(f"Memory ({user.name}#{user.discriminator}){' [TEST MODE]' if test_mode else ''}")
            return True
        except Exception as e:
            self.logger.error(f"Memory error: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return False
