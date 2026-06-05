import os
from datetime import datetime, timezone
import discord
from games.base.dm_game import DMGame
from core.logging.setup import get_logger
from repositories.game_session_repository import GameSessionRepository
class TicTacToe(DMGame):
    def __init__(self, bot):
        super().__init__(bot)
        # Support both old and new config structure
        games = self.dm_config.get('GAMES', {})
        if not games:
            games = self.dm_config.get('games', {})
        self.game_config = games.get('TicTacToe', {})
        self.logger = get_logger("DMGames")
    
    async def _run_game(self, user: discord.User, game_name: str, test_mode: bool = False) -> bool:
        try:
            if test_mode:
                last_game_id = -999999  # Fake game_id for test mode
            else:
                last_game_id = await self.bot.app.games.get_last_game_id('tictactoe')
                if not last_game_id:
                    return False
            
            test_label = " 🧪 TEST GAME 🧪" if test_mode else ""
            
            from games.dm.tictactoe.tic_tac_toe_buttons import TicTacToeButtons
            view = TicTacToeButtons(last_game_id, self.bot, self.config, self.game_config, test_mode=test_mode)
            # Register view for persistence across bot restarts
            self.bot.add_view(view)
            
            # Generate initial empty board image
            initial_image_path = await view.generate_board_image()
            initial_image_file = discord.File(initial_image_path, filename="tictactoe.png")
            
            embed = discord.Embed(
                title=f"TicTacToe #{last_game_id}{test_label}",
                description="Welcome to TicTacToe! Begin by clicking on any of the center 9 buttons below!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.set_image(url="attachment://tictactoe.png")
            logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            await user.send(embed=embed, view=view, file=initial_image_file)
            
            # Clean up initial image after sending
            try:
                os.remove(initial_image_path)
            except Exception:
                pass
            
            if not test_mode:
                current_unix = int(datetime.now(timezone.utc).timestamp())
                await GameSessionRepository().start_session(
                    last_game_id, user.id, "tictactoe", started_at=current_unix
                )
            
            self.logger.info(f"TicTacToe ({user.name}#{user.discriminator})")
            return True
        except Exception as e:
            self.logger.error(f"TicTacToe error: {e}")
            return False
