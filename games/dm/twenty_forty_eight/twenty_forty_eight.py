from datetime import datetime, timezone
import discord
from games.base.dm_game import DMGame
from core.logging.setup import get_logger
from repositories.game_session_repository import GameSessionRepository
class TwentyFortyEight(DMGame):
    def __init__(self, bot):
        super().__init__(bot)
        # Support both old and new config structure
        games = self.dm_config.get('GAMES', {})
        if not games:
            games = self.dm_config.get('games', {})
        self.game_config = games.get('2048', {}) or games.get('Twenty Forty Eight', {})
        self.logger = get_logger("DMGames")
    
    async def _run_game(self, user: discord.User, game_name: str, test_mode: bool = False) -> bool:
        try:
            if test_mode:
                last_game_id = -999999  # Fake game_id for test mode
            else:
                # Game name in database is "2048"
                last_game_id = await self.bot.app.games.get_last_game_id('2048')
                if not last_game_id:
                    return False
            
            test_label = " 🧪 TEST GAME 🧪" if test_mode else ""
            
            embed = discord.Embed(
                title=f"2048 #{last_game_id}{test_label}",
                description="Welcome to 2048! Use the direction buttons to move tiles. Combine tiles with the same number to reach 2048!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.add_field(name="Score", value="0", inline=True)
            embed.add_field(name="Moves", value="0", inline=True)
            embed.add_field(name="Highest Tile", value="2", inline=True)
            logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            from games.dm.twenty_forty_eight.twenty_forty_eight_buttons import TwentyFortyEightButtons
            view = TwentyFortyEightButtons(last_game_id, self.bot, self.config, self.game_config, self.dm_config, user.id, test_mode=test_mode)
            # Register view for persistence across bot restarts
            self.bot.add_view(view)
            await user.send(embed=embed, view=view)
            
            # Save initial state
            if not test_mode:
                await view._save_state()
            
            if not test_mode:
                current_unix = int(datetime.now(timezone.utc).timestamp())
                repo = GameSessionRepository()
                if not await repo.has_session(last_game_id, user.id, "2048"):
                    await repo.start_session(
                        last_game_id,
                        user.id,
                        "2048",
                        stats={"score": 0, "moves": 0, "highest_tile": 2},
                        started_at=current_unix,
                    )
            
            self.logger.info(f"2048 ({user.name}#{user.discriminator}){' [TEST MODE]' if test_mode else ''}")
            return True
        except Exception as e:
            self.logger.error(f"2048 error: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return False
